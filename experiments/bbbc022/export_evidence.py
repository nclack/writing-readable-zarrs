"""Export BBBC022 records without opening the source pack or stored arrays."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import tarfile


GIB = 1 << 30
FRAME_BYTES = 520 * 696 * 2
WORKLOADS = ("translated-256", "aligned-512", "translated-512", "full-scan")
BACKENDS = ("damacy", "tensorstore")
EXTENSION_EXPERIMENT = "shard-count-extension"
EXTENSION_MINIMUM_BYTES = 96 * GIB
SPEC_URL = (
    "https://zarr-specs.readthedocs.io/en/latest/v3/data-types/"
    "index.html#permitted-fill-values"
)
TEXT_SUFFIXES = {
    ".json", ".jsonl", ".log", ".txt", ".md", ".py", ".sh", ".patch",
    ".sha256", ".xml", ".toml", ".lock", ".yaml", ".yml", ".csv",
}
SKIP_DIRECTORIES = {
    "data", "store", "stores", "arrays", "images", "c", "build", "native",
    ".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    "environment", ".venv", ".pixi", "regenerated",
}
WRITE_METRICS = (
    "logical_gibs", "elapsed_s", "append_s", "drain_s", "drain_fraction",
    "logical_bytes", "submitted_bytes", "metered_output_bytes",
    "final_file_bytes", "allocated_file_bytes", "padding_ratio",
    "metered_bytes_per_logical_byte", "final_bytes_per_logical_byte",
    "allocated_bytes_per_logical_byte", "init_s", "separate_warmup_s",
    "memory_host_peak_bytes", "memory_device_used_bytes", "peak_pending_mib",
)
READ_METRICS = (
    "useful_source_gib_per_second", "output_float32_gib_per_second",
    "active_seconds", "measurement_wall_seconds", "cache_control_seconds",
    "useful_source_bytes", "output_float32_bytes", "reader_bytes",
    "decoded_bytes", "decoded_amplification", "passes", "peak_rss_kib",
    "nfs_payload_read_bytes_shared",
)


def require(value, message):
    if not value:
        raise ValueError(message)


def json_text(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def identity(value):
    return hashlib.sha256(json_text(value).encode()).hexdigest()


def write_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def ratio(numerator, denominator):
    if finite(numerator) and finite(denominator) and denominator > 0:
        return numerator / denominator
    return None


def number(value, digits=3):
    return f"{value:.{digits}f}" if finite(value) else "unavailable"


def cell(value):
    if value is None:
        return ""
    if isinstance(value, (list, dict, tuple)):
        return json_text(value)
    if isinstance(value, bool):
        return str(value).lower()
    return value


def write_csv(path, rows, fields=()):
    columns = list(dict.fromkeys([*fields, *(key for row in rows for key in row)]))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns or ["status"])
        writer.writeheader()
        writer.writerows({key: cell(value) for key, value in row.items()} for row in rows)


def compress_file(source, destination):
    digest = hashlib.sha256()
    size = 0
    with destination.open("wb") as out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0, compresslevel=9) as zipped:
            if source is not None and source.is_file():
                with source.open("rb") as stream:
                    for block in iter(lambda: stream.read(1 << 20), b""):
                        zipped.write(block)
                        digest.update(block)
                        size += len(block)
    return {
        "source": str(source) if source is not None else None,
        "source_exists": source is not None and source.is_file(),
        "uncompressed_bytes": size,
        "uncompressed_sha256": digest.hexdigest(),
        "compressed_bytes": destination.stat().st_size,
        "compressed_sha256": sha256(destination),
    }


def artifact_candidates(root, reads, selected):
    found = {}
    skipped = []

    def add(path, name):
        if path.is_symlink() or not path.is_file():
            return
        if path.suffix not in TEXT_SUFFIXES or path.name.startswith(".coverage"):
            return
        size = path.stat().st_size
        if size > 32 * GIB // 1024:
            skipped.append({"source": str(path), "bytes": size, "reason": "text_artifact_over_32_MiB"})
            return
        found.setdefault(name, path)

    for path in root.iterdir():
        if path.is_file():
            add(path, "root/" + path.name)
    for folder in (root / "sources", root / "logs"):
        if folder.is_dir():
            for path in folder.iterdir():
                if path.is_file():
                    add(path, "root/" + path.relative_to(root).as_posix())
    jobs = root / "jobs"
    if jobs.is_dir():
        for directory, children, files in os.walk(jobs, followlinks=False):
            directory = Path(directory)
            depth = len(directory.relative_to(jobs).parts)
            children[:] = sorted(
                name for name in children
                if name not in SKIP_DIRECTORIES
                and not (directory / name).is_symlink()
                and depth < 6
                and not (directory / name).resolve().is_relative_to(reads)
            )
            for name in sorted(files):
                path = directory / name
                if path == selected:
                    continue
                add(path, "root/" + path.relative_to(root).as_posix())
            metadata = directory / "store/images/zarr.json"
            if metadata.is_file():
                add(metadata, "root/" + metadata.relative_to(root).as_posix())
    if reads.is_dir():
        for path in reads.iterdir():
            if path.is_file() and path.name != "records.jsonl":
                add(path, "reads/" + path.name)
        cases = reads / "cases"
        if cases.is_dir():
            for directory in sorted(cases.iterdir()):
                if directory.is_dir() and not directory.is_symlink():
                    for name in ("case.json", "process.log"):
                        add(directory / name, f"reads/cases/{directory.name}/{name}")
    for name in ("write_benchmark.py", "read_benchmark.py", "run_gpu.sh", "run_cpu_build.sh",
                 "plan.json", "writer.patch", "export_evidence.py"):
        add(Path(__file__).resolve().parent / name, "export-time-scripts/" + name)
    return found, skipped


def make_bundle(root, reads, output):
    require(root.is_dir(), f"Study root is missing: {root}")
    require(reads.is_dir(), f"Reader output directory is missing: {reads}")
    require(output != root and not output.is_relative_to(root / "data"),
            "Evidence output must not replace the study or its arrays")
    raw = output / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    marker = root / "writes-complete.txt"
    attempt = None
    if marker.is_file():
        attempt = Path(marker.read_text().strip())
        attempt = attempt if attempt.is_absolute() else root / attempt
        attempt = attempt.resolve()
        require(attempt.is_relative_to(root / "jobs"), "Writer completion points outside root/jobs")
    selected = attempt / "measurements/observations.jsonl" if attempt else None
    streams = {
        "writer-observations.jsonl.gz": compress_file(selected, raw / "writer-observations.jsonl.gz"),
        "reader-records.jsonl.gz": compress_file(reads / "records.jsonl", raw / "reader-records.jsonl.gz"),
    }
    candidates, skipped = artifact_candidates(root, reads, selected)
    artifacts = []
    with (raw / "provenance.tar.gz").open("wb") as out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0, compresslevel=9) as zipped:
            with tarfile.open(fileobj=zipped, mode="w|", format=tarfile.PAX_FORMAT) as archive:
                for name, path in sorted(candidates.items()):
                    data = path.read_bytes()
                    item = tarfile.TarInfo(name)
                    item.size = len(data)
                    item.mtime = 0
                    item.mode = 0o644
                    archive.addfile(item, io.BytesIO(data))
                    artifacts.append({
                        "path": name, "source": str(path), "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    })
    bundle = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "study_root": str(root), "reader_output": str(reads),
        "writer_attempt": str(attempt) if attempt else None,
        "writer_attempt_relative": attempt.relative_to(root).as_posix() if attempt else None,
        "writer_completion_marker_present": marker.is_file(),
        "streams": streams,
        "provenance_archive_sha256": sha256(raw / "provenance.tar.gz"),
        "artifacts": artifacts, "omitted_text_artifacts": skipped,
        "external_data": "Pixel stores, the source raw pack and compiled binaries are not bundled.",
    }
    write_json(output / "bundle.json", bundle)
    return bundle


class Evidence:
    def __init__(self, directory):
        self.directory = directory
        self.bundle = json.loads((directory / "bundle.json").read_text())
        self.artifacts = {}
        archive_path = directory / "raw/provenance.tar.gz"
        require(sha256(archive_path) == self.bundle["provenance_archive_sha256"],
                "Provenance archive hash differs")
        expected = {row["path"]: row for row in self.bundle["artifacts"]}
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive:
                require(member.isfile() and member.name in expected, "Unexpected provenance member")
                data = archive.extractfile(member).read()
                require(hashlib.sha256(data).hexdigest() == expected[member.name]["sha256"],
                        f"Provenance member hash differs: {member.name}")
                self.artifacts[member.name] = data
        require(set(self.artifacts) == set(expected), "Provenance member missing")
        self.problems = []
        self.plan = self.json("root/plan.json", {})
        self.read_run = self.json("reads/run.json", {})
        attempt = self.bundle.get("writer_attempt_relative")
        self.write_prefix = "root/" + attempt + "/measurements/" if attempt else None
        self.extension = self.json(self.write_prefix + "extension-decision.json", {}) if attempt else {}
        self.write_complete = self.json(self.write_prefix + "complete.json", {}) if attempt else {}
        for name, record in self.bundle["streams"].items():
            require(sha256(directory / "raw" / name) == record["compressed_sha256"],
                    f"Raw record hash differs: {name}")
            if not record["source_exists"]:
                self.problems.append(f"Missing source record stream: {name}")

    def json(self, name, default=None):
        return json.loads(self.artifacts[name]) if name in self.artifacts else default

    def events(self, name):
        with gzip.open(self.directory / "raw" / name, "rt") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    require(isinstance(row, dict), "Event is not an object")
                    yield line_number, row
                except (ValueError, TypeError) as error:
                    self.problems.append(f"{name}:{line_number}: {error}")


def writer_rows(evidence, events=None, locator="raw/writer-observations.jsonl.gz"):
    rows = []
    counts = Counter()
    if events is None:
        events = evidence.events("writer-observations.jsonl.gz")
    for line, record in events:
        case = record.get("case", {})
        native = record.get("native", {})
        measured = native.get("measurement", {})
        metrics = record.get("metrics", {})
        check = record.get("store_check", {})
        shape = check.get("shape")
        chunk = case.get("chunk_shape", [])
        shard = case.get("shard_shape", [])
        logical = metrics.get("logical_bytes", measured.get("logical_input_bytes"))
        padded = metrics.get("submitted_bytes", measured.get("input_bytes"))
        output = metrics.get("metered_output_bytes", measured.get("output_bytes"))
        elapsed = metrics.get("elapsed_s", measured.get("elapsed_s"))
        exclusions = []
        if record.get("status") != "pass" or record.get("returncode") != 0:
            exclusions.append("writer_process_or_validation_failed")
        if record.get("scope") != "measurement":
            exclusions.append("correctness_or_unknown_scope")
        if native.get("status") != "pass" or measured.get("coverage_status") != "sufficient":
            exclusions.append("native_measurement_not_qualified")
        if not finite(logical) or logical <= 0 or not finite(elapsed) or elapsed <= 0:
            exclusions.append("missing_or_invalid_denominator")
        rate = ratio(logical, elapsed)
        rate = rate / GIB if rate is not None else None
        if finite(rate) and finite(metrics.get("logical_gibs")):
            if not math.isclose(rate, metrics["logical_gibs"], rel_tol=1e-9, abs_tol=1e-12):
                exclusions.append("rate_denominator_mismatch")
        if case.get("experiment") == "shared-layouts" and shape:
            if math.prod(shape) * 2 != logical:
                exclusions.append("stored_logical_shape_mismatch")
        if len(chunk) == 3 and finite(logical) and finite(padded):
            padded_frame = 2 * math.prod(math.ceil(n / c) * c for n, c in zip((520, 696), chunk[1:]))
            if padded * FRAME_BYTES != logical * padded_frame:
                exclusions.append("padding_denominator_mismatch")
        accepted = not exclusions
        row = {
            "id": record.get("id"), "raw_line": line,
            "source_locator": f"{locator}#line={line}",
            "status": record.get("status"), "returncode": record.get("returncode"),
            "scope": record.get("scope"), "role": record.get("role"),
            "accepted": accepted,
            "primary": accepted and record.get("role") == "sample",
            "exclusion": ";".join(exclusions), "error": record.get("error"),
            "case_id": case.get("id"), "experiment": case.get("experiment"),
            "series": case.get("series", "shared-layouts"), "round": record.get("round"),
            "job_id": record.get("slurm_job_id"), "policy": measured.get("policy"),
            "backend": "gpu", "destination": "shared NFS",
            "chunk_bytes": case.get("chunk_bytes"), "chunk_kib": ratio(case.get("chunk_bytes"), 1024),
            "chunk_shape": chunk, "shard_shape": shard,
            "chunks_per_shard": case.get("chunks_per_shard"),
            "raw_shard_bytes": case.get("raw_shard_bytes"),
            "actual_layer_shards": case.get("actual_layer_shards"),
            "target_shards": case.get("target_shards"),
            "codec": case.get("codec"), "blosc_block_bytes": case.get("blosc_block_bytes"),
            "shuffle": case.get("shuffle"), "level_hint": case.get("level"),
            "logical_shape": shape, "logical_bytes": logical, "submitted_bytes": padded,
            "metered_output_bytes": output, "final_file_bytes": check.get("final_file_bytes"),
            "allocated_file_bytes": check.get("allocated_file_bytes"),
            "padding_ratio": ratio(padded, logical),
            "metered_bytes_per_logical_byte": ratio(output, logical),
            "final_bytes_per_logical_byte": ratio(check.get("final_file_bytes"), logical),
            "allocated_bytes_per_logical_byte": ratio(check.get("allocated_file_bytes"), logical),
            "elapsed_s": elapsed, "append_s": measured.get("append_s"),
            "drain_s": metrics.get("drain_s", measured.get("drain_s")),
            "drain_fraction": metrics.get("drain_fraction", measured.get("drain_fraction")),
            "logical_gibs": rate, "init_s": native.get("init_s"),
            "source_preparation_s": measured.get("prep_s"),
            "warmup_s": measured.get("warmup_s"),
            "separate_warmup_s": measured.get("separate_warmup_s"),
            "warmup_input_bytes": measured.get("warmup_input_bytes"),
            "warmup_output_bytes": measured.get("warmup_output_bytes"),
            "complete_batches": measured.get("complete_batches"),
            "generation_transitions": measured.get("generation_transitions"),
            "memory_host_peak_bytes": native.get("memory_host_peak_bytes"),
            "memory_device_used_bytes": native.get("memory_device_used_bytes"),
            "peak_pending_mib": native.get("stalls", {}).get("peak_pending_mib"),
            "checked_plane_count": check.get("checked_plane_count"),
            "retained_path": record.get("retained_path"),
            "metadata_sha256": identity(check["metadata"]) if "metadata" in check else None,
            "file_count": check.get("file_count"), "shard_file_count": check.get("shard_file_count"),
        }
        rows.append(row)
        counts[row["id"]] += 1
    for row in rows:
        if counts[row["id"]] != 1:
            row.update(accepted=False, primary=False)
            row["exclusion"] += ";duplicate_writer_id"
    return rows


def interrupted_shard_rows(evidence):
    restart = evidence.json("root/restarted-shards.json", {})
    if not restart:
        return []
    old_attempt = restart.get("old_attempt")
    require(isinstance(old_attempt, str), "Restart metadata must identify old_attempt")
    path = Path(old_attempt)
    if path.is_absolute():
        require(path.is_relative_to(Path(evidence.bundle["study_root"])),
                "Interrupted attempt must be inside the recorded study root")
        path = path.relative_to(Path(evidence.bundle["study_root"]))
    if path.name != "observations.jsonl":
        if path.name != "measurements":
            path = path / "measurements"
        path = path / "observations.jsonl"
    name = "root/" + path.as_posix()
    require(name in evidence.artifacts, f"Interrupted shard records are missing from the archive: {name}")
    events = [
        (line, json.loads(text))
        for line, text in enumerate(evidence.artifacts[name].decode().splitlines(), 1)
        if text.strip()
    ]
    rows = writer_rows(evidence, events, "raw/provenance.tar.gz!" + name)
    reason = restart.get("reason", "benchmark_wrapper_capacity_fix_and_full_shard_restart")
    output = []
    for row in rows:
        if row["experiment"] != "shard-count":
            continue
        row["original_primary_eligibility"] = row["primary"]
        row["primary"] = False
        row["excluded_from_primary_reason"] = reason
        row["restart_failed_id"] = restart.get("failed_id")
        row["supplementary_phase"] = "interrupted_shards_before_wrapper_capacity_fix"
        output.append(row)
    return output


def post_primary_extension(evidence, write_keys):
    marker = "root/shard-extension-complete.txt"
    if marker not in evidence.artifacts:
        return None
    attempt = Path(evidence.artifacts[marker].decode().strip())
    root = Path(evidence.bundle["study_root"])
    if attempt.is_absolute():
        require(attempt.is_relative_to(root / "jobs"),
                "Post-primary extension points outside the recorded root/jobs")
        attempt = attempt.relative_to(root)
    require(attempt.parts and attempt.parts[0] == "jobs" and ".." not in attempt.parts,
            "Post-primary extension must identify a job attempt")
    prefix = "root/" + attempt.as_posix() + "/"
    protocol_name = prefix + "protocol.json"
    records_name = prefix + "measurements/observations.jsonl"
    require(protocol_name in evidence.artifacts, "Post-primary extension protocol is missing")
    require(records_name in evidence.artifacts, "Post-primary extension records are missing")
    protocol = evidence.json(protocol_name)
    protocol_hash = protocol.get("protocol_sha256")
    require(protocol_hash == identity({
        key: value for key, value in protocol.items() if key != "protocol_sha256"
    }), "Post-primary extension protocol hash differs")
    events = [
        (line, json.loads(text))
        for line, text in enumerate(evidence.artifacts[records_name].decode().splitlines(), 1)
        if text.strip()
    ]
    originals = dict(events)
    rows = writer_rows(evidence, events, "raw/provenance.tar.gz!" + records_name)
    expected = {
        (round_number, role, count)
        for round_number in (1, 2, 3)
        for role, count in (("sample", 30), ("sample", 54),
                            ("reference-before", 15), ("reference-after", 15))
    }
    fast = evidence.plan.get("shard_count", {}).get("fast", {})
    expected_settings = {
        "codec": fast.get("codec", "blosc-lz4"),
        "chunk_bytes": fast.get("chunk_bytes", 65536),
        "chunk_shape": [4, 64, 128],
        "blosc_block_bytes": fast.get("blosc_block_bytes", 16384),
        "shuffle": fast.get("shuffle", "bit"),
        "level_hint": fast.get("level_hint", 3),
        "policy": "coverage-qualified-through-final-close-v2",
    }
    for row in rows:
        original = originals[row["raw_line"]]
        case = original.get("case", {})
        measured = original.get("native", {}).get("measurement", {})
        reasons = []
        if case.get("experiment") != EXTENSION_EXPERIMENT or case.get("family") != EXTENSION_EXPERIMENT:
            reasons.append("wrong_extension_experiment")
        if case.get("protocol_sha256") != protocol_hash:
            reasons.append("extension_protocol_identity_mismatch")
        if case.get("minimum_logical_bytes") != EXTENSION_MINIMUM_BYTES:
            reasons.append("extension_minimum_volume_mismatch")
        if not finite(row["logical_bytes"]) or row["logical_bytes"] < EXTENSION_MINIMUM_BYTES:
            reasons.append("extension_logical_volume_too_small")
        if measured.get("requested_frames") != math.ceil(EXTENSION_MINIMUM_BYTES / FRAME_BYTES):
            reasons.append("extension_requested_frames_mismatch")
        if any(row.get(key) != value for key, value in expected_settings.items()):
            reasons.append("extension_codec_chunk_or_timing_policy_mismatch")
        if (row["round"], row["role"], row["actual_layer_shards"]) not in expected:
            reasons.append("unexpected_extension_schedule_slot")
        if reasons:
            row["accepted"] = False
            row["exclusion"] = ";".join(filter(None, [row["exclusion"], *reasons]))
        row["primary"] = False
        row["phase"] = EXTENSION_EXPERIMENT
        row["analysis_scope"] = "post-primary adaptive follow-up"
        row["protocol_sha256"] = case.get("protocol_sha256")
        row["minimum_logical_bytes"] = case.get("minimum_logical_bytes")
        row["requested_frames"] = measured.get("requested_frames")
        row["extension_sample"] = row["accepted"] and row["role"] == "sample"
        row["extension_reference"] = row["accepted"] and row["role"] in ("reference-before", "reference-after")
        row["excluded_from_primary_reason"] = "separate_post_primary_job_and_96_GiB_minimum"
        row["protocol_source"] = "raw/provenance.tar.gz!" + protocol_name
    grouping = ("phase", "protocol_sha256", "minimum_logical_bytes", *write_keys)
    summary = summaries([row for row in rows if row["extension_sample"]], grouping, WRITE_METRICS)
    groups = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["extension_sample"]:
            key = (row["protocol_sha256"], row["job_id"], row["policy"], row["round"],
                   row["codec"], row["chunk_bytes"], row["blosc_block_bytes"],
                   row["shuffle"], row["level_hint"])
            groups[key][row["actual_layer_shards"]].append(row)
    pairs = []
    for key, counts in sorted(groups.items(), key=lambda item: json_text(item[0])):
        if len(counts[54]) != 1 or len(counts[30]) != 1:
            continue
        numerator, denominator = counts[54][0], counts[30][0]
        pairs.append({
            "phase": EXTENSION_EXPERIMENT, "protocol_sha256": key[0],
            "job_id": key[1], "policy": key[2], "round": key[3],
            "codec": key[4], "chunk_bytes": key[5], "blosc_block_bytes": key[6],
            "shuffle": key[7], "level_hint": key[8],
            "minimum_logical_bytes": EXTENSION_MINIMUM_BYTES,
            "comparison": "54/30", "numerator_shards": 54, "denominator_shards": 30,
            "numerator_id": numerator["id"], "denominator_id": denominator["id"],
            "numerator_source": numerator["source_locator"],
            "denominator_source": denominator["source_locator"],
            "numerator_logical_gibs": numerator["logical_gibs"],
            "denominator_logical_gibs": denominator["logical_gibs"],
            "numerator_logical_bytes": numerator["logical_bytes"],
            "denominator_logical_bytes": denominator["logical_bytes"],
            "rate_ratio": numerator["logical_gibs"] / denominator["logical_gibs"],
        })
    pair_keys = (
        "phase", "protocol_sha256", "job_id", "policy", "minimum_logical_bytes",
        "comparison", "numerator_shards", "denominator_shards", "codec",
        "chunk_bytes", "blosc_block_bytes", "shuffle", "level_hint",
    )
    pair_summary = summaries(pairs, pair_keys, ("rate_ratio",))
    references = [row for row in rows if row["extension_reference"]]
    drift = reference_drift(references)
    for row in drift:
        row.update(phase=EXTENSION_EXPERIMENT, protocol_sha256=protocol_hash,
                   minimum_logical_bytes=EXTENSION_MINIMUM_BYTES)
    actual = Counter(
        (row["round"], row["role"], row["actual_layer_shards"])
        for row in rows if row["accepted"]
    )
    audit = {
        "phase": EXTENSION_EXPERIMENT, "protocol_sha256": protocol_hash,
        "attempt": attempt.as_posix(), "marker_present": True,
        "expected_rows": 12, "rows": len(rows),
        "expected_samples": 6, "accepted_samples": sum(row["extension_sample"] for row in rows),
        "expected_references": 6, "accepted_references": len(references),
        "paired_54_over_30_rounds": len(pairs), "reference_pairs": len(drift),
        "minimum_logical_bytes": EXTENSION_MINIMUM_BYTES,
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "missing_conditions": sorted(expected - set(actual)),
        "unexpected_conditions": sorted(set(actual) - expected),
        "duplicate_conditions": [list(key) for key, count in actual.items() if count != 1],
        "complete": len(rows) == 12 and set(actual) == expected
            and all(count == 1 for count in actual.values()) and len(pairs) == len(drift) == 3,
        "primary_pooling": False,
        "primary_extension_decision": evidence.extension,
        "completion_document": evidence.json(prefix + "complete.json",
                                             evidence.json(prefix + "measurements/complete.json", {})),
    }
    points = [
        figure_point(
            "shard-extension", "rate", row["job_id"], row["actual_layer_shards"], row,
            "logical_gibs", phase=EXTENSION_EXPERIMENT, protocol_sha256=protocol_hash,
            job_id=row["job_id"], minimum_logical_bytes=EXTENSION_MINIMUM_BYTES,
        )
        for row in summary
    ]
    points += [
        figure_point(
            "shard-extension", "paired-summary", row["job_id"], index, row, "rate_ratio",
            phase=EXTENSION_EXPERIMENT, protocol_sha256=protocol_hash,
            job_id=row["job_id"], minimum_logical_bytes=EXTENSION_MINIMUM_BYTES,
        )
        for index, row in enumerate(pair_summary)
    ]
    points += [
        {
            "figure": "shard-extension", "panel": "paired-round",
            "series": row["job_id"], "x": row["round"], "metric": "rate_ratio",
            "median": row["rate_ratio"], "min": row["rate_ratio"], "max": row["rate_ratio"],
            "n": 1, "phase": EXTENSION_EXPERIMENT, "protocol_sha256": protocol_hash,
            "job_id": row["job_id"], "minimum_logical_bytes": EXTENSION_MINIMUM_BYTES,
        }
        for row in pairs
    ]
    return {
        "protocol": protocol, "protocol_name": protocol_name, "records_name": records_name,
        "rows": rows, "summary": summary, "pairs": pairs, "pair_summary": pair_summary,
        "references": references, "drift": drift, "figure_data": points, "audit": audit,
    }


def reader_rows(evidence):
    cases = defaultdict(lambda: {"results": [], "terminals": [], "passes": 0})
    event_counts = Counter()
    schedule = evidence.json("reads/schedule.json", [])
    layouts = evidence.json("reads/layouts.json", {})
    for line, record in evidence.events("reader-records.jsonl.gz"):
        event = record.get("event")
        event_counts[event] += 1
        case_id = record.get("case_id")
        if not case_id:
            continue
        entry = cases[case_id]
        if event == "result":
            entry["results"].append((line, record))
        elif event == "case_finished":
            entry["terminals"].append((line, record))
        elif event == "started":
            entry["machine"] = record.get("machine", {})
        elif event == "pass":
            entry["passes"] += 1
    scheduled = {row["case_id"]: row for row in schedule}
    rows, statuses = [], []
    keys = ("case_id", "phase", "repeat", "layout_id", "workload", "backend")
    for case_id in sorted(set(cases) | set(scheduled)):
        entry = cases[case_id]
        terminals = entry["terminals"]
        terminal = terminals[-1][1] if terminals else {}
        original = scheduled.get(case_id, terminal)
        terminal_ok = (
            len(terminals) == 1 and terminal.get("status") == "accepted"
            and terminal.get("returncode") == 0 and not terminal.get("invalid_json_lines")
        )
        statuses.append({
            **{key: original.get(key) for key in keys},
            "case_id": case_id,
            "status": terminal.get("status", "missing_case_finished"),
            "returncode": terminal.get("returncode"),
            "result_count": len(entry["results"]), "terminal_count": len(terminals),
            "observed_pass_events": entry["passes"],
            "accepted": terminal_ok and len(entry["results"]) == 1,
            "wall_seconds": terminal.get("wall_seconds"),
            "message": terminal.get("message"),
        })
        for line, result in entry["results"]:
            exclusions = []
            if not terminal_ok:
                exclusions.append("missing_or_unsuccessful_matching_case_finished")
            if len(entry["results"]) != 1:
                exclusions.append("multiple_result_events")
            if result.get("status") != "accepted":
                exclusions.append("result_not_accepted")
            if not result.get("policy_id") or not result.get("trace_sha256"):
                exclusions.append("missing_policy_or_trace_identity")
            if any(result.get(key) != terminal.get(key) for key in keys):
                exclusions.append("terminal_identity_mismatch")
            if case_id in scheduled and any(result.get(key) != scheduled[case_id].get(key) for key in keys):
                exclusions.append("schedule_identity_mismatch")
            useful, active = result.get("useful_source_bytes"), result.get("active_seconds")
            derived = ratio(useful, active)
            derived = derived / GIB if derived is not None else None
            if not finite(derived) or derived <= 0:
                exclusions.append("invalid_useful_rate_denominator")
            elif not finite(result.get("useful_source_gib_per_second")) or not math.isclose(
                derived, result["useful_source_gib_per_second"], rel_tol=1e-9, abs_tol=1e-12
            ):
                exclusions.append("useful_rate_denominator_mismatch")
            if finite(useful) and result.get("output_float32_bytes") != 2 * useful:
                exclusions.append("float32_output_denominator_mismatch")
            if result.get("backend") == "tensorstore" and result.get("decoded_bytes") is not None:
                exclusions.append("unexpected_tensorstore_decoded_counter")
            machine = entry.get("machine", evidence.read_run.get("machine", {}))
            layout = layouts.get(result.get("layout_id"), {})
            chunk = layout.get("chunk_shape", [])
            chunk_bytes = layout.get("raw_chunk_bytes")
            if chunk_bytes is None and chunk:
                chunk_bytes = math.prod(chunk) * 2
            row = {
                **{key: result.get(key) for key in keys},
                "raw_line": line,
                "source_locator": f"raw/reader-records.jsonl.gz#line={line}",
                "status": result.get("status"), "terminal_status": terminal.get("status"),
                "returncode": terminal.get("returncode"), "accepted": not exclusions,
                "primary": not exclusions and result.get("phase") == "measurement",
                "exclusion": ";".join(exclusions),
                "policy_id": result.get("policy_id"), "trace_sha256": result.get("trace_sha256"),
                "machine_id": identity(machine), "hostname": machine.get("hostname"),
                "job_id": machine.get("environment", {}).get("SLURM_JOB_ID"),
                "cpu_affinity": machine.get("cpu_affinity"),
                "chunk_shape": chunk, "chunk_bytes": chunk_bytes,
                "chunk_kib": ratio(chunk_bytes, 1024),
                "metadata_sha256": layout.get("metadata_sha256"),
                "complete_logical_scan": result.get("complete_logical_scan"),
                "geometry_matches_all_observed_decode_passes":
                    result.get("geometry_matches_all_observed_decode_passes"),
                "server_cache": result.get("server_cache"),
                "cache_mode": result.get("cache_mode"),
                "measurement_peak_rss_available": result.get("measurement_peak_rss_available"),
                **{key: result.get(key) for key in READ_METRICS},
            }
            rows.append(row)
    accepted_cases = Counter(row["case_id"] for row in rows if row["accepted"])
    for status in statuses:
        status["accepted"] = accepted_cases[status["case_id"]] == 1
    return rows, statuses, dict(event_counts)


def summaries(rows, keys, metrics):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(json_text(row.get(key)) for key in keys)].append(row)
    result = []
    for key in sorted(groups):
        members = groups[key]
        common = {name: members[0].get(name) for name in keys}
        summary = {"group_id": identity(common), **common, "n": len(members)}
        for metric in metrics:
            values = [row[metric] for row in members if finite(row.get(metric))]
            summary[metric + "_n"] = len(values)
            summary[metric + "_median"] = statistics.median(values) if values else None
            summary[metric + "_min"] = min(values) if values else None
            summary[metric + "_max"] = max(values) if values else None
        result.append(summary)
    return result


def paired_shards(rows):
    groups = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["primary"] and row["experiment"] == "shard-count" and row["role"] == "sample":
            key = (row["round"], row["policy"], row["job_id"], row["codec"],
                   row["chunk_bytes"], row["blosc_block_bytes"], row["shuffle"], row["level_hint"])
            groups[key][row["actual_layer_shards"]].append(row)
    pairs = []
    for key, counts in sorted(groups.items(), key=lambda item: json_text(item[0])):
        for numerator, denominator in ((9, 4), (15, 4), (30, 15), (54, 30)):
            if len(counts[numerator]) != 1 or len(counts[denominator]) != 1:
                continue
            a, b = counts[numerator][0], counts[denominator][0]
            pairs.append({
                "comparison": f"{numerator}/{denominator}", "round": key[0],
                "policy": key[1], "job_id": key[2], "codec": key[3],
                "numerator_shards": numerator, "denominator_shards": denominator,
                "numerator_id": a["id"], "denominator_id": b["id"],
                "numerator_logical_gibs": a["logical_gibs"],
                "denominator_logical_gibs": b["logical_gibs"],
                "numerator_logical_bytes": a["logical_bytes"],
                "denominator_logical_bytes": b["logical_bytes"],
                "rate_ratio": a["logical_gibs"] / b["logical_gibs"],
            })
    return pairs


def reference_drift(rows):
    groups = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["accepted"] and row["role"] in ("reference-before", "reference-after"):
            groups[(row["case_id"], row["round"], row["policy"], row["job_id"])][row["role"]].append(row)
    output = []
    for key, roles in sorted(groups.items(), key=lambda item: json_text(item[0])):
        before, after = roles["reference-before"], roles["reference-after"]
        if len(before) == len(after) == 1:
            output.append({
                "case_id": key[0], "round": key[1], "policy": key[2], "job_id": key[3],
                "before_id": before[0]["id"], "after_id": after[0]["id"],
                "before_logical_gibs": before[0]["logical_gibs"],
                "after_logical_gibs": after[0]["logical_gibs"],
                "after_over_before": after[0]["logical_gibs"] / before[0]["logical_gibs"],
            })
    return output


def aligned_pairs(rows):
    groups = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["primary"] and row["workload"] in ("aligned-512", "translated-512"):
            key = (row["layout_id"], row["backend"], row["repeat"], row["policy_id"], row["machine_id"])
            groups[key][row["workload"]].append(row)
    output = []
    for key, workloads in sorted(groups.items(), key=lambda item: json_text(item[0])):
        aligned, translated = workloads["aligned-512"], workloads["translated-512"]
        if len(aligned) == len(translated) == 1:
            a, t = aligned[0], translated[0]
            output.append({
                "layout_id": key[0], "backend": key[1], "repeat": key[2],
                "policy_id": key[3], "machine_id": key[4],
                "chunk_kib": a["chunk_kib"], "aligned_case_id": a["case_id"],
                "translated_case_id": t["case_id"],
                "aligned_trace_sha256": a["trace_sha256"],
                "translated_trace_sha256": t["trace_sha256"],
                "aligned_useful_gibs": a["useful_source_gib_per_second"],
                "translated_useful_gibs": t["useful_source_gib_per_second"],
                "aligned_over_translated_rate": a["useful_source_gib_per_second"] / t["useful_source_gib_per_second"],
            })
    return output


def joint_rows(writes, reads):
    output = []
    for writer in writes:
        row = {
            "layout_id": writer["case_id"], "chunk_kib": writer["chunk_kib"],
            "chunk_shape": writer["chunk_shape"], "shard_shape": writer["shard_shape"],
            "write_group_id": writer["group_id"], "write_n": writer["n"],
            "write_policy": writer["policy"],
        }
        for key in ("logical_gibs", "final_bytes_per_logical_byte", "metered_bytes_per_logical_byte"):
            for statistic in ("median", "min", "max"):
                row["write_" + key + "_" + statistic] = writer[key + "_" + statistic]
        for backend in BACKENDS:
            for workload in ("translated-256", "full-scan"):
                candidates = [
                    r for r in reads
                    if r["layout_id"] == writer["case_id"] and r["backend"] == backend and r["workload"] == workload
                ]
                prefix = backend + "_" + workload.replace("-", "_")
                row[prefix + "_groups"] = len(candidates)
                if len(candidates) == 1:
                    reader = candidates[0]
                    for name in ("group_id", "n", "policy_id", "trace_sha256", "machine_id"):
                        row[prefix + "_" + name] = reader[name]
                    for statistic in ("median", "min", "max"):
                        row[prefix + "_useful_gibs_" + statistic] = reader["useful_source_gib_per_second_" + statistic]
        output.append(row)
    return output


def figure_point(figure, panel, series, x, summary, metric, **fields):
    return {
        "figure": figure, "panel": panel, "series": series, "x": x,
        "metric": metric, "median": summary[metric + "_median"],
        "min": summary[metric + "_min"], "max": summary[metric + "_max"],
        "n": summary[metric + "_n"], "group_id": summary["group_id"], **fields,
    }


def figure_data(shared, reads, shards, paired):
    output = {"shared-layout": [], "read-rates": [], "shard-count": []}
    for row in shared:
        fields = {"policy": row["policy"], "job_id": row["job_id"], "layout_id": row["case_id"]}
        output["shared-layout"].append(figure_point(
            "shared-layout", "rate", "GPU " + row["codec"], row["chunk_kib"], row, "logical_gibs", **fields
        ))
        for metric, series in (("final_bytes_per_logical_byte", "Final file lengths"),
                               ("metered_bytes_per_logical_byte", "Metered shard writes")):
            output["shared-layout"].append(figure_point(
                "shared-layout", "size", series, row["chunk_kib"], row, metric, **fields
            ))
    for row in reads:
        output["read-rates"].append(figure_point(
            "read-rates", row["workload"], {"damacy": "Damacy CPU", "tensorstore": "TensorStore CPU"}[row["backend"]],
            row["chunk_kib"], row,
            "useful_source_gib_per_second", policy_id=row["policy_id"],
            trace_sha256=row["trace_sha256"], machine_id=row["machine_id"], layout_id=row["layout_id"],
        ))
    for row in shards:
        output["shard-count"].append(figure_point(
            "shard-count", "rate", row["codec"], row["actual_layer_shards"], row, "logical_gibs",
            policy=row["policy"], job_id=row["job_id"], codec=row["codec"],
        ))
    for position, row in enumerate(sorted(
        paired, key=lambda r: (r["codec"], r["numerator_shards"], r["denominator_shards"])
    )):
        output["shard-count"].append(figure_point(
            "shard-count", "paired", f"{row['codec']} {row['comparison']}", position, row, "rate_ratio",
            policy=row["policy"], job_id=row["job_id"], codec=row["codec"], comparison=row["comparison"],
        ))
    return output


def plot_figures(output, data):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
        "svg.fonttype": "none", "svg.hashsalt": "bbbc022-evidence-v1",
        "figure.dpi": 120, "savefig.dpi": 300,
    })

    def lines(axis, points, extra_keys=()):
        groups = defaultdict(list)
        for point in points:
            if finite(point["median"]) and finite(point["x"]):
                groups[(point["series"], *(point.get(key) for key in extra_keys))].append(point)
        for group, members in sorted(groups.items(), key=lambda item: json_text(item[0])):
            members = sorted(members, key=lambda row: row["x"])
            x = [row["x"] for row in members]
            y = [row["median"] for row in members]
            label = group[0]
            if sum(key[0] == group[0] for key in groups) > 1:
                label += " " + identity(group)[0:6]
            axis.errorbar(
                x, y, yerr=[[r["median"] - r["min"] for r in members],
                           [r["max"] - r["median"] for r in members]],
                marker="o", markersize=4, capsize=3, linewidth=1.3, label=label,
            )
        axis.grid(axis="y", alpha=0.25)
        if groups:
            axis.legend(fontsize=8)
        else:
            axis.text(0.5, 0.5, "No qualified observations", transform=axis.transAxes,
                      ha="center", va="center")

    def save(figure, name):
        figure.tight_layout()
        figure.savefig(output / f"{name}.png", metadata={"Software": "Matplotlib"})
        figure.savefig(output / f"{name}.svg", metadata={"Date": None, "Creator": "Matplotlib"})
        plt.close(figure)

    figure, axes = plt.subplots(1, 2, figsize=(9, 3.5))
    for axis, panel in zip(axes, ("rate", "size")):
        lines(axis, [row for row in data["shared-layout"] if row["panel"] == panel], ("policy", "job_id"))
        axis.set_xscale("log", base=2)
        axis.set_xticks([16, 32, 64, 128, 256, 512], labels=["16", "32", "64", "128", "256", "512"])
        axis.set_xlabel("Raw chunk capacity (KiB)")
    axes[0].set_ylabel("Logical input GiB/s")
    axes[0].set_title("Fixed-volume GPU writes")
    axes[1].set_ylabel("Bytes per logical input byte")
    axes[1].set_title("Output cost on the same logical volume")
    save(figure, "shared-layout")
    figure, axes = plt.subplots(2, 2, figsize=(10, 7))
    for axis, workload in zip(axes.flat, WORKLOADS):
        lines(axis, [row for row in data["read-rates"] if row["panel"] == workload],
              ("policy_id", "trace_sha256", "machine_id"))
        axis.set_xscale("log", base=2)
        axis.set_xticks([16, 32, 64, 128, 256, 512], labels=["16", "32", "64", "128", "256", "512"])
        axis.set_xlabel("Raw chunk capacity (KiB)")
        axis.set_ylabel("Useful uint16 source GiB/s")
        axis.set_title(workload)
    save(figure, "read-rates")
    figure, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    lines(axes[0], [row for row in data["shard-count"] if row["panel"] == "rate"], ("policy", "job_id"))
    axes[0].set_xlabel("Actual append-layer shards")
    axes[0].set_ylabel("Logical input GiB/s")
    axes[0].set_title("Fixed codec/chunk series")
    paired = [row for row in data["shard-count"] if row["panel"] == "paired"]
    for index, row in enumerate(paired):
        axes[1].errorbar(
            index, row["median"],
            yerr=[[row["median"] - row["min"]], [row["max"] - row["median"]]],
            marker="o", capsize=3, color="tab:blue",
        )
        axes[1].annotate(f"n={row['n']}", (index, row["max"]), xytext=(0, 5),
                         textcoords="offset points", ha="center", fontsize=8)
    axes[1].axhline(1, color="0.4", linestyle="--", linewidth=1)
    axes[1].set_xticks(
        range(len(paired)), labels=[f"{row['codec']}\n{row['comparison']}" for row in paired]
    )
    axes[1].set_xlabel("Numerator / denominator actual shards")
    axes[1].set_ylabel("Paired logical-rate ratio")
    axes[1].set_title("Median and observed range across paired rounds")
    axes[1].grid(axis="y", alpha=0.25)
    save(figure, "shard-count")


def write_extension_outputs(output, evidence, extension, plots):
    tables = {
        "shard-extension-runs.csv": extension["rows"],
        "shard-extension-summary.csv": extension["summary"],
        "shard-extension-paired-ratios.csv": extension["pairs"],
        "shard-extension-paired-summary.csv": extension["pair_summary"],
        "shard-extension-references.csv": extension["references"],
        "shard-extension-reference-drift.csv": extension["drift"],
        "shard-extension-figure-data.csv": extension["figure_data"],
    }
    for name, rows in tables.items():
        write_csv(output / name, rows)
    write_json(output / "shard-extension-validation.json", extension["audit"])
    (output / "shard-extension-protocol.json").write_bytes(
        evidence.artifacts[extension["protocol_name"]]
    )
    if not plots:
        return
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    groups = defaultdict(list)
    for row in extension["summary"]:
        groups[(row["job_id"], row["protocol_sha256"], row["policy"])].append(row)
    for key, members in sorted(groups.items(), key=lambda item: json_text(item[0])):
        members = sorted(members, key=lambda row: row["actual_layer_shards"])
        axes[0].errorbar(
            [row["actual_layer_shards"] for row in members],
            [row["logical_gibs_median"] for row in members],
            yerr=[
                [row["logical_gibs_median"] - row["logical_gibs_min"] for row in members],
                [row["logical_gibs_max"] - row["logical_gibs_median"] for row in members],
            ],
            marker="o", capsize=3, label=f"Job {key[0]}",
        )
        for row in members:
            axes[0].annotate(
                f"n={row['n']}", (row["actual_layer_shards"], row["logical_gibs_max"]),
                xytext=(0, 5), textcoords="offset points", ha="center", fontsize=8,
            )
    if groups:
        axes[0].legend(fontsize=8)
    else:
        axes[0].text(0.5, 0.5, "No qualified follow-up samples",
                     transform=axes[0].transAxes, ha="center", va="center")
    axes[0].set_xticks([30, 54])
    axes[0].set_xlabel("Actual append-layer shards")
    axes[0].set_ylabel("Logical input GiB/s")
    axes[0].set_title("Separate follow-up: 96 GiB logical minimum")
    labels = []
    for index, row in enumerate(extension["pairs"]):
        axes[1].plot(index, row["rate_ratio"], "o", color="tab:blue")
        labels.append(f"Round {row['round']}")
    for row in extension["pair_summary"]:
        index = len(labels)
        axes[1].errorbar(
            index, row["rate_ratio_median"],
            yerr=[[row["rate_ratio_median"] - row["rate_ratio_min"]],
                  [row["rate_ratio_max"] - row["rate_ratio_median"]]],
            marker="D", capsize=4, color="black",
        )
        labels.append("Median\nand range")
    axes[1].axhline(1, color="0.4", linestyle="--", linewidth=1)
    axes[1].set_xticks(range(len(labels)), labels=labels)
    axes[1].set_ylabel("Paired 54 / 30 logical-rate ratio")
    axes[1].set_title("Post-primary adaptive comparison")
    for axis in axes:
        axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(output / "shard-extension.png", metadata={"Software": "Matplotlib"})
    figure.savefig(output / "shard-extension.svg", metadata={"Date": None, "Creator": "Matplotlib"})
    plt.close(figure)


def coverage(evidence, writes, reads, read_cases):
    plan = evidence.plan
    shared = plan.get("shared_layouts", {})
    shard = plan.get("shard_count", {})
    shapes = shared.get("chunk_shapes", [])
    layouts = [f"c{math.prod(shape) * 2 // 1024}" for shape in shapes]
    expected_writes = set()
    for layout in layouts:
        for repeat in range(1, shared.get("repetitions", 3) + 1):
            expected_writes.add((layout, repeat, "sample"))
    for repeat in range(1, shard.get("repetitions", 6) + 1):
        for series in ("fast", "slow_control"):
            for target in shard.get(series, {}).get("targets", []):
                expected_writes.add((f"{series}-target{target}", repeat, "sample"))
        for role in ("reference-before", "reference-after"):
            expected_writes.add(("fast-target16", repeat, role))
    extension = evidence.extension.get("include_actual54", evidence.write_complete.get("max54_extension"))
    if extension:
        for repeat in range(4, shard.get("repetitions", 6) + 1):
            expected_writes.add(("fast-target54", repeat, "sample"))
    accepted_writes = Counter(
        (row["case_id"], row["round"], row["role"]) for row in writes if row["accepted"]
    )
    expected_reads = {
        (layout, backend, workload, repeat)
        for layout in layouts for backend in BACKENDS for workload in WORKLOADS
        for repeat in range(1, plan.get("readers", {}).get("repetitions", 3) + 1)
    }
    accepted_reads = Counter(
        (row["layout_id"], row["backend"], row["workload"], row["repeat"])
        for row in reads if row["primary"]
    )
    return {
        "writer_completion_marker_present": evidence.bundle["writer_completion_marker_present"],
        "writer_rows": len(writes),
        "writer_status_counts": dict(Counter(row["status"] for row in writes)),
        "writer_accepted_shared_samples": sum(row["primary"] and row["experiment"] == "shared-layouts" for row in writes),
        "writer_accepted_shard_samples": sum(row["primary"] and row["experiment"] == "shard-count" for row in writes),
        "writer_accepted_references": sum(row["accepted"] and row["role"] in ("reference-before", "reference-after") for row in writes),
        "writer_expected_with_references": len(expected_writes),
        "writer_missing": sorted(expected_writes - set(accepted_writes)),
        "writer_unexpected": sorted(set(accepted_writes) - expected_writes),
        "writer_duplicate_conditions": [list(key) for key, n in accepted_writes.items() if n != 1],
        "writer_complete": bool(expected_writes) and set(accepted_writes) == expected_writes
            and all(n == 1 for n in accepted_writes.values()) and evidence.write_complete.get("status") == "pass",
        "conditional54_included": extension,
        "conditional54_decision": evidence.extension,
        "reader_result_rows": len(reads), "reader_case_rows": len(read_cases),
        "reader_status_counts": dict(Counter(row["status"] for row in read_cases)),
        "reader_accepted_primary": sum(row["primary"] for row in reads),
        "reader_expected_primary": len(expected_reads),
        "reader_missing": sorted(expected_reads - set(accepted_reads)),
        "reader_unexpected": sorted(set(accepted_reads) - expected_reads),
        "reader_duplicate_conditions": [list(key) for key, n in accepted_reads.items() if n != 1],
        "reader_complete": bool(expected_reads) and set(accepted_reads) == expected_reads
            and all(n == 1 for n in accepted_reads.values()),
        "problems": evidence.problems,
    }


def write_findings(output, evidence, audit, shared, reads, paired, drift, followup=None):
    text = [
        f"This export contains {audit['writer_accepted_shared_samples']} qualified shared-layout write samples, "
        f"{audit['writer_accepted_shard_samples']} qualified shard samples, "
        f"{audit['writer_accepted_references']} separate writer references, and "
        f"{audit['reader_accepted_primary']} of {audit['reader_expected_primary']} expected measurement read results. "
        f"Writer coverage is {'complete' if audit['writer_complete'] else 'incomplete'}; "
        f"reader coverage is {'complete' if audit['reader_complete'] else 'incomplete'}. "
        "Missing, rejected and duplicate conditions are listed in validation.json and read-cases.csv.",
        "Medians and observed minimum–maximum ranges describe retained repetitions; ranges are not confidence intervals. "
        "Correctness observations and before/after references are excluded from primary summaries. "
        "A reader result is admitted only with one matching successful case_finished event and process return code zero.",
        "The source contains sixteen 520 × 696 uint16 microscopy fields. The shared arrays repeat this ordered source "
        "from plane zero for 32,768 frames: 23,718,789,120 logical bytes (22.08984375 GiB), "
        "2,048 complete source cycles and sixteen append-axis shard generations. The append axis represents replay, "
        "not newly measured spatial content. Shards are [2048,512,512], with four files per append layer. "
        "The six chunk layouts submit respectively 27, 30, 30, 36, 48 and 64 GiB after spatial padding.",
    ]
    restart = evidence.json("root/restarted-shards.json", {})
    if restart:
        text.append(
            "The shared-layout observations remain from their completed original job and binary. "
            "The entire shard-count experiment was restarted after the benchmark sink wrapper's 32-writer limit "
            "prevented the first 54-shard observation from starting; the codec itself was not the limiting component. "
            "The wrapper limit was increased to 64 in a separately identified binary. "
            "The primary shard summaries use only the restarted series, with no old/new shard-job pooling. "
            f"The {audit['supplementary_interrupted_shard_rows']} interrupted shard records "
            f"({audit['supplementary_interrupted_shard_qualified']} qualified measurements or references; "
            f"{audit['supplementary_interrupted_shard_failed']} failed) remain in "
            "[supplementary-interrupted-shards.csv](supplementary-interrupted-shards.csv), "
            "with original status, available rates, job identities and source locations. "
            "Their exclusion was fixed by the capacity repair and full restart, without selection by measured rate. "
            f"The recorded restart reason is: {restart.get('reason', 'benchmark wrapper capacity fix and full restart').rstrip('.')}. "
            "The failed startup has no measured rate and is not assigned zero throughput. "
            "[source-phases.json](source-phases.json) records the phase-specific jobs, binary hashes and patches."
        )
    if shared:
        text += [
            "The following qualified fixed-volume write summaries use logical input GiB/s and final file bytes per logical byte.",
            "| Chunk KiB | n | Write median [min, max] GiB/s | Final-size ratio median [min, max] |",
            "|---:|---:|---:|---:|",
        ]
        for row in sorted(shared, key=lambda r: (r["chunk_kib"], r["group_id"])):
            text.append(
                f"| {row['chunk_kib']:g} | {row['n']} | "
                f"{number(row['logical_gibs_median'])} [{number(row['logical_gibs_min'])}, {number(row['logical_gibs_max'])}] | "
                f"{number(row['final_bytes_per_logical_byte_median'], 6)} "
                f"[{number(row['final_bytes_per_logical_byte_min'], 6)}, {number(row['final_bytes_per_logical_byte_max'], 6)}] |"
            )
    text.append(
        "Fixed-volume write timing starts with appending to the newly initialized writer and includes final drain and close. "
        "Source loading, initialization and the separate discard warmup are excluded from this rate and retained separately. "
        "Dynamic shard measurements use the distinct coverage-qualified policy with two seconds requested warmup, "
        "three seconds requested append, a 32 GiB logical minimum and at least two generation transitions. "
        "Actual dynamic volumes can differ. The 54-shard geometry has 44.1796875 logical GiB per generation, "
        "so the coverage requirement can extend the measured input substantially."
    )
    text.append(
        "These writer rates characterize drain capacity with preloaded, continuously available input. "
        "Sustained acquisition rates will be lower and need headroom for network and storage variation. "
        "These measurements do not establish a universal headroom percentage or include TIFF decoding and source loading. "
        "The interval includes filesystem I/O completion and close; it does not establish crash-durable storage."
    )
    text.append(
        "Metered shard-write bytes, final file lengths and allocated bytes are recorded separately. "
        "Fixed-volume size ratios use the same logical uint16 input bytes as denominator. "
        "Final file lengths include the store's metadata and shard files; allocated bytes use st_blocks × 512. "
        "Only shared-layout observations have a final-file census here. No final-size ratio is inferred for dynamic shard runs, "
        "and no 10% size threshold or single scalar read winner is imposed."
    )
    if "root/retained-store-accounting.json" in evidence.artifacts:
        text.append(
            "The supplied retained-store-accounting.json preserves the additional per-file length and page-alignment audit, "
            "including its recorded checks of W = sum(ceil(L/A) × A). Consult that audit's explicit equality results; "
            "the exporter does not replace metered writes with final lengths."
        )
    for row in paired:
        text.append(
            f"The paired {row['codec']} {row['comparison']} shard rate ratio has median "
            f"{number(row['rate_ratio_median'])} "
            f"(median rate change {number(100 * (row['rate_ratio_median'] - 1), 2)}%), "
            f"observed range {number(row['rate_ratio_min'])}–{number(row['rate_ratio_max'])}, n={row['n']}. "
            f"Policy {row['policy']}; job {row['job_id']}."
        )
    if drift:
        values = [row["after_over_before"] for row in drift]
        largest_drop = min(drift, key=lambda row: row["after_over_before"])
        text.append(
            f"Across {len(values)} before/after reference pairs, the after/before 15-shard rate ratio has median "
            f"{number(statistics.median(values))} and range {number(min(values))}–{number(max(values))}. "
            "Reference drift is reported separately and is not divided out of the sample measurements."
        )
        if largest_drop["after_over_before"] < 0.9:
            text.append(
                f"The largest reference drop was in round {largest_drop['round']}, job {largest_drop['job_id']}: "
                f"after/before = {number(largest_drop['after_over_before'], 4)} "
                f"({number(largest_drop['before_logical_gibs'])} to "
                f"{number(largest_drop['after_logical_gibs'])} logical GiB/s). "
                "This observed variation limits conclusions about a stable throughput ceiling."
            )
            for row in paired:
                if row["comparison"] == "30/15":
                    text.append(
                        f"The full-series median paired {row['codec']} 30/15 gain is "
                        f"{number(100 * (row['rate_ratio_median'] - 1), 2)}% across {row['n']} pairs. "
                        "It describes these observations and should not be interpreted as a stable ceiling."
                    )
    extension = evidence.extension
    if extension:
        text.append(
            f"The recorded 54-shard extension decision is {extension.get('include_actual54')}; "
            f"the first-three-round median 30/15 ratio was {number(extension.get('median_ratio'))}, "
            f"with {number(extension.get('remaining_s'), 1)} seconds remaining on the measurement deadline. "
            "When enabled, the 54-shard condition has rounds 4–6 only; compare it with the paired 30-shard observations "
            "from those same rounds. This adaptive selection is not six independent repetitions at 54 shards."
        )
    if followup is not None:
        details = followup["audit"]
        text.append(
            "A separate post-primary 30-versus-54 follow-up was chosen after reviewing the complete six-round "
            "primary 30/15 comparison. This later adaptive decision leaves the original first-three-round "
            f"decision ({evidence.extension.get('include_actual54')}) unchanged. "
            "It uses a separate GPU job and a common 96 GiB logical-input minimum for samples and references, "
            "rather than the primary shard series' 32 GiB minimum. Its observations are never pooled with "
            "the primary job or used to change primary sample counts. "
            "[shard-extension-protocol.json](shard-extension-protocol.json) preserves the primary rates and decisions, "
            "the later rationale, binary identity, settings and saved schedule."
        )
        for row in paired:
            if row["comparison"] == "30/15":
                text.append(
                    f"The completed primary {row['codec']} 30/15 comparison used {row['n']} paired rounds and has median "
                    f"{number(row['rate_ratio_median'], 6)}, with observed range "
                    f"{number(row['rate_ratio_min'], 6)}–{number(row['rate_ratio_max'], 6)}. "
                    "This complete-series result motivated the later follow-up; it was not the original extension gate."
                )
        text.append(
            f"The separate follow-up export contains {details['rows']} of {details['expected_rows']} expected records: "
            f"{details['accepted_samples']} of 6 qualified 30/54 samples and "
            f"{details['accepted_references']} of 6 qualified 15-shard before/after references. "
            f"Its coverage is {'complete' if details['complete'] else 'incomplete'}. "
            "[shard-extension-runs.csv](shard-extension-runs.csv) retains every follow-up record, including any failure; "
            "[shard-extension-validation.json](shard-extension-validation.json) records missing or duplicate slots. "
            "The matched 54/30 rate ratios and 15-shard reference drift are separate from all primary summaries."
        )
        for row in followup["pair_summary"]:
            text.append(
                f"In the post-primary follow-up, the paired 54/30 logical-rate ratio has median "
                f"{number(row['rate_ratio_median'], 6)}, observed range "
                f"{number(row['rate_ratio_min'], 6)}–{number(row['rate_ratio_max'], 6)}, n={row['n']}, "
                f"GPU job {row['job_id']}. These are observed repetitions of the later selected comparison, "
                "not an independently prespecified extension of the six-round primary study."
            )
    text.append(
        "Changing shard count changes realizable grouping, append-axis extent and work per file. "
        "These comparisons do not isolate an abstract file-count effect, establish a universal optimum, "
        "or establish a causal relationship with NFS nconnect. Worker, output-buffer and per-file limits, "
        "the recorded machine and the recorded mount belong to the result."
    )
    if reads:
        text += [
            "Read summaries below use useful uint16 source GiB/s, not float32 output bandwidth. "
            "The complete read-summary.csv also retains policy, trace and machine identities.",
            "| Layout | Backend | Workload | n | Useful GiB/s median [min, max] |",
            "|---|---|---|---:|---:|",
        ]
        for row in sorted(reads, key=lambda r: (r["workload"], r["backend"], r["chunk_kib"], r["group_id"])):
            text.append(
                f"| {row['layout_id']} | {row['backend']} | {row['workload']} | {row['n']} | "
                f"{number(row['useful_source_gib_per_second_median'])} "
                f"[{number(row['useful_source_gib_per_second_min'])}, {number(row['useful_source_gib_per_second_max'])}] |"
            )
    text.append(
        "Readers assemble contiguous host float32 output, whose bytes are exactly twice the useful uint16 selection bytes. "
        "Active read/assembly time excludes source loading, validation, Python selection preparation, index warming and client eviction. "
        "File-scoped client eviction is checked before each pass; metadata and shard indexes are warm and server cache state is uncontrolled. "
        "Shared mount counters can include other processes and are not server disk bytes. Decoded-byte and decoded-amplification counters "
        "are available for Damacy only; TensorStore entries remain blank. Process peak RSS is not a measured-interval peak. "
        "Aligned and translated 512-pixel traces have separate identities and coverage; their paired comparison remains separate."
    )
    text.append(
        "The initial native writer emitted uint16 fill_value as 0.0. Damacy rejected that metadata before codec decoding. "
        "The retained metadata-only diagnosis restored reads by changing the spelling to integer zero; direct Blosc samples matched. "
        "The isolated writer-fill-value.patch changes metadata spelling without changing encoded pixels or the codec. "
        "Native writer source/binary identities were recorded after rebuilding; no additional reader patch was needed for this repair. "
        "The reader retains the pre-existing CPU codec and benchmark instrumentation changes in "
        "[reader.patch](reader.patch), documented in [reader-source.md](reader-source.md). "
        f"The [official Zarr data-type specification]({SPEC_URL}) requires integer fill values without a fraction or exponent. "
        "Original failures, diagnosis records and the narrow repair are retained in the provenance archive."
    )
    text.append(
        "Plots show medians with observed ranges and expose their numerical inputs in the corresponding figure-data CSVs. "
        "The joint table connects the writer and both readers for translated-256 and full-scan workloads; "
        "a blank joint value means missing or multiple incomparable reader groups, not zero throughput."
    )
    paragraphs = []
    for index, line in enumerate(text):
        if line.startswith("|"):
            if index and not text[index - 1].startswith("|"):
                paragraphs.append("")
            paragraphs.append(line)
        else:
            if paragraphs:
                paragraphs.append("")
            paragraphs.append(line)
    (output / "findings.md").write_text("\n".join(paragraphs) + "\n")


def export(evidence, output, plots):
    writes = writer_rows(evidence)
    supplementary = interrupted_shard_rows(evidence)
    reads, read_cases, event_counts = reader_rows(evidence)
    write_keys = (
        "experiment", "series", "case_id", "policy", "job_id", "backend", "destination",
        "chunk_bytes", "chunk_kib", "chunk_shape", "shard_shape", "chunks_per_shard",
        "raw_shard_bytes", "actual_layer_shards", "target_shards", "codec",
        "blosc_block_bytes", "shuffle", "level_hint",
    )
    write_summary = summaries([row for row in writes if row["primary"]], write_keys, WRITE_METRICS)
    followup = post_primary_extension(evidence, write_keys)
    shared = [row for row in write_summary if row["experiment"] == "shared-layouts"]
    shards = [row for row in write_summary if row["experiment"] == "shard-count"]
    read_keys = (
        "phase", "policy_id", "trace_sha256", "machine_id", "hostname", "job_id",
        "layout_id", "backend", "workload", "chunk_bytes", "chunk_kib", "chunk_shape",
    )
    read_summary = summaries([row for row in reads if row["primary"]], read_keys, READ_METRICS)
    shard_pairs = paired_shards(writes)
    pair_summary = summaries(
        shard_pairs, ("comparison", "numerator_shards", "denominator_shards", "policy", "job_id", "codec"),
        ("rate_ratio",),
    )
    drift = reference_drift(writes)
    alignment = aligned_pairs(reads)
    alignment_summary = summaries(
        alignment, ("layout_id", "backend", "policy_id", "machine_id", "chunk_kib",
                    "aligned_trace_sha256", "translated_trace_sha256"),
        ("aligned_over_translated_rate", "aligned_useful_gibs", "translated_useful_gibs"),
    )
    audit = coverage(evidence, writes, reads, read_cases)
    audit["reader_event_counts"] = event_counts
    audit["supplementary_interrupted_shard_rows"] = len(supplementary)
    audit["supplementary_interrupted_shard_qualified"] = sum(row["accepted"] for row in supplementary)
    audit["supplementary_interrupted_shard_failed"] = sum(row["status"] != "pass" for row in supplementary)
    if followup is not None:
        audit["post_primary_shard_extension"] = followup["audit"]
    audit["raw_compressed_bytes"] = sum(path.stat().st_size for path in (evidence.directory / "raw").iterdir() if path.is_file())
    audit["raw_over_15_MiB"] = audit["raw_compressed_bytes"] > 15 * (1 << 20)
    tables = {
        "write-runs.csv": writes, "write-summary.csv": write_summary,
        "shared-layout-summary.csv": shared, "shard-summary.csv": shards,
        "shard-paired-ratios.csv": shard_pairs, "shard-paired-summary.csv": pair_summary,
        "write-references.csv": [row for row in writes if row["accepted"] and row["role"] in ("reference-before", "reference-after")],
        "write-reference-drift.csv": drift, "read-runs.csv": reads,
        "read-cases.csv": read_cases, "read-summary.csv": read_summary,
        "read-alignment-pairs.csv": alignment, "read-alignment-summary.csv": alignment_summary,
        "joint-layouts.csv": joint_rows(shared, read_summary),
        "supplementary-interrupted-shards.csv": supplementary,
    }
    for name, rows in tables.items():
        write_csv(output / name, rows)
    figures = figure_data(shared, read_summary, shards, pair_summary)
    for name, rows in figures.items():
        write_csv(output / f"{name}-figure-data.csv", rows)
    if plots:
        plot_figures(output, figures)
    if followup is not None:
        write_extension_outputs(output, evidence, followup, plots)
    write_json(output / "validation.json", audit)
    write_findings(output, evidence, audit, shared, read_summary, pair_summary, drift, followup)
    for name in (
        "retained-store-accounting.json", "source-phases.json", "restarted-shards.json",
        "input-source.json", "size-accounting.md", "allocation-ledger.json",
        "reader.patch", "reader-source.md", "run_cpu_build.sh",
    ):
        if "root/" + name in evidence.artifacts:
            (output / name).write_bytes(evidence.artifacts["root/" + name])
    metadata = {
        "schema_version": 1, "source_root": evidence.bundle["study_root"],
        "writer_attempt": evidence.bundle["writer_attempt"],
        "reader_output": evidence.bundle["reader_output"],
        "plan": evidence.plan, "provenance": evidence.json("root/provenance.json", {}),
        "writer_identity": evidence.json("root/writer-identity.json", {}),
        "source_phases": evidence.json("root/source-phases.json", {}),
        "shard_restart": evidence.json("root/restarted-shards.json", {}),
        "input_source": evidence.json("root/input-source.json", {}),
        "reader_run": evidence.read_run,
        "writer_policy_scope": "New fixed-volume and dynamic coverage-qualified phases remain separate.",
        "size_ratios": "Bytes divided by the observation's logical uint16 input bytes; source integers retained.",
        "summary_definition": "Median, minimum and maximum of individual qualified observations, with n per metric.",
        "read_acceptance": "One matching result and successful case_finished, returncode zero, matching identity.",
        "nfs_causality": "No causal nconnect attribution or universal shard/chunk optimum.",
        "external_arrays": evidence.json("root/read-manifest.json", {}).get("layouts", []),
        "plots_generated": plots,
    }
    if followup is not None:
        metadata["post_primary_shard_extension"] = {
            "audit": followup["audit"], "protocol": followup["protocol"],
            "protocol_source": "raw/provenance.tar.gz!" + followup["protocol_name"],
            "records_source": "raw/provenance.tar.gz!" + followup["records_name"],
            "included_in_primary": False,
        }
    write_json(output / "metadata.json", metadata)
    (output / "README.md").write_text(
        "BBBC022 measured evidence\n\n"
        "See [findings](findings.md), [validation and completeness](validation.json), "
        "[joint layout table](joint-layouts.csv), [write summaries](write-summary.csv), "
        "[read summaries](read-summary.csv), and [paired shard ratios](shard-paired-summary.csv). "
        "Figures are PNG and editable SVG; every figure has a CSV of its plotted observations.\n\n"
        "The input is sixteen mock-control fields from plate 20585, site 1, channel w5 of "
        "[BBBC022v1](https://bbbc.broadinstitute.org/BBBC022), "
        "Gustafsdottir and colleagues' U2OS Cell Painting experiment in the Broad Bioimage Benchmark Collection. "
        "The source images are CC0. [input-source.json](input-source.json) records the exact selection and TIFF hashes.\n\n"
        "Raw writer observations and reader events are preserved under raw/ as deterministic gzip streams "
        "(mtime zero). raw/provenance.tar.gz contains only selected text metadata, configurations, "
        "traces, schedules, source identities, patches, scripts, helpers and logs. "
        "bundle.json lists every bundled artifact and checksum. Pixel stores, source image payloads "
        "and compiled binaries remain outside this bundle; their original paths and identities are retained.\n\n"
        "Regenerate summaries and figures without cluster originals using Python 3.11+ and Matplotlib:\n\n"
        "~~~bash\npython3 export_evidence.py --from-bundle . --output regenerated\n~~~\n\n"
        "Use --no-plots for standard-library-only table regeneration. To collect the original run, use:\n\n"
        "~~~bash\npython3 export_evidence.py --root STUDY_ROOT --reads READER_OUTPUT --output EVIDENCE_OUTPUT\n~~~\n\n"
        "The exporter opens recorded text files only. It does not inspect pixel stores, execute native benchmarks, "
        "allocate cluster resources, or change the historical readable-zarrs-evidence archive. "
        "Collection, compression and plotting should run on a compute allocation. "
        "Unqualified and provisional observations remain in raw records; read-cases.csv records failed and missing cases. "
        "An incomplete export is labeled incomplete rather than padded with expected results.\n"
        + (
            "\nThe [post-primary shard follow-up](shard-extension-summary.csv) has separate "
            "[54/30 paired ratios](shard-extension-paired-ratios.csv), "
            "[references](shard-extension-references.csv), "
            "[protocol](shard-extension-protocol.json) and "
            "[validation](shard-extension-validation.json). It was selected after reviewing all six primary rounds "
            "and uses a separate job with a 96 GiB logical minimum. It does not alter the primary extension decision, "
            "counts or summaries. These extra outputs are enabled only by the archived shard-extension-complete.txt marker.\n"
            if followup is not None else ""
        )
        + (
            "\n[Size accounting](size-accounting.md) explains the relation between metered writes, "
            "final file lengths, alignment and metadata for the retained stores.\n"
            if "root/size-accounting.md" in evidence.artifacts else ""
        )
        + (
            "\n[Allocation ledger](allocation-ledger.json) preserves the recorded Slurm jobs and resource use.\n"
            if "root/allocation-ledger.json" in evidence.artifacts else ""
        )
        + (
            "\n[Reader source](reader-source.md) identifies the base revision and single cumulative patch "
            "that reproduce all 310 frozen native source hashes.\n"
            if "root/reader-source.md" in evidence.artifacts else ""
        )
    )
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--root", type=Path)
    source.add_argument("--from-bundle", type=Path)
    parser.add_argument("--reads", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.root:
        require(args.reads is not None, "--reads is required with --root")
        make_bundle(args.root.resolve(), args.reads.resolve(), output)
    else:
        previous = args.from_bundle.resolve()
        require((previous / "bundle.json").is_file(), "Portable bundle is missing bundle.json")
        if previous != output:
            (output / "raw").mkdir(exist_ok=True)
            shutil.copyfile(previous / "bundle.json", output / "bundle.json")
            for path in (previous / "raw").iterdir():
                if path.is_file():
                    shutil.copyfile(path, output / "raw" / path.name)
    script = Path(__file__).resolve()
    if script != output / "export_evidence.py":
        shutil.copyfile(script, output / "export_evidence.py")
    audit = export(Evidence(output), output, not args.no_plots)
    generated = {}
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "output-checksums.json":
            generated[path.name] = sha256(path)
    write_json(output / "output-checksums.json", generated)
    print(json_text({
        "output": str(output), "writer_complete": audit["writer_complete"],
        "reader_complete": audit["reader_complete"],
        "writer_shared_samples": audit["writer_accepted_shared_samples"],
        "writer_shard_samples": audit["writer_accepted_shard_samples"],
        "reader_accepted": audit["reader_accepted_primary"],
        "raw_compressed_bytes": audit["raw_compressed_bytes"],
    }))


if __name__ == "__main__":
    main()
