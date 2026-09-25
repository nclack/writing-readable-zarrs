#!/usr/bin/env bash
set -euo pipefail
study_root="$(realpath "$1")"
test -n "${SLURM_JOB_ID:-}"
export PATH="$HOME/.pixi/bin:$HOME/.pixi/envs/cuda-toolkit/bin:$PATH"
export CUDAToolkit_ROOT="$HOME/.pixi/envs/cuda-toolkit"
export LD_LIBRARY_PATH="$HOME/opt/chucky-deps/.pixi/envs/default/lib:$HOME/opt/nvcomp-5.3.0.16/lib:$HOME/opt/lib"
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 BLOSC_NTHREADS=1
export PYTHONDONTWRITEBYTECODE=1
for setting in $(compgen -A variable CHUCKY_BENCH_); do unset "$setting"; done
attempt="$study_root/jobs/gpu-$SLURM_JOB_ID"
mkdir "$attempt"
cp "$study_root/jobs/run_gpu.sh" "$study_root/sources/write_benchmark.py" \
    "$study_root/plan.json" "$study_root/writer.patch" "$study_root/provenance.json" \
    "$study_root/writer-fill-value.patch" "$study_root/writer-identity.json" \
    "$study_root/writer-metering.patch" "$study_root/restarted-shards.json" \
    "$study_root/writer-run-hashes.json" "$study_root/source-hashes.json" "$attempt/"
date -u +%FT%TZ > "$attempt/started.txt"
finish() {
    result=$?
    cat /proc/self/mountstats > "$attempt/mountstats-after.txt"
    date -u +%FT%TZ > "$attempt/finished.txt"
    printf '%s\n' "$result" > "$attempt/exit-code.txt"
}
trap finish EXIT
scontrol show job -d "$SLURM_JOB_ID" > "$attempt/slurm-job.txt"
lscpu > "$attempt/lscpu.txt"
nvidia-smi -q -x > "$attempt/gpu.xml"
findmnt -J -T "$study_root" > "$attempt/filesystem.json"
cat /proc/self/mountstats > "$attempt/mountstats-before.txt"
python_bin="$HOME/tmp/2026-09-25-damacy-l40-nfs/environment/bin/python"
"$python_bin" - "$study_root" "$attempt" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
root, attempt = map(Path, sys.argv[1:])
assert len(os.sched_getaffinity(0)) == 8
affinity = sorted(os.sched_getaffinity(0))
physical = {(Path(f'/sys/devices/system/cpu/cpu{cpu}/topology/physical_package_id').read_text().strip(),
             Path(f'/sys/devices/system/cpu/cpu{cpu}/topology/core_id').read_text().strip())
            for cpu in affinity}
assert len(physical) == 8
mount = json.loads((attempt / 'filesystem.json').read_text())['filesystems'][0]
assert mount['fstype'] in ('nfs', 'nfs4')
assert 'nconnect=16' in mount['options'].split(',')
for name, expected in json.loads((root / 'source-hashes.json').read_text()).items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
for name, expected in json.loads((root / 'writer-run-hashes.json').read_text()).items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
identity = json.loads((root / 'writer-identity.json').read_text())
assert hashlib.sha256(Path(identity['path']).read_bytes()).hexdigest() == identity['sha256']
assert os.sysconf('SC_PAGE_SIZE') == identity['page_alignment']
(attempt / 'environment.json').write_text(json.dumps({
    'cpu_affinity': affinity, 'physical_cpu_count': len(physical),
    'page_alignment': os.sysconf('SC_PAGE_SIZE'), 'writer': identity,
    'python': sys.version, 'slurm_job_id': os.environ['SLURM_JOB_ID'],
    'node': os.environ['SLURM_JOB_NODELIST'],
    'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
    'slurm_job_gpus': os.environ.get('SLURM_JOB_GPUS'),
}, indent=2) + '\n')
restart = json.loads((root / 'restarted-shards.json').read_text())
previous = Path(restart['old_attempt'])
phases = {
    'shared_layouts': {
        'attempt': str(previous), 'job_id': '3836189',
        'writer_identity': json.loads((previous / 'writer-identity.json').read_text()),
        'selection': 'All 18 completed shared-layout samples carried unchanged',
    },
    'shard_count': {
        'attempt': str(attempt), 'job_id': os.environ['SLURM_JOB_ID'],
        'writer_identity': identity,
        'selection': 'Entire shard sweep restarted after raising the benchmark metering capacity',
    },
    'restart': restart,
}
(root / 'source-phases.json').write_text(json.dumps(phases, indent=2) + '\n')
(attempt / 'source-phases.json').write_text(json.dumps(phases, indent=2) + '\n')
print('Frozen sources and binary, eight physical CPUs and NFS nconnect=16 verified', flush=True)
PY
ctest --test-dir "$study_root/build/writer" --output-on-failure --no-tests=error --timeout 120 \
    -R '^(test-bench_(coverage|report|reset_(cpu|gpu))|test-test_(json_writer|zarr_array))$' \
    > "$attempt/writer-tests.log" 2>&1
"$python_bin" "$study_root/sources/write_benchmark.py" --root "$study_root" \
    --output "$attempt/preflight" --phase preflight --deadline-seconds 480 \
    > "$attempt/preflight.log" 2>&1
printf '%s\n' 'All seven small BBBC022 stores passed full value checks, including 54 shards'
shared_from="$study_root/jobs/gpu-3836189/measurements/observations.jsonl"
"$python_bin" "$study_root/sources/write_benchmark.py" --root "$study_root" \
    --output "$attempt/measurements" --phase shards --shared-from "$shared_from" --deadline-seconds 3000 \
    > "$attempt/measurements.log" 2>&1
printf '%s\n' "$attempt" > "$study_root/writes-complete.txt"
printf '%s\n' 'Shared layouts and shard-count measurements complete'
