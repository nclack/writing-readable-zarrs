import argparse
import csv
import hashlib
import json
import math
import shutil
import statistics
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def truth(value):
    return str(value).lower() == "true"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def same_number(left, right):
    return math.isclose(float(left), float(right), rel_tol=1e-11, abs_tol=1e-12)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_read(root):
    rows = read_csv(root / "read-runs.csv")
    by_id = {item["run_id"]: item for item in rows}
    require(len(rows) == len(by_id), "Duplicate read run IDs")
    summaries = read_csv(root / "read-summary.csv")
    for summary in summaries:
        members = [by_id[key] for key in json.loads(summary["source_run_ids"])]
        require(len(members) == int(summary["repetitions"]), "Read repetition count mismatch")
        require(all(item["status"] == "ok" for item in members), "Read summary includes excluded row")
        require(all(item["comparison_group"] == summary["comparison_group"] for item in members), "Read group mismatch")
        for metric in ("primary_gib_s", "output_active_gib_s", "storage_active_gib_s", "compression_ratio"):
            values = [float(item[metric]) for item in members if item.get(metric)]
            if values:
                require(same_number(statistics.median(values), summary[metric + "_median"]), "Read median mismatch")
                require(same_number(min(values), summary[metric + "_min"]), "Read minimum mismatch")
                require(same_number(max(values), summary[metric + "_max"]), "Read maximum mismatch")
    return {"rows": len(rows), "statuses": dict(Counter(item["status"] for item in rows)),
            "summaries_checked": len(summaries), "method": "independent median/range calculation from source_run_ids"}


def check_write(root):
    rows = read_csv(root / "write-runs.csv")
    by_id = {item["row_id"]: item for item in rows}
    require(len(rows) == len(by_id), "Duplicate write row IDs")
    summaries = read_csv(root / "write-summary.csv")
    groups = defaultdict(list)
    for summary in summaries:
        members = [by_id[key] for key in json.loads(summary["run_ids"])]
        valid = [item for item in members if truth(item["original_measurement_valid"]) and item["throughput_logical_gibs"]]
        require(len(valid) == int(summary["valid_observations"]), "Write repetition count mismatch")
        require(all(item["comparison_group"] == summary["comparison_group"] for item in members), "Write group mismatch")
        rates = [float(item["throughput_logical_gibs"]) for item in valid]
        if rates:
            require(same_number(statistics.median(rates), summary["median_logical_gibs"]), "Write median mismatch")
            require(same_number(min(rates), summary["min_logical_gibs"]), "Write minimum mismatch")
            require(same_number(max(rates), summary["max_logical_gibs"]), "Write maximum mismatch")
        require(summary["strict_final_stored_size_winner"] == "", "Unavailable final stored-size winner was invented")
        if truth(summary["proxy_frontier_eligible"]):
            groups[summary["comparison_group"]].append(summary)
    winners = 0
    for group in groups.values():
        costs = {item["summary_id"]: Fraction(int(item["sink_write_byte_sum"]), int(item["logical_byte_sum"])) for item in group}
        limit = min(costs.values()) * Fraction(11, 10)
        fastest = max(float(item["median_logical_gibs"]) for item in group if costs[item["summary_id"]] <= limit)
        for item in group:
            cost, speed = costs[item["summary_id"]], float(item["median_logical_gibs"])
            within = cost <= limit
            winner = within and speed == fastest
            frontier = not any(costs[other["summary_id"]] <= cost and float(other["median_logical_gibs"]) >= speed
                               and (costs[other["summary_id"]] < cost or float(other["median_logical_gibs"]) > speed)
                               for other in group)
            require(truth(item["proxy_within_10pct"]) == within, "Write 10% threshold mismatch")
            require(truth(item["proxy_10pct_winner"]) == winner, "Write winner mismatch")
            require(truth(item["proxy_frontier"]) == frontier, "Write frontier mismatch")
            winners += winner
    return {"rows": len(rows), "summaries_checked": len(summaries), "proxy_comparison_groups": len(groups),
            "proxy_winners_checked": winners, "method": "independent row medians and exact Fraction(11,10) size threshold"}


def check_conversion(root):
    rows = read_csv(root / "conversion-runs.csv")
    arrays = read_csv(root / "conversion-array-layouts.csv")
    require(len({item["run_id"] for item in rows}) == len(rows), "Duplicate conversion run ID")
    for item in rows:
        for metric in ("elapsed_s", "throughput_B_s", "host_peak_bytes", "device_peak_bytes", "pinned_host_peak_bytes"):
            require(item[metric] == "", "Unmeasured conversion metric is not null")
    return {"runs": len(rows), "array_layout_records": len(arrays), "unmeasured_metrics_preserved_as_null": True}


def check_concurrency(root):
    rows = [json.loads(line) for line in (root / "concurrency-records.jsonl").read_text().splitlines()]
    require(len({(item["source_file"], item["source_record"]) for item in rows}) == len(rows), "Duplicate concurrency locator")
    for item in rows:
        if item.get("throughput_value") is not None:
            factor = 1024**3 if item["throughput_unit"] == "GiB/s" else 1e9
            require(same_number(item["throughput_value"] * factor, item["throughput_bytes_s"]), "Concurrency unit conversion mismatch")
        if item["family"] == "orca_append_shard_split" and item["role"] == "sample":
            require(item["total_output_files"] == item["writer_layer_shards"] * item["append_axis_shards"], "Orca layer geometry mismatch")
    pairs = read_csv(root / "concurrency-paired.csv")
    for pair in pairs:
        require(same_number(float(pair["higher_bytes_s"]) / float(pair["lower_bytes_s"]), pair["paired_ratio"]), "Paired throughput ratio mismatch")
    return {"rows": len(rows), "families": dict(Counter(item["family"] for item in rows)), "pairs_checked": len(pairs)}


def check_figures(root):
    rows = read_csv(root / "figures/figure-data.csv")
    summaries = {name: {item["summary_id"]: item for item in read_csv(root / name)}
                 for name in ("read-summary.csv", "write-summary.csv")}
    for item in rows:
        require(item["source_record"].startswith("summary_id="), "Figure locator has no summary ID")
        ident = item["source_record"].split("=", 1)[1]
        original = summaries[item["source_file"]][ident]
        for metric in ("primary_gib_s_median", "median_logical_gibs", "proxy_size_penalty_percent", "raw_chunk_bytes"):
            if item.get(metric):
                require(same_number(item[metric], original[metric]), "Figure data differs from summary")
    return {"source_summary_rows_checked": len(rows), "figures": sorted({item["figure"] for item in rows})}


def regenerate(root, temporary):
    checks = {}
    jobs = []
    jobs.append(("reads", [sys.executable, str(root / "scripts/aggregate_reads.py"), "--from-rows", str(root / "read-runs.csv"), "--output", str(temporary / "reads")],
                 ["read-summary.csv", "read-frontiers.csv", "read-plot-data.csv", "read-workload-comparisons.csv", "read-export-checks.json"]))
    jobs.append(("writes", [sys.executable, str(root / "write-analysis.py"), "--from-rows", str(root / "write-runs.csv"), "--metadata", str(root / "write-metadata.json"), "--output", str(temporary / "writes")],
                 ["write-summary.csv", "write-frontier-data.csv", "write-winners.csv", "write-block-comparisons.csv", "write-reference-drift.csv", "write-findings.md"]))
    (temporary / "conversions").mkdir()
    for name in ("conversion-runs.csv", "conversion-phase-timings.csv"):
        shutil.copyfile(root / name, temporary / "conversions" / name)
    jobs.append(("conversions", [sys.executable, str(root / "scripts/conversion-analysis.py"), "--summarize-only", "--output", str(temporary / "conversions")],
                 ["conversion-summary.csv", "conversion-plot-data.csv", "conversion-findings.md"]))
    (temporary / "concurrency").mkdir()
    shutil.copyfile(root / "concurrency-records.jsonl", temporary / "concurrency/concurrency-records.jsonl")
    jobs.append(("concurrency", [sys.executable, str(root / "scripts/aggregate_concurrency.py"), "--from-rows", "--output", str(temporary / "concurrency")],
                 ["concurrency-runs.csv", "concurrency-summary.csv", "concurrency-paired.csv", "concurrency-plot-data.csv", "concurrency-read-overlap.csv", "concurrency-storage-controls.csv", "concurrency-findings.md"]))
    for label, command, names in jobs:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        require(completed.returncode == 0, f"Portable {label} regeneration failed: {completed.stderr}")
        matches = {}
        for name in names:
            if not (root / name).exists():
                continue
            matches[name] = sha256(root / name) == sha256(temporary / label / name)
            require(matches[name], f"Portable output mismatch: {name}")
        checks[label] = {"files_byte_identical": matches, "command": command}
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.evidence.resolve()
    results = {"validated_utc": datetime.now(timezone.utc).isoformat(),
               "scope": "Lightweight checks of exported records and portable summary regeneration; no benchmark, payload read, test suite or allocation"}
    results["reads"] = check_read(root)
    results["writes"] = check_write(root)
    results["conversions"] = check_conversion(root)
    results["concurrency"] = check_concurrency(root)
    results["figures"] = check_figures(root)
    with tempfile.TemporaryDirectory(prefix="readable-zarrs-validate-", dir="/tmp") as directory:
        results["portable_regeneration"] = regenerate(root, Path(directory))
    results["status"] = "passed"
    target = root / "validation"
    target.mkdir(exist_ok=True)
    (target / "bundle-validation.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps({"status": results["status"], "reads": results["reads"]["rows"], "writes": results["writes"]["rows"],
                      "concurrency": results["concurrency"]["rows"], "conversions": results["conversions"]["runs"],
                      "portable_outputs": sum(len(item["files_byte_identical"]) for item in results["portable_regeneration"].values())}))


if __name__ == "__main__":
    main()
