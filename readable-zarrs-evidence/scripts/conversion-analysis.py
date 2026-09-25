#!/usr/bin/env python3
import argparse
import collections
import csv
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics


def packed(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def write_csv(path, rows, fields=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: packed(value) if isinstance(value, (list, dict)) else value
                             for key, value in row.items()})


class Sources:
    def __init__(self, cache=None):
        self.cached = cache is not None
        self.records = json.loads(cache.read_text())["records"] if cache else {}

    def read(self, path, kind="retained_record", required=True):
        key = str(path)
        if key not in self.records:
            if self.cached:
                raise ValueError(f"Source missing from saved collection: {key}")
            if not path.is_file():
                self.records[key] = {"source_file": key, "exists": False, "kind": kind}
            else:
                data = path.read_bytes()
                self.records[key] = {
                    "source_file": key, "exists": True, "kind": kind,
                    "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                    "mtime_ns_at_collection": path.stat().st_mtime_ns,
                    "text": data.decode("utf-8", errors="replace"),
                }
        record = self.records[key]
        if not record["exists"]:
            if required:
                raise FileNotFoundError(path)
            return None
        return record["text"]

    def document(self, path, kind="retained_record", required=True):
        text = self.read(path, kind, required)
        return json.loads(text) if text is not None else None

    def digest(self, path):
        return self.records[str(path)].get("sha256")

    def save(self, output):
        manifest = [{k: v for k, v in record.items() if k != "text"}
                    for _, record in sorted(self.records.items())]
        write_csv(output / "conversion-source-manifest.csv", manifest)
        (output / "conversion-source-records.json").write_text(json.dumps({
            "collection_date": "2026-09-25", "contains_payloads": False,
            "note": "Small text records and explicitly indexed zarr.json only. Current metadata is not a historical measurement.",
            "records": self.records,
        }, indent=2) + "\n")


def inner_and_shard(metadata):
    outer = metadata["chunk_grid"]["configuration"]["chunk_shape"]
    codec = next((c for c in metadata["codecs"] if c["name"] == "sharding_indexed"), None)
    return (codec["configuration"]["chunk_shape"], outer) if codec else (outer, None)


def histogram(values):
    counts = collections.Counter(packed(v) for v in values)
    return [{"value": json.loads(value), "arrays": count} for value, count in sorted(counts.items())]


def line_location(text, pattern):
    lines = [(i, line) for i, line in enumerate(text.splitlines(), 1) if re.search(pattern, line)]
    if len(lines) != 1:
        raise ValueError(f"Expected one record for {pattern!r}, got {len(lines)}")
    return lines[0]


def configurations(home):
    root = home / "tmp/2026-06-15-chammi-reformat"
    scenarios = home / "data/damacy/scenarios/chammi"
    entries = [
        ("mix", "cpu_job", None, 2474377),
        ("idr0017", "cpu_job", None, 2474377),
        ("idr0017-4shard", "cpu_job2", [1, 2, 1, 2, 8], 2474402),
        ("idr0017-8shard", "cpu_job2", [1, 2, 1, 1, 8], 2474402),
        ("idr0017-2shard", "cpu_job3", [1, 2, 1, 4, 8], 2474768),
        ("idr0017-16shard", "cpu_job3", [1, 2, 1, 1, 4], 2474768),
        ("idr0017-32shard", "cpu_job3", [1, 2, 1, 1, 2], 2474768),
        ("idr0017-64shard", "cpu_job3", [1, 2, 1, 1, 1], 2474768),
        ("idr0017-128shard", "cpu_job3", [1, 1, 1, 1, 1], 2474768),
    ]
    result = []
    for tag, job, shard_chunks, job_id in entries:
        dataset = "mix" if tag == "mix" else "idr0017"
        result.append({
            "family": "chammi", "config_id": f"chammi-{tag}", "tag": tag,
            "dataset": f"CHAMMI-75 {dataset}", "job_id": job_id,
            "log": root / f"{job}.log", "job_script": root / f"{job}.sh",
            "script": home / "data/damacy/scenarios/make_sharded_chammi.py",
            "before": scenarios / f"before-{dataset}.json",
            "after": scenarios / f"after-{tag}.json",
            "inner": [1, 1, 1, 256, 256], "shard_chunks": shard_chunks,
            "window": None, "expected_arrays": 512,
        })
    root = home / "tmp/2026-06-15-dynacell-reformat"
    for tag, inner in [("reformat", [1, 1, 1, 128, 128]), ("current", [1, 1, 4, 256, 256])]:
        result.append({
            "family": "dynacell", "config_id": f"dynacell-{tag}", "tag": tag,
            "dataset": "DynaCell 50 bounded origin windows", "job_id": 2476048,
            "log": root / "logs/rechunk.log", "job_script": root / "cpu_rechunk.sh",
            "script": root / "reformat_dynacell.py", "before": root / "src-dynacell.json",
            "after": root / f"cmp-{tag}.json", "inner": inner,
            "shard_chunks": [2, 1, 2, 4, 4], "window": [16, 1, 8, 512, 512],
            "expected_arrays": 50,
        })
    return result


def extract_runs(home, sources):
    runs, array_rows = [], []
    for order, config in enumerate(configurations(home), 1):
        log = sources.read(config["log"])
        sources.read(config["job_script"])
        sources.read(config["script"], "implementation_snapshot")
        before = sources.document(config["before"])["dataset"]
        after = sources.document(config["after"])["dataset"]
        if set(before["uris"]) != set(after["uris"]):
            raise ValueError(f"Source/output array set differs: {config['config_id']}")
        destination = after["store_root"]
        line, completion = line_location(log, rf"wrote \d+ (?:sharded )?arrays under {re.escape(destination)}(?:;|$)")
        written = int(re.search(r"wrote (\d+)", completion).group(1))
        if written != len(after["uris"]) or written != config["expected_arrays"]:
            raise ValueError(f"Completion count differs: {config['config_id']}")
        if config["family"] == "chammi":
            scenario_line, scenario_completion = line_location(log, rf"wrote scenario chammi/{re.escape(config['after'].name)} ")
            if "0 skipped, 0 errors" not in scenario_completion:
                raise ValueError(f"Nonzero failures need separate status: {scenario_completion}")
            record_end = scenario_line
        else:
            preceding = log.splitlines()[max(0, line - 4):line - 1]
            if not any("50/50 (0 errors)" in item for item in preceding):
                raise ValueError("Missing DynaCell completion status")
            record_end = line + 2
        run_id = f"{config['config_id']}-job{config['job_id']}"
        layouts = []
        destination_probe = Path(destination) / after["uris"][0] / "zarr.json"
        probe = sources.document(destination_probe, "current_destination_metadata", required=False)
        for uri in before["uris"]:
            source_path = Path(before["store_root"]) / uri / "zarr.json"
            metadata = sources.document(source_path, "current_source_metadata")
            full_shape = metadata["shape"]
            shape = [min(s, w) for s, w in zip(full_shape, config["window"])] if config["window"] else full_shape
            inner = [min(s, c) for s, c in zip(shape, config["inner"])]
            grid = [math.ceil(s / c) for s, c in zip(shape, inner)]
            shard = ([c * min(g, n) for c, g, n in zip(inner, grid, config["shard_chunks"])]
                     if config["shard_chunks"] else [c * g for c, g in zip(inner, grid)])
            count = math.prod(math.ceil(s / c) for s, c in zip(shape, shard))
            dtype = metadata["data_type"]
            size = {"uint8": 1, "uint16": 2, "float32": 4}[dtype]
            source_inner, source_shard = inner_and_shard(metadata)
            output_path = Path(destination) / uri / "zarr.json"
            output_metadata = (sources.document(output_path, "current_destination_metadata")
                               if config["family"] == "dynacell" else None)
            if output_metadata:
                actual_inner, actual_shard = inner_and_shard(output_metadata)
                if (actual_inner, actual_shard, output_metadata["shape"], output_metadata["data_type"]) != (inner, shard, shape, dtype):
                    raise ValueError(f"Current output metadata differs from recorded script: {output_path}")
            layout = {
                "run_id": run_id, "config_id": config["config_id"], "relative_array": uri,
                "source_metadata_file": str(source_path), "source_metadata_sha256": sources.digest(source_path),
                "source_metadata_observed_date": "2026-09-25", "source_format": metadata["zarr_format"],
                "source_array_shape": full_shape, "source_chunk_shape": source_inner,
                "source_shard_shape": source_shard, "source_dtype": dtype, "source_codecs": metadata["codecs"],
                "destination_metadata_file": str(output_path),
                "destination_metadata_sha256": sources.digest(output_path) if output_metadata else None,
                "destination_array_shape": shape, "destination_chunk_shape": inner,
                "destination_shard_shape": shard, "destination_dtype": dtype,
                "destination_layout_basis": "current_metadata_and_retained_script" if output_metadata else "retained_script_applied_to_current_source_metadata",
                "destination_codecs": output_metadata["codecs"] if output_metadata else [
                    {"name": "sharding_indexed", "chunk_shape": inner,
                     "codecs": [{"name": "bytes", "endian": "little"}, {"name": "zstd", "level": 3}],
                     "index_codecs": ["bytes_little_endian", "crc32c"], "index_location": "end"}],
                "processing_block_shape": shape, "processing_block_nominal_bytes": math.prod(shape) * size,
                "destination_chunk_capacity_bytes": math.prod(inner) * size,
                "destination_shard_capacity_bytes": math.prod(shard) * size,
                "shards_per_array_from_geometry": count,
                "numeric_byte_basis": "uncompressed_geometry_not_peak_memory_or_storage_traffic",
                "execution_source_file": str(config["log"]), "execution_source_locator": f"L{line}-L{record_end}",
            }
            array_rows.append(layout)
            layouts.append(layout)
        sizes = [item["processing_block_nominal_bytes"] for item in layouts]
        human_size = next((text.split("\t")[0] for text in log.splitlines()
                           if text.endswith("\t" + destination)), None)
        logged_histogram = None
        if "shards/array" in completion:
            logged_histogram = completion.split("shards/array ", 1)[1]
        elif config["family"] == "dynacell":
            logged_histogram = re.search(r"shards/array (\{[^}]+\})", log.splitlines()[line]).group(1)
        run = {
            "run_id": run_id, "config_id": config["config_id"], "family": config["family"],
            "record_granularity": "one_logged_configuration_batch", "source_file": str(config["log"]),
            "source_locator": f"L{line}-L{record_end}", "source_sha256": sources.digest(config["log"]),
            "script_file": str(config["script"]), "script_snapshot_sha256": sources.digest(config["script"]),
            "job_script_file": str(config["job_script"]), "source_scenario_file": str(config["before"]),
            "destination_scenario_file": str(config["after"]), "job_id": config["job_id"],
            "date": "2026-06-15", "date_basis": "job_log" if config["family"] == "dynacell" else "dated_job_directory_and_log_context",
            "execution_order_in_retained_jobs": order, "tool": "TensorStore via Python",
            "requested_tool_version": ">=0.1.84", "measured_tool_version": None, "tool_revision": None,
            "script_revision_status": "retained_script_snapshot_no_measured_revision_pin",
            "backend": "CPU", "machine": "cpu-turin-gp-l-243-191" if config["family"] == "dynacell" else None,
            "workload": "zarr_to_zarr_rechunking", "dataset": config["dataset"],
            "source_storage_path": before["store_root"], "destination_storage_path": destination,
            "source_storage_type": None, "destination_storage_type": None,
            "storage_context": "shared /mnt/main0 paths; historical filesystem/mount options not captured in conversion job",
            "recorded_mount_options": None, "recorded_nconnect": None,
            "source_format": "Zarr v3", "destination_format": "Zarr v3", "format_version_changed": False,
            "source_dtype": histogram([a["source_dtype"] for a in layouts]),
            "destination_dtype": histogram([a["destination_dtype"] for a in layouts]),
            "value_transform": "none in script; DynaCell selects origin window" if config["window"] else "none in script",
            "scope": "bounded_origin_window_per_array" if config["window"] else "complete_level_zero_array_per_worker",
            "array_count": written, "source_array_shapes": histogram([a["source_array_shape"] for a in layouts]),
            "destination_array_shapes": histogram([a["destination_array_shape"] for a in layouts]),
            "source_chunk_shapes": histogram([a["source_chunk_shape"] for a in layouts]),
            "source_shard_shapes": histogram([a["source_shard_shape"] for a in layouts]),
            "destination_chunk_shapes": histogram([a["destination_chunk_shape"] for a in layouts]),
            "destination_shard_shapes": histogram([a["destination_shard_shape"] for a in layouts]),
            "destination_layout_evidence": "current_retained_metadata_and_log" if probe else "script_and_log_outputs_absent_at_checked_paths",
            "source_layout_evidence": "explicitly_indexed_current_metadata_2026-09-25_not_historical_hashes",
            "requested_chunk_shape": config["inner"], "requested_shard_inner_chunk_counts": config["shard_chunks"],
            "requested_shard_rule": "whole_array_rounded_to_inner_grid" if config["shard_chunks"] is None else "inner_chunk_counts_clipped_to_grid",
            "shards_per_array_logged": logged_histogram,
            "shards_per_array_from_geometry": histogram([a["shards_per_array_from_geometry"] for a in layouts]),
            "destination_chunk_capacity_min_bytes": min(a["destination_chunk_capacity_bytes"] for a in layouts),
            "destination_chunk_capacity_max_bytes": max(a["destination_chunk_capacity_bytes"] for a in layouts),
            "destination_shard_capacity_min_bytes": min(a["destination_shard_capacity_bytes"] for a in layouts),
            "destination_shard_capacity_max_bytes": max(a["destination_shard_capacity_bytes"] for a in layouts),
            "capacity_byte_definition": "uncompressed geometry; never encoded/stored bytes",
            "codec": "blosc-zstd level 1 bitshuffle blocksize=0; crc32c index" if config["window"] else "zstd level 3; crc32c index",
            "traversal": "array tasks submitted in scenario URI order; futures complete out of order; each task reads then writes one full processing block",
            "processing_block_shape": config["window"] or "whole source array; see companion per-array CSV",
            "processing_block_min_nominal_bytes": min(sizes), "processing_block_max_nominal_bytes": max(sizes),
            "logical_processed_bytes_from_current_metadata": sum(sizes),
            "geometry_quantity_scope": "derived array values; not measured source traffic or memory peak",
            "workers_requested": 16, "submitted_array_tasks": written, "measured_tasks_in_flight": None,
            "measured_active_input_files": None, "measured_active_output_files": None,
            "queue_limit_bytes": None, "cache_limit_bytes": None, "configured_host_memory_budget_bytes": None,
            "configured_device_memory_budget_bytes": None, "job_memory_request_bytes": None,
            "temporary_storage": None, "intermediate_storage": None,
            "repetition": 1, "source_io_and_decode_executed": True, "source_io_and_decode_timed": None,
            "input_staging": "source read().result() materializes whole processing block before destination write().result()",
            "timing_scope": "no per-configuration conversion timer; later read benchmark timers excluded",
            "elapsed_s": None, "throughput_B_s": None, "throughput_numerator": None,
            "host_peak_bytes": None, "host_peak_method": "not_recorded", "host_peak_scope": None,
            "device_peak_bytes": None, "device_peak_method": "not_recorded_CPU_conversion",
            "pinned_host_peak_bytes": None, "component_allocation_measurements": None,
            "modeled_total_peak_bytes": None, "temporary_disk_peak_bytes": None,
            "source_bytes_read": None, "output_bytes_rewritten": None, "stored_output_bytes": None,
            "output_allocated_size_human": human_size, "output_size_method": "rounded du -sh after writes",
            "conversion_memory_budget_met": None, "status": "logged_complete",
            "errors_logged": 0, "skips_logged": 0 if config["family"] == "chammi" else None,
            "validation_status": "destination write futures completed; later reads exist; no exhaustive value-equality check found",
            "durability_scope": "write futures awaited; no explicit durable-storage measurement",
            "output_retention_check": "all indexed output metadata retained" if config["family"] == "dynacell" else "first indexed output metadata absent; output trees not scanned",
            "notes": "Scenario max_gpu_memory_mb=8192 applies to later Damacy reads, not conversion. No memory/reread/concurrency/budget sweep.",
        }
        runs.append(run)
    return runs, array_rows


def extract_phases(home, sources):
    path = home / "tmp/2026-06-15-dynacell-reformat/logs/rechunk.log"
    text = sources.read(path)
    start_line, start_text = line_location(text, "=== rechunk start")
    end_line, end_text = line_location(text, "=== rechunk done")
    start = re.search(r"\d{4}-\d\d-\d\dT\S+", start_text).group()
    end = re.search(r"\d{4}-\d\d-\d\dT\S+", end_text).group()
    elapsed = (datetime.datetime.fromisoformat(end) - datetime.datetime.fromisoformat(start)).total_seconds()
    return [{
        "phase_id": "dynacell-job2476048-both-conversions", "source_file": str(path),
        "source_locator": f"L{start_line}-L{end_line}", "source_sha256": sources.digest(path),
        "job_id": 2476048, "machine": "cpu-turin-gp-l-243-191", "start_utc": start, "end_utc": end,
        "elapsed_from_printed_markers_s": elapsed, "marker_resolution_s": 1,
        "covered_config_ids": ["dynacell-reformat", "dynacell-current"],
        "scope": "two sequential conversions, Python/uv setup, dependency installation (2.67 s logged), scenario writing and logging",
        "includes_source_read_decode": True, "per_configuration_timer": False,
        "throughput_B_s": None, "usable_for_conversion_throughput_comparison": False,
        "exclusion_reason": "combined coarse job interval; no per-layout timing boundary or storage completion policy",
    }]


def extract_coverage(home, sources):
    tmp = home / "tmp"
    cases = [
        ("missing-tiff-conversion", "coverage_gap", "TIFF-to-Zarr streaming", None,
         "No complete collection-of-TIFFs-to-Zarr timing or peak-memory experiment located in scoped search.", "no_measurement"),
        ("missing-v2-to-v3", "coverage_gap", "Zarr v2-to-v3 conversion", None,
         "Both logged conversion scripts use zarr3 sources and destinations; corpus version labels do not establish a format conversion.", "no_measurement"),
        ("replay-input-preparation", "excluded_preloaded_replay", "Chucky source-frame versus layer-buffer replay",
         tmp / "2026-09-16-writer-comparison/input-preparation-comparison/comparison.json",
         "Existing raw pixels repeat; source preparation is outside throughput timing. Process memory includes preparation but no TIFF-source decode pipeline.", "measured_process_high_water_mark_and_sampled_RSS; configured_buffers_separate"),
        ("replay-tensorstore-transactions", "excluded_preloaded_replay", "TensorStore / Chucky frame replay",
         tmp / "2026-09-16-writer-comparison/tensorstore-transactions/results/study.json",
         "Six complete records plus separate preflights. Preloaded raw pack; no TIFF/Zarr source reading during timed writes. Cache and source-copy limits do not cap transaction/process memory.", "measured_process_high_water_mark_and_250ms_samples; configured_2GiB_cache_64MiB_copy_budget"),
        ("replay-tensorstore-timeout", "excluded_incomplete_preloaded_replay", "TensorStore framewise timeout",
         tmp / "2026-09-16-writer-comparison/tensorstore-frame-input/analysis.json",
         "Record e309bbae21ae088dcfd3-r1 timed out before validation; rising sampled RSS is not eventual required peak and no completed throughput exists.", "sampled_process_RSS_and_observed_kernel_HWM_at_timeout"),
        ("opencell-tiff-to-raw", "excluded_corpus_preparation", "TIFF pages to raw replay pack",
         tmp / "2026-09-08-opencell/extract.log",
         "Source TIFF pixels are decoded into .raw packs, followed by separate replay/readback checks. Not an end-to-end TIFF-to-Zarr measurement.", "conversion_peak_not_recorded"),
        ("opencell-initial-fetch-failure", "excluded_failed_corpus_preparation", "Initial OpenCell source-layout check",
         tmp / "2026-09-08-opencell/fetch.log",
         "Initial source planning rejected a ZCYX TIFF where CZYX was expected. Later extraction records are retained separately; neither is a complete TIFF-to-Zarr performance run.", "conversion_peak_not_recorded"),
        ("bbbc022-tiff-to-raw", "excluded_corpus_preparation", "BBBC022 TIFFs to raw replay pack",
         tmp / "2026-09-13-bbbc022-pilot.qFGPCw/slurm-3671605.log",
         "Earlier 576-field raw import retained; later 16-field subset differs. Corpus preparation and later Zarr writes are separate operations.", "conversion_peak_not_recorded"),
        ("bbbc010-jump-tiff-to-raw", "excluded_corpus_preparation", "BBBC010 and JUMP-Scope TIFF-origin raw corpus additions",
         tmp / "2026-09-10-corpus-additions/license-additions.md",
         "Decoded TIFF pixels are repacked as headerless raw image assets; import metadata does not supply complete TIFF-to-Zarr timing or memory.", "conversion_peak_not_recorded"),
        ("cosem-v2-corpus-v3", "excluded_corpus_preparation", "Source Zarr v2 to raw pack",
         tmp / "2026-09-13-cosem-stack.ruflut1h/import.log",
         "COSEM dataset v2 and corpus v3 label .raw releases; source is Zarr v2, destination is raw bytes, not Zarr v3.", "conversion_peak_not_recorded"),
        ("corpus-geometry", "excluded_model", "Read-amplification geometry survey",
         tmp / "2026-06-15-corpus128/corpus/summary.json",
         "Metadata-only geometry predictions; no destination conversion process measured.", "no_process_peak"),
        ("compression-survey", "excluded_sample_recompression", "Sampled block compression",
         tmp / "2026-06-15-compression-survey/results.json",
         "Bounded source reads and sampled sub-block compression, not complete destination stores. 512 MiB per-array read cap is configured, not measured memory.", "configured_read_cap_only"),
        ("size-impact", "excluded_sample_recompression_model", "Sampled recompression plus corpus-size projection",
         tmp / "2026-06-15-size-impact/results.json",
         "Compressed-byte samples and geometry/size projection do not measure full conversion timing, memory, temporary disk peak or rewritten traffic. 256 MiB cap is configured.", "configured_read_cap_only"),
        ("external-idr0017-reference", "excluded_unrecorded_conversion", "Existing unsharded read control",
         home / "data/damacy/scenarios/chammi/ivirshup-idr0017.json",
         "Existing rechunked v3 data and read benchmark exist; actual conversion tool, execution log, time and memory not found. Date in path is not verified execution time.", "no_conversion_measurement"),
        ("chucky-memory-model", "excluded_writer_allocation_model", "Chucky memory estimate audit",
         home / ".claude/projects/-mnt-main0-home-nclack-src-chucky/memory/memory-estimate-is-accurate.md",
         "Writer estimate / observed device allocation or free-memory delta is not a complete TIFF/rechunking process peak.", "component_estimate_and_writer_measurement_not_conversion_peak"),
    ]
    result = []
    for ident, status, scope, path, reason, memory in cases:
        if path:
            text = sources.read(path)
            locator = "/records" if ident == "replay-tensorstore-transactions" else ("/samples" if ident == "replay-input-preparation" else "/record_id" if ident == "replay-tensorstore-timeout" else f"L1-L{len(text.splitlines())}")
        else:
            locator = "conversion-search-manifest.csv and targeted source manifest"
        result.append({"coverage_id": ident, "status": status, "scope": scope,
                       "source_file": str(path) if path else None, "source_locator": locator,
                       "source_sha256": sources.digest(path) if path else None,
                       "included_in_conversion_runs": False, "reason": reason,
                       "memory_evidence_kind": memory,
                       "raw_or_summary": "raw_run_records" if ident == "replay-tensorstore-transactions" else "summary_with_raw_links" if ident.startswith("replay-") else "log_or_definition" if path else "scoped_search_gap"})
    references = [
        "src/chucky/scripts/writers/README.md",
        "tmp/2026-09-16-writer-comparison/tensorstore-transactions/RESULTS.md",
        "tmp/2026-09-16-writer-comparison/tensorstore-transactions/storage-preflight.json",
        "tmp/2026-09-16-writer-comparison/tensorstore-frame-input/RESULTS.md",
        "tmp/2026-09-16-writer-comparison/input-preparation-comparison/summary.md",
        "tmp/2026-09-08-opencell/extract.sh", "tmp/2026-09-08-opencell/store.sh",
        "tmp/2026-09-08-opencell/store.log", "tmp/2026-09-13-bbbc022-pilot.qFGPCw/import.sh",
        "data/chucky-benchmarks-data/scripts/import_bbbc022.py",
        "tmp/2026-09-07-chucky-microscopy-pr/worktree/scripts/datasets/extract.py",
        "tmp/2026-09-13-cosem-stack.ruflut1h/import_cosem.py",
        "tmp/2026-09-13-microscopy-v3-rc1.gbqip5w3/notes.md",
        "tmp/2026-06-15-compression-survey/survey.py", "tmp/2026-06-15-size-impact/size_impact.py",
        ".claude/projects/-mnt-main0-home-nclack-src-damacy/memory/chammi-reformat-test.md",
        ".claude/projects/-mnt-main0-home-nclack-src-damacy/memory/corpus-survey.md",
        ".claude/projects/-mnt-main0-home-nclack-src-damacy/memory/katamari-real-crop.md",
        ".claude/projects/-mnt-main0-home-nclack-src-acquire-zarr/memory/MEMORY.md",
    ]
    for path in references:
        sources.read(home / path, "scope_or_implementation_reference")
    reference = sources.document(home / "data/damacy/scenarios/chammi/ivirshup-idr0017.json")["dataset"]
    sources.document(Path(reference["store_root"]) / reference["uris"][0] / "zarr.json", "current_reference_metadata", required=False)
    return result


def scan_job_metadata(home, output):
    root = home / "tmp"
    patterns = {
        "conversion": re.compile(r"(?:tiff.{0,24}zarr|tif.{0,24}zarr|zarr.{0,24}tiff|rechunk|reformat|bioformats2raw|bf2raw|v2.{0,8}to.{0,8}v3)", re.I),
        "tiff": re.compile(r"(?:tiff|\.tif\b|bioformats)", re.I),
    }
    suffixes = {".py", ".sh", ".md", ".txt", ".log"}
    skipped = {"build", "build-cpu", "build-release", "build-gpu", "source", "sources", "src", "store", "stores", "data", "datasets", "payloads", "assets", ".git", ".venv", "venv", "node_modules", "public-download"}
    manifest, matches = [], []
    for job in sorted(root.iterdir()):
        if not job.is_dir() or job.is_symlink():
            continue
        for base, directories, names in os.walk(job, followlinks=False):
            depth = len(Path(base).relative_to(job).parts)
            directories[:] = [d for d in directories if depth < 1 and d not in skipped and ".zarr" not in d and not d.startswith("build")]
            for name in sorted(names):
                path = Path(base) / name
                if path.suffix not in suffixes or path.is_symlink() or path.stat().st_size > 1000000:
                    continue
                data = path.read_bytes()
                lines = data.decode("utf-8", errors="replace").splitlines()
                count = 0
                for kind, pattern in patterns.items():
                    found = [(i, line) for i, line in enumerate(lines, 1) if pattern.search(line)]
                    count += len(found)
                    for line, value in found:
                        matches.append({"source_file": str(path), "source_locator": f"L{line}", "search": kind, "text": value[:500]})
                manifest.append({"source_file": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "matched_lines": count, "search_scope": "job_root_plus_one_subdirectory_text_only"})
    write_csv(output / "conversion-search-manifest.csv", manifest)
    write_csv(output / "conversion-search-matches.csv", matches)
    (output / "conversion-search-scope.json").write_text(json.dumps({
        "root": str(root), "maximum_directory_depth_below_job": 1,
        "maximum_bytes_per_file": 1000000, "suffixes": sorted(suffixes),
        "skipped_directory_names": sorted(skipped), "skipped_directory_patterns": ["*.zarr*", "build*"],
        "symlinks_followed": False, "payloads_read": False,
        "patterns": {name: pattern.pattern for name, pattern in patterns.items()},
        "files_examined": len(manifest), "bytes_examined": sum(row["bytes"] for row in manifest),
        "additional_targeted_sources": "conversion-source-manifest.csv",
    }, indent=2) + "\n")


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def number(value):
    return float(value) if value not in (None, "", "null") else None


def summarize(output):
    runs = read_csv(output / "conversion-runs.csv")
    groups = collections.defaultdict(list)
    for row in runs:
        groups[row["config_id"]].append(row)
    summary = []
    for config, rows in groups.items():
        first = rows[0]
        record = {"config_id": config, "family": first["family"], "dataset": first["dataset"],
                  "tool": first["tool"], "machine": first["machine"] or None,
                  "recorded_attempts": len(rows), "logged_complete_attempts": sum(row["status"] == "logged_complete" for row in rows),
                  "source_run_ids": [row["run_id"] for row in rows],
                  "source_file": "conversion-runs.csv", "source_locator": f"config_id={config}",
                  "raw_source_files": sorted({row["source_file"] for row in rows}),
                  "workers_requested": int(first["workers_requested"]),
                  "requested_chunk_shape": first["requested_chunk_shape"],
                  "destination_chunk_capacity_min_bytes": int(first["destination_chunk_capacity_min_bytes"]),
                  "destination_chunk_capacity_max_bytes": int(first["destination_chunk_capacity_max_bytes"]),
                  "comparison_limit": "one execution per configuration; fixed workers; geometry changes; no complete per-run conversion time or measured peak",
                  "memory_budget_met": None}
        for field in ("elapsed_s", "throughput_B_s", "host_peak_bytes", "device_peak_bytes", "pinned_host_peak_bytes"):
            values = [number(row[field]) for row in rows if number(row[field]) is not None]
            record[field + "_measured_n"] = len(values)
            record[field + "_median"] = statistics.median(values) if values else None
            record[field + "_min"] = min(values) if values else None
            record[field + "_max"] = max(values) if values else None
        summary.append(record)
    write_csv(output / "conversion-summary.csv", summary)
    plot = [{"run_id": row["run_id"], "config_id": row["config_id"], "family": row["family"],
             "machine": row["machine"] or None, "workers_requested": int(row["workers_requested"]),
             "host_peak_bytes": number(row["host_peak_bytes"]), "device_peak_bytes": number(row["device_peak_bytes"]),
             "elapsed_s": number(row["elapsed_s"]), "throughput_B_s": number(row["throughput_B_s"]),
             "chunk_capacity_min_bytes": int(row["destination_chunk_capacity_min_bytes"]),
             "chunk_capacity_max_bytes": int(row["destination_chunk_capacity_max_bytes"]),
             "shard_capacity_min_bytes": int(row["destination_shard_capacity_min_bytes"]),
             "shard_capacity_max_bytes": int(row["destination_shard_capacity_max_bytes"]),
             "geometry_is_modeled": True, "status": row["status"], "plot_eligible_memory_throughput": False,
             "missing_reason": "per-conversion timing and measured peak memory absent; do not plot null as zero",
             "source_file": row["source_file"], "source_locator": row["source_locator"],
             "derived_source_file": "conversion-runs.csv", "derived_source_locator": f"run_id={row['run_id']}"}
            for row in runs]
    write_csv(output / "conversion-plot-data.csv", plot)
    n_arrays = sum(int(row["array_count"]) for row in runs)
    phases = read_csv(output / "conversion-phase-timings.csv")
    lines = [
        "# Conversion findings", "",
        f"The archive contains **{len(runs)} logged Zarr v3-to-v3 conversion executions** across CHAMMI and DynaCell ({n_arrays:,} array-copy completions, including repeated copies of the same inputs). All report completion without errors. **None has measured conversion peak memory or a per-configuration conversion timer.** No complete TIFF-to-Zarr or Zarr v2-to-v3 performance run was found in the scoped search. These gaps prevent a memory-versus-throughput ranking or a statement that any setting meets a measured memory budget.", "",
        "| Family | Actual conversion scope | Retained measurement | Limit |",
        "| --- | --- | --- | --- |",
        "| CHAMMI | TensorStore CPU, 16 array workers; nine configurations of 512 complete level-0 arrays; v3 to v3, 256² target chunks clipped at small array edges; idr0017 shard counts 1–128 | Per-configuration completion/error counts and rounded allocated output size | No configuration timer, peak memory, conversion machine hostname or historical mount record; first recorded output metadata absent at all nine checked paths |",
        "| DynaCell | TensorStore CPU, 16 workers; two copies of 50 `[16,1,8,512,512]` float32 origin windows; v3 to v3 | Complete counts; both sets of indexed output metadata retained; one combined job interval | Copies are bounded windows, not full source arrays; no per-layout timing or peak memory |", "",
        f"The DynaCell log's printed markers span {phases[0]['elapsed_from_printed_markers_s']} seconds on `cpu-turin-gp-l-243-191`, covering **both** conversions, imports/package setup (including a logged 2.67-second installation), scenario output and logging. Its one-second timestamp resolution and mixed scope are retained in `conversion-phase-timings.csv`; no per-layout throughput is calculated from this interval. Damacy `results-current.json`, `results-reformat.json` and CHAMMI GPU logs measure later read workloads and are excluded from conversion timing.", "",
        "Both scripts materialize a source array/window with `read().result()` before `write(data).result()` within each worker. This establishes source I/O/decoding execution and a per-worker input block, not a memory peak. DynaCell's processing block has 128 MiB of nominal float32 data; sixteen workers can overlap, but TensorStore allocations, caches, codec output, object lifetimes and actual overlap were not measured. Do not multiply worker peaks or assume entire output shards are buffered. Neither script changes workers, cache limits, processing-block size or memory budgets across matched memory measurements.", "",
        "DynaCell's destination read chunks are `[1,1,1,128,128]` (64 KiB) versus `[1,1,4,256,256]` (1 MiB); destination shards are `[2,1,2,512,512]` (4 MiB, 32 per array) versus `[2,1,8,512,512]` (16 MiB, 8 per array). These are uncompressed capacities. CHAMMI's heterogeneous shapes and edge clipping are preserved per array. Geometry computed from current source metadata is explicitly labeled: it is not a historical measured byte counter. Source/destination shape, dtype, codec and shard records are in `conversion-array-layouts.csv`; current metadata hashes cannot establish unchanged historical source content.", "",
        "The whole-array CHAMMI write and window DynaCell write let TensorStore choose internal chunk scheduling. No source-reread counters, rewritten-output counters, internal retained-buffer measurements or temporary-disk peaks exist in the located records. Input tasks are submitted in scenario order and complete out of order; active input/output file counts were not measured. Rounded `du -sh` values describe allocated blocks and are retained as text; they cannot stand in for exact final stored bytes. Awaited write futures do not independently establish physical-media durability.", "",
        "The embedded Damacy `max_gpu_memory_mb=8192` settings govern later GPU readers and are not budgets for these CPU converters. No host, device or pinned-host conversion peak was located. No input-scale memory sweep exists, so dataset-size-independent conversion memory is untested. A change in chunk or shard layout has read evidence elsewhere in this bundle, but the present records do not measure its memory cost to produce.", "",
        "The useful near misses remain separate in `conversion-coverage.csv`: OpenCell and BBBC022 TIFF importers produce raw pixel packs; the later Chucky/TensorStore studies replay preloaded packs with source preparation outside writer timing. Those studies retain real process RSS/high-water marks, 250 ms samples and a TensorStore timeout, but they are not complete TIFF conversion measurements. COSEM 'dataset v2 / corpus v3' labels a raw-pack release; its Zarr v2 source is not transformed into Zarr v3. June recompression surveys measure sampled encoded blocks and model whole-corpus size; their read caps are configured limits, not observed peaks.", "",
        "Historical NFS `nconnect=16` is explicitly retained in September writer preflights, including the TensorStore transaction study. It is not retroactively applied to June conversions. CHAMMI's later shard-count read sweep belongs to the read/concurrency analysis, and shard counts per array are not measured simultaneous file activity or acquisition append-layer concurrency.", "",
        "`conversion-summary.csv` summarizes each recorded configuration without manufacturing repetitions. `conversion-plot-data.csv` preserves all 11 attempts with null memory and throughput plus a false plotting-eligibility flag; an empty measurement is never zero. The source cache contains text scripts/logs/scenarios and indexed `zarr.json` metadata only. No image, chunk, TIFF or raw-pixel payload was read or copied, and no new conversion/benchmark was run.", "",
        "Reproduce summaries on a copied bundle with `python3 scripts/conversion-analysis.py --output . --summarize-only`. Rebuild the extracts without cluster access with `python3 scripts/conversion-analysis.py --output . --from-cache conversion-source-records.json`. The original collection used `--scan-metadata`; its exact file list/hashes, matched lines and search depth/exclusions are in `conversion-search-manifest.csv`, `conversion-search-matches.csv` and `conversion-search-scope.json`. Targeted references and missing paths appear in `conversion-source-manifest.csv`. The scoped search does not claim to cover arbitrary remote histories or every payload tree.", "",
        "The smallest follow-up for the unresolved conversion-memory claim is one instrumented repeat of the existing DynaCell window conversion, preserving data, layout, workers, machine and destination: time source open/read/decode through final write completion and collect the complete process/job host-memory high-water mark, with the storage completion boundary stated. This would attach an actual memory requirement and throughput to an already demonstrated layout. It is a proposed experiment only; it was not run here.", "",
    ]
    (output / "conversion-findings.md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-home", type=Path, default=Path("/mnt/main0/home/nclack"))
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--from-cache", type=Path)
    parser.add_argument("--summarize-only", action="store_true")
    parser.add_argument("--scan-metadata", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.summarize_only:
        sources = Sources(args.from_cache)
        runs, arrays = extract_runs(args.source_home, sources)
        if len(runs) != 11 or len(arrays) != 4708:
            raise ValueError("Unexpected conversion record count")
        write_csv(args.output / "conversion-runs.csv", runs)
        write_csv(args.output / "conversion-array-layouts.csv", arrays)
        write_csv(args.output / "conversion-phase-timings.csv", extract_phases(args.source_home, sources))
        write_csv(args.output / "conversion-coverage.csv", extract_coverage(args.source_home, sources))
        sources.save(args.output)
        if args.scan_metadata:
            if args.from_cache:
                raise ValueError("Metadata scan requires original filesystem; omit when using cache")
            scan_job_metadata(args.source_home, args.output)
    summarize(args.output)
    print(f"Conversion exports written to {args.output}")


if __name__ == "__main__":
    main()
