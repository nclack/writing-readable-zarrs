#!/usr/bin/env bash
set -euo pipefail
study_root="$(realpath "$1")"
evidence_output="$2"
test -n "${SLURM_JOB_ID:-}"
test -f "$study_root/writes-complete.txt"
export PATH="$HOME/.pixi/bin:$PATH"
export LD_LIBRARY_PATH="$HOME/opt/lib:$HOME/.pixi/envs/damacy-cpu-deps/lib"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 BLOSC_NTHREADS=1
export PYTHONDONTWRITEBYTECODE=1
export MPLCONFIGDIR="$(mktemp -d /tmp/bbbc022-plots.XXXXXXXX)"
unset DAMACY_BENCH_READ_MODE DAMACY_BENCH_CPU_READ_CHUNKS DAMACY_TRACE_READS DAMACY_SHARD_ROOT DAMACY_SHARD_TRACE DAMACY_STORAGE_TIER
export PYTHONPATH="$study_root/build/reader/python:$study_root/sources"
export DAMACY_NFS_MOUNT=/mnt/main0
attempt="$study_root/jobs/reads-$SLURM_JOB_ID"
mkdir "$attempt"
date -u +%FT%TZ > "$attempt/started.txt"
finish() {
    result=$?
    cat /proc/self/mountstats > "$attempt/mountstats-after.txt"
    date -u +%FT%TZ > "$attempt/finished.txt"
    printf '%s\n' "$result" > "$attempt/exit-code.txt"
}
trap finish EXIT
cp "$study_root/jobs/run_cpu_reads.sh" "$study_root/sources/read_benchmark.py" \
    "$study_root/sources/account_stores.py" "$study_root/sources/export_evidence.py" \
    "$study_root/read-manifest.json" "$study_root/plan.json" \
    "$study_root/reader-run-hashes.json" "$study_root/source-hashes.json" "$attempt/"
scontrol show job -d "$SLURM_JOB_ID" > "$attempt/slurm-job.txt"
lscpu > "$attempt/lscpu.txt"
findmnt -J -T "$study_root" > "$attempt/filesystem.json"
cat /proc/self/mountstats > "$attempt/mountstats-before.txt"
python_bin="$HOME/tmp/2026-09-25-damacy-l40-nfs/environment/bin/python"
source_path="$HOME/tmp/2026-09-07-chucky-microscopy-pr/worktree/bench/data/microscopy/data/bbbc022-v1/bbbc022-mito.raw"
"$python_bin" - "$study_root" "$attempt" <<'PY'
import hashlib, json, os, re, subprocess, sys
from importlib.metadata import version
from pathlib import Path
import cpu_pareto as base
from damacy import _native
root, attempt = map(Path, sys.argv[1:])
affinity = sorted(os.sched_getaffinity(0))
assert base.physical_cpus() == len(affinity) == 48
assert not _native.CUDA_ENABLED
allocated = re.search(r'\bAllocTRES=([^\s]+)', (attempt / 'slurm-job.txt').read_text())
assert allocated and 'gres/gpu' not in allocated.group(1)
assert version('numpy') == '2.3.3' and version('tensorstore') == '0.1.85'
mount = json.loads((attempt / 'filesystem.json').read_text())['filesystems'][0]
assert mount['fstype'] in ('nfs', 'nfs4')
assert 'nconnect=16' in mount['options'].split(',')
for manifest in ('source-hashes.json', 'reader-run-hashes.json'):
    for name, expected in json.loads((root / manifest).read_text()).items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
build = Path((root / 'build-complete.txt').read_text().strip())
identity = json.loads((build / 'reader-identity.json').read_text())
native_hash = hashlib.sha256(Path(_native.__file__).read_bytes()).hexdigest()
assert native_hash == identity['native_sha256']
dependencies = subprocess.check_output(['ldd', _native.__file__], text=True)
assert all(name not in dependencies.lower() for name in ('libcuda', 'libcudart', 'libnvcomp'))
environment = {
    'cpu_affinity': affinity, 'physical_cpu_count': base.physical_cpus(),
    'python': sys.version, 'numpy': version('numpy'),
    'tensorstore': version('tensorstore'), 'reader': identity,
    'loaded_native': _native.__file__, 'loaded_native_sha256': native_hash,
    'loaded_dependencies': dependencies, 'cuda_enabled': False,
    'allocated_resources': allocated.group(1),
    'slurm_job_id': os.environ['SLURM_JOB_ID'],
}
(attempt / 'environment.json').write_text(json.dumps(environment, indent=2) + '\n')
print('Frozen CPU reader, 48 physical CPUs and NFS nconnect=16 verified', flush=True)
PY
"$python_bin" "$study_root/sources/account_stores.py" --root "$study_root" \
    --output "$study_root/retained-store-accounting.json" > "$attempt/accounting.log" 2>&1
"$python_bin" "$study_root/sources/read_benchmark.py" --manifest "$study_root/read-manifest.json" \
    --source "$source_path" --output "$attempt/preflight" --preflight --deadline-seconds 800 \
    > "$attempt/preflight.log" 2>&1
printf '%s\n' 'Both readers passed all four workloads on all six retained layouts'
"$python_bin" "$study_root/sources/read_benchmark.py" --manifest "$study_root/read-manifest.json" \
    --source "$source_path" --output "$attempt/measurements" --deadline-seconds 5000 \
    > "$attempt/measurements.log" 2>&1
"$python_bin" - "$attempt" <<'PY'
import json, sys
from pathlib import Path
attempt = Path(sys.argv[1])
for name, count in (('preflight', 48), ('measurements', 144)):
    summary = json.loads((attempt / name / 'summary.json').read_text())
    assert summary['complete'] and summary['planned_observations'] == count
    assert summary['status_counts'] == {'accepted': count}
print('All 144 scheduled read measurements accepted', flush=True)
PY
printf '%s\n' "$attempt/measurements" > "$study_root/reads-complete.txt"
cat /proc/self/mountstats > "$attempt/mountstats-after-measurements.txt"
"$python_bin" "$study_root/sources/export_evidence.py" --root "$study_root" \
    --reads "$attempt/measurements" --output "$evidence_output" > "$attempt/export.log" 2>&1
"$python_bin" "$evidence_output/export_evidence.py" --from-bundle "$evidence_output" \
    --output "$attempt/regenerated" --no-plots > "$attempt/regeneration.log" 2>&1
"$python_bin" - "$attempt" "$evidence_output" <<'PY'
import hashlib, json, sys
from pathlib import Path
attempt, evidence = map(Path, sys.argv[1:])
checked = {}
for source in sorted(evidence.glob('*.csv')):
    regenerated = attempt / 'regenerated' / source.name
    assert regenerated.read_bytes() == source.read_bytes(), source.name
    checked[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
for name in ('findings.md', 'validation.json'):
    assert (attempt / 'regenerated' / name).read_bytes() == (evidence / name).read_bytes(), name
validation = json.loads((evidence / 'validation.json').read_text())
assert validation['writer_complete'] and validation['reader_complete']
(attempt / 'portable-verification.json').write_text(json.dumps({
    'status': 'pass', 'identical_csv_files': checked,
    'identical_findings_and_validation': True,
}, indent=2) + '\n')
print('Portable evidence regeneration reproduced every CSV, findings and validation', flush=True)
PY
printf '%s\n' 'BBBC022 measurements and evidence export complete'
