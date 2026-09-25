import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import signal
import statistics
import struct
import subprocess
import time
from datetime import datetime, timezone


GIB = 1 << 30
FRAME_BYTES = 520 * 696 * 2
FIXED_POLICY = "fixed-volume-after-discard-warmup-through-close-v1"
STREAM_POLICY = "coverage-qualified-through-final-close-v2"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def utc():
    return datetime.now(timezone.utc).isoformat()


def predicted_layout(chunk, target, frames=65536):
    grid = [math.ceil(n / c) for n, c in zip([frames, 520, 696], chunk)]
    parts = [1, 1]
    while math.prod(parts) < target:
        choices = [
            axis
            for axis in range(2)
            if parts[axis] < grid[axis + 1]
            and (parts[axis] + 1) * parts[1 - axis] <= target
        ]
        if not choices:
            break
        axis = max(choices, key=lambda d: grid[d + 1] / parts[d])
        parts[axis] += 1
    inner = [math.ceil(grid[d + 1] / parts[d]) for d in range(2)]
    chunk_bytes = 2 * math.prod(chunk)
    cps = [min(grid[0], GIB // (chunk_bytes * math.prod(inner))), *inner]
    return {
        "chunk_shape": chunk,
        "chunks_per_shard": cps,
        "shard_shape": [c * n for c, n in zip(chunk, cps)],
        "actual_layer_shards": math.prod(
            math.ceil(grid[d] / cps[d]) for d in (1, 2)
        ),
        "raw_shard_bytes": math.prod(cps) * chunk_bytes,
    }


def fixed_cases(plan):
    spec = plan["shared_layouts"]
    cases = []
    for shape in spec["chunk_shapes"]:
        size = math.prod(shape) * 2
        cases.append({
            "id": f"c{size // 1024}", "experiment": "shared-layouts",
            "codec": spec["codec"], "chunk_bytes": size, "chunk_depth": 1,
            "chunk_shape": shape, "blosc_block_bytes": spec["blosc_block_bytes"],
            "shuffle": spec["shuffle"], "level": spec["level_hint"],
            "shard_shape": spec["shard_shape"], "actual_layer_shards": 4,
            "chunks_per_shard": [s // c for s, c in zip(spec["shard_shape"], shape)],
            "raw_shard_bytes": GIB,
        })
    return cases


def shard_case(plan, series, target):
    spec = plan["shard_count"][series]
    shape = [4, 64, 128] if series == "fast" else [4, 128, 256]
    layout = predicted_layout(shape, target, plan["shard_count"]["geometry_frames"])
    return {
        "id": f"{series}-target{target}", "experiment": "shard-count",
        "series": series, "target_shards": target,
        "codec": spec["codec"], "chunk_bytes": spec["chunk_bytes"],
        "chunk_depth": spec["chunk_depth"],
        "blosc_block_bytes": spec["blosc_block_bytes"],
        "shuffle": spec["shuffle"], "level": spec["level_hint"], **layout,
    }


def command(root, plan, source, case, output, fixed_frames=None):
    args = [
        str(root / "build/writer/bench/bench_stream_microscopy"),
        "--backend", "gpu", "--input", str(source), "--dtype", "u16",
        "--width", "696", "--height", "520", "--codec", case["codec"],
        "--chunk-bytes", str(case["chunk_bytes"]),
        "--chunk-depth", str(case["chunk_depth"]),
        "--blosc-block-bytes", str(case["blosc_block_bytes"]),
        "--blosc-shuffle", case["shuffle"], "--level", str(case["level"]),
        "--geometry-frames", str(plan["shard_count"]["geometry_frames"]),
        "--batch-bytes", str(plan["writer_resources"]["batch_target_bytes"]),
        "--max-threads", str(plan["writer_resources"]["cpu_workers"]),
        "--memory-budget", str(16 * GIB), "--max-attempts", "1", "--json",
        "-o", str(output),
    ]
    if fixed_frames is not None:
        args += ["--fixed-frames", str(fixed_frames), "--duration", "0.25",
                 "--warmup", "0.25", "--shard-shape"]
        args += [str(n) for n in case["shard_shape"]]
    else:
        spec = plan["shard_count"]
        args += ["--concurrent-shards", str(case["target_shards"]),
                 "--frames", str(math.ceil(spec["minimum_logical_bytes"] / FRAME_BYTES)),
                 "--warmup", str(spec["warmup_s"]), "--duration", str(spec["duration_s"])]
    return args


def validate_native(native, case, frames=None, small=False):
    m = native.get("measurement", {})
    expected_policy = FIXED_POLICY if frames is not None else STREAM_POLICY
    require(m.get("policy") == expected_policy, "unexpected timing policy")
    dimensions = m["geometry"]["dimensions"]
    require([d["chunk_size"] for d in dimensions] == case["chunk_shape"], "chunk shape changed")
    require([d["chunks_per_shard"] for d in dimensions] == case["chunks_per_shard"], "shard geometry changed")
    require(m["attempt"] == 1, "unplanned retry")
    require(m["logical_input_bytes"] % FRAME_BYTES == 0, "partial logical frame")
    padded = 2 * math.prod(
        math.ceil(n / c) * c for n, c in zip([520, 696], case["chunk_shape"][1:])
    )
    require(m["input_bytes"] * FRAME_BYTES == m["logical_input_bytes"] * padded,
            "logical versus padded byte accounting changed")
    require(abs(m["elapsed_s"] - m["append_s"] - m["drain_s"]) < 0.0001,
            "append and drain do not sum to measured time")
    if frames is not None:
        require(m["logical_input_bytes"] == frames * FRAME_BYTES, "fixed volume changed")
        require(m["warmup_input_bytes"] == 0 and m["warmup_output_bytes"] == 0,
                "warmup data entered the measured store")
        require(m["separate_warmup_s"] > 0, "separate warmup missing")
    if small:
        require(native.get("error") == "insufficient_coverage",
                "small correctness run must stop at the coverage check")
    else:
        require(native.get("status") == "pass" and m["coverage_status"] == "sufficient",
                "native coverage rejected")
        require(m["complete_batches"] >= 4 and m["generation_transitions"] >= 2,
                "too few batches or generations")
        require(m["drain_s"] <= 0.1 * m["elapsed_s"] + 1e-6, "final drain dominates")
        replay = native["image_replay"]
        require(replay["order"] == "cyclic" and replay["source_bytes"] == 16 * FRAME_BYTES,
                "source replay differs")
        require(replay["codec"] == case["codec"] and native["blosc_block_bytes"] == case["blosc_block_bytes"],
                "codec or block size changed")
    return {
        "logical_bytes": m["logical_input_bytes"], "submitted_bytes": m["input_bytes"],
        "metered_output_bytes": m["output_bytes"], "elapsed_s": m["elapsed_s"],
        "logical_gibs": m["logical_input_bytes"] / GIB / m["elapsed_s"],
        "drain_s": m["drain_s"], "drain_fraction": m["drain_s"] / m["elapsed_s"],
    }


def check_store(output, case, source_array, frames=None, all_planes=False):
    import numpy as np
    import tensorstore as ts

    array_path = output / "images"
    metadata = json.loads((array_path / "zarr.json").read_text())
    shape = metadata["shape"]
    require(shape[1:] == [520, 696], "stored logical image shape includes padding")
    require(frames is None or shape[0] == frames, "stored frame extent differs")
    require(metadata["data_type"] == "uint16", "stored dtype differs")
    require(metadata["chunk_grid"]["configuration"]["chunk_shape"] == case["shard_shape"],
            "stored shard shape differs")
    sharding = metadata["codecs"][0]
    require(sharding["name"] == "sharding_indexed", "unexpected outer codec")
    cfg = sharding["configuration"]
    require(cfg["chunk_shape"] == case["chunk_shape"], "stored chunk shape differs")
    checks = set(range(shape[0])) if all_planes else set(range(min(shape[0], 16)))
    if not all_planes:
        checks.update([shape[0] - 1, shape[0] - 2, shape[0] // 2])
        for t in range(case["shard_shape"][0], shape[0], case["shard_shape"][0]):
            checks.update((t - 1, t))
    array = ts.open({"driver": "zarr3", "kvstore": {"driver": "file", "path": str(array_path)}},
                    context=ts.Context({"data_copy_concurrency": {"limit": 4}, "file_io_concurrency": {"limit": 4},
                                        "cache_pool": {"total_bytes_limit": 0}}), read=True).result()
    digest = hashlib.sha256()
    for frame in sorted(checks):
        values = array[frame].read(order="C").result()
        require(values.dtype == np.uint16 and np.array_equal(values, source_array[frame % 16]),
                f"source mismatch at frame {frame}")
        digest.update(values.tobytes())
    files = [p for p in output.rglob("*") if p.is_file()]
    stats = [p.stat() for p in files]
    shard_files = sorted(p for p in (array_path / "c").rglob("*") if p.is_file())
    require(len(shard_files) == math.ceil(shape[0] / case["shard_shape"][0]) * case["actual_layer_shards"],
            "stored shard file count differs")
    index_bytes = math.prod(case["chunks_per_shard"]) * 16 + 4
    with shard_files[0].open("rb") as f:
        if cfg.get("index_location", "end") == "end":
            f.seek(-index_bytes, os.SEEK_END)
        index = f.read(index_bytes)
        offset, count = struct.unpack_from("<QQ", index)
        require(offset != (1 << 64) - 1 and count >= 16, "first chunk missing")
        f.seek(offset)
        header = struct.unpack("<BBBBIII", f.read(16))
    require(header[3] == 2 and header[4] == case["chunk_bytes"], "Blosc header dtype/size differs")
    return {
        "array_path": str(array_path), "shape": shape, "metadata": metadata,
        "checked_frames": sorted(checks), "checked_plane_count": len(checks),
        "checked_output_sha256": digest.hexdigest(),
        "final_file_bytes": sum(s.st_size for s in stats),
        "allocated_file_bytes": sum(s.st_blocks * 512 for s in stats),
        "file_count": len(files), "shard_file_count": len(shard_files),
        "index_bytes_per_shard": index_bytes,
        "first_blosc_header": dict(zip(
            ("version", "codec_version", "flags", "typesize", "raw_bytes", "block_bytes", "encoded_bytes"),
            header)),
    }


class Study:
    def __init__(self, root, output, deadline_seconds):
        import numpy as np

        self.root, self.output = root, output
        output.mkdir(parents=True, exist_ok=False)
        self.plan = json.loads((root / "plan.json").read_text())
        provenance = json.loads((root / "provenance.json").read_text())
        self.source = Path(provenance["input_path"])
        raw = self.source.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == provenance["input_sha256"], "input hash changed")
        self.source_array = np.frombuffer(raw, dtype="<u2").reshape(16, 520, 696)
        self.deadline = time.monotonic() + deadline_seconds
        self.records = []
        self.kept = {}
        self.counter = 0

    def run(self, case, round_number, role, frames=None, small=False, retain=False):
        require(time.monotonic() + 30 < self.deadline, "study deadline reached")
        self.counter += 1
        run_id = f"{self.counter:03d}-{case['id']}-r{round_number}-{role}"
        directory = self.output / run_id
        directory.mkdir()
        store = directory / "store"
        args = command(self.root, self.plan, self.source, case, store, frames)
        record = {"id": run_id, "case": case, "round": round_number, "role": role,
                  "scope": "correctness" if small else "measurement", "started_utc": utc(),
                  "command": args, "slurm_job_id": os.environ["SLURM_JOB_ID"]}
        save(directory / "request.json", record)
        start = time.monotonic()
        try:
            with (directory / "stdout.log").open("w") as stdout, (directory / "stderr.log").open("w") as stderr:
                process = subprocess.Popen(args, stdout=stdout, stderr=stderr, start_new_session=True)
                try:
                    code = process.wait(timeout=min(420, max(1, self.deadline - time.monotonic() - 10)))
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    raise RuntimeError("native writer timeout")
            record["returncode"] = code
            documents = [json.loads(line) for line in (directory / "stdout.log").read_text().splitlines()
                         if line.startswith("{")]
            require(len(documents) == 1, "expected exactly one native JSON result")
            native = record["native"] = documents[0]
            record["metrics"] = validate_native(native, case, frames, small)
            require(code == (1 if small else 0),
                    "native writer failed")
            if frames is not None:
                record["store_check"] = check_store(store, case, self.source_array, frames, small)
            if retain and case["id"] not in self.kept:
                target = self.root / "data" / case["id"]
                require(not target.exists(), "retained store would overwrite existing data")
                store.rename(target)
                record["store_check"]["written_array_path"] = record["store_check"]["array_path"]
                record["store_check"]["array_path"] = str(target / "images")
                record["retained_path"] = str(target / "images")
                self.kept[case["id"]] = {
                    "id": case["id"], "path": str(target / "images"),
                    "chunk_shape": case["chunk_shape"], "writer_record": str(directory / "result.json"),
                }
            record["status"] = "pass"
        except Exception as error:
            record["status"] = "error"
            record["error"] = f"{type(error).__name__}: {error}"
        record["finished_utc"] = utc()
        record["process_and_check_wall_s"] = time.monotonic() - start
        save(directory / "result.json", record)
        with (self.output / "observations.jsonl").open("a") as f:
            f.write(json.dumps(record, allow_nan=False) + "\n")
        self.records.append(record)
        if record["status"] == "pass" and store.exists():
            shutil.rmtree(store)
        print(json.dumps({k: record.get(k) for k in ("id", "status", "metrics", "error")}), flush=True)
        require(record["status"] == "pass", record.get("error", "case failed"))
        return record

    def preflight(self):
        for case in fixed_cases(self.plan):
            self.run(case, 0, "preflight", frames=17, small=True)
        self.run(shard_case(self.plan, "fast", 54), 0, "preflight", frames=17, small=True)
        save(self.output / "complete.json", {"status": "pass", "complete_volume_checks": 7,
                                             "frames_per_store": 17, "source_planes": 16})

    def carry_shared(self, source):
        lines = source.read_text().splitlines()
        records = [(line, json.loads(line)) for line in lines]
        records = [(line, record) for line, record in records
                   if record["case"]["experiment"] == "shared-layouts"]
        expected = {(case["id"], repeat) for case in fixed_cases(self.plan)
                    for repeat in range(1, self.plan["shared_layouts"]["repetitions"] + 1)}
        require(len(records) == len(expected), "completed shared-layout count differs")
        require({(r["case"]["id"], r["round"]) for _, r in records} == expected,
                "completed shared-layout schedule differs")
        for _, record in records:
            require(record["status"] == "pass" and record["returncode"] == 0
                    and record["role"] == "sample", "shared-layout record was not accepted")
            validate_native(record["native"], record["case"], self.plan["shared_layouts"]["frames"])
            require(record.get("store_check"), "shared-layout value check missing")
        self.records = [record for _, record in records]
        self.counter = max(int(record["id"].split("-", 1)[0]) for record in self.records)
        manifest = json.loads((self.root / "read-manifest.json").read_text())
        require(manifest["shape"] == [self.plan["shared_layouts"]["frames"], 520, 696],
                "retained logical shape differs")
        self.kept = {layout["id"]: layout for layout in manifest["layouts"]}
        require(set(self.kept) == {case["id"] for case in fixed_cases(self.plan)},
                "retained layout set differs")
        for layout in self.kept.values():
            original = json.loads(Path(layout["writer_record"]).read_text())
            require(original in self.records and original["retained_path"] == layout["path"],
                    "retained writer record differs")
        (self.output / "observations.jsonl").write_text("\n".join(line for line, _ in records) + "\n")
        save(self.output / "carried-shared-records.json", {
            "source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "record_ids": [r["id"] for r in self.records],
            "reason": "Shared-layout measurements completed before the separate shard experiment restart",
        })

    def measure(self, shared_from=None):
        rng = random.Random(self.plan["seed"])
        cases = fixed_cases(self.plan)
        if shared_from is not None:
            self.carry_shared(shared_from)
        for round_number in range(1, self.plan["shared_layouts"]["repetitions"] + 1):
            order = cases.copy()
            rng.shuffle(order)
            if shared_from is None:
                for case in order:
                    self.run(case, round_number, "sample", frames=self.plan["shared_layouts"]["frames"], retain=True)
        require(len(self.kept) == len(cases), "retained layout missing")
        manifest = {
            "schema_version": 1, "source": {"shape": [16, 520, 696], "dtype": "uint16",
                "sha256": self.plan["input_sha256"], "replay": "cyclic", "start_plane": 0},
            "shape": [self.plan["shared_layouts"]["frames"], 520, 696],
            "shard_shape": self.plan["shared_layouts"]["shard_shape"],
            "layouts": [self.kept[c["id"]] for c in cases],
            "helpers_dir": str(self.root / "sources"), "seed": self.plan["seed"],
            "min_active_seconds": 10, "min_useful_bytes": GIB,
            "case_timeout_seconds": 180,
        }
        if shared_from is None:
            save(self.root / "read-manifest.json", manifest)
        targets = self.plan["shard_count"]["fast"]["targets"].copy()
        extension = False
        for round_number in range(1, self.plan["shard_count"]["repetitions"] + 1):
            reference = shard_case(self.plan, "fast", 16)
            self.run(reference, round_number, "reference-before")
            order = [shard_case(self.plan, "fast", target) for target in targets]
            order += [shard_case(self.plan, "slow_control", target)
                      for target in self.plan["shard_count"]["slow_control"]["targets"]]
            rng.shuffle(order)
            for case in order:
                self.run(case, round_number, "sample")
            self.run(reference, round_number, "reference-after")
            if round_number == 3:
                pairs = []
                for paired_round in range(1, 4):
                    samples = {r["case"]["target_shards"]: r["metrics"]["logical_gibs"]
                               for r in self.records if r["case"].get("series") == "fast"
                               and r["round"] == paired_round and r["role"] == "sample"}
                    pairs.append(samples[48] / samples[16])
                extension = statistics.median(pairs) > 1.05 and self.deadline - time.monotonic() > 1200
                save(self.output / "extension-decision.json", {
                    "paired_30_over_15_ratios": pairs, "median_ratio": statistics.median(pairs),
                    "remaining_s": self.deadline - time.monotonic(), "include_actual54": extension,
                    "rule": "median gain above5% and more than1200s remaining after round3",
                })
                if extension:
                    targets.append(54)
        save(self.output / "complete.json", {"status": "pass", "observations": len(self.records),
                                             "max54_extension": extension, "retained_layouts": len(self.kept)})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deadline-seconds", type=float, required=True)
    parser.add_argument("--phase", choices=("preflight", "measure", "shards"), required=True)
    parser.add_argument("--shared-from", type=Path)
    args = parser.parse_args()
    require(bool(os.environ.get("SLURM_JOB_ID")), "run on a compute allocation")
    study = Study(args.root.resolve(), args.output.resolve(), args.deadline_seconds)
    if args.phase == "shards":
        require(args.shared_from is not None, "shard restart needs completed shared-layout records")
        study.measure(args.shared_from.resolve())
    else:
        require(args.shared_from is None, "shared records apply only to a shard restart")
        getattr(study, args.phase)()


if __name__ == "__main__":
    main()
