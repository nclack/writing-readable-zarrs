import argparse
import ast
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median


GIB = 1 << 30
PR160 = "5126f0958c0be3922a0a00c49d127ba62ddbc6a9"
PR164 = "ec2a6ed0ee1468e41eb70ee19eee6101f9dbbeb2"
PR168 = "8d0931e7d131fd5d4c565458736ab586012c78c1"
CHUNKS = {16: [1, 64, 128], 32: [1, 128, 128], 64: [1, 128, 256],
          128: [1, 256, 256], 256: [2, 256, 256], 512: [1, 512, 512],
          1024: [8, 256, 256]}
GROUP_FIELDS = ["phase", "machine", "reader", "revision", "implementation",
                "storage_type", "content_id", "workload", "selection_shape",
                "cache_policy", "timing_policy", "output_dtype", "output_device",
                "decode_workers", "file_workers", "read_buffer_chunks",
                "queries_per_pass", "samples_per_batch", "query_reference_sha256",
                "seed", "byte_domain"]
CONFIG_FIELDS = ["comparison_group", "configuration_id", "chunk_shape", "shard_shape",
                 "codec", "block_bytes", "array_shape", "array_count"]
METRICS = ["primary_gib_s", "output_active_gib_s", "output_wall_gib_s",
           "useful_active_gib_s", "useful_wall_gib_s", "storage_active_gib_s",
           "storage_wall_gib_s", "decoded_amplification", "modeled_decoded_amplification",
           "encoded_amplification", "storage_amplification", "nfs_payload_gib_s",
           "compression_ratio", "seconds", "active_seconds", "samples_per_second",
           "process_peak_rss_bytes"]


def compact(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def digest_value(value):
    return hashlib.sha256(compact(value).encode()).hexdigest()


def num(value):
    if value is None or value == "":
        return None
    return float(value)


def div(a, b):
    return None if a is None or b is None or b == 0 else a / b


def rate(a, seconds):
    result = div(a, seconds)
    return None if result is None else result / GIB


def csv_value(value):
    if value is None:
        return ""
    if isinstance(value, (list, dict, tuple)):
        return compact(value)
    return value


def write_csv(path, rows):
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys, lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: csv_value(v) for k, v in row.items()} for row in rows)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


class ReadExport:
    def __init__(self, home, output):
        self.home = home
        self.output = output
        self.rows = []
        self.sources = {}
        self.metadata = {}
        self.shared_metadata = {}
        self.duplicates = {}
        self.json_cache = {}
        self.log_runs = {}
        self.families = []
        self.attempts = []
        self.exclusions = []
        self.constant_cache = {}

    def record(self, path, role, phase=None, status=None):
        path = Path(path)
        key = str(path)
        if key not in self.sources:
            entry = {"source_file": key, "role": role, "phase": phase, "status": status}
            if path.is_file():
                data = path.read_bytes()
                entry.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            else:
                entry.update(bytes=None, sha256=None, status="missing")
            self.sources[key] = entry
        return self.sources[key]

    def read(self, path, role="metadata", phase=None):
        path = Path(path)
        if not path.is_file():
            return {}
        key = str(path)
        if key not in self.json_cache:
            self.record(path, role, phase)
            self.json_cache[key] = json.loads(path.read_text())
        return self.json_cache[key]

    def metadata_id(self, value):
        ident = digest_value(value)[:24]
        self.metadata[ident] = value
        return ident

    def shared_id(self, kind, value):
        ident = digest_value([kind, value])[:24]
        self.shared_metadata[ident] = {"kind": kind, "value": value}
        return ident

    def job_context(self, path, expected_id=None):
        job = next((p for p in path.parents if re.fullmatch(r"(?:[a-z-]*job)-\d+", p.name)), None)
        if job and expected_id and not job.name.endswith("-" + str(expected_id)):
            original = list(job.parent.glob("*job-" + str(expected_id)))
            if len(original) == 1:
                job = original[0]
        result = {"job_directory": str(job) if job else None}
        if job:
            for name in ["started.txt", "finished.txt", "exit-code.txt", "filesystem.txt",
                         "local-filesystem.txt", "nfs-filesystem.txt", "slurm-job.txt"]:
                p = job / name
                if p.is_file():
                    self.record(p, "job_provenance")
                    result[name] = p.read_text().strip()
        return result

    def nearby(self, path, names):
        for parent in path.parents:
            for name in names:
                candidate = parent / name
                if candidate.is_file():
                    yield candidate
            if parent == self.home / "tmp":
                return

    def constants(self, path):
        if path in self.constant_cache:
            return self.constant_cache[path]
        values = {}
        if path:
            self.record(path, "frozen_measurement_source")
            for node in ast.parse(path.read_text()).body:
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {"CHUNKS", "SEED", "SHARD_SHAPE"} for t in node.targets):
                    try:
                        values[node.targets[0].id] = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        pass
        self.constant_cache[path] = values
        return values

    def find_audit(self, path):
        for p in path.parents:
            if (p / "audit.json").is_file():
                return p / "audit.json"
            if p.name in {"results", "patterns", "preflight", "xor-results"}:
                break
        return None

    def append(self, row, identity):
        row["run_id"] = digest_value([row["source_file"], row["source_record"]])[:24]
        if identity in self.duplicates:
            row["duplicate_of_run_id"] = self.duplicates[identity]
            row["original_status"] = row["status"]
            row["status"] = "duplicate_export"
        else:
            self.duplicates[identity] = row["run_id"]
            row["duplicate_of_run_id"] = None
        if not row.get("machine"):
            row["comparison_scope"] = "unknown machine; each source run kept separate"
            missing_machine = row["run_id"]
        else:
            row["comparison_scope"] = "same phase, machine, reader mode, input, trace, resources, storage and timing"
            missing_machine = None
        group = [csv_value(row.get(k)) for k in GROUP_FIELDS] + [missing_machine]
        row["comparison_group"] = digest_value(group)[:20]
        config = [csv_value(row.get(k)) for k in CONFIG_FIELDS]
        row["summary_id"] = digest_value(config)[:20]
        self.rows.append(row)

    def modern(self, path, phase, fallback_revision, objective, status):
        path = Path(path)
        data = self.read(path, "raw_measurements", phase)
        if not isinstance(data, dict) or not isinstance(data.get("measurements"), list):
            return
        audit_path = self.find_audit(path)
        audit = self.read(audit_path, "encoding_audit", phase) if audit_path else {}
        case = data.get("case", {})
        settings = data.get("backend_settings", {})
        environment = data.get("environment", {})
        native = data.get("native_identity") or {}
        geometry = {k: v for k, v in data.get("geometry", {}).items() if k != "required_chunk_ranges"}
        storage = data.get("storage", {})
        mount = storage.get("mount", {})
        reader = data.get("backend", "damacy")
        revision = (native.get("revision") or fallback_revision) if reader == "damacy" else settings.get("version")
        if reader == "tensorstore" and not revision:
            revision = environment.get("versions", {}).get("tensorstore")
        shards = audit.get("shards", [])
        original = phase.startswith("pr160-")
        manifest_path = next(self.nearby(path, ["manifest.json"]), None)
        manifest = self.read(manifest_path, "experiment_manifest", phase) if manifest_path else {}
        if not isinstance(manifest, dict):
            manifest = {}
        source_path = next(self.nearby(path, ["sources/cpu_pareto.py", "repo/bench/cpu_pareto.py"]), None)
        source_constants = self.constants(source_path)
        source_hashes = [s.get("source_sha256") for s in shards]
        content_id = digest_value(source_hashes) if source_hashes and all(source_hashes) else None
        chunk_bytes = case.get("chunk_kib", 0) * 1024 or None
        chunk_shape = manifest.get("chunk_shapes", {}).get(str(case.get("chunk_kib"))) or source_constants.get("CHUNKS", CHUNKS).get(case.get("chunk_kib"))
        array_shape = data.get("volume_shape") or audit.get("shape")
        shard_shape = data.get("shard_shape") or audit.get("shard_shape") or audit.get("shape")
        workload = data.get("workload", "full-scan")
        if original and (case.get("group") == "input_check" or phase.endswith("-patterns")):
            objective = "no scalar winner recorded; input/codec control; exported frontiers are descriptive"
        shape = data.get("sample_shape")
        cache = data.get("cache", "warm")
        storage_type = storage.get("tier", "local")
        job = self.job_context(path, environment.get("slurm_job_id"))
        if status == "ok" and data.get("diagnostic_only"):
            status = "trace_only"
        if "concurrency" in path.parts:
            status = "trace_only" if status == "ok" else status
        if cache == "cold":
            cache_policy = "zero client file residency before every pass; within-pass reuse allowed"
            if storage_type == "nfs":
                cache_policy += "; server cache uncontrolled"
        else:
            cache_policy = "warm file cache; no decoded-data cache"
        if original and cache == "cold":
            timing = "complete wall including file eviction and residency checks"
        elif original:
            timing = "active read loop after one correctness/warmup pass"
        else:
            timing = "active planning, reads, decode, dtype conversion and assembly; preparation/cache control excluded"
        if workload == "full-scan":
            sampling = "nonoverlapping tiles cover complete logical array; no edge padding for recorded shapes"
            alignment = "full coverage; repeated identical passes"
        elif workload == "aligned":
            sampling = "fixed 256-grid XY origins; random Z planes; crop extent unchanged"
            alignment = "XY aligned to 256; Z not generally aligned to depth>1 chunks"
        else:
            sampling = ("round-robin independent arrays; uniform valid XY starts and random Z planes" if original else
                        "round-robin shard start regions; uniform valid XY start within each region; random Z plane")
            alignment = "translated; repeated identical query list each pass; overlap allowed"
        query_count = data.get("query_count")
        if query_count is None and shape and audit.get("logical_bytes") is not None:
            query_count = audit["logical_bytes"] // (math.prod(shape) * 2)
        useful_source = data.get("raw_volume_bytes", audit.get("logical_bytes"))
        metadata = {"job_ref": self.shared_id("job", job), "environment_ref": self.shared_id("environment", environment),
                    "native_identity_ref": self.shared_id("native_identity", native or None),
                    "backend_settings_ref": self.shared_id("backend_settings", settings), "geometry": geometry,
                    "storage_ref": self.shared_id("storage", storage),
                    "audit_file": str(audit_path) if audit_path else None,
                    "source_hashes": source_hashes,
                    "encoded_shard_hashes": [s.get("sha256") for s in shards],
                    "chunk_shape_source": str(source_path) if source_path else str(manifest_path),
                    "manifest_file": str(manifest_path) if manifest_path else None,
                    "measurements_file": str(path), "warmups_individually_timed": False}
        metadata_id = self.metadata_id(metadata)
        for index, measurement in enumerate(data["measurements"]):
            stats = measurement.get("stats", {})
            decode = stats.get("decode", {})
            assemble = stats.get("assemble", {})
            io = stats.get("io", {})
            useful = measurement.get("useful_bytes", measurement.get("logical_bytes"))
            output = measurement.get("output_bytes", assemble.get("output_bytes"))
            decoded = measurement.get("decoded_bytes", decode.get("output_bytes"))
            encoded = measurement.get("encoded_bytes", decode.get("input_bytes"))
            wall = measurement.get("seconds")
            active = measurement.get("active_read_seconds", wall)
            process_bytes = measurement.get("storage_bytes")
            physical = process_bytes if storage_type != "nfs" else None
            physical_active = measurement.get("active_storage_bytes", physical) if storage_type != "nfs" else None
            output_wall = rate(output, wall)
            output_active = rate(output, active)
            primary = output_wall if original else output_active
            reported_primary = measurement.get("output_float32_active_gib_s") if not original else measurement.get("float32_gib_s", measurement.get("output_gib_s"))
            reported_basis = "output_float32_active_gib_s" if not original else "float32_gib_s or output_gib_s"
            if original and reported_primary is None and measurement.get("useful_gib_s") is not None:
                reported_primary = 2 * measurement["useful_gib_s"]
                reported_basis = "2 * useful_gib_s (uint16 to float32)"
            repeat = next((int(p.split("-")[1]) for p in reversed(path.parts) if re.fullmatch(r"repeat-\d+", p)), measurement.get("repeat"))
            order_path = next(self.nearby(path, ["run-order.json"]), None)
            order = self.read(order_path, "execution_schedule", phase) if order_path else []
            selected_order = None
            if isinstance(order, list):
                expected = {**case, "implementation": data.get("implementation", reader), "repeat": repeat, "workload": workload, "cache": cache, "storage": storage_type, "storage_tier": storage_type}
                candidates = [i + 1 for i, point in enumerate(order) if isinstance(point, dict) and all(expected.get(k) == v for k, v in point.items() if k in expected)]
                if len(candidates) == 1:
                    selected_order = candidates[0]
            pass_details = measurement.get("pass_details", [])
            residency = [page for detail in pass_details for page in detail.get("resident_pages_before", [])]
            row = {
                "source_file": str(path), "source_record": f"/measurements/{index}",
                "source_sha256": self.sources[str(path)]["sha256"], "metadata_id": metadata_id,
                "phase": phase, "configuration_id": "-".join(str(case.get(k, "unknown")) for k in ["input", "codec", "chunk_kib", "block_kib"]),
                "case_group": case.get("group"),
                "reader": reader, "revision": revision, "binary_sha256": native.get("native_sha256"),
                "implementation": data.get("implementation", reader),
                "date_start": job.get("started.txt"), "date_end": job.get("finished.txt"),
                "run_order": selected_order, "order_source": str(order_path) if order_path else None,
                "repeat": repeat, "machine": environment.get("hostname"), "slurm_job_id": environment.get("slurm_job_id"),
                "backend": "CPU", "allocated_physical_cores": environment.get("physical_cores"),
                "storage_type": "NFS" if storage_type == "nfs" else "local block storage",
                "storage_destination": storage.get("files", [{}])[0].get("path") if storage.get("files") else None,
                "mount_options": mount.get("options"), "mount_source": mount.get("source"),
                "nconnect": int(re.search(r"(?:^|,)nconnect=(\d+)", mount.get("options", "")).group(1)) if re.search(r"(?:^|,)nconnect=(\d+)", mount.get("options", "")) else None,
                "input_kind": "synthetic", "content": case.get("input"), "content_id": content_id,
                "source_dtype": "uint16", "array_shape": array_shape,
                "array_count": len(shards) if original else 1, "logical_volume_bytes": useful_source,
                "chunk_shape": chunk_shape, "raw_chunk_bytes": chunk_bytes, "chunk_byte_definition": "uncompressed uint16 capacity",
                "shard_shape": shard_shape, "shard_grid": data.get("shard_grid", audit.get("shard_grid")),
                "raw_shard_bytes": math.prod(shard_shape) * 2 if shard_shape else None,
                "shard_byte_definition": "uncompressed uint16 capacity", "shard_count": len(shards) or None,
                "codec": case.get("codec"), "codec_level": 3, "shuffle": "bitshuffle",
                "block_bytes": case.get("block_kib", 0) * 1024 or None,
                "effective_block_bytes": sorted({v for s in shards for v in s.get("actual_block_bytes", [])}) or None,
                "codec_split_mode": "never", "workload": workload, "selection_shape": shape,
                "axes": "ZYX", "origin_distribution": sampling, "alignment": alignment,
                "seed": manifest.get("query_seed", 20260916 + 2000 if not original else None),
                "query_reference_sha256": data.get("references_sha256"), "queries_per_pass": query_count,
                "samples_per_batch": data.get("samples_per_batch"), "passes": measurement.get("passes"),
                "sample_count": query_count * measurement["passes"] if query_count is not None and measurement.get("passes") is not None else None,
                "decode_workers": data.get("workers"), "file_workers": data.get("io_workers"),
                "read_buffer_chunks": settings.get("read_buffer_chunks"), "input_buffers": settings.get("input_buffers"),
                "request_concurrency": settings.get("outstanding_batches"),
                "read_coalescing": "benchmark/revision dependent; frozen settings and geometry in metadata",
                "min_shards_per_batch": geometry.get("min_shards_per_batch"), "max_shards_per_batch": geometry.get("max_shards_per_batch"),
                "cache_policy": cache_policy, "decoded_cache_bytes": settings.get("decoded_cache_bytes"),
                "page_residency_max_before": max(residency) if residency else None,
                "warmup_passes": data.get("warmup_full_passes", data.get("warmup_full_scans")),
                "warmup_policy": "one full correctness/warmup pass outside timing" if original and cache == "warm" else "correctness checks, metadata/index preparation and cache control outside active reads",
                "output_dtype": settings.get("output_dtype", "float32"), "output_device": "host memory",
                "timing_policy": timing, "seconds": wall, "active_seconds": active,
                "cache_control_seconds": measurement.get("cache_control_seconds"),
                "useful_logical_bytes": useful, "output_bytes": output, "decoded_chunk_bytes": decoded,
                "encoded_payload_bytes": encoded, "reader_bytes": measurement.get("reader_bytes", io.get("input_bytes")),
                "index_bytes_transferred": None, "stored_index_bytes": sum(s.get("index_bytes", 0) for s in shards) if shards else None,
                "stored_shard_bytes": audit.get("stored_bytes", data.get("stored_bytes")),
                "compression_ratio": audit.get("compression_ratio", data.get("compression_ratio")),
                "process_read_bytes_diagnostic": process_bytes, "storage_bytes": physical,
                "storage_active_bytes": physical_active, "storage_counter_scope": "process local block reads" if storage_type != "nfs" else "unavailable; shared NFS payload reported separately",
                "nfs_payload_read_bytes": measurement.get("nfs_payload_read_bytes") if storage_type == "nfs" else None,
                "nfs_payload_gib_s": measurement.get("nfs_payload_gib_s") if storage_type == "nfs" else None,
                "shared_nfs_payload_per_useful_byte": div(measurement.get("nfs_payload_read_bytes"), useful) if storage_type == "nfs" else None,
                "nfs_counter_scope": storage.get("nfs_counter_scope") if storage_type == "nfs" else None,
                "nfs_read_rtt_ms": measurement.get("nfs_read_rtt_ms") if storage_type == "nfs" else None,
                "nfs_idle_fraction_of_active": measurement.get("nfs_idle_fraction_of_active") if storage_type == "nfs" else None,
                "primary_gib_s": primary, "byte_domain": "returned float32 output",
                "reported_primary_gib_s": reported_primary, "reported_primary_basis": reported_basis,
                "source_unit": "GiB/s", "output_active_gib_s": output_active, "output_wall_gib_s": output_wall,
                "useful_active_gib_s": rate(useful, active), "useful_wall_gib_s": rate(useful, wall),
                "storage_active_gib_s": rate(physical_active, active), "storage_wall_gib_s": rate(physical, wall),
                "decoded_amplification": div(decoded, useful), "encoded_amplification": div(encoded, useful),
                "modeled_decoded_amplification": measurement.get("geometric_decoded_per_useful_byte", geometry.get("read_amplification")),
                "modeled_encoded_bytes": measurement.get("geometric_encoded_bytes"),
                "storage_amplification": div(physical_active, useful),
                "samples_per_second": div(query_count * measurement["passes"], active) if query_count is not None and measurement.get("passes") is not None else None,
                "process_peak_rss_bytes": data.get("peak_rss_bytes"),
                "memory_scope": "ru_maxrss for measurement process including setup and all repetitions; not a conversion peak",
                "frontier_objective": objective, "winner_selection": "undefined; no recorded scalar read winner rule",
                "status": status, "exclusion_reason": None if status == "ok" else status,
                "limitations": "synthetic content; no training/viewer timing; observed ranges are not confidence intervals",
            }
            if reader == "tensorstore":
                row["encoded_payload_bytes"] = None
                row["encoded_amplification"] = None
                row["modeled_encoded_bytes"] = measurement.get("geometric_encoded_bytes")
            self.append(row, (self.sources[str(path)]["sha256"], index))
        self.sources[str(path)]["measurement_count"] = len(data["measurements"])
        self.sources[str(path)]["status"] = status
        self.json_cache.pop(str(path), None)

    def collect_modern(self):
        base = self.home / "tmp/2026-09-16-damacy-pr160-pareto"
        specs = [
            (base / "job-3715528/results", "pr160-warm-baseline", PR160, "maximize compression and useful throughput", "ok"),
            (base / "amplification-job-3716180/results", "pr160-warm-random-crops", PR160, "minimize encoded/useful bytes and maximize useful throughput", "ok"),
            (base / "amplification-job-3716180/xor-results", "pr160-warm-xor-crops", PR160, "minimize encoded/useful bytes and maximize useful throughput", "ok"),
            (base / "amplification-job-3716180/patterns", "pr160-warm-patterns", PR160, "maximize compression and useful throughput", "ok"),
            (base / "smooth-job-3716593/results", "pr160-warm-smooth-crops", PR160, "minimize encoded/useful bytes and maximize useful throughput", "ok"),
            (base / "smooth-job-3716593/patterns", "pr160-warm-smooth-patterns", PR160, "maximize compression and useful throughput", "ok"),
            (base / "storage-job-3717912/results", "pr160-cold-storage", PR160, "minimize storage/useful bytes and maximize useful throughput", "ok"),
            (base / "storage-job-3717174/results", "pr160-cold-storage", PR160, "minimize storage/useful bytes and maximize useful throughput", "ok"),
            (base / "storage-job-3717813/results", "pr160-cold-storage", PR160, "minimize storage/useful bytes and maximize useful throughput", "ok"),
            (base / "storage-job-3717755/results", "pr160-cold-excluded-node", PR160, "none", "excluded_other_node"),
        ]
        recent = [
            ("2026-09-23-damacy-pr160-shard-grid", "job-3804241", "cpu-fixed-layout-pilot", PR160, "none; fixed layout"),
            ("2026-09-23-damacy-pr160-shard-grid", "job-3804536", "cpu-fixed-layout-pilot", PR160, "none; fixed layout"),
            ("2026-09-23-damacy-pr164-before-after", "job-3806589", "cpu-scheduling-paired", PR164, "none; fixed layout"),
            ("2026-09-24-damacy-cold-readahead", "job-3808884", "cpu-readahead-control", PR164, "none; fixed layout"),
            ("2026-09-24-damacy-cpu-read-buffers", "job-3810330", "cpu-buffer-control", PR164, "none; fixed layout"),
            ("2026-09-24-damacy-cold-chunks", "job-3811387", "cpu-small-chunks", PR168, "maximize compression and output throughput; original traffic frontier retained separately"),
            ("2026-09-24-damacy-cold-blocks", "job-3822266", "cpu-chunk-blocks", PR168, "maximize compression and output throughput"),
            ("2026-09-25-damacy-nfs-spot", "job-3832563", "cpu-nfs-local-spot", PR168, "no recorded winner; exploratory compression/output frontier over four encodings"),
        ]
        for folder, job, phase, revision, objective in recent:
            root = self.home / "tmp" / folder / job
            specs.append((root / "results", phase, revision, objective, "ok"))
            specs.append((root / "preflight", phase, revision, objective, "preflight"))
        for job in ["job-3803792", "job-3803936"]:
            specs.append((self.home / "tmp/2026-09-23-damacy-pr160-shard-grid" / job / "results", "cpu-fixed-layout-superseded", PR160, "none; failed pilot allocation", "excluded_superseded_pilot"))
        for job in ["job-3715459", "job-3715509", "job-3715528", "amplification-job-3716180", "smooth-job-3716593"]:
            for name in ["preflight", "pattern-preflight", "xor-preflight", "query-preflight"]:
                root = base / job / name
                if root.is_dir():
                    specs.append((root, "pr160-preflight", PR160, "none; correctness/preflight", "preflight"))
        for root, phase, revision, objective, status in specs:
            files = sorted(root.rglob("measurements.json")) if root.is_dir() else []
            self.families.append({"phase": phase, "raw_root": str(root), "status": status,
                                  "measurement_files": len(files), "metadata_bytes": sum(p.stat().st_size for p in files),
                                  "frontier_objective": objective, "revision_fallback": revision})
            for path in files:
                self.modern(path, phase, revision, objective, status)
            for path in sorted(root.rglob("attempts.json")) if root.is_dir() else []:
                attempts = self.read(path, "attempt_status", phase)
                self.sources[str(path)]["attempts"] = attempts
                if isinstance(attempts, list):
                    for i, attempt in enumerate(attempts):
                        state = attempt.get("status") if isinstance(attempt, dict) else None
                        if not state and isinstance(attempt, dict) and "returncode" in attempt:
                            state = "attempt_completed" if attempt["returncode"] == 0 else "attempt_failed"
                        self.attempts.append({"source_file": str(path), "source_record": f"/{i}", "phase": phase, "attempt": attempt, "status": state or "recorded_attempt", "performance_row": False})
        folders = [base] + [self.home / "tmp" / value[0] for value in recent]
        for folder in dict.fromkeys(folders):
            for path in sorted(folder.glob("*.md")) + sorted(folder.glob("*ledger*.json")) + sorted(folder.glob("completion.json")) + sorted(folder.glob("allocation*.log")):
                self.record(path, "study_context")
            for job in sorted(folder.glob("*job-*")):
                if not job.is_dir():
                    continue
                for name in ["exit-code.txt", "started.txt", "finished.txt", "slurm-job.txt"]:
                    if (job / name).is_file():
                        entry = self.record(job / name, "allocation_status")
                        entry["value"] = (job / name).read_text().strip()
                        if name == "exit-code.txt":
                            self.attempts.append({"source_file": str(job / name), "source_record": "/", "phase": folder.name, "attempt": job.name, "status": "allocation_completed" if entry["value"] == "0" else "allocation_failed_or_canceled", "exit_code": entry["value"], "performance_row": False})
                for path in sorted(job.glob("allocation*.log")):
                    self.record(path, "allocation_log")
                for report in sorted(job.glob("*report*")):
                    if report.is_dir():
                        for path in sorted(report.glob("*.csv")):
                            self.record(path, "existing_report_export_not_independent_runs")
            logs = list(folder.glob("allocation*.log"))
            for job in folder.glob("*job-*"):
                if job.is_dir():
                    for directory in job.iterdir():
                        if directory.is_dir() and ("preflight" in directory.name or directory.name in {"results", "xor-results", "patterns"}):
                            logs.extend(directory.rglob("*.log"))
            for path in sorted(set(logs)):
                if path.stat().st_size > 2000000:
                    continue
                messages = []
                for line_number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                    if re.search(r"RuntimeError:|AssertionError:|ValueError:|CalledProcessError:|TIME LIMIT|CANCELLED", line):
                        messages.append({"line": line_number, "text": line[:800]})
                if messages:
                    entry = self.record(path, "retained_failure_log")
                    entry["status"] = "failed_attempt_or_guard"
                    self.exclusions.append({"source_file": str(path), "source_record": f"line {messages[-1]['line']}",
                                            "status": "failed_attempt_or_guard", "reason": messages[-1]["text"],
                                            "details": messages, "action": "retained without fabricated timing; completed cases and later reruns remain separate"})
        for attempt in self.attempts:
            if attempt["status"] in {"allocation_failed_or_canceled", "attempt_failed"}:
                self.exclusions.append({**attempt, "reason": "nonzero retained exit status; consult associated failure logs", "action": "no fabricated performance metrics"})
        self.exclusions.append({"source_file": str(self.home / "tmp/2026-09-25-damacy-l40-nfs/job-3833138/started.txt"),
                                "source_record": "/", "status": "incomplete_at_inventory_snapshot",
                                "reason": "preparation started 2026-09-25T16:48:29Z; no finished/exit/results artifact at first inspection; root STATE was stale",
                                "action": "no read speed exported; not polled for new measurements"})

    def collect_log_context(self):
        roots = [self.home / "tmp" / p for p in ["2026-06-12-survey", "2026-06-15-chammi-reformat", "2026-06-15-bench128", "2026-06-15-dynacell-reformat/logs"]]
        for root in roots:
            for path in sorted(root.glob("*.log")):
                if path.stat().st_size > 1000000:
                    continue
                text = path.read_text(errors="replace")
                self.record(path, "legacy_job_log")
                machine = re.search(r"(?:node:\s*|\bon\s+)(cw-[\w-]+|cpu-[\w-]+)", text)
                job = re.search(r"srun: job (\d+)", text)
                arrays = None
                for line in text.splitlines():
                    match = re.search(r"n_arrays=(\d+)", line)
                    if match:
                        arrays = int(match.group(1))
                    match = re.search(r"results:\s*(\S+results.json)", line)
                    if match:
                        self.log_runs[match.group(1)] = {"machine": machine.group(1) if machine else None,
                                                        "slurm_job_id": job.group(1) if job else None,
                                                        "array_count": arrays, "log_source": str(path)}

    def legacy_native(self, path, phase):
        data = self.read(path, "legacy_native_result", phase)
        if not isinstance(data, dict) or "timings_ms" not in data:
            return
        scenario = data.get("scenario", {})
        dataset = scenario.get("dataset", {})
        sampling = scenario.get("sampling", {})
        pipeline = scenario.get("pipeline", {})
        context = dict(self.log_runs.get(str(path), {}))
        timestamp = path.parent.name
        if "chammi-" in str(path) and "c120" in str(path):
            if "20260615-012323" <= timestamp <= "20260615-012918":
                phase = "microscopy-chammi-sparse-confirmation"
                context.update(machine="cw-us-e4a2-l40-202-047", slurm_job_id="2474434", log_source=str(self.home / "tmp/2026-06-15-chammi-reformat/gpu_confirm.log"))
            elif "20260615-040234" <= timestamp <= "20260615-041353":
                phase = "microscopy-chammi-dense-confirmation"
                context.update(machine="cw-us-e4a2-l40-202-063", slurm_job_id="2474778", log_source=str(self.home / "tmp/2026-06-15-chammi-reformat/gpu_curve.log"))
        stages = {s["name"]: s for s in data.get("stages", [])}
        counters = data.get("counters", {})
        sample_count = sampling.get("n_batches", 0) * sampling.get("samples_per_batch", 0)
        sample_bytes = data.get("derived", {}).get("bytes_per_sample")
        output_bytes = sample_count * sample_bytes if sample_bytes is not None else None
        seconds = data["timings_ms"].get("wall", 0) / 1000
        scenario_copy = json.loads(json.dumps(scenario))
        uris = scenario_copy.get("dataset", {}).pop("uris", None)
        if uris:
            scenario_copy["dataset"].update(uri_count=len(uris), uri_list_sha256=digest_value(uris), first_uri=uris[0], last_uri=uris[-1])
        meta = self.metadata_id({"scenario": scenario_copy, "log_context": context,
                                 "stages": stages, "counters": counters,
                                 "original_derived": data.get("derived", {}),
                                 "source_scenario": str(path.parent / "scenario.json")})
        name = scenario.get("name", path.parent.parent.name)
        is_microscopy = bool(uris) or any(word in name for word in ["chammi", "dynacell", "survey", "allencell"])
        date = None
        if re.fullmatch(r"\d{8}-\d{6}", path.parent.name):
            date = datetime.strptime(path.parent.name, "%Y%m%d-%H%M%S").isoformat() + "Z"
        content = "chammi-idr0017" if "idr0017" in name else "chammi-mix" if "mix" in name and "chammi" in name else name
        source_root = dataset.get("store_root")
        cache_source = context.get("log_source")
        source_dtypes = dataset.get("dtypes", [])
        source_item_bytes = {"u8": 1, "uint8": 1, "u16": 2, "uint16": 2, "f32": 4, "float32": 4}.get(source_dtypes[0]) if len(set(source_dtypes)) == 1 else None
        chunk_shape = dataset.get("chunk_shape", dataset.get("chunks"))
        shard_shape = dataset.get("shard_shape", dataset.get("shards"))
        useful_bytes = sample_count * math.prod(sampling["sample_shape"]) * source_item_bytes if source_item_bytes and sampling.get("sample_shape") else None
        row = {
            "source_file": str(path), "source_record": "/", "source_sha256": self.sources[str(path)]["sha256"],
            "metadata_id": meta, "phase": phase, "configuration_id": name, "reader": "damacy", "revision": None,
            "implementation": "legacy_gpu_pipeline", "date_start": date, "date_end": None, "run_order": date,
            "repeat": None, "machine": context.get("machine"), "slurm_job_id": context.get("slurm_job_id"),
            "backend": "GPU", "storage_type": "historical filesystem unverified" if not source_root else "path on shared filesystem; historical mount unverified",
            "storage_destination": source_root, "mount_options": None, "nconnect": None,
            "input_kind": "microscopy" if is_microscopy else "synthetic", "content": content,
            "content_id": digest_value(uris) if uris else digest_value(dataset), "source_dtype": dataset.get("dtypes"),
            "array_shape": dataset.get("zarr_shape", dataset.get("shape")), "array_count": context.get("array_count", dataset.get("n_zarrs")),
            "chunk_shape": chunk_shape, "raw_chunk_bytes": math.prod(chunk_shape) * source_item_bytes if chunk_shape and source_item_bytes else None,
            "shard_shape": shard_shape, "raw_shard_bytes": math.prod(shard_shape) * source_item_bytes if shard_shape and source_item_bytes else None,
            "layout_provenance": "scenario geometry when present; actual heterogeneous URI metadata not reconstructed",
            "shard_count": None, "codec": dataset.get("codecs", dataset.get("compressor")), "block_bytes": None,
            "workload": "random-crops", "selection_shape": sampling.get("sample_shape"),
            "axes": "TCZYX" if len(sampling.get("sample_shape", [])) == 5 else None,
            "origin_distribution": "xorshift64* array choice and valid origins; warmup consumes RNG; timed trace identity unverified",
            "alignment": "unaligned random", "seed": sampling.get("seed"), "query_reference_sha256": None,
            "queries_per_pass": sample_count, "samples_per_batch": sampling.get("samples_per_batch"), "passes": 1,
            "sample_count": sample_count, "pushed_samples_including_warmup": counters.get("samples_pushed"),
            "decode_workers": None, "file_workers": pipeline.get("n_io_threads"), "read_buffer_chunks": None,
            "request_concurrency": pipeline.get("lookahead_samples"), "read_coalescing": pipeline.get("max_read_op_kb"),
            "distinct_files_touched": counters.get("distinct_shards"), "distinct_arrays_touched": counters.get("distinct_zarrs"),
            "cache_policy": "legacy best-effort file eviction; verify linked job log" if cache_source else "not recorded in result JSON",
            "cache_source": cache_source, "warmup_batches": sampling.get("n_warmup_batches"),
            "output_dtype": pipeline.get("dtype"), "output_device": "GPU; no returned host copy measured",
            "timing_policy": "steady-state native wall after warmup; device transfer/decode/assembly included; startup reported separately",
            "seconds": seconds, "active_seconds": seconds,
            "output_bytes": output_bytes, "useful_logical_bytes": useful_bytes,
            "decoded_chunk_bytes": stages.get("decode", {}).get("output_bytes"),
            "encoded_payload_bytes": stages.get("decode", {}).get("input_bytes"),
            "reader_bytes": stages.get("io", {}).get("input_bytes"), "storage_bytes": None,
            "index_bytes_transferred": None, "compression_ratio": None,
            "primary_gib_s": rate(output_bytes, seconds), "byte_domain": "returned pipeline-dtype output",
            "source_unit": "decimal MB/s", "source_throughput": data.get("derived", {}).get("throughput_mb_s"),
            "output_active_gib_s": rate(output_bytes, seconds), "output_wall_gib_s": rate(output_bytes, seconds),
            "samples_per_second": div(sample_count, seconds), "decoded_amplification": div(stages.get("decode", {}).get("output_bytes"), useful_bytes),
            "modeled_decoded_amplification": None, "storage_amplification": None,
            "decoded_per_output_byte": div(stages.get("decode", {}).get("output_bytes"), output_bytes),
            "frontier_objective": "none recorded; layout/tuning controls", "winner_selection": "undefined",
            "status": "ok", "exclusion_reason": None,
            "limitations": "source dtypes/layouts and exact binary often absent; do not compare GPU output bytes with native-dtype TensorStore bytes; trace may differ after reformat",
        }
        self.append(row, (self.sources[str(path)]["sha256"], 0))
        self.json_cache.pop(str(path), None)

    def legacy_tensorstore(self, path):
        data = self.read(path, "legacy_tensorstore_result", "microscopy-tensorstore-threads")
        if not isinstance(data, dict) or data.get("backend") != "tensorstore" or "rows" not in data:
            return
        scenario_path = data.get("scenario_path")
        scenario = self.read(scenario_path, "legacy_scenario") if scenario_path else {}
        dataset = scenario.get("dataset", {})
        scenario_small = json.loads(json.dumps(scenario))
        uris = scenario_small.get("dataset", {}).pop("uris", None)
        if uris:
            scenario_small["dataset"]["uri_list_sha256"] = digest_value(uris)
            scenario_small["dataset"]["uri_count"] = len(uris)
        meta = self.metadata_id({"scenario": scenario_small, "original_compare_block": data.get("compare"),
                                 "original_patch_bytes": data.get("patch_bytes"), "scenario_source": scenario_path,
                                 "limitation": "June source revision and destination dtype absent; old compare sample counts include native warmup"})
        for i, measurement in enumerate(data["rows"]):
            counted = measurement["samples"] * data["patch_bytes"]
            row = {"source_file": str(path), "source_record": f"/rows/{i}",
                   "source_sha256": self.sources[str(path)]["sha256"], "metadata_id": meta,
                   "phase": "microscopy-tensorstore-threads", "configuration_id": f"{data['scenario']}-threads{measurement['threads']}",
                   "reader": "tensorstore", "revision": None, "implementation": "legacy_cpu_thread_sweep",
                   "date_start": "2026-06-12" if "survey-baseline" in path.parts else "2026-06-14",
                   "machine": "cpu-turin-gp-l-243-197" if "survey-baseline" in path.parts else None,
                   "machine_evidence": str(self.home / "tmp/2026-06-12-survey/ts-sweep.log") if "survey-baseline" in path.parts else None,
                   "backend": "CPU", "storage_type": "path on shared filesystem; historical mount unverified",
                   "storage_destination": dataset.get("store_root"), "mount_options": None, "nconnect": None,
                   "input_kind": "microscopy" if uris else "unknown", "content": data.get("scenario"),
                   "content_id": digest_value(uris) if uris else None, "source_dtype": None, "array_shape": None,
                   "array_count": data.get("n_arrays"), "chunk_shape": None, "raw_chunk_bytes": None,
                   "shard_shape": None, "codec": None, "block_bytes": None,
                   "workload": "random-crops", "selection_shape": data.get("sample_shape"),
                   "seed": scenario.get("sampling", {}).get("seed"), "queries_per_pass": data.get("n_timed_samples"),
                   "samples_per_batch": None, "query_reference_sha256": None,
                   "origin_distribution": "ported xorshift64*; warmup/timed sequence identity with native runs not proven",
                   "alignment": "unaligned random", "decode_workers": measurement.get("threads"), "file_workers": None,
                   "read_buffer_chunks": None, "cache_policy": "best-effort fadvise eviction before warmup; server and subsequent client cache uncontrolled" if data.get("drop_cache") else "not evicted",
                   "warmup_samples": data.get("n_warmup_samples"), "output_dtype": None, "output_device": "host memory",
                   "timing_policy": "Python read+decode timed loop after warmup; open/eviction excluded",
                   "seconds": measurement.get("wall_s"), "active_seconds": measurement.get("wall_s"),
                   "sample_count": measurement.get("samples"), "samples_per_second": measurement.get("samples_s"),
                   "reported_numerator_bytes": counted, "useful_logical_bytes": None, "output_bytes": None,
                   "primary_gib_s": measurement["gb_s"] * 1e9 / GIB,
                   "byte_domain": "archived patch_bytes; destination dtype unrecorded", "source_unit": "decimal GB/s",
                   "source_throughput": measurement.get("gb_s"), "compression_ratio": None,
                   "frontier_objective": "thread sweep; no layout frontier", "winner_selection": "undefined",
                   "status": "ok", "exclusion_reason": None,
                   "limitations": "single observation/thread; byte domains differ from native f32 in original comparison; use within-reader trends"}
            self.append(row, (self.sources[str(path)]["sha256"], i))

    def collect_legacy(self):
        self.collect_log_context()
        specs = [(self.home / "src/damacy/bench/runs", "legacy-native"),
                 (self.home / "data/damacy/scenarios/survey-baseline/runs", "microscopy-survey-baseline"),
                 (self.home / "data/damacy/scenarios/survey-tuned/runs", "microscopy-survey-tuned")]
        for root, phase in specs:
            for path in sorted(root.rglob("results.json")) if root.is_dir() else []:
                actual = "microscopy-chammi-" + ("120batch" if "c120" in str(path) else "initial") if "chammi-" in str(path) else phase
                self.legacy_native(path, actual)
        for folder, phase in [("2026-06-15-bench128", "microscopy-128crop"), ("2026-06-15-dynacell-reformat", "microscopy-dynacell-reformat"), ("2026-06-14-array-starve", "legacy-array-count-control")]:
            root = self.home / "tmp" / folder
            for directory in sorted(root.iterdir()):
                if directory.is_dir() and (directory.name.startswith(("runs-", "cmp-runs", "r2-"))):
                    for path in sorted(directory.rglob("results.json")):
                        self.legacy_native(path, phase)
            for path in sorted(root.glob("results-*.json")):
                self.legacy_native(path, phase)
            for path in sorted(root.glob("cmp-ts-*.json")):
                self.legacy_tensorstore(path)
        for path in sorted((self.home / "data/damacy/scenarios/survey-baseline/scenarios").glob("*.tensorstore.json")):
            self.legacy_tensorstore(path)

    def finish(self):
        write_csv(self.output / "read-runs.csv", self.rows)
        write_json(self.output / "read-metadata.json", {"records": self.metadata, "shared_objects": self.shared_metadata,
                   "reference_rule": "read-runs.metadata_id addresses records; each *_ref addresses shared_objects whose value preserves the original object"})
        write_csv(self.output / "read-attempts.csv", self.attempts)
        write_csv(self.output / "read-exclusions.csv", self.exclusions)
        write_json(self.output / "read-source-manifest.json", {
            "observed_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "small read benchmark records only; no payload traversal or benchmark execution",
            "families": self.families, "sources": list(self.sources.values()),
            "l40_snapshot": {"job": "3833138", "started_utc": "2026-09-25T16:48:29Z", "status": "preparation incomplete at inventory inspection; not polled for new results", "timed_read_results": 0},
            "row_statuses": dict(Counter(row["status"] for row in self.rows)),
        })


def summarize(rows, output):
    grouped = defaultdict(list)
    for row in rows:
        if row.get("status") == "ok":
            grouped[row["summary_id"]].append(row)
    summaries = []
    for ident, samples in sorted(grouped.items()):
        first = samples[0]
        result = {key: first.get(key) for key in GROUP_FIELDS + ["comparison_group", "configuration_id", "raw_chunk_bytes", "chunk_shape", "shard_shape", "shard_grid", "shard_count", "raw_shard_bytes", "codec", "codec_level", "shuffle", "block_bytes", "effective_block_bytes", "array_shape", "array_count", "source_dtype", "input_kind", "content", "frontier_objective", "winner_selection"]}
        result.update(summary_id=ident, repetitions=len(samples),
                      source_run_ids=[row["run_id"] for row in samples],
                      source_locators=[row["source_file"] + "#" + row["source_record"] for row in samples],
                      variation_definition="observed min/max; not a confidence interval")
        for field in METRICS:
            values = [num(row.get(field)) for row in samples if num(row.get(field)) is not None]
            for name, value in [("median", median(values) if values else None), ("min", min(values) if values else None), ("max", max(values) if values else None)]:
                result[field + "_" + name] = value
        summaries.append(result)
    frontiers = []
    groups = defaultdict(list)
    for row in summaries:
        groups[row["comparison_group"]].append(row)
    for group in groups.values():
        available = [row["primary_gib_s_median"] for row in group if row["primary_gib_s_median"] is not None]
        fastest = max(available) if available else None
        for row in group:
            row["fastest_median_among_tested"] = row["primary_gib_s_median"] == fastest if fastest is not None else None
        for metric, maximize, label in [("compression_ratio_median", True, "compression/output"), ("encoded_amplification_median", False, "encoded-traffic/output"), ("storage_amplification_median", False, "local-storage-traffic/output")]:
            eligible = [row for row in group if row.get(metric) is not None and row.get("primary_gib_s_median") is not None]
            for row in eligible:
                def dominates(other):
                    x, ox = row[metric], other[metric]
                    y, oy = row["primary_gib_s_median"], other["primary_gib_s_median"]
                    return oy >= y and (ox >= x if maximize else ox <= x) and (oy > y or ox != x)
                frontiers.append({"comparison_group": row["comparison_group"], "summary_id": row["summary_id"],
                                  "phase": row["phase"], "reader": row["reader"], "implementation": row["implementation"],
                                  "content": row["content"], "workload": row["workload"], "storage_type": row["storage_type"],
                                  "configuration_id": row["configuration_id"], "raw_chunk_bytes": row["raw_chunk_bytes"],
                                  "chunk_shape": row["chunk_shape"], "codec": row["codec"], "block_bytes": row["block_bytes"],
                                  "frontier_axes": label, "cost_value": row[metric], "cost_direction": "maximize" if maximize else "minimize",
                                  "primary_gib_s_median": row["primary_gib_s_median"],
                                  "on_frontier": not any(dominates(other) for other in eligible),
                                  "recorded_frontier_objective": row["frontier_objective"],
                                  "winner_selection": "undefined; nondominance is not a scalar winner rule",
                                  "source_run_ids": row["source_run_ids"]})
    write_csv(output / "read-summary.csv", summaries)
    write_csv(output / "read-frontiers.csv", frontiers)
    workloads = defaultdict(list)
    match_fields = ["phase", "machine", "reader", "implementation", "revision", "storage_type", "content_id", "configuration_id", "cache_policy", "read_buffer_chunks"]
    for row in summaries:
        workloads[tuple(str(row.get(k)) for k in match_fields)].append(row)
    comparisons = []
    for points in workloads.values():
        crops = [r for r in points if r["workload"] == "random-1x256x256"]
        controls = [r for r in points if r["workload"] in {"aligned", "full-scan"}]
        for crop in crops:
            for control in controls:
                comparisons.append({"phase": crop["phase"], "reader": crop["reader"], "implementation": crop["implementation"],
                                    "storage_type": crop["storage_type"], "configuration_id": crop["configuration_id"],
                                    "crop_summary_id": crop["summary_id"], "control_summary_id": control["summary_id"],
                                    "control_workload": control["workload"], "crop_selection_shape": crop["selection_shape"],
                                    "control_selection_shape": control["selection_shape"], "chunk_shape": crop["chunk_shape"],
                                    "crop_primary_gib_s": crop["primary_gib_s_median"], "control_primary_gib_s": control["primary_gib_s_median"],
                                    "control_to_crop_ratio": div(control["primary_gib_s_median"], crop["primary_gib_s_median"]),
                                    "scope": "different selections/workloads on same encoding; aligned refers to XY 256-grid, not necessarily whole chunks",
                                    "source_run_ids": crop["source_run_ids"] + control["source_run_ids"]})
    write_csv(output / "read-workload-comparisons.csv", comparisons)
    plot_keys = ["summary_id", "comparison_group", "phase", "reader", "implementation", "input_kind", "content", "storage_type", "workload", "selection_shape", "chunk_shape", "raw_chunk_bytes", "codec", "block_bytes", "repetitions", "primary_gib_s_median", "primary_gib_s_min", "primary_gib_s_max", "compression_ratio_median", "decoded_amplification_median", "modeled_decoded_amplification_median", "storage_amplification_median", "timing_policy", "byte_domain", "source_run_ids"]
    write_csv(output / "read-plot-data.csv", [{key: row.get(key) for key in plot_keys} for row in summaries])
    checked_rates = 0
    for row in rows:
        if row.get("status") != "ok" or not (row["phase"].startswith("cpu-") or row["phase"].startswith("pr160-")):
            continue
        output_bytes, useful = num(row.get("output_bytes")), num(row.get("useful_logical_bytes"))
        if output_bytes is not None and useful is not None and output_bytes != 2 * useful:
            raise ValueError("uint16/float32 byte identity failed: " + row["run_id"])
        reported, primary = num(row.get("reported_primary_gib_s")), num(row.get("primary_gib_s"))
        if reported is not None and primary is not None:
            checked_rates += 1
            if not math.isclose(reported, primary, rel_tol=1e-10, abs_tol=1e-12):
                raise ValueError("archived rate differs from counter-derived rate: " + row["run_id"])
        if row.get("storage_type") == "NFS" and num(row.get("storage_bytes")) is not None:
            raise ValueError("NFS process read_bytes was mislabeled as physical traffic")
    counts = {"rows": len(rows), "statuses": dict(Counter(r["status"] for r in rows)),
              "accepted_rows_by_phase": dict(Counter(r["phase"] for r in rows if r["status"] == "ok")),
              "summary_rows": len(summaries), "frontier_rows": len(frontiers), "workload_comparison_rows": len(comparisons),
              "archived_rates_verified": checked_rates,
              "comparison_groups": len(groups), "null_policy": "empty CSV field is unknown/unavailable, never zero",
              "summary_filter": "status == ok only; duplicate/preflight/trace rows retained but excluded",
              "scalar_winner_rule": None}
    write_json(output / "read-export-checks.json", counts)
    return counts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, default=Path("/mnt/main0/home/nclack"))
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--from-rows", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.from_rows:
        with args.from_rows.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
    else:
        export = ReadExport(args.home, args.output)
        export.collect_modern()
        export.collect_legacy()
        export.finish()
        with (args.output / "read-runs.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
    print(json.dumps(summarize(rows, args.output), indent=2))


if __name__ == "__main__":
    main()
