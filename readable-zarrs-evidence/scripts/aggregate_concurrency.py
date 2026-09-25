import argparse
import csv
import hashlib
import io
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path


GIB = 1024**3
COMMON = (
    "source_file source_record run_id config_id family phase tool revision date machine backend "
    "content dataset workload destination storage_type mount_options recorded_nconnect "
    "mount_evidence_source role status valid_for_summary exclusion_reason comparison_group "
    "parameter_name parameter_value parameter_definition order repetition array_shape dtype "
    "chunk_shape raw_chunk_bytes shard_shape raw_shard_bytes shard_byte_definition "
    "concurrent_shards_target writer_layer_shards files_per_array distinct_files_touched "
    "active_files_peak active_files_mean workers request_depth per_file_request_limit "
    "codec codec_level shuffle blosc_block_bytes cache_policy warmup_status warmup_s "
    "warmup_input_bytes elapsed_s timing_policy throughput_value throughput_unit "
    "throughput_bytes_s throughput_numerator logical_input_bytes submitted_bytes "
    "sink_write_bytes final_stored_bytes host_peak_bytes host_memory_scope "
    "device_memory_bytes device_memory_scope memory_budget_bytes source_read_decode_timed "
    "geometry_scope notes"
).split()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def compact(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def write_csv(path, rows, columns=None):
    keys = list(columns or [])
    keys.extend(sorted({key for row in rows for key in row} - set(keys)))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: compact(value) if isinstance(value, (list, dict, bool)) else value
                             for key, value in row.items()})


class Sources:
    def __init__(self, home):
        self.home = home
        self.files = {}

    def read(self, path):
        data = path.read_bytes()
        self.files[str(path)] = {
            "source_file": str(path), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        return data.decode()

    def json(self, path):
        return json.loads(self.read(path))


def row(path, record, **values):
    result = dict.fromkeys(COMMON)
    result.update(source_file=str(path), source_record=record)
    result.update(values)
    return result


def microscopy(sources):
    root = sources.home / "tmp/2026-09-07-chucky-microscopy-pr/worktree/build-microscopy-shards-20260914"
    path = root / "run-3684715/study.json"
    study = sources.json(path)
    plan = study["plan"]
    mount = study["storage"]["filesystems"][0]
    rows = []
    for index, record in enumerate(study["records"]):
        case = plan["cases"][record["case_id"]]
        result = record["result"]
        measured = result.get("measurement", {})
        replay = result.get("image_replay", {})
        shape = replay.get("chunk_shape")
        grouping = replay.get("chunks_per_shard")
        shard = [a * b for a, b in zip(shape, grouping)] if shape and grouping else None
        metadata = plan["inputs"][case["input_id"]]
        rate = result.get("throughput_logical_gibs")
        command = record.get("command", [])
        output = command[command.index("-o") + 1] if "-o" in command else "discard"
        rows.append(row(
            path, f"/records/{index}", run_id=record["id"], config_id=record["case_id"],
            family="microscopy_shard_targets", phase=study["id"], tool="chucky",
            revision=study["source"]["revision"], source_patch_sha256=study["source"]["patch_sha256"],
            date=record.get("started"), machine=study["machine"]["hostname"], backend=case["backend"],
            content="microscopy", dataset=case["input_id"], workload="preloaded_cyclic_streaming_replay",
            destination=output, storage_type="nfs" if record["sink"] == "fs" else "discard",
            mount_options=mount["options"] if record["sink"] == "fs" else None,
            recorded_nconnect=16 if record["sink"] == "fs" else None,
            mount_evidence_source=str(path) + "#/storage", role=record["role"], status=result["status"],
            valid_for_summary=result["status"] == "pass" and measured.get("coverage_status") == "sufficient",
            comparison_group="|".join((study["id"], case["input_id"], case["backend"], case["name"], record["sink"], record["role"])),
            parameter_name="writer_layer_shards", parameter_value=record["actual_shards"],
            parameter_definition="geometry count in the non-append dimensions; not measured overlapping writes",
            order=index + 1, repetition=record["round"], array_shape=replay.get("shape"), dtype=replay.get("dtype"),
            chunk_shape=shape, raw_chunk_bytes=case["chunk_bytes"], shard_shape=shard,
            raw_shard_bytes=case["layout"]["full_shard_bytes"], shard_byte_definition="uncompressed capacity",
            concurrent_shards_target=case["target_shards"], writer_layer_shards=record["actual_shards"],
            workers=result.get("worker_threads"), io_workers=plan["fixed"]["io_workers"],
            per_file_request_limit=plan["fixed"]["per_file_write_limit"], output_buffers=plan["fixed"]["output_buffers"],
            codec=case["codec"], codec_level=case["level"], shuffle=case["shuffle"], blosc_block_bytes=case.get("blosc_block_bytes"),
            cache_policy="direct shard writes; server cache uncontrolled", warmup_status="completed",
            warmup_s=measured.get("warmup_s"), warmup_input_bytes=measured.get("warmup_input_bytes"),
            warmup_output_bytes=measured.get("warmup_output_bytes"), warmup_drain_s=measured.get("warmup_drain_s"),
            elapsed_s=measured.get("elapsed_s"), timing_policy=measured.get("policy"),
            throughput_value=rate, throughput_unit="GiB/s", throughput_bytes_s=rate * GIB if rate is not None else None,
            throughput_numerator="logical unpadded input bytes", logical_input_bytes=result.get("logical_input_bytes"),
            submitted_bytes=result.get("submitted_bytes"), sink_write_bytes=result.get("output_bytes"),
            sink_byte_definition="metered shard writes, including indexes/padding; not final file census; metadata bytes excluded",
            host_peak_bytes=result.get("memory_host_peak_bytes"), host_memory_scope="process peak resident memory, including preloaded raw input",
            device_memory_bytes=result.get("memory_device_used_bytes"), device_memory_scope="free-memory delta; not peak",
            memory_budget_bytes=None, source_read_decode_timed=False,
            geometry_scope="recorded replay layout", reference_shape=replay.get("reference_shape"),
            input_pack_shape=metadata["shape"], input_pack_sha256=metadata["sha256"],
            actual_batch_bytes=replay.get("actual_batch_bytes"), append_bytes=measured.get("append_bytes"),
            generation_transitions=measured.get("generation_transitions"), final_drain_s=measured.get("drain_s"),
            drain_fraction=measured.get("drain_fraction"), coverage_status=measured.get("coverage_status"),
            process_wall_s=record.get("process_wall_s"), recorded_boundaries=measured.get("boundaries"),
            diagnostics=result.get("diagnostics"), source_rate_requirement_bytes_s=None,
            notes="Paired target order randomized within each round. Geometry and per-file write size change with count. No acquisition source-rate proof or crash durability measurement.",
        ))
    failure_path = root / "run-3684596/validation-failure.json"
    failure = sources.json(failure_path)
    measure = failure["measurement"]
    rows.append(row(
        failure_path, "/", run_id="3684596-geometry-validation", family="microscopy_shard_targets",
        phase="geometry_validation", tool="chucky", revision=study["source"]["revision"],
        date=failure["finished"], backend="gpu", content="microscopy", role="preflight",
        status=failure["error"], valid_for_summary=False,
        exclusion_reason="Short geometry validation failed the existing final-drain coverage limit; no study observations in this job",
        elapsed_s=measure["elapsed_s"], throughput_value=measure["throughput_in_gibs"],
        throughput_unit="GiB/s", throughput_bytes_s=measure["throughput_in_gibs"] * GIB,
        throughput_numerator="logical input bytes", logical_input_bytes=measure["logical_input_bytes"],
        warmup_status="completed", warmup_s=measure["warmup_s"], final_drain_s=measure["drain_s"],
        drain_fraction=measure["drain_fraction"], geometry_scope="fixture geometry differs from study",
    ))
    for name in ("plan.json", "run_shards.py", "source.patch", "validation-correction.json", "validation-duration-correction.json"):
        sources.read(root / name)
    return rows


def chammi(sources):
    root = sources.home / "tmp/2026-06-15-chammi-reformat"
    logs = {}
    for name in ("gpu_job.log", "gpu_job2.log", "gpu_confirm.log", "gpu_curve.log"):
        text = sources.read(root / name)
        match = re.search(r"gpu node: ([^ ]+)", text)
        logs[name] = match.group(1) if match else None
    for name in ("cpu_job.sh", "cpu_job2.sh", "cpu_job3.sh", "cpu_job.log", "cpu_job2.log", "cpu_job3.log"):
        sources.read(root / name)
    sources.read(sources.home / "data/damacy/scenarios/make_sharded_chammi.py")
    counts_to_grouping = {
        1: [1, 2, 1, 8, 8], 2: [1, 2, 1, 4, 8], 4: [1, 2, 1, 2, 8],
        8: [1, 2, 1, 1, 8], 16: [1, 2, 1, 1, 4], 32: [1, 2, 1, 1, 2],
        64: [1, 2, 1, 1, 1], 128: [1, 1, 1, 1, 1],
    }
    rows = []
    bench = sources.home / "src/damacy/bench/runs"
    for parent in sorted(bench.iterdir()):
        if not parent.name.startswith("chammi-") or "idr0017" not in parent.name:
            continue
        for path in sorted(parent.glob("*/results.json")):
            result = sources.json(path)
            scenario = result["scenario"]
            name = scenario["name"]
            timestamp = path.parent.name
            if "-c120" in name:
                dense = timestamp >= "20260615-040000"
                phase = "dense_sweep" if dense else "sparse_confirmation"
                log_name = "gpu_curve.log" if dense else "gpu_confirm.log"
            else:
                phase = "exploratory"
                log_name = "gpu_job2.log" if ("4shard" in name or "8shard" in name) else "gpu_job.log"
            kind = "indexed_shards" if "after" in name else "unsharded_rechunk" if "ivirshup" in name else "original_whole_plane"
            match = re.search(r"-(\d+)shard", name)
            count = int(match.group(1)) if match else 1
            chunk = [1, 1, 1, 256, 256]
            if kind == "original_whole_plane":
                count, chunk = 2, [1, 1, 1, 2048, 2048]
            elif kind == "unsharded_rechunk":
                count = 128
            grouping = counts_to_grouping[count] if kind == "indexed_shards" else [1] * 5
            shard = [a * b for a, b in zip(chunk, grouping)] if kind == "indexed_shards" else None
            sampling, pipeline = scenario["sampling"], scenario["pipeline"]
            selection_hash = digest({"sampling": sampling, "uris": scenario["dataset"]["uris"]})
            seconds = result["timings_ms"]["wall"] / 1000
            counters = result["counters"]
            derived = result["derived"]
            rate = derived["throughput_mb_s"] / 1000
            stages = {stage["name"]: stage for stage in result["stages"]}
            sample_count = sampling["samples_per_batch"] * sampling["n_batches"]
            rows.append(row(
                path, "/", run_id=timestamp + ":" + name, config_id=name, family="chammi_shard_sweep",
                phase=phase, tool="damacy", date=timestamp, machine=logs[log_name], backend="gpu",
                content="microscopy", dataset="CHAMMI-75/idr0017", workload="translated_XY_crop",
                destination=scenario["dataset"]["store_root"], storage_type="shared filesystem; run-time mount not retained",
                mount_evidence_source=None, role="sample", status="retained_result", valid_for_summary=True,
                comparison_group="|".join(("chammi", phase, kind, selection_hash[:16], digest(pipeline)[:16])),
                parameter_name="files_per_array", parameter_value=count,
                parameter_definition="stored files per array from generation geometry; not simultaneous active files",
                order=timestamp, array_shape=[1, 2, 1, 2048, 2048], dtype="uint8", chunk_shape=chunk,
                raw_chunk_bytes=math.prod(chunk), shard_shape=shard,
                raw_shard_bytes=math.prod(shard) if shard else None,
                shard_byte_definition="modeled uncompressed capacity", files_per_array=count,
                distinct_files_touched=counters.get("distinct_shards"),
                reader_lookahead_samples=pipeline.get("lookahead_samples"), io_workers=pipeline.get("n_io_threads"),
                workers=None, codec="zstd", codec_level=3, cache_policy="best-effort client page-cache eviction before run; server caches uncontrolled; warmup follows eviction",
                warmup_status="included in run protocol; excluded from timed output numerator",
                warmup_batches=sampling.get("n_warmup_batches"), elapsed_s=seconds,
                timing_policy="timed sample-volume / wall; initialization and warmup outside wall",
                throughput_value=rate, throughput_unit="GB/s", throughput_bytes_s=rate * 1e9,
                throughput_numerator="returned float32 output bytes", returned_bytes=sample_count * derived["bytes_per_sample"],
                selection_shape=sampling["sample_shape"], sampling_seed=sampling["seed"], sample_count=sample_count,
                samples_per_batch=sampling["samples_per_batch"], trace_identity=selection_hash,
                memory_budget_bytes=pipeline.get("max_gpu_memory_mb", 0) * 1024**2 if "max_gpu_memory_mb" in pipeline else None,
                configured_pipeline=pipeline, geometry_scope="generation scripts and 512-array shard-count histograms; representative source shape; generated outputs no longer retained",
                layout_kind=kind, phase_log=str(root / log_name), original_count_label=1 if kind == "original_whole_plane" else count,
                recorded_io_stage_bytes=stages.get("io", {}).get("input_bytes"),
                recorded_decode_stage_bytes=stages.get("decode", {}).get("output_bytes"),
                counter_scope="native result; distinct_shards includes warmup activity; no active-file overlap trace",
                notes="Geometry is reconstructed from the retained writer script/commands, not a current payload census. Keep phases separate; original analysis selected latest or last-three runs.",
            ))
    return rows


def read_overlap(sources):
    root = sources.home / "tmp/2026-09-23-damacy-pr160-shard-grid"
    path = root / "job-3804536/report/concurrency.json"
    records = sources.json(path)
    filesystem_path = root / "job-3804241/filesystem.txt"
    mount = sources.read(filesystem_path).splitlines()[-1].split()
    rows = []
    for index, item in enumerate(records):
        codec = "lz4" if "-lz4-" in item["setting"] else "zstd"
        rows.append(row(
            path, f"/{index}", run_id=item["setting"] + ":" + item["backend"] + ":overlap",
            config_id=item["setting"], family="sixteen_shard_read_overlap", phase="accepted_pilot_diagnostic",
            tool=item["backend"], revision="5126f0958c0be3922a0a00c49d127ba62ddbc6a9 plus retained patches" if item["backend"] == "damacy" else "0.1.85",
            date="2026-09-23/24", machine="cpu-turin-gp-l-244-025", backend="cpu", content="synthetic",
            dataset="smooth4", workload="translated_XY_crop_instrumented", destination="node-local /tmp",
            storage_type="local XFS", mount_options=mount[-1], mount_evidence_source=str(filesystem_path),
            role="diagnostic", status="verified_chunk_ranges", valid_for_summary=False,
            exclusion_reason="Tracing is excluded from throughput measurements",
            comparison_group="sixteen_shard_overlap|" + codec + "|" + item["backend"],
            parameter_name="available_shards", parameter_value=16,
            parameter_definition="files touched by one diagnostic batch; observed overlap in separate fields",
            array_shape=[512, 4096, 4096], dtype="uint16", chunk_shape=[1, 128, 256], raw_chunk_bytes=65536,
            shard_shape=[512, 1024, 1024], raw_shard_bytes=GIB, shard_byte_definition="uncompressed capacity",
            distinct_files_touched=item["shards_read"], active_files_peak=item["peak_concurrent_shards"],
            active_files_mean=item["mean_concurrent_shards"], workers=32, io_workers=16,
            codec="blosc-" + codec, codec_level=3, shuffle="bit", blosc_block_bytes=16384,
            cache_policy="local page-cache eviction and zero-residency checks; fresh per-pass caches; warmed metadata",
            elapsed_s=item["read_span_seconds"], timing_policy=item["scope"],
            selection_shape=[1, 256, 256], reads_per_shard=item["reads_per_shard"],
            seconds_by_concurrent_shards=item["seconds_by_concurrent_shards"],
            fraction_at_sixteen_shards=item["fraction_at_sixteen_shards"],
            verified_chunk_ranges=item["verified_chunk_ranges"], record_kind="retained_derived_diagnostic",
            notes="Fixed count, not a shard-count sweep. Counts do not establish NFS behavior because this experiment used local XFS.",
        ))
    return rows


def later_read_overlap(sources):
    experiments = (
        ("2026-09-23-damacy-pr164-before-after", "job-3806589"),
        ("2026-09-24-damacy-cold-readahead", "job-3808884"),
        ("2026-09-24-damacy-cpu-read-buffers", "job-3810330"),
        ("2026-09-24-damacy-cold-chunks", "job-3811387"),
        ("2026-09-24-damacy-cold-blocks", "job-3822266"),
    )
    shapes = {16: [1, 64, 128], 32: [1, 128, 128], 64: [1, 128, 256],
              128: [1, 256, 256], 512: [1, 512, 512]}
    rows = []
    for experiment, job in experiments:
        root = sources.home / "tmp" / experiment / job
        path = root / "report/concurrency.csv"
        records = csv.DictReader(io.StringIO(sources.read(path)))
        filesystem_path = root / "filesystem.txt"
        mount = sources.read(filesystem_path).splitlines()[-1].split()
        slurm = sources.read(root / "slurm-job.txt")
        node = re.search(r"\bNodeList=([^\s]+)", slurm)
        for index, item in enumerate(records):
            def number(key):
                value = item.get(key)
                return float(value) if value not in (None, "") else None

            chunk_kib = int(item.get("chunk_kib", "64"))
            block_kib = int(item.get("block_kib", "16"))
            implementation = item["implementation"]
            workload = item.get("workload", "random-1x256x256")
            reader = "tensorstore" if implementation == "tensorstore" else "damacy"
            revision = "0.1.85" if reader == "tensorstore" else None
            if reader == "damacy" and experiment.endswith(("cold-chunks", "cold-blocks")):
                revision = "8d0931e7d131fd5d4c565458736ab586012c78c1 plus retained benchmark controls"
            rows.append(row(
                path, f"line:{index + 2}", run_id=f"{experiment}:{index + 1}",
                config_id=f"{item['codec']}-c{chunk_kib}-b{block_kib}-{implementation}-{workload}",
                family="read_overlap_controls", phase=experiment, tool=reader, revision=revision,
                date=experiment[:10], machine=node[1] if node else None, backend="cpu", content="synthetic",
                dataset="smooth4", workload=workload, destination="node-local /tmp", storage_type="local XFS",
                mount_options=mount[-1], mount_evidence_source=str(filesystem_path), role="diagnostic",
                status="retained_verified_trace_summary", valid_for_summary=False,
                exclusion_reason="Instrumented traces are excluded from throughput repetitions",
                comparison_group=f"read_overlap|{experiment}|{item['codec']}|{chunk_kib}|{block_kib}|{implementation}|{workload}",
                parameter_name="available_shards", parameter_value=16,
                parameter_definition="fixed available files; observed read-call and file overlap are separate",
                repetition=int(item["repeat"]) if item.get("repeat") else None,
                array_shape=[512, 4096, 4096], dtype="uint16", chunk_shape=shapes[chunk_kib],
                raw_chunk_bytes=chunk_kib * 1024, shard_shape=[512, 1024, 1024], raw_shard_bytes=GIB,
                shard_byte_definition="uncompressed capacity", active_files_peak=number("peak_shards"),
                active_files_mean=number("mean_shards"), workers=32, io_workers=16,
                codec="blosc-" + item["codec"], codec_level=3, shuffle="bit", blosc_block_bytes=block_kib * 1024,
                cache_policy="local client pages evicted/checked; metadata warmed; caches reset; readahead mode recorded in implementation",
                elapsed_s=number("read_span_seconds"), timing_policy="overlapping application pread calls in separate instrumented diagnostic",
                selection_shape=[8, 256, 256] if workload == "full-scan" else [1, 256, 256],
                implementation=implementation, record_kind="retained_derived_diagnostic",
                active_file_read_calls_peak=number("peak_active_file_reads") if "peak_active_file_reads" in item else number("peak_read_calls"),
                active_file_read_calls_mean=number("mean_active_file_reads") if "mean_active_file_reads" in item else number("mean_read_calls"),
                fraction_at_sixteen_shards=number("fraction_at_sixteen_shards"),
                verified_chunk_ranges=number("verified_chunk_ranges"), read_calls=number("read_calls"),
                recorded_reader_mib=number("reader_mib"), recorded_storage_mib=number("storage_mib"),
                trace_seconds=number("trace_seconds"), original_table_row=item,
                geometry_scope="retained per-encoding report and fixed sixteen-shard protocol",
                notes="Application call overlap is not device queue depth. The full-scan trace is a diagnostic subset, not a throughput measurement of the entire array. See read-runs for separate trace/timed-run locators.",
            ))
    return rows


def orca(sources):
    root = sources.home / "tmp/2026-09-04-orca-shard-split"
    rows = []
    for phase in ("pilot-results", "results", "confirm-results", "large-split-results"):
        environment_path = root / phase / "environment.txt"
        environment = sources.read(environment_path).splitlines()
        mount = next((line.split() for line in environment if line.startswith("/mnt/main0 ")), [])
        revision = next((line for line in environment if re.fullmatch(r"[a-f0-9]{40}", line)), None)
        table_path = root / phase / "runs.tsv"
        table = list(csv.DictReader(io.StringIO(sources.read(table_path)), delimiter="\t"))
        if not table:
            rows.append(row(table_path, "/", family="orca_append_shard_split", phase=phase, tool="chucky",
                            machine=environment[1], revision=revision, role="preflight", status="no_recorded_measurements",
                            valid_for_summary=False, exclusion_reason="Manifest contains header only"))
        for index, entry in enumerate(table):
            path = Path(entry["result"])
            result = sources.json(path)
            report_path = Path(entry["report"])
            report = sources.read(report_path)
            dimensions = []
            for line in report.splitlines():
                match = re.match(r"\s*\d+\s+([tczyx])\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+\d+\s+", line)
                if match:
                    dimensions.append((match[1], *map(int, match.groups()[1:])))
            chunk = [dim[2] for dim in dimensions]
            shard = [dim[2] * dim[4] for dim in dimensions]
            layer = math.prod(dim[5] for dim in dimensions[1:]) if dimensions else None
            total_files = math.prod(dim[5] for dim in dimensions) if dimensions else None
            append_shards = dimensions[0][5] if dimensions else None
            cap = int(entry["cap_mib"])
            minimum = int(entry.get("min_append_shards", "4"))
            parameter = "append_axis_shards"
            rate = result.get("throughput_in_gibs")
            rows.append(row(
                path, "/", run_id=path.stem, config_id=f"append-{minimum}-write-cap-{cap}",
                family="orca_append_shard_split", phase=phase, tool="chucky", revision=revision,
                date=entry["started_utc"], end_date=entry["ended_utc"], machine=environment[1], backend="gpu",
                content="synthetic", dataset="orca2_single", workload="synthetic_streaming_replay",
                destination=None, storage_type="nfs", mount_options=mount[-1] if mount else None,
                recorded_nconnect=16 if mount and "nconnect=16" in mount[-1] else None,
                mount_evidence_source=str(environment_path), role="sample", status=result["status"],
                valid_for_summary=result["status"] == "pass",
                comparison_group=f"orca|{phase}|{environment[1]}|write-cap-{cap}",
                parameter_name=parameter, parameter_value=append_shards,
                parameter_definition="count along append axis; writer layer remains a separate geometry count",
                order=index + 1, repetition=int(entry["block"]), array_shape=[dim[1] for dim in dimensions],
                dtype="uint16", chunk_shape=chunk, raw_chunk_bytes=math.prod(chunk) * 2 if chunk else None,
                shard_shape=shard, raw_shard_bytes=math.prod(shard) * 2 if shard else None,
                shard_byte_definition="uncompressed capacity reconstructed from recorded layout",
                writer_layer_shards=layer, total_output_files=total_files,
                append_axis_shards=append_shards, requested_min_append_shards=minimum,
                output_write_cap_bytes=cap * 1024**2, workers=result.get("worker_threads"), codec="none",
                cache_policy="filesystem write mode not encoded in result; historical NFS mount retained",
                warmup_status="not recorded", elapsed_s=result.get("wall_s"),
                timing_policy="pump_data_prefill_blocked plus bench_zarr_flush; includes fill/pump and drain; init excluded",
                throughput_value=rate, throughput_unit="GiB/s", throughput_bytes_s=rate * GIB if rate is not None else None,
                throughput_numerator="reported input GiB; synthetic padded layout volume",
                submitted_bytes=result.get("input_gib") * GIB if result.get("input_gib") is not None else None,
                sink_write_bytes=result.get("stages", {}).get("sink", {}).get("in_bytes"),
                host_peak_bytes=result.get("memory_host_peak_bytes"), host_memory_scope="process peak resident memory",
                device_memory_bytes=result.get("memory_device_used_bytes"), device_memory_scope="free-memory delta, not peak",
                geometry_scope="per-execution human-readable layout table", manifest_source=str(table_path),
                manifest_record=index + 2, paired_condition=entry.get("condition"), report_source=str(report_path),
                notes="Append-axis subdivision and write cap sweep; do not interpret total output-file count as concurrent streaming shard count. Per-run destination is not recorded in the manifest. Uncompressed codec is established from the report's zero compression pool and absence of a compression stage.",
            ))
    sources.read(root / "results/experiment.patch")
    sources.read(root / "repo/bench/bench_util.c")
    return rows


def storage_controls(sources):
    root = sources.home / "tmp/2026-08-24-nfs"
    rows = []
    for name in ("probe-cpu.log", "probe-l40.log"):
        path = root / name
        lines = sources.read(path).splitlines()
        machine = re.search(r"host=([^ ]+)", "\n".join(lines))[1]
        header = next(line for line in lines if line.startswith("label,backend,"))
        for number, line in enumerate(lines, 1):
            if not line.startswith(("nfs-", "local-")) or "," not in line:
                continue
            entry = next(csv.DictReader(io.StringIO(header + "\n" + line)))
            if None in entry:
                continue
            files, depth = int(entry["files"]), int(entry["depth"])
            rate = float(entry["throughput_gbps"])
            group = "|".join(("filesystem_controls", machine, entry["filesystem"], entry["request_bytes"], entry["mode"], entry["fsync"], entry["per_file_cap"], str(files)))
            rows.append(row(
                path, f"line:{number}", run_id=entry["label"], config_id=re.sub(r"-r\d+$", "", entry["label"]),
                family="filesystem_controls", phase=name, tool="chucky dev/io-depth", date="2026-08-24",
                machine=machine, backend=entry["backend"], content="synthetic", dataset="generated filesystem write buffers",
                workload="filesystem_write_control", storage_type=entry["filesystem"],
                mount_evidence_source=str(path), role="sample", status="pass" if entry["failures"] == "0" else "failed",
                valid_for_summary=entry["failures"] == "0", comparison_group=group,
                parameter_name="configured_request_depth", parameter_value=depth,
                parameter_definition="in-flight request cap across available files; not a measured active-file count",
                order=number, available_files=files, workers=int(entry["workers"]), request_depth=depth,
                per_file_request_limit=int(entry["per_file_cap"]), request_bytes=int(entry["request_bytes"]),
                preallocation=entry["prealloc"], fsync_requested=entry["fsync"] == "1",
                cache_policy=entry["mode"], elapsed_s=float(entry["wall_s"]),
                timing_policy="retained io-depth wall_s; setup_s and fsync_s are separately reported",
                throughput_value=rate, throughput_unit="GB/s", throughput_bytes_s=rate * 1e9,
                throughput_numerator="reported written bytes", submitted_bytes=int(entry["total_bytes"]),
                achieved_request_depth=float(entry["achieved_depth"]), p50_us=float(entry["p50_us"]),
                p99_us=float(entry["p99_us"]), failures=int(entry["failures"]),
                setup_s=float(entry["setup_s"]), fsync_s=float(entry["fsync_s"]),
                notes="Probe script calls this nconnect=16; per-job mount options were not saved, so recorded_nconnect is null. File and worker counts change in some controls.",
            ))
    sources.read(root / "probe.sh")
    sources.read(root / "streams.log")
    sources.read(root / "streams.sh")
    return rows


def summarize(rows):
    groups = defaultdict(list)
    for item in rows:
        if item.get("comparison_group") and item.get("throughput_bytes_s") is not None:
            groups[(item["comparison_group"], item["parameter_value"])].append(item)
    summaries = []
    for (group, value), attempts in sorted(groups.items(), key=lambda pair: str(pair[0])):
        accepted = [item for item in attempts if item["valid_for_summary"]]
        if not accepted:
            continue
        first = accepted[0]
        speeds = [item["throughput_bytes_s"] for item in accepted]
        durations = [item["elapsed_s"] for item in accepted if item.get("elapsed_s") is not None]
        memory = [item["host_peak_bytes"] for item in accepted if item.get("host_peak_bytes") is not None]
        summary = {key: first.get(key) for key in (
            "family", "phase", "tool", "revision", "machine", "backend", "content", "dataset", "workload",
            "storage_type", "recorded_nconnect", "role", "parameter_name", "parameter_definition",
            "chunk_shape", "raw_chunk_bytes", "shard_shape", "raw_shard_bytes", "writer_layer_shards",
            "codec", "codec_level", "blosc_block_bytes", "workers", "io_workers", "request_depth",
            "cache_policy", "timing_policy", "throughput_numerator", "layout_kind",
        )}
        summary.update(
            comparison_group=group, parameter_value=value, attempts=len(attempts), repetitions=len(accepted),
            failures_or_excluded=len(attempts) - len(accepted), median_bytes_s=statistics.median(speeds),
            minimum_bytes_s=min(speeds), maximum_bytes_s=max(speeds),
            minimum_elapsed_s=min(durations) if durations else None, maximum_elapsed_s=max(durations) if durations else None,
            host_peak_median_bytes=statistics.median(memory) if memory else None,
            source_rows=[item["source_file"] + "#" + item["source_record"] for item in attempts],
            range_definition="observed minimum/maximum; not a confidence interval",
        )
        summaries.append(summary)
    by_group = defaultdict(list)
    for summary in summaries:
        by_group[summary["comparison_group"]].append(summary)
    for members in by_group.values():
        previous = None
        for summary in sorted(members, key=lambda item: item["parameter_value"]):
            summary["previous_parameter_value"] = previous["parameter_value"] if previous else None
            summary["gain_over_previous_median_fraction"] = summary["median_bytes_s"] / previous["median_bytes_s"] - 1 if previous else None
            previous = summary
    return summaries


def paired_changes(rows):
    groups = defaultdict(lambda: defaultdict(dict))
    for item in rows:
        if item["family"] == "microscopy_shard_targets" and item["role"] == "sample" and item["valid_for_summary"]:
            groups[item["comparison_group"]][item["repetition"]][item["concurrent_shards_target"]] = item
    pairs = []
    for group, rounds in sorted(groups.items()):
        for number, targets in sorted(rounds.items()):
            if set(targets) != {4, 16}:
                raise ValueError(f"Incomplete pair: {group}, round {number}")
            lower, higher = targets[4], targets[16]
            pairs.append({
                "comparison_group": group, "round": number, "dataset": lower["dataset"], "backend": lower["backend"],
                "codec": lower["codec"], "chunk_shape": lower["chunk_shape"], "raw_chunk_bytes": lower["raw_chunk_bytes"],
                "lower_shards": lower["writer_layer_shards"], "higher_shards": higher["writer_layer_shards"],
                "lower_bytes_s": lower["throughput_bytes_s"], "higher_bytes_s": higher["throughput_bytes_s"],
                "paired_ratio": higher["throughput_bytes_s"] / lower["throughput_bytes_s"],
                "source_file": lower["source_file"], "source_records": [lower["source_record"], higher["source_record"]],
                "run_ids": [lower["run_id"], higher["run_id"]],
            })
    return pairs


def findings(rows, summaries, pairs):
    lines = [
        "# Shard and file concurrency findings", "",
        "The paired microscopy experiment supports a larger streaming shard layer on its measured L40/NFS setup, especially for fast GPU codecs. It does not establish sixteen as an optimum or test whether the best count tracks NFS connections. The broader read sweep also benefits from distributing data across files, but its medians do not peak at sixteen.", "",
        f"Export: {len(rows)} rows, {len(summaries)} summary points, and {len(pairs)} matched write pairs. Every row retains a source locator. Reference observations, failed preflight, diagnostics and incomplete pilot are visible. Missing values are empty CSV cells / JSON null, never measured zeros.", "",
        "## Paired microscopy streaming", "",
        "Chucky on cw-us-e4a2-l40-234-003, 2026-09-14; historical study storage records establish NFSv3 with nconnect=16. Four output buffers, 32 I/O workers, four CPU compression workers and a four-write per-file cap are fixed. Three selected settings per input were tested for eight randomized paired rounds. Rates are logical input GiB/s; output accounting is metered shard writes, not a final stored-file census.", "",
        "| Input | Backend | Codec | Actual layer count | Four-shard median GiB/s | Larger-layer median GiB/s | Median paired gain |",
        "| --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    grouped = defaultdict(list)
    for pair in pairs:
        grouped[pair["comparison_group"]].append(pair)
    for group, members in sorted(grouped.items()):
        first = members[0]
        low = statistics.median(item["lower_bytes_s"] for item in members) / GIB
        high = statistics.median(item["higher_bytes_s"] for item in members) / GIB
        gain = statistics.median(item["paired_ratio"] for item in members) - 1
        lines.append(f"| {first['dataset']} | {first['backend']} | {first['codec']} | 4 → {first['higher_shards']} | {low:.3f} | {high:.3f} | {gain:+.1%} |")
    samples = [item for item in rows if item["family"] == "microscopy_shard_targets" and item["role"] == "sample"]
    if samples:
        lines.extend(["", f"Accepted sample durations span {min(item['elapsed_s'] for item in samples):.2f}–{max(item['elapsed_s'] for item in samples):.2f} seconds. Final drain is included and reaches {max(item['drain_fraction'] for item in samples):.2%} of the measured interval. The two-second requested warmup is recorded separately. Raw packs are preloaded; source reading/decoding is outside timing. No recorded source-rate requirement, arrival trace or long-duration acquisition test establishes sustained acquisition at a specified rate."])
    lines.extend([
        "", "The targets change shard grouping and append-axis extent while each paired chunk/codec/source stays fixed. Full shard capacity is recorded in uncompressed bytes and is at most about 1 GiB in this study. BBBC022 has fifteen, not sixteen, shards in the larger layer. Available files do not measure simultaneous writes. The four versus larger comparison has no observations above sixteen, so it cannot locate a throughput plateau.", "",
        "`concurrency-paired.csv` preserves all 96 per-round ratios. The summary's minimum/maximum ranges are observed variation. Most compressed CPU pairs gain only a few percent; GPU Blosc-Zstd on BBBC022 also changes little. These are counterexamples to a universal large shard-count benefit. Interleaved uncompressed NFS/discard references and paired ordering reduce drift concerns, but do not measure cluster-wide network load. Larger filesystem variation than discard variation is evidence of a storage-path difference, not a complete causal attribution.", "",
        "## CHAMMI read count sweep", "",
        "All retained idr0017 phases are exported: exploratory, sparse confirmation and the dense three-round sweep. The dense phase ran on cw-us-e4a2-l40-202-063. Original whole-plane, unsharded rechunk and indexed-shard series have separate groups. Rates below are returned float32 decimal GB/s, not uint8 source bytes. Same seed alone is insufficient; the grouping also hashes the ordered URI list, sampling and pipeline settings.", "",
        "| Indexed shards per array | Median GB/s | Observed GB/s range | Repetitions |",
        "| ---: | ---: | ---: | ---: |",
    ])
    dense = sorted((item for item in summaries if item["family"] == "chammi_shard_sweep" and item["phase"] == "dense_sweep" and item["layout_kind"] == "indexed_shards"), key=lambda item: item["parameter_value"])
    for item in dense:
        lines.append(f"| {item['parameter_value']} | {item['median_bytes_s']/1e9:.3f} | {item['minimum_bytes_s']/1e9:.3f}–{item['maximum_bytes_s']/1e9:.3f} | {item['repetitions']} |")
    lines.extend([
        "", "These are 64 KiB raw inner chunks in representative uint8 arrays, with shards shrinking from 8 MiB to 64 KiB; this is not the 1 GiB-shard experiment. Thirty-two has the largest dense-sweep median. Rates subsequently fall, so the medians do not show a flat sixteen-and-above plateau. Historical max-run interpretations near sixteen are not used to discard lower repetitions. A before-layout count of one in the old analysis is also misleading: the retained uint8 [1,2,1,2048,2048] metadata has two whole-plane files per representative array.", "",
        "No retained per-job mount record establishes nconnect for these June runs. Their paths and archive context indicate shared storage, but the export leaves recorded_nconnect null. File-count histograms and generation scripts establish layouts; the generated sharded arrays themselves are no longer retained. Geometry reconstructed from those scripts is labeled modeled. distinct_shards counters are not simultaneously active files and can include warmup. Advisory client page-cache eviction does not control server caches; warmup follows eviction.", "",
        "## Measured read overlap and filesystem controls", "",
        "The September 23 fixed-count CPU pilot uses local XFS, not NFS: sixteen available 1 GiB raw shards, 64 KiB chunks, 16 KiB Blosc blocks, 32 decode/copy participants and 16 file readers. Separate instrumented diagnostics show peak overlapping shard reads of 9/10 for Damacy LZ4/Zstd and 14 for TensorStore. Time-weighted means are about 5.0 versus 6.8–6.9. Each diagnostic touches all sixteen shards and verifies 3,033 required ranges. These instrumented observations are excluded from throughput summaries and do not supply a shard-count optimum.", "",
        "Later scheduling, readahead, buffer, chunk and block studies retain another 224 diagnostic table rows in concurrency-read-overlap.csv. They change this early picture: sixteen-way overlap is reached in later traces. For the 512/512 KiB Zstd scan diagnostic, Damacy's mean simultaneous shard reads are 10.95 with readahead disabled and 5.05 with default advice, versus TensorStore's 4.40. Both earlier and later phases remain visible. Distinct active files and active read calls have separate columns; these are application calls, not device queue depths. The fixed count does not identify an optimum or an NFS connection relationship.", "",
        "Synthetic Orca append-axis and write-cap experiments are exported separately. Total output-file count and append-axis shard count are distinguished from the non-append layer geometry. Changing the total file count does not automatically change the number of active layer files. The three completed phases used different L40 nodes and are not pooled. The empty pilot manifest remains visible.", "",
        "The August filesystem microbenchmarks include one/eight/64 available files, request depth, request size, local/NFS and sync controls. They record actual achieved request depth, not simultaneous file counts. Two-repeat NFS depth points show appreciable variation, including different rankings across repeats; the script's nconnect=16 description is not a recorded run-time mount, so that field remains null. Source logs retain network counters for a separate wire check, not load attribution for every run. No matched nconnect sweep was found in these records.", "",
        "## Reproduction", "",
        "From this directory, run `python3 scripts/aggregate_concurrency.py --from-rows` to recreate CSV summaries and these findings from concurrency-records.jsonl. Omit `--from-rows` to reread the retained sources on the cluster; use `--source-home` when that archive root moves. The script reads metadata only and never invokes an archived benchmark script. Source paths and SHA256 values are in concurrency-sources.json.", "",
        "## Focused follow-ups, proposed only", "",
        "1. Vary the streaming layer count above and below sixteen while fixing real input, chunk/codec, raw shard capacity, workers and timing; interleave repetitions. This would test the plateau rather than only the 4/16 contrast.",
        "2. Vary nconnect in a matched storage experiment while fixing file counts, geometry, reader/writer budgets and workload; measure actual file/request overlap. This would test whether the useful file count tracks connections.",
        "3. At fixed read layout and trace, vary request scheduling while retaining source/output hashes and byte counters. This would test why sixteen available shard files produce fewer overlapping reads.", "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-home", type=Path, default=Path.home())
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--from-rows", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    records = args.output / "concurrency-records.jsonl"
    if args.from_rows:
        rows = [json.loads(line) for line in records.read_text().splitlines()]
    else:
        sources = Sources(args.source_home)
        rows = microscopy(sources) + chammi(sources) + read_overlap(sources) + later_read_overlap(sources) + orca(sources) + storage_controls(sources)
        records.write_text("".join(compact(item) + "\n" for item in rows))
        (args.output / "concurrency-sources.json").write_text(json.dumps(list(sources.files.values()), indent=2) + "\n")
    summaries = summarize(rows)
    pairs = paired_changes(rows)
    write_csv(args.output / "concurrency-runs.csv", rows, COMMON)
    write_csv(args.output / "concurrency-summary.csv", summaries)
    write_csv(args.output / "concurrency-plot-data.csv", summaries)
    write_csv(args.output / "concurrency-paired.csv", pairs)
    write_csv(args.output / "concurrency-read-overlap.csv", [item for item in rows if item["family"] in ("sixteen_shard_read_overlap", "read_overlap_controls")])
    write_csv(args.output / "concurrency-storage-controls.csv", [item for item in rows if item["family"] == "filesystem_controls"])
    (args.output / "concurrency-findings.md").write_text(findings(rows, summaries, pairs))
    print(json.dumps({"rows": len(rows), "families": dict(Counter(item["family"] for item in rows)), "summary_points": len(summaries), "paired_rounds": len(pairs)}))


if __name__ == "__main__":
    main()
