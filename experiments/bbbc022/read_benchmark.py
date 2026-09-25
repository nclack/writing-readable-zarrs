#!/usr/bin/env python3
"""Measure the retained BBBC022 arrays on a CPU compute node.

The manifest has schema_version=1, source={shape, dtype, sha256, replay,
start_plane}, shape, shard_shape, helpers_dir, and layouts=[{id, path,
chunk_shape}]. Paths identify Zarr arrays, including their images subdirectory.
Optional settings are seed, samples_per_batch, crop_samples,
min_active_seconds, min_useful_bytes, and case_timeout_seconds.

Example: python read_benchmark.py --manifest read-manifest.json --output reads
    --source bbbc022-mito.raw --deadline-seconds 4000

Each observation runs in a fresh process. The output directory preserves the
common trace, complete schedule, individual logs, checks, passes and failures.
Preflight observations are a separate phase with smaller traces and one repeat.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import platform
import random
import re
import resource
import signal
import subprocess
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

GIB = 1 << 30
MIB = 1 << 20
SOURCE_SHA256 = "1eff677d3f7d6785bdc8e65079613d6ba2c801a19f33503517a12b8df54affc7"
SOURCE_SHAPE = [16, 520, 696]
SHARD_SHAPE = [2048, 512, 512]
CHUNK_SHAPES = {
    (1, 64, 128),
    (1, 128, 128),
    (1, 128, 256),
    (1, 256, 256),
    (1, 256, 512),
    (1, 512, 512),
}
BACKENDS = ("damacy", "tensorstore")
METADATA_CACHE_BYTES = 256 * MIB
HELPERS = (
    "shard_grid_readers.py",
    "cold_read_config.py",
    "cpu_pareto.py",
    "storage_reads.py",
    "cpu_storage_reads.py",
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def json_hash(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class Events:
    def __init__(self, path, case=None):
        self.path = Path(path)
        self.stream = self.path.open("x", buffering=1)
        self.case = case or {}

    def emit(self, event, **fields):
        row = {"event": event, "utc": utc_now(), **self.case, **fields}
        self.stream.write(json.dumps(row, sort_keys=True) + "\n")
        return row

    def close(self):
        self.stream.close()


def compute_node_required():
    require(
        os.environ.get("SLURM_JOB_ID"),
        "Run measurements inside an allocated Slurm compute job",
    )


def machine():
    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": sys.version,
        "python_executable": sys.executable,
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "environment": {
            name: os.environ.get(name)
            for name in (
                "SLURM_JOB_ID",
                "SLURM_JOB_NODELIST",
                "SLURM_CPUS_PER_TASK",
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "PYTHONPATH",
                "DAMACY_BENCH_READ_MODE",
                "DAMACY_STORAGE_TIER",
                "DAMACY_NFS_MOUNT",
            )
        },
    }


def normalize_manifest(raw, path, preflight):
    require(raw.get("schema_version") == 1, "Expected manifest schema_version=1")
    source = raw["source"]
    require(source["shape"] == SOURCE_SHAPE, "Unexpected BBBC022 source shape")
    require(source["dtype"] == "uint16", "Expected uint16 source")
    require(source["sha256"] == SOURCE_SHA256, "Unexpected BBBC022 source hash")
    require(
        source["replay"] == "cyclic" and source["start_plane"] == 0,
        "Expected cyclic replay starting at plane zero",
    )
    shape = raw["shape"]
    require(
        len(shape) == 3 and all(isinstance(n, int) and n > 0 for n in shape),
        "Invalid logical shape",
    )
    require(shape[1:] == SOURCE_SHAPE[1:], "Logical image extent must be 520 by 696")
    require(raw["shard_shape"] == SHARD_SHAPE, "Unexpected fixed shard shape")
    for name, wanted in (("decode_workers", 32), ("io_workers", 16), ("repeats", 3)):
        require(raw.get(name, wanted) == wanted, f"This protocol fixes {name}={wanted}")
    require(raw.get("cache_tier", "nfs") == "nfs", "This protocol measures NFS")
    parent = Path(path).resolve().parent
    layouts = []
    for row in raw["layouts"]:
        require(
            re.fullmatch(r"[A-Za-z0-9_-]+", row["id"]),
            "Layout IDs must be simple file names",
        )
        require(tuple(row["chunk_shape"]) in CHUNK_SHAPES, "Unexpected chunk shape")
        location = Path(row["path"])
        location = location if location.is_absolute() else parent / location
        layouts.append({**row, "path": str(location.resolve())})
    require(
        layouts and len({row["id"] for row in layouts}) == len(layouts),
        "Missing or duplicate layout IDs",
    )
    require(
        len({tuple(row["chunk_shape"]) for row in layouts}) == len(layouts),
        "Duplicate chunk geometry",
    )
    helpers = Path(raw["helpers_dir"])
    helpers = helpers if helpers.is_absolute() else parent / helpers
    settings = {
        "seed": int(raw.get("seed", 20260925)),
        "samples_per_batch": int(raw.get("samples_per_batch", 128)),
        "crop_samples": int(raw.get("crop_samples", 4096)),
        "min_active_seconds": float(raw.get("min_active_seconds", 10.0)),
        "min_useful_bytes": int(raw.get("min_useful_bytes", GIB)),
        "case_timeout_seconds": float(raw.get("case_timeout_seconds", 180.0)),
        "decode_workers": 32,
        "io_workers": 16,
        "repeats": 3,
        "metadata_cache_bytes": METADATA_CACHE_BYTES,
    }
    require(
        0 < settings["samples_per_batch"] <= 128, "Batch size must be between 1 and 128"
    )
    require(
        settings["crop_samples"] > 0
        and settings["crop_samples"] % settings["samples_per_batch"] == 0,
        "Crop count must contain complete batches",
    )
    require(
        settings["min_active_seconds"] >= 5
        and settings["min_useful_bytes"] >= 512 * MIB,
        "Measurement policy is shorter than the approved fallback",
    )
    require(
        settings["case_timeout_seconds"] > settings["min_active_seconds"] + 5,
        "Case timeout is too short",
    )
    if preflight:
        settings.update(
            repeats=1,
            crop_samples=settings["samples_per_batch"],
            min_active_seconds=0.1,
            min_useful_bytes=0,
        )
    return {
        "schema_version": 1,
        "source": source,
        "shape": shape,
        "shard_shape": SHARD_SHAPE,
        "layouts": layouts,
        "helpers_dir": str(helpers.resolve()),
        "nfs_mount": raw.get("nfs_mount", "/mnt/main0"),
        "phase": "preflight" if preflight else "measurement",
        "settings": settings,
        "policy_id": json_hash(settings),
    }


def inspect_layout(layout, shape):
    uri = Path(layout["path"])
    metadata_path = uri / "zarr.json"
    metadata = read_json(metadata_path)
    require(
        metadata["zarr_format"] == 3 and metadata["node_type"] == "array",
        "Expected a Zarr v3 array",
    )
    require(
        metadata["shape"] == shape,
        "Stored logical extent differs from the manifest; padding must not extend it",
    )
    require(
        metadata["data_type"] == "uint16" and metadata["fill_value"] == 0,
        "Expected uint16 with zero fill",
    )
    require(metadata["chunk_grid"]["name"] == "regular", "Expected regular shards")
    require(
        metadata["chunk_grid"]["configuration"]["chunk_shape"] == SHARD_SHAPE,
        "Stored shard shape differs",
    )
    codecs = metadata["codecs"]
    require(
        len(codecs) == 1 and codecs[0]["name"] == "sharding_indexed",
        "Expected one sharding_indexed codec",
    )
    sharding = codecs[0]["configuration"]
    require(
        sharding["chunk_shape"] == layout["chunk_shape"],
        "Stored inner chunk shape differs",
    )
    inner = sharding["codecs"]
    require(
        len(inner) == 2 and inner[0]["name"] == "bytes" and inner[1]["name"] == "blosc",
        "Expected bytes followed by Blosc",
    )
    require(
        inner[0].get("configuration", {}).get("endian", "little") == "little",
        "Expected little-endian pixels",
    )
    blosc = inner[1]["configuration"]
    for name, wanted in (
        ("cname", "zstd"),
        ("clevel", 3),
        ("shuffle", "bitshuffle"),
        ("blocksize", 16384),
        ("typesize", 2),
    ):
        require(
            blosc.get(name) == wanted, f"Unexpected Blosc {name}: {blosc.get(name)!r}"
        )
    indexes = sharding["index_codecs"]
    require(
        indexes and indexes[0]["name"] == "bytes",
        "Expected an uncompressed little-endian shard index",
    )
    require(
        indexes[0].get("configuration", {}).get("endian", "little") == "little",
        "Unexpected index byte order",
    )
    require(
        all(row["name"] == "crc32c" for row in indexes[1:]),
        "Unsupported shard-index codec",
    )
    require(
        sharding.get("index_location", "end") in ("start", "end"),
        "Unexpected index location",
    )
    chunks_per_shard = math.prod(
        s // c for s, c in zip(SHARD_SHAPE, layout["chunk_shape"], strict=True)
    )
    index_bytes = 16 * chunks_per_shard + 4 * (len(indexes) - 1)
    encoding = metadata["chunk_key_encoding"]
    separator = encoding.get("configuration", {}).get("separator", "/")
    require(
        encoding["name"] == "default" and separator in ("/", "."),
        "Unsupported shard key encoding",
    )
    coordinates = list(
        itertools.product(
            *(range(math.ceil(n / s)) for n, s in zip(shape, SHARD_SHAPE, strict=True))
        )
    )
    files = []
    for coordinate in coordinates:
        file = uri / separator.join(("c", *(str(n) for n in coordinate)))
        stat = file.stat()
        require(
            file.is_file() and stat.st_size >= index_bytes,
            f"Missing or short shard: {file}",
        )
        files.append(
            {
                "path": str(file),
                "coordinate": list(coordinate),
                "bytes": stat.st_size,
                "allocated_bytes": stat.st_blocks * 512,
            }
        )
    footprint = index_bytes * len(files)
    require(
        footprint <= METADATA_CACHE_BYTES // 2,
        "Shard indexes exceed the fixed metadata-cache budget with headroom",
    )
    return {
        **layout,
        "metadata": metadata,
        "metadata_sha256": file_hash(metadata_path),
        "files": files,
        "index_bytes_per_file": index_bytes,
        "index_bytes_all_files": footprint,
        "raw_chunk_bytes": math.prod(layout["chunk_shape"]) * 2,
        "logical_bytes": math.prod(shape) * 2,
        "full_scan_chunk_capacity_bytes": math.prod(
            math.ceil(n / c) for n, c in zip(shape, layout["chunk_shape"], strict=True)
        )
        * math.prod(layout["chunk_shape"])
        * 2,
        "raw_shard_capacity_bytes": math.prod(SHARD_SHAPE) * 2,
        "expected_shard_files": len(files),
        "file_bytes": sum(row["bytes"] for row in files),
        "allocated_bytes": sum(row["allocated_bytes"] for row in files),
    }


def make_trace(manifest):
    shape, settings = manifest["shape"], manifest["settings"]
    rng = random.Random(settings["seed"])
    count = settings["crop_samples"]
    frames = [rng.randrange(shape[0]) for _ in range(count)]
    translated_small = [
        [t, rng.randrange(shape[1] - 255), rng.randrange(shape[2] - 255)]
        for t in frames
    ]
    translated_large = []
    for frame in frames:
        while True:
            y, x = rng.randrange(shape[1] - 511), rng.randrange(shape[2] - 511)
            if y or x:
                translated_large.append([frame, y, x])
                break
    scan_frames = list(range(shape[0]))
    if manifest["phase"] == "preflight" and shape[0] > 256:
        scan_frames = sorted(
            {
                *range(min(16, shape[0])),
                *range(0, shape[0], SHARD_SHAPE[0]),
                shape[0] - 1,
            }
        )
    descriptions = (
        ("translated-256", [1, 256, 256], translated_small),
        ("aligned-512", [1, 512, 512], [[t, 0, 0] for t in frames]),
        ("translated-512", [1, 512, 512], translated_large),
        ("full-scan", [1, shape[1], shape[2]], [[t, 0, 0] for t in scan_frames]),
    )
    workloads = {}
    for name, sample_shape, starts in descriptions:
        batch = math.gcd(len(starts), settings["samples_per_batch"])
        workload = {
            "name": name,
            "sample_shape": sample_shape,
            "samples_per_batch": batch,
            "starts": starts,
            "useful_source_bytes_per_pass": len(starts) * math.prod(sample_shape) * 2,
            "output_float32_bytes_per_pass": len(starts) * math.prod(sample_shape) * 4,
            "complete_logical_scan": name == "full-scan"
            and scan_frames == list(range(shape[0])),
        }
        workload["trace_sha256"] = json_hash(workload)
        workloads[name] = workload
    require(
        workloads["aligned-512"]["starts"]
        == [[row[0], 0, 0] for row in workloads["translated-512"]["starts"]],
        "Alignment pair frame lists differ",
    )
    return {
        "schema_version": 1,
        "phase": manifest["phase"],
        "seed": settings["seed"],
        "shape": shape,
        "workloads": workloads,
    }


def touched_shards(starts, sample_shape):
    found = set()
    for start in starts:
        ranges = [
            range(a // s, (a + n - 1) // s + 1)
            for a, n, s in zip(start, sample_shape, SHARD_SHAPE, strict=True)
        ]
        found.update(itertools.product(*ranges))
    return found


def validation_starts(shape, workload):
    size = workload["sample_shape"]
    edge = [shape[d] - size[d] for d in range(3)]
    starts = [(t, edge[1], edge[2]) for t in range(0, shape[0], SHARD_SHAPE[0])]
    starts.extend((t, 0, 0) for t in range(min(16, shape[0])))
    starts.extend(
        (
            (shape[0] - 1, edge[1], edge[2]),
            tuple(workload["starts"][0]),
            tuple(workload["starts"][-1]),
        )
    )
    starts = list(dict.fromkeys(starts))
    batch = workload["samples_per_batch"]
    original = list(starts)
    while len(starts) % batch:
        starts.append(original[len(starts) % len(original)])
    return [list(row) for row in starts]


def source_hashes(source, starts, sample_shape):
    import numpy as np

    hashes, known = {}, {}
    for index, (t, y, x) in enumerate(starts):
        key = (t % SOURCE_SHAPE[0], y, x)
        if key not in known:
            values = np.ascontiguousarray(
                source[
                    key[0] : key[0] + 1,
                    y : y + sample_shape[1],
                    x : x + sample_shape[2],
                ],
                dtype=np.float32,
            )
            require(list(values.shape) == sample_shape, "Invalid validation slice")
            known[key] = hashlib.sha256(values.tobytes(order="C")).hexdigest()
        hashes[str(index)] = known[key]
    return hashes


def geometry(workload, chunk_shape):
    batch = workload["samples_per_batch"]
    unique_count = visits = maximum = 0
    sample_shape = workload["sample_shape"]
    for first in range(0, len(workload["starts"]), batch):
        chunks, batch_visits = set(), 0
        for start in workload["starts"][first : first + batch]:
            ranges = [
                range(a // c, (a + n - 1) // c + 1)
                for a, n, c in zip(start, sample_shape, chunk_shape, strict=True)
            ]
            batch_visits += math.prod(len(row) for row in ranges)
            chunks.update(itertools.product(*ranges))
        unique_count += len(chunks)
        visits += batch_visits
        maximum = max(maximum, batch_visits)
    return {
        "max_chunk_uses_per_batch": maximum,
        "sample_chunk_visits_per_pass": visits,
        "batch_unique_chunks_per_pass": unique_count,
        "batch_unique_chunk_capacity_bytes_per_pass": unique_count
        * math.prod(chunk_shape)
        * 2,
        "interpretation": "Geometric reference: nominal chunks counted once per batch; actual decoding may differ. This is not a storage-byte or TensorStore decode counter.",
    }


def reset_tensorstore(reader, layout, readers):
    import tensorstore as ts

    started = time.perf_counter()
    before = readers.tensorstore_file_metrics()
    old_pools = {
        key: reader.context[key] for key in ("cache_pool", "cache_pool#metadata")
    }
    reader.context = ts.Context(
        {
            "cache_pool": {"total_bytes_limit": 0},
            "cache_pool#metadata": {"total_bytes_limit": METADATA_CACHE_BYTES},
        },
        parent=reader.shared_context,
    )
    for name, pool in old_pools.items():
        require(
            reader.context[name] is not pool, f"TensorStore cache pool reused: {name}"
        )
    for name, worker_resource in reader.shared_resources.items():
        require(
            reader.context[name] is worker_resource,
            f"TensorStore worker resource changed: {name}",
        )
    source = ts.open(
        reader.source_spec, context=reader.context, read=True, write=False
    ).result()
    points = [
        tuple(n * s for n, s in zip(row["coordinate"], SHARD_SHAPE, strict=True))
        for row in layout["files"]
    ]

    def warm():
        pending = [
            source[point].storage_statistics(query_fully_stored=True)
            for point in points
        ]
        require(
            all(future.result().fully_stored for future in pending),
            "Missing data while warming every shard index",
        )

    warm()
    first = readers.tensorstore_file_metrics()
    warm()
    second = readers.tensorstore_file_metrics()
    byte_key = "/tensorstore/kvstore/file/bytes_read"
    require(
        first[byte_key] - before[byte_key] >= layout["index_bytes_all_files"],
        "Index warmup did not account for every shard index",
    )
    require(
        second[byte_key] == first[byte_key],
        "TensorStore indexes were reread on the second warmup sweep",
    )
    reader.array = source.astype(ts.float32)
    reader.settings["data_cache_resets"] += 1
    return {
        "seconds": time.perf_counter() - started,
        "shards_warmed": len(points),
        "index_bytes_all_files": layout["index_bytes_all_files"],
        "first_sweep_file_bytes": first[byte_key] - before[byte_key],
        "second_sweep_file_bytes": second[byte_key] - first[byte_key],
        "fresh_data_and_metadata_pools": True,
        "shared_worker_resources": True,
    }


def audit_counters(backend, stats, useful, reference):
    if backend == "damacy":
        output = stats["assemble"]["output_bytes"]
        decoded = stats["decode"]["output_bytes"]
        reader_bytes = stats["io"]["input_bytes"]
        require(stats["gpu_bytes_committed"] == 0, "Unexpected GPU memory use")
        require(
            decoded == stats["assemble"]["input_bytes"],
            "Decode/assembly counters disagree",
        )
        require(
            stats["file_reader"]["read_jobs"] == stats["reads_issued"],
            "File read counters disagree",
        )
    else:
        output = stats["output_bytes"]
        decoded = None
        reader_bytes = stats["file_metrics"]["/tensorstore/kvstore/file/bytes_read"]
    require(
        output == 2 * useful,
        f"Float32 output byte count differs: {output} != {2 * useful}",
    )
    require(reader_bytes > 0, "No reader bytes counted")
    return {
        "useful_source_bytes": useful,
        "output_float32_bytes": output,
        "reader_bytes": reader_bytes,
        "decoded_bytes": decoded,
        "decoded_amplification": decoded / useful if decoded is not None else None,
        "decoded_matches_batch_unique_chunk_capacity": decoded
        == reference["batch_unique_chunk_capacity_bytes_per_pass"]
        if decoded is not None
        else None,
        "chunks_match_batch_unique_geometry": stats["chunks_dispatched"]
        == reference["batch_unique_chunks_per_pass"]
        if backend == "damacy"
        else None,
    }


def run_worker(config_path):
    config = read_json(config_path)
    case, manifest = config["case"], config["manifest"]
    events = Events(config["events_path"], case)
    stage = "setup"
    try:
        compute_node_required()
        os.environ["DAMACY_BENCH_READ_MODE"] = "persistent-default"
        os.environ["DAMACY_STORAGE_TIER"] = "nfs"
        os.environ["DAMACY_NFS_MOUNT"] = manifest["nfs_mount"]
        events.emit(
            "started",
            status="running",
            machine=machine(),
            policy_id=manifest["policy_id"],
        )
        require(version("numpy") == "2.3.3", "Expected NumPy 2.3.3")
        import numpy as np

        sys.path.insert(0, manifest["helpers_dir"])
        import shard_grid_readers as readers
        import storage_reads as storage

        original_context = readers.tensorstore_context

        def tensorstore_context(workers, io_workers):
            result = original_context(workers, io_workers)
            result["cache_pool#metadata"]["total_bytes_limit"] = METADATA_CACHE_BYTES
            return result

        readers.tensorstore_context = tensorstore_context
        frozen = config["layout"]
        layout = inspect_layout(frozen, manifest["shape"])
        require(
            layout["metadata_sha256"] == frozen["metadata_sha256"],
            "Array metadata changed after scheduling",
        )
        require(
            layout["files"] == frozen["files"],
            "Shard file sizes changed after scheduling",
        )
        trace = read_json(config["trace_path"])
        require(json_hash(trace) == config["trace_sha256"], "Saved trace changed")
        workload = trace["workloads"][case["workload"]]
        raw = Path(config["source"]).read_bytes()
        require(len(raw) == math.prod(SOURCE_SHAPE) * 2, "Unexpected raw source length")
        require(hashlib.sha256(raw).hexdigest() == SOURCE_SHA256, "Source hash changed")
        source = np.frombuffer(raw, dtype="<u2").reshape(SOURCE_SHAPE)
        checks = validation_starts(manifest["shape"], workload)
        checked_shards = touched_shards(checks, workload["sample_shape"])
        all_shards = {tuple(row["coordinate"]) for row in layout["files"]}
        require(
            checked_shards == all_shards, "Validation does not cover every shard index"
        )
        hashes = source_hashes(source, checks, workload["sample_shape"])
        reference = geometry(workload, layout["chunk_shape"])
        validation_workload = {**workload, "starts": checks}
        validation_reference = geometry(validation_workload, layout["chunk_shape"])
        limits = {
            "max_chunk_uses_per_batch": max(
                reference["max_chunk_uses_per_batch"],
                validation_reference["max_chunk_uses_per_batch"],
            )
        }
        events.emit(
            "prepared",
            workload={key: value for key, value in workload.items() if key != "starts"},
            query_count=len(workload["starts"]),
            geometry=reference,
            metadata_sha256=layout["metadata_sha256"],
            logical_shape=manifest["shape"],
            source_sha256=SOURCE_SHA256,
        )
        settings = manifest["settings"]
        stage = "validation"
        args = (layout["path"], workload, limits, layout["raw_chunk_bytes"], 32, 16)
        with (
            readers.open_reader(case["backend"], *args) as reader,
            storage.Files([row["path"] for row in layout["files"]]) as files,
        ):
            if case["backend"] == "tensorstore":
                reader.settings["metadata_cache_bytes"] = METADATA_CACHE_BYTES
                reader.settings["index_warmup_scope"] = (
                    "Every stored shard, all T/XY coordinates; second sweep must read zero bytes"
                )
            started = time.perf_counter()
            count = reader.prepare(checks, workload["sample_shape"])(hashes)
            require(count == len(checks), "Incomplete output validation")
            events.emit(
                "validation",
                status="passed",
                seconds=time.perf_counter() - started,
                checked_samples=count,
                unique_starts=len({tuple(row) for row in checks}),
                source_plane_ids=sorted({row[0] % 16 for row in checks}),
                checked_shards=sorted(checked_shards),
                starts=checks,
                hashes=hashes,
                output_dtype="float32",
                contiguous=True,
                logical_tail_checked=any(
                    row[0] == manifest["shape"][0] - 1 for row in checks
                ),
                output_values="Exact SHA256 comparison to float32 crops of retained uint16 source, outside timing",
            )
            events.emit(
                "settings",
                reader=reader.settings,
                storage=files.description(),
                numpy_version=version("numpy"),
                damacy_module=getattr(
                    getattr(reader, "damacy", None), "__file__", None
                ),
            )
            stage = "measurement"
            idle_before = files.idle()
            passes = []
            active = control = 0.0
            started = time.perf_counter()
            prepared = None
            if case["backend"] == "damacy":
                prepared = reader.prepare(workload["starts"], workload["sample_shape"])
            while True:
                control_started = time.perf_counter()
                warmup = None
                if case["backend"] == "tensorstore":
                    prepared = None
                    warmup = reset_tensorstore(reader, layout, readers)
                    prepared = reader.prepare(
                        workload["starts"], workload["sample_shape"]
                    )
                residency = files.evict()
                require(not any(residency), "Client shard pages remain resident")
                control_elapsed = time.perf_counter() - control_started
                control += control_elapsed
                events.emit(
                    "cache",
                    pass_index=len(passes),
                    resident_pages_before=residency,
                    eviction_attempts=files.last_eviction_attempts,
                    eviction_stable_seconds=0.02,
                    index_warmup=warmup,
                    control_seconds=control_elapsed,
                )
                reader.stats_reset()
                before = files.snapshot()
                pass_started = time.perf_counter()
                prepared({})
                elapsed = time.perf_counter() - pass_started
                after = files.snapshot()
                stats = reader.stats()
                counters = audit_counters(
                    case["backend"],
                    stats,
                    workload["useful_source_bytes_per_pass"],
                    reference,
                )
                delta = storage.interval(before, after)
                require(
                    delta["nfs"]["payload_read_bytes"] > 0,
                    "No NFS payload reads observed after client eviction",
                )
                row = events.emit(
                    "pass",
                    status="completed",
                    pass_index=len(passes),
                    active_seconds=elapsed,
                    control_seconds=control_elapsed,
                    counters=counters,
                    reader_stats=stats,
                    storage_delta=delta,
                    storage_before=before,
                    storage_after=after,
                )
                passes.append(row)
                active += elapsed
                if (
                    active >= settings["min_active_seconds"]
                    and len(passes) * workload["useful_source_bytes_per_pass"]
                    >= settings["min_useful_bytes"]
                ):
                    break
            wall = time.perf_counter() - started
            idle_after = files.idle()
            useful = len(passes) * workload["useful_source_bytes_per_pass"]
            decoded = (
                sum(row["counters"]["decoded_bytes"] for row in passes)
                if case["backend"] == "damacy"
                else None
            )
            result = events.emit(
                "result",
                status="accepted",
                provisional_until_successful_process_exit=True,
                policy_id=manifest["policy_id"],
                policy=settings,
                trace_sha256=workload["trace_sha256"],
                passes=len(passes),
                active_seconds=active,
                measurement_wall_seconds=wall,
                cache_control_seconds=control,
                useful_source_bytes=useful,
                output_float32_bytes=2 * useful,
                useful_source_gib_per_second=useful / active / GIB,
                output_float32_gib_per_second=2 * useful / active / GIB,
                decoded_bytes=decoded,
                decoded_amplification=decoded / useful if decoded is not None else None,
                reader_bytes=sum(row["counters"]["reader_bytes"] for row in passes),
                nfs_payload_read_bytes_shared=sum(
                    row["storage_delta"]["nfs"]["payload_read_bytes"] for row in passes
                ),
                nfs_counter_scope="Shared client mount, may include other processes; not server disk bytes",
                server_cache="Uncontrolled; zero client residency does not imply cold server storage",
                cache_mode="Per-file client eviction before every pass; no global cache drops",
                idle_before=idle_before,
                idle_after=idle_after,
                resident_pages_after=files.residency(),
                complete_logical_scan=workload["complete_logical_scan"],
                geometric_reference=reference,
                geometry_matches_all_observed_decode_passes=all(
                    row["counters"]["decoded_matches_batch_unique_chunk_capacity"]
                    for row in passes
                )
                if decoded is not None
                else None,
                reader_settings=reader.settings,
                peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                measurement_peak_rss_available=False,
            )
            write_json(config["result_path"], result)
        return 0
    except BaseException as error:
        events.emit(
            "error",
            status="failed",
            stage=stage,
            error_type=type(error).__name__,
            message=str(error),
            traceback=traceback.format_exc(),
        )
        return 1
    finally:
        events.close()


def make_schedule(manifest, trace, chosen_layouts, chosen_backends):
    rng = random.Random(manifest["settings"]["seed"] + 1)
    combinations = list(itertools.product(chosen_layouts, trace["workloads"]))
    schedule = []
    for repeat in range(manifest["settings"]["repeats"]):
        ordered = list(combinations)
        rng.shuffle(ordered)
        for position, (layout, workload) in enumerate(ordered):
            backends = list(chosen_backends)
            if (repeat + position) % 2:
                backends.reverse()
            for backend in backends:
                schedule.append(
                    {
                        "case_id": f"r{repeat + 1}-{layout}-{workload}-{backend}",
                        "phase": manifest["phase"],
                        "repeat": repeat + 1,
                        "order": len(schedule),
                        "layout_id": layout,
                        "workload": workload,
                        "backend": backend,
                    }
                )
    return schedule


def collect_events(path, destination):
    rows, invalid = [], []
    if path.exists():
        for number, line in enumerate(path.read_text().splitlines(), 1):
            try:
                row = json.loads(line)
                rows.append(row)
                destination.stream.write(json.dumps(row, sort_keys=True) + "\n")
            except json.JSONDecodeError:
                invalid.append({"line": number, "text": line[:1000]})
    return rows, invalid


def stop_process(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)


def run_supervisor(args):
    compute_node_required()
    require(args.deadline_seconds > 0, "A positive overall deadline is required")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    events = Events(output / "records.jsonl")
    terminals, schedule = [], []
    began = time.monotonic()
    deadline = began + args.deadline_seconds
    try:
        raw = read_json(args.manifest)
        manifest = normalize_manifest(raw, args.manifest, args.preflight)
        trace = make_trace(manifest)
        trace_path = output / "trace.json"
        write_json(trace_path, trace)
        layout_ids = args.layout or [row["id"] for row in manifest["layouts"]]
        require(
            set(layout_ids) <= {row["id"] for row in manifest["layouts"]},
            "Unknown requested layout",
        )
        backends = args.backend or list(BACKENDS)
        require(
            len(set(layout_ids)) == len(layout_ids)
            and len(set(backends)) == len(backends),
            "Duplicate requested case selection",
        )
        schedule = make_schedule(manifest, trace, layout_ids, backends)
        write_json(output / "schedule.json", schedule)
        run = {
            "schema_version": 1,
            "started_utc": utc_now(),
            "manifest": manifest,
            "original_manifest": raw,
            "manifest_path": str(Path(args.manifest).resolve()),
            "source_path": str(Path(args.source).resolve()),
            "script_path": str(Path(__file__).resolve()),
            "script_sha256": file_hash(__file__),
            "trace_sha256": json_hash(trace),
            "machine": machine(),
            "argv": sys.argv,
            "deadline_seconds": args.deadline_seconds,
            "helper_sha256": {
                name: file_hash(Path(manifest["helpers_dir"]) / name)
                for name in HELPERS
            },
            "timing": "Active reads and host output assembly only; source loading, validation, planning of Python selections, index warming and client eviction excluded",
            "units": "Useful bytes are uint16 logical selections; contiguous host float32 output has twice as many bytes; GiB=2^30",
            "schedule_policy": "Three shuffled rounds, adjacent backend pairs with alternating order; incomplete and failed cases remain in the schedule",
            "decoded_cache": "None; fresh process per observation and fresh TensorStore pools per pass",
            "accepted_observation": "A worker result is usable only when its case_finished record has status=accepted and the process exited successfully",
        }
        write_json(output / "run.json", run)
        events.emit(
            "run_started",
            phase=manifest["phase"],
            planned_observations=len(schedule),
            policy_id=manifest["policy_id"],
        )
        layouts = {}
        invalid_layouts = {}
        for layout in manifest["layouts"]:
            if layout["id"] not in layout_ids:
                continue
            try:
                layouts[layout["id"]] = inspect_layout(layout, manifest["shape"])
            except Exception as error:
                invalid_layouts[layout["id"]] = str(error)
                events.emit(
                    "layout_error",
                    status="failed",
                    layout_id=layout["id"],
                    message=str(error),
                )
        write_json(output / "layouts.json", layouts)
        require(
            Path(args.source).stat().st_size == math.prod(SOURCE_SHAPE) * 2,
            "Unexpected raw source length",
        )
        require(file_hash(args.source) == SOURCE_SHA256, "Source hash differs")
        for case in schedule:
            if case["layout_id"] in invalid_layouts:
                terminals.append(
                    events.emit(
                        "case_finished",
                        **case,
                        status="invalid_layout",
                        message=invalid_layouts[case["layout_id"]],
                    )
                )
                continue
            remaining = deadline - time.monotonic()
            if remaining < manifest["settings"]["min_active_seconds"] + 10:
                terminals.append(
                    events.emit(
                        "case_finished",
                        **case,
                        status="not_run_deadline",
                        remaining_seconds=remaining,
                    )
                )
                continue
            directory = output / "cases" / case["case_id"]
            directory.mkdir(parents=True)
            case_path = directory / "case.json"
            raw_path = directory / "records.jsonl"
            result_path = directory / "result.json"
            config = {
                "case": case,
                "manifest": manifest,
                "layout": layouts[case["layout_id"]],
                "trace_path": str(trace_path),
                "trace_sha256": json_hash(trace),
                "source": str(Path(args.source).resolve()),
                "events_path": str(raw_path),
                "result_path": str(result_path),
            }
            write_json(case_path, config)
            timeout = min(manifest["settings"]["case_timeout_seconds"], remaining - 5)
            events.emit(
                "case_started",
                **case,
                timeout_seconds=timeout,
                config_path=str(case_path),
            )
            started = time.monotonic()
            timed_out = False
            with (directory / "process.log").open("wb") as log:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--worker",
                        str(case_path),
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    stop_process(process)
                except BaseException:
                    stop_process(process)
                    raise
            rows, invalid_lines = collect_events(raw_path, events)
            results = [
                row
                for row in rows
                if row["event"] == "result" and row.get("status") == "accepted"
            ]
            status = (
                "timeout"
                if timed_out
                else "accepted"
                if process.returncode == 0 and len(results) == 1 and not invalid_lines
                else "failed"
            )
            terminals.append(
                events.emit(
                    "case_finished",
                    **case,
                    status=status,
                    returncode=process.returncode,
                    wall_seconds=time.monotonic() - started,
                    timeout_seconds=timeout,
                    completed_passes=sum(row["event"] == "pass" for row in rows),
                    invalid_json_lines=invalid_lines,
                    raw_records_path=str(raw_path),
                    result_path=str(result_path) if result_path.exists() else None,
                )
            )
        counts = Counter(row["status"] for row in terminals)
        summary = {
            "phase": manifest["phase"],
            "planned_observations": len(schedule),
            "status_counts": dict(counts),
            "elapsed_seconds": time.monotonic() - began,
            "complete": counts.get("accepted", 0) == len(schedule),
            "finished_utc": utc_now(),
        }
        write_json(output / "summary.json", summary)
        events.emit("run_finished", **summary)
        return 0 if summary["complete"] else 2
    except BaseException as error:
        events.emit(
            "run_error",
            status="failed",
            error_type=type(error).__name__,
            message=str(error),
            traceback=traceback.format_exc(),
        )
        finished = {row["case_id"] for row in terminals}
        for case in schedule:
            if case["case_id"] not in finished:
                events.emit(
                    "case_finished",
                    **case,
                    status="not_run_after_error",
                    message=str(error),
                )
        return 1
    finally:
        events.close()


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--manifest")
    parser.add_argument(
        "--output",
        help="Fresh output directory; existing records are never overwritten",
    )
    parser.add_argument("--source")
    parser.add_argument("--deadline-seconds", type=float, default=4000)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument(
        "--layout", action="append", help="Optional layout ID, repeatable"
    )
    parser.add_argument("--backend", choices=BACKENDS, action="append")
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return run_worker(args.worker)
    if not (args.manifest and args.output and args.source):
        parser.error("--manifest, --output and --source are required")
    return run_supervisor(args)


if __name__ == "__main__":
    raise SystemExit(main())
