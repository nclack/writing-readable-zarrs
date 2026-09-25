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
attempt="$study_root/jobs/fill-fix-$SLURM_JOB_ID"
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
cp "$study_root/sources/diagnose_reads.py" "$study_root/sources/read_benchmark.py" \
    "$study_root/writer-fill-value.patch" "$attempt/"
python_bin="$HOME/tmp/2026-09-25-damacy-l40-nfs/environment/bin/python"
source_path="$HOME/tmp/2026-09-07-chucky-microscopy-pr/worktree/bench/data/microscopy/data/bbbc022-v1/bbbc022-mito.raw"
"$python_bin" "$study_root/sources/diagnose_reads.py" \
    --roundtrip "$study_root/jobs/read-preflight-3836086/writer-roundtrip.json" \
    --source "$source_path" --helpers-dir "$study_root/sources" \
    --output "$attempt/diagnosis" > "$attempt/diagnosis.log" 2>&1
"$python_bin" - "$study_root" "$attempt" <<'PY'
import json, os, sys
from pathlib import Path
import cpu_pareto as base
root, attempt = map(Path, sys.argv[1:])
assert base.physical_cpus() == len(os.sched_getaffinity(0)) == int(os.environ['SLURM_CPUS_PER_TASK'])
diagnosis = json.loads((attempt / 'diagnosis/diagnosis.json').read_text())
assert diagnosis['original_metadata_unchanged']
assert diagnosis['reads'][0]['result']['status'] == 'failed'
assert all(row['result']['status'] == 'passed' and row['returncode'] == 0
           for row in diagnosis['reads'][1:])
assert all(row['decoded_matches_source'] for row in diagnosis['first_chunk']['observations'])
manifest = json.loads((root / 'jobs/read-preflight-3836086/manifest.json').read_text())
manifest['layouts'][0]['path'] = diagnosis['metadata_view_uri']
(attempt / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('Metadata-only correction restores Damacy interior and edge reads; Blosc bytes match source', flush=True)
PY
"$python_bin" "$study_root/sources/read_benchmark.py" --manifest "$attempt/manifest.json" \
    --source "$source_path" --output "$attempt/readers" --preflight --deadline-seconds 500 \
    > "$attempt/readers.log" 2>&1
export PATH="$HOME/.pixi/bin:$HOME/.pixi/envs/cuda-toolkit/bin:$PATH"
export CUDAToolkit_ROOT="$HOME/.pixi/envs/cuda-toolkit"
export LD_LIBRARY_PATH="$HOME/opt/chucky-deps/.pixi/envs/default/lib:$HOME/opt/nvcomp-5.3.0.16/lib:$HOME/opt/lib"
cmake --build "$study_root/build/writer" -j16 --target \
    bench_stream_microscopy bench_stream_smallepoch_single test_bench_coverage \
    test_bench_report test_bench_reset test_bench_multiscale test_json_writer test_zarr_array \
    > "$attempt/writer-build.log" 2>&1
ctest --test-dir "$study_root/build/writer" --output-on-failure --no-tests=error --timeout 120 \
    -R '^test-test_(json_writer|zarr_array)$' > "$attempt/metadata-tests.log" 2>&1
"$python_bin" - "$study_root" "$attempt" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
root, attempt = map(Path, sys.argv[1:])
hashes = json.loads((root / 'source-hashes.json').read_text())
change = json.loads((root / 'fill-value-fix.json').read_text())
name = change['source_file']
assert hashes[name] == change['before_sha256']
assert hashlib.sha256((root / name).read_bytes()).hexdigest() == change['after_sha256']
hashes[name] = change['after_sha256']
(root / 'source-hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
binary = root / 'build/writer/bench/bench_stream_microscopy'
record = {'path': str(binary), 'sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
          'slurm_build_job': os.environ['SLURM_JOB_ID'], 'zero_integer_fill_fix': change,
          'page_alignment': os.sysconf('SC_PAGE_SIZE')}
(root / 'writer-identity.json').write_text(json.dumps(record, indent=2) + '\n')
(attempt / 'writer-identity.json').write_text(json.dumps(record, indent=2) + '\n')
PY
printf '%s\n' "$attempt" > "$study_root/fill-fix-complete.txt"
printf '%s\n' 'Both readers pass all four workloads; writer metadata fix built and tested'
