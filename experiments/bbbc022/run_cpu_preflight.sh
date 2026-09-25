#!/usr/bin/env bash
set -euo pipefail
study_root="$(realpath "$1")"
test -n "${SLURM_JOB_ID:-}"
export PATH="$HOME/.pixi/bin:$PATH"
export LD_LIBRARY_PATH="$HOME/opt/lib:$HOME/.pixi/envs/damacy-cpu-deps/lib"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 BLOSC_NTHREADS=1
export PYTHONDONTWRITEBYTECODE=1
unset DAMACY_BENCH_READ_MODE DAMACY_BENCH_CPU_READ_CHUNKS DAMACY_TRACE_READS DAMACY_SHARD_ROOT DAMACY_SHARD_TRACE DAMACY_STORAGE_TIER
export PYTHONPATH="$study_root/build/reader/python:$study_root/sources"
export DAMACY_NFS_MOUNT=/mnt/main0
attempt="$study_root/jobs/read-preflight-$SLURM_JOB_ID"
mkdir "$attempt"
date -u +%FT%TZ > "$attempt/started.txt"
finish() {
    result=$?
    date -u +%FT%TZ > "$attempt/finished.txt"
    printf '%s\n' "$result" > "$attempt/exit-code.txt"
}
trap finish EXIT
scontrol show job -d "$SLURM_JOB_ID" > "$attempt/slurm-job.txt"
lscpu > "$attempt/lscpu.txt"
findmnt -J -T "$study_root" > "$attempt/filesystem.json"
cp "$study_root/sources/read_benchmark.py" "$study_root/sources/write_benchmark.py" "$attempt/"
python_bin="$HOME/tmp/2026-09-25-damacy-l40-nfs/environment/bin/python"
"$python_bin" - "$study_root" "$attempt" <<'PY'
import json, os, sys
from pathlib import Path
import numpy as np
from damacy import _native
from write_benchmark import check_store, fixed_cases
root, attempt = map(Path, sys.argv[1:])
assert len(os.sched_getaffinity(0)) == 48
assert not _native.CUDA_ENABLED
plan = json.loads((root / 'plan.json').read_text())
provenance = json.loads((root / 'provenance.json').read_text())
store = root / 'jobs/gpu-3836072/preflight/001-c16-r0-preflight/store'
raw = np.fromfile(provenance['input_path'], dtype='<u2').reshape(16, 520, 696)
check = check_store(store, fixed_cases(plan)[0], raw, frames=17, all_planes=True)
(attempt / 'writer-roundtrip.json').write_text(json.dumps(check, indent=2) + '\n')
manifest = {
    'schema_version': 1,
    'source': {'shape': [16, 520, 696], 'dtype': 'uint16',
               'sha256': provenance['input_sha256'], 'replay': 'cyclic', 'start_plane': 0},
    'shape': [17, 520, 696], 'shard_shape': [2048, 512, 512],
    'layouts': [{'id': 'c16', 'path': str(store / 'images'), 'chunk_shape': [1, 64, 128]}],
    'helpers_dir': str(root / 'sources'),
}
(attempt / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('All 17 written planes match BBBC022, including the repeated source plane', flush=True)
PY
source_path="$HOME/tmp/2026-09-07-chucky-microscopy-pr/worktree/bench/data/microscopy/data/bbbc022-v1/bbbc022-mito.raw"
"$python_bin" "$study_root/sources/read_benchmark.py" --manifest "$attempt/manifest.json" \
    --source "$source_path" --output "$attempt/readers" --preflight --deadline-seconds 500 \
    > "$attempt/readers.log" 2>&1
printf '%s\n' "$attempt" > "$study_root/read-preflight-complete.txt"
printf '%s\n' 'Both CPU readers passed the small BBBC022 preflight'
