import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import stat


POLICY = "fixed-volume-after-discard-warmup-through-close-v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    data = path.read_bytes()
    return json.loads(data), {
        "path": str(path), "sha256": hashlib.sha256(data).hexdigest()
    }


def source_path(root, value):
    path = Path(value)
    return (path if path.is_absolute() else root / path).resolve()


def inventory(store, array, alignment, index_bytes):
    files = []
    other_entries = []
    shard_prefix = (array / "c").relative_to(store)

    def fail(error):
        raise error

    for directory, names, filenames in os.walk(store, onerror=fail, followlinks=False):
        names.sort()
        for name in names:
            path = Path(directory, name)
            if path.is_symlink():
                other_entries.append(path.relative_to(store).as_posix())
        for name in sorted(filenames):
            path = Path(directory, name)
            info = path.lstat()
            relative = path.relative_to(store)
            if not stat.S_ISREG(info.st_mode):
                other_entries.append(relative.as_posix())
                continue
            kind = "shard" if shard_prefix in relative.parents else (
                "metadata" if name == "zarr.json" else "other"
            )
            row = {
                "path": relative.as_posix(), "kind": kind,
                "st_size": info.st_size, "st_blocks": info.st_blocks,
                "allocated_bytes": info.st_blocks * 512,
            }
            if kind == "shard":
                row["final_padding_bytes"] = (-info.st_size) % alignment
                row["aligned_bytes"] = info.st_size + row["final_padding_bytes"]
                row["index_bytes"] = index_bytes
            files.append(row)
    return sorted(files, key=lambda row: row["path"]), sorted(other_entries)


def account_layout(root, manifest, position, entry, alignment):
    result = {"id": entry["id"], "manifest_locator": f"#/layouts/{position}"}
    try:
        record_path = source_path(root, entry["writer_record"])
        record, record_source = read_json(record_path)
        result["writer_record"] = {
            **record_source,
            **{key: record.get(key) for key in (
                "id", "slurm_job_id", "status", "returncode", "scope", "round", "role"
            )},
        }
        native = record["native"]
        measurement = native["measurement"]
        metrics = record["metrics"]
        checked_store = record["store_check"]
        result["writer_metrics"] = metrics
        result["native_measurement"] = measurement
        result["native_output_bytes"] = native["output_bytes"]
        result["writer_store_check"] = {
            key: checked_store[key] for key in (
                "final_file_bytes", "allocated_file_bytes", "file_count",
                "shard_file_count", "index_bytes_per_shard", "shape"
            )
        }
        array = source_path(root, entry["path"])
        store = array.parent
        require(array.name == "images" and array.is_dir(), "retained images array missing")
        require(store.parent == root / "data", "retained store is outside ROOT/data")
        shape = manifest["shape"]
        chunk = entry["chunk_shape"]
        shard = manifest["shard_shape"]
        require(len(shape) == len(chunk) == len(shard) == 3, "expected rank three")
        require(all(type(n) is int and n > 0 for n in shape + chunk + shard),
                "invalid geometry")
        require(all(s % c == 0 for s, c in zip(shard, chunk)), "shards do not divide into chunks")
        counts = [s // c for s, c in zip(shard, chunk)]
        index_bytes = 16 * math.prod(counts) + 4
        expected_shards = math.prod((n + s - 1) // s for n, s in zip(shape, shard))
        files, other_entries = inventory(store, array, alignment, index_bytes)
        shards = [row for row in files if row["kind"] == "shard"]
        metadata = [row for row in files if row["kind"] == "metadata"]
        logical_bytes = measurement["logical_input_bytes"]
        output_bytes = measurement["output_bytes"]
        require(type(logical_bytes) is int and logical_bytes > 0, "invalid logical byte count")
        require(type(output_bytes) is int and output_bytes >= 0, "invalid metered byte count")
        total = {
            "logical_bytes": logical_bytes, "metered_output_bytes": output_bytes,
            "file_count": len(files), "shard_file_count": len(shards),
            "metadata_file_count": len(metadata),
            "other_file_count": sum(row["kind"] == "other" for row in files),
            "final_file_bytes": sum(row["st_size"] for row in files),
            "shard_file_bytes": sum(row["st_size"] for row in shards),
            "metadata_file_bytes": sum(row["st_size"] for row in metadata),
            "allocated_file_bytes": sum(row["allocated_bytes"] for row in files),
            "st_blocks": sum(row["st_blocks"] for row in files),
            "aligned_shard_file_bytes": sum(row["aligned_bytes"] for row in shards),
            "final_padding_bytes": sum(row["final_padding_bytes"] for row in shards),
            "index_bytes_per_shard": index_bytes,
            "index_bytes": len(shards) * index_bytes,
        }
        total["logical_to_final_ratio"] = (
            logical_bytes / total["final_file_bytes"] if total["final_file_bytes"] else None
        )
        result.update({
            "array_path": str(array), "store_path": str(store), "shape": shape,
            "chunk_shape": chunk, "shard_shape": shard, "chunks_per_shard": counts,
            "page_alignment": alignment, "files": files, "other_entries": other_entries,
            "totals": total,
        })
        dimensions = measurement["geometry"]["dimensions"]
        checks = {
            "writer_passed": record["status"] == native["status"] == "pass" and record["returncode"] == 0,
            "fixed_volume": measurement["policy"] == POLICY and measurement["fixed_volume"] is True,
            "warmup_excluded": measurement["warmup_input_bytes"] == measurement["warmup_output_bytes"] == 0,
            "retained_path_matches": source_path(root, record["retained_path"]) == array
                and source_path(root, checked_store["array_path"]) == array,
            "record_case_matches": record["case"]["id"] == entry["id"],
            "geometry_matches": [d["chunk_size"] for d in dimensions] == chunk
                and [d["chunks_per_shard"] for d in dimensions] == counts
                and checked_store["shape"] == shape,
            "logical_bytes_match": logical_bytes == math.prod(shape) * 2
                == metrics["logical_bytes"] == native["logical_input_bytes"],
            "metered_bytes_match": output_bytes == metrics["metered_output_bytes"] == native["output_bytes"],
            "expected_shard_count": len(shards) == expected_shards,
            "expected_metadata": {row["path"] for row in metadata} == {"zarr.json", "images/zarr.json"},
            "only_expected_files": total["other_file_count"] == 0 and not other_entries,
            "indexes_fit": all(row["st_size"] >= index_bytes for row in shards),
            "metered_equals_aligned_shards": output_bytes == total["aligned_shard_file_bytes"],
            "final_size_identity": total["final_file_bytes"] ==
                output_bytes - total["final_padding_bytes"] + total["metadata_file_bytes"],
        }
        for key in ("final_file_bytes", "allocated_file_bytes", "file_count", "shard_file_count", "index_bytes_per_shard"):
            checks[f"writer_census_{key}"] = total[key] == checked_store[key]
        result["checks"] = checks
        result["status"] = "pass" if all(checks.values()) else "error"
        result["failed_checks"] = [name for name, passed in checks.items() if not passed]
    except (OSError, ValueError, KeyError, TypeError) as error:
        result["status"] = "error"
        result["error"] = f"{type(error).__name__}: {error}"
    return result


def main():
    parser = argparse.ArgumentParser(description="Account for retained BBBC022 files without reading payloads")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    require(bool(os.environ.get("SLURM_JOB_ID")), "run on a compute allocation")
    root = args.root.resolve()
    output = args.output.resolve() if args.output else root / "retained-store-accounting.json"
    require(root / "data" not in output.parents, "accounting output must be outside retained stores")
    report = {
        "schema_version": 1, "root": str(root),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(), "slurm_job_id": os.environ["SLURM_JOB_ID"],
        "method": {
            "scope": "retained fixed-volume stores after successful close and drain",
            "payload_reads": False,
            "file_size": "st_size for every regular file under the retained array's parent store",
            "allocated_bytes": "st_blocks * 512; separate from file length",
            "alignment_source": "identity_source JSON pointer plus /page_alignment",
            "metered_identity": "output_bytes = sum(ceil(shard_st_size / page_alignment) * page_alignment)",
            "final_padding": "sum((-shard_st_size) % page_alignment)",
            "final_size_identity": "final_file_bytes = output_bytes - final_padding_bytes + metadata_file_bytes",
            "index_bytes_per_shard": "16 * product(chunks_per_shard) + 4, including CRC",
            "internal_padding": "retained inside shard files; not subtracted",
            "metadata": "final zarr.json files; replacement traffic is not metered",
            "dynamic_runs": "not applicable without adding warmup_output_bytes to metered output",
        },
    }
    try:
        manifest, report["manifest"] = read_json(root / "read-manifest.json")
        phases_path = root / "source-phases.json"
        if phases_path.exists():
            phases, identity_source = read_json(phases_path)
            identity = phases["shared_layouts"]["writer_identity"]
            identity_source["json_pointer"] = "#/shared_layouts/writer_identity"
        else:
            identity, identity_source = read_json(root / "writer-identity.json")
            identity_source["json_pointer"] = "#"
        report["identity_source"] = identity_source
        report["writer_identity"] = identity
        alignment = identity["page_alignment"]
        require(type(alignment) is int and alignment > 0, "invalid writer page alignment")
        require(manifest["source"]["dtype"] == "uint16", "unexpected source dtype")
        entries = manifest["layouts"]
        require(entries and len({entry["id"] for entry in entries}) == len(entries),
                "manifest layout IDs are missing or duplicated")
        report["layouts"] = [
            account_layout(root, manifest, index, entry, alignment)
            for index, entry in enumerate(entries)
        ]
        passed = sum(row["status"] == "pass" for row in report["layouts"])
        report["summary"] = {
            "layout_count": len(entries), "passed_layout_count": passed,
            "failed_layout_count": len(entries) - passed,
        }
        report["status"] = "pass" if passed == len(entries) else "error"
    except (OSError, ValueError, KeyError, TypeError) as error:
        report["status"] = "error"
        report["error"] = f"{type(error).__name__}: {error}"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": report["status"], "output": str(output), **report.get("summary", {})}))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
