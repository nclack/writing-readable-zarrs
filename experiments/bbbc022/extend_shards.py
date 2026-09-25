#!/usr/bin/env python3
"""Run a separate BBBC022 30-versus-54 shard follow-up after the primary reads."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics
import sys
import time
import traceback
from pathlib import Path

FAMILY = "shard-count-extension"
GIB = 1 << 30
MINIMUM_LOGICAL_BYTES = 96 * GIB
WRITER_SHA256 = "9702c7bb6089c69449553fa4a42e9ff96af7c4a5461acbb86bccbf8a32288ed9"
PRIMARY_JOB = "3836375"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def protocol_hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def primary_evidence(root, base):
    primary_attempt = Path((root / "writes-complete.txt").read_text().strip()).resolve()
    measurements = primary_attempt / "measurements"
    completion = load(measurements / "complete.json")
    decision = load(measurements / "extension-decision.json")
    records_path = measurements / "observations.jsonl"
    records = [json.loads(line) for line in records_path.read_text().splitlines()]
    require(
        completion["status"] == "pass"
        and completion["observations"] == len(records) == 66,
        "Primary writer series is not complete with 66 observations",
    )
    require(
        completion["max54_extension"] is False
        and decision["include_actual54"] is False,
        "Primary extension decision must remain false",
    )
    shards = [
        record for record in records if record["case"]["experiment"] == "shard-count"
    ]
    require(len(shards) == 48, "Expected 48 completed primary shard observations")
    require(
        {str(record["slurm_job_id"]) for record in shards} == {PRIMARY_JOB},
        "Primary shard observations came from a different job",
    )
    expected = {
        (repeat, "fast", target, "sample")
        for repeat in range(1, 7)
        for target in (4, 12, 16, 48)
    }
    expected.update(
        (repeat, "slow_control", target, "sample")
        for repeat in range(1, 7)
        for target in (4, 16)
    )
    expected.update(
        (repeat, "fast", 16, role)
        for repeat in range(1, 7)
        for role in ("reference-before", "reference-after")
    )
    actual = {
        (row["round"], row["case"]["series"], row["case"]["target_shards"], row["role"])
        for row in shards
    }
    require(actual == expected, "Primary six-round shard schedule differs")
    for record in shards:
        require(
            record["status"] == "pass" and record["returncode"] == 0,
            "Primary shard observation failed",
        )
        base.validate_native(record["native"], record["case"])
    paired = []
    for repeat in range(1, 7):
        samples = {
            row["case"]["actual_layer_shards"]: row
            for row in shards
            if row["round"] == repeat
            and row["role"] == "sample"
            and row["case"]["series"] == "fast"
        }
        rates = {}
        for count in (15, 30):
            record = samples[count]
            m = record["native"]["measurement"]
            rates[count] = m["logical_input_bytes"] / GIB / m["elapsed_s"]
            require(
                math.isclose(
                    rates[count], record["metrics"]["logical_gibs"], rel_tol=1e-12
                ),
                "Primary saved rate differs from native counters",
            )
        references = {
            row["role"]: {
                "record_id": row["id"],
                "logical_gibs": row["metrics"]["logical_gibs"],
            }
            for row in shards
            if row["round"] == repeat
            and row["role"] in ("reference-before", "reference-after")
        }
        paired.append(
            {
                "round": repeat,
                "record_15": samples[15]["id"],
                "record_30": samples[30]["id"],
                "logical_gibs_15": rates[15],
                "logical_gibs_30": rates[30],
                "ratio_30_over_15": rates[30] / rates[15],
                "references": references,
            }
        )
    ratios = [row["ratio_30_over_15"] for row in paired]
    require(
        len(decision["paired_30_over_15_ratios"]) == 3,
        "Primary first-three decision has the wrong number of pairs",
    )
    require(
        all(
            math.isclose(a, b, rel_tol=1e-12)
            for a, b in zip(
                ratios[:3], decision["paired_30_over_15_ratios"], strict=True
            )
        ),
        "Primary first-three ratios changed",
    )
    first_median = statistics.median(ratios[:3])
    median = statistics.median(ratios)
    require(
        math.isclose(first_median, decision["median_ratio"], rel_tol=1e-12),
        "Primary decision median changed",
    )
    require(
        first_median <= 1.05 and median > 1.05,
        "Later six-round gain does not meet the supplementary selection rule",
    )
    identity = load(primary_attempt / "writer-identity.json")
    require(identity["sha256"] == WRITER_SHA256, "Primary writer binary differs")
    return {
        "attempt": str(primary_attempt),
        "job_id": PRIMARY_JOB,
        "observations_path": str(records_path),
        "observations_sha256": file_hash(records_path),
        "completion": completion,
        "first_three_decision": decision,
        "first_three_decision_sha256": file_hash(
            measurements / "extension-decision.json"
        ),
        "six_round_pairs": paired,
        "six_round_median_ratio": median,
        "supplementary_decision": {
            "eligible": True,
            "threshold": 1.05,
            "uses_all_six_completed_rounds": True,
        },
        "writer_identity": identity,
    }


def completed_reads(root):
    measurements = Path((root / "reads-complete.txt").read_text().strip()).resolve()
    summary = load(measurements / "summary.json")
    require(
        summary["phase"] == "measurement" and summary["complete"] is True,
        "Main CPU reads are incomplete",
    )
    require(
        summary["planned_observations"] == 144
        and summary["status_counts"] == {"accepted": 144},
        "Main CPU read schedule did not complete",
    )
    attempt = measurements.parent
    require(
        (attempt / "finished.txt").is_file(), "Wait until the main CPU job has finished"
    )
    require(
        (attempt / "exit-code.txt").read_text().strip() == "0",
        "Main CPU job did not finish successfully",
    )
    return {
        "measurements": str(measurements),
        "summary": summary,
        "summary_sha256": file_hash(measurements / "summary.json"),
        "job_finished_utc": (attempt / "finished.txt").read_text().strip(),
    }


def protected_files(root, primary, reads):
    paths = [
        root / name
        for name in (
            "plan.json",
            "read-manifest.json",
            "writes-complete.txt",
            "reads-complete.txt",
            "source-phases.json",
            "writer-identity.json",
            "writer-run-hashes.json",
            "source-hashes.json",
        )
    ]
    primary_directory = Path(primary["attempt"]) / "measurements"
    paths.extend(
        primary_directory / name
        for name in ("observations.jsonl", "extension-decision.json", "complete.json")
    )
    paths.append(Path(reads["measurements"]) / "summary.json")
    paths.extend(
        Path(row["path"]) / "zarr.json"
        for row in load(root / "read-manifest.json")["layouts"]
    )
    return {str(path): file_hash(path) for path in paths}


def make_schedule(seed):
    first = [48, 54]
    random.Random(seed).shuffle(first)
    result = []
    for repeat in range(1, 4):
        order = first if repeat % 2 else list(reversed(first))
        selections = [
            (16, "reference-before"),
            *((target, "sample") for target in order),
            (16, "reference-after"),
        ]
        for target, role in selections:
            result.append(
                {
                    "order": len(result) + 1,
                    "round": repeat,
                    "target_shards": target,
                    "actual_layer_shards": {16: 15, 48: 30, 54: 54}[target],
                    "role": role,
                }
            )
    return result


def execute(args):
    require(os.environ.get("SLURM_JOB_ID"), "Run on an allocated L40 compute node")
    require(
        0 < args.deadline_seconds <= 1000,
        "Follow-up deadline must be at most 1000 seconds",
    )
    root, output = args.root.resolve(), args.output.resolve()
    require(
        output.parent == root / "jobs",
        "Output must be a new job attempt under ROOT/jobs",
    )
    output.mkdir(parents=True, exist_ok=True)
    require(
        not (output / "protocol.json").exists(),
        "Do not overwrite an existing follow-up protocol",
    )
    require(
        not (root / "shard-extension-complete.txt").exists(),
        "This follow-up already completed",
    )
    sys.path.insert(0, str(root / "sources"))
    import write_benchmark as base

    require(
        Path(base.__file__).resolve() == root / "sources/write_benchmark.py",
        "Wrong frozen writer helper imported",
    )
    primary = primary_evidence(root, base)
    reads = completed_reads(root)
    identity = load(root / "writer-identity.json")
    require(
        identity["sha256"] == file_hash(identity["path"]) == WRITER_SHA256,
        "Writer binary changed",
    )
    plan = load(root / "plan.json")
    require(
        plan["shard_count"]["measurement_policy"] == base.STREAM_POLICY,
        "Primary measurement policy changed",
    )
    require(
        plan["shard_count"]["geometry_frames"] == 65536, "Geometry reference changed"
    )
    fast = plan["shard_count"]["fast"]
    for key, value in {
        "codec": "blosc-lz4",
        "chunk_bytes": 65536,
        "chunk_depth": 4,
        "blosc_block_bytes": 16384,
        "shuffle": "bit",
        "level_hint": 3,
    }.items():
        require(fast[key] == value, f"Primary fast control changed: {key}")
    require(
        plan["writer_resources"]
        == {
            "output_buffers": 4,
            "io_workers": 32,
            "cpu_workers": 4,
            "batch_target_bytes": 67108864,
            "per_file_write_limit": 4,
        },
        "Writer resource settings changed",
    )
    geometries = {
        target: base.shard_case(plan, "fast", target) for target in (16, 48, 54)
    }
    require(
        {target: case["actual_layer_shards"] for target, case in geometries.items()}
        == {16: 15, 48: 30, 54: 54},
        "Requested targets map to different shard counts",
    )
    frames = math.ceil(MINIMUM_LOGICAL_BYTES / base.FRAME_BYTES)
    require(
        frames >= 2 * geometries[54]["shard_shape"][0],
        "Minimum volume does not span two complete 54-shard layers",
    )
    schedule = make_schedule(plan["seed"])
    before = protected_files(root, primary, reads)
    protocol = {
        "schema_version": 1,
        "family": FAMILY,
        "phase": "post-primary-supplementary",
        "protocol_hash_scope": "canonical JSON excluding protocol_sha256",
        "amendment_reason": "The predeclared first-three-round rule did not select 54 shards. The completed six-round median gain of 30 over 15 exceeds 5%; a separate follow-up asks whether gains continue beyond 30. It does not change the primary selection or combine the new 96 GiB series with the primary 32 GiB series.",
        "primary": primary,
        "completed_reads": reads,
        "writer_binary_sha256": WRITER_SHA256,
        "source_sha256": plan["input_sha256"],
        "minimum_logical_bytes": MINIMUM_LOGICAL_BYTES,
        "minimum_requested_frames": frames,
        "minimum_frame_rounded_logical_bytes": frames * base.FRAME_BYTES,
        "local_plan_override": {
            "shard_count.minimum_logical_bytes": {
                "before": plan["shard_count"]["minimum_logical_bytes"],
                "after": MINIMUM_LOGICAL_BYTES,
            }
        },
        "measurement_policy": base.STREAM_POLICY,
        "warmup_s": plan["shard_count"]["warmup_s"],
        "duration_s": plan["shard_count"]["duration_s"],
        "writer_resources": plan["writer_resources"],
        "geometry_frames": plan["shard_count"]["geometry_frames"],
        "cases": {str(target): case for target, case in geometries.items()},
        "rounds": 3,
        "planned_observations": 12,
        "seed": plan["seed"],
        "order_policy": "Seeded starting order for 30/54, reversed on the next round; 15-shard references before and after every pair",
        "schedule": schedule,
        "deadline_seconds": args.deadline_seconds,
        "native_case_timeout_seconds": 420,
        "automatic_retries": 0,
        "retention": "Native records and logs retained; successful temporary extension stores removed by the existing Study runner; failed stores retained; primary retained arrays untouched",
        "protected_file_hashes": before,
        "harness_sha256": {
            "extend_shards.py": file_hash(__file__),
            "write_benchmark.py": file_hash(base.__file__),
        },
        "environment": load(output / "environment.json")
        if (output / "environment.json").exists()
        else None,
    }
    protocol["protocol_sha256"] = protocol_hash(protocol)
    save(output / "protocol.json", protocol)
    save(output / "schedule.json", schedule)
    study = base.Study(root, output / "measurements", args.deadline_seconds)
    study.plan["shard_count"]["minimum_logical_bytes"] = MINIMUM_LOGICAL_BYTES
    unchanged = json.loads(json.dumps(study.plan))
    unchanged["shard_count"]["minimum_logical_bytes"] = plan["shard_count"][
        "minimum_logical_bytes"
    ]
    require(unchanged == plan, "Local plan changed beyond the declared minimum input")
    original_validate = base.validate_native

    def validate_extension(native, case, frames=None, small=False):
        metrics = original_validate(native, case, frames, small)
        require(
            frames is None and not small and case["family"] == FAMILY,
            "Unexpected follow-up observation type",
        )
        require(
            metrics["logical_bytes"] >= MINIMUM_LOGICAL_BYTES,
            "Follow-up observation did not reach 96 GiB of logical input",
        )
        return metrics

    base.validate_native = validate_extension
    began = time.monotonic()
    try:
        for slot in schedule:
            case = dict(geometries[slot["target_shards"]])
            case.update(
                experiment=FAMILY,
                family=FAMILY,
                protocol_sha256=protocol["protocol_sha256"],
                minimum_logical_bytes=MINIMUM_LOGICAL_BYTES,
            )
            study.run(case, slot["round"], slot["role"])
        require(
            len(study.records) == 12
            and all(record["status"] == "pass" for record in study.records),
            "Follow-up observations are incomplete",
        )
        require(
            protected_files(root, primary, reads) == before,
            "A primary artifact changed during the follow-up",
        )
        pairs = []
        for repeat in range(1, 4):
            samples = {
                row["case"]["actual_layer_shards"]: row
                for row in study.records
                if row["round"] == repeat and row["role"] == "sample"
            }
            pairs.append(
                {
                    "round": repeat,
                    "logical_gibs_30": samples[30]["metrics"]["logical_gibs"],
                    "logical_gibs_54": samples[54]["metrics"]["logical_gibs"],
                    "ratio_54_over_30": samples[54]["metrics"]["logical_gibs"]
                    / samples[30]["metrics"]["logical_gibs"],
                }
            )
        completion = {
            "status": "pass",
            "family": FAMILY,
            "observations": 12,
            "planned_observations": 12,
            "rounds": 3,
            "minimum_logical_bytes": MINIMUM_LOGICAL_BYTES,
            "protocol_sha256": protocol["protocol_sha256"],
            "slurm_job_id": os.environ["SLURM_JOB_ID"],
            "elapsed_seconds": time.monotonic() - began,
            "pairs": pairs,
            "median_54_over_30": statistics.median(
                row["ratio_54_over_30"] for row in pairs
            ),
            "primary_artifacts_unchanged": True,
        }
        save(output / "measurements/complete.json", completion)
        save(output / "complete.json", completion)
        print(json.dumps(completion, sort_keys=True), flush=True)
        return 0
    except BaseException as error:
        save(
            output / "failure.json",
            {
                "status": "error",
                "family": FAMILY,
                "protocol_sha256": protocol["protocol_sha256"],
                "recorded_observations": len(study.records),
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
        )
        save(
            output / "measurements/not-run.json",
            [
                {**slot, "status": "not_run_after_error"}
                for slot in schedule[len(study.records) :]
            ],
        )
        raise
    finally:
        base.validate_native = original_validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deadline-seconds", type=float, default=1000)
    return execute(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
