#!/usr/bin/env bash
set -euo pipefail
study_root="$(realpath "$1")"
test -n "${SLURM_JOB_ID:-}"
export PATH="$HOME/.pixi/bin:$HOME/.pixi/envs/cuda-toolkit/bin:$PATH"
export CUDAToolkit_ROOT="$HOME/.pixi/envs/cuda-toolkit"
export LD_LIBRARY_PATH="$HOME/opt/chucky-deps/.pixi/envs/default/lib:$HOME/opt/nvcomp-5.3.0.16/lib:$HOME/opt/lib"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 BLOSC_NTHREADS=1
export PYTHONDONTWRITEBYTECODE=1
attempt="$study_root/jobs/meter-fix-$SLURM_JOB_ID"
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
cp "${BASH_SOURCE[0]}" "$study_root/writer-metering.patch" "$study_root/metering-failure.md" "$attempt/"
python3 - "$study_root" "$attempt" <<'PY'
import difflib
import hashlib
import json
import os
from pathlib import Path
import sys

root, attempt = map(Path, sys.argv[1:])
cpus = os.sched_getaffinity(0)
cores = set()
for cpu in cpus:
    topology = Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
    cores.add(tuple((topology / name).read_text().strip()
                    for name in ('physical_package_id', 'core_id')))
if len(cpus) != 8 or len(cores) != 8:
    raise RuntimeError('This rebuild requires eight allocated physical CPU cores')
name = 'writer/bench/sink_metering.h'
before = (root / name).read_bytes()
expected_before = '3fe30f2377bdf8ce602a931570c5c52a6ee542c5bbd75486353228a8a79b84c1'
expected_after = '140df2d3624db8b7376f2519ea569352bebd22022b22cad8adbca087650a4c8d'
if hashlib.sha256(before).hexdigest() != expected_before:
    raise RuntimeError('Metering header differs from the reviewed original')
hash_bytes = (root / 'source-hashes.json').read_bytes()
hashes = json.loads(hash_bytes)
if hashes[name] != expected_before:
    raise RuntimeError('Source manifest does not identify the reviewed metering header')
identity_bytes = (root / 'writer-identity.json').read_bytes()
identity = json.loads(identity_bytes)
binary = root / 'build/writer/bench/bench_stream_microscopy'
if Path(identity['path']).resolve() != binary.resolve():
    raise RuntimeError('Writer identity names a different binary')
if hashlib.sha256(binary.read_bytes()).hexdigest() != identity['sha256']:
    raise RuntimeError('Current writer binary differs from its recorded identity')
after = before.replace(b'#define METER_MAX_WRITERS 32\n', b'#define METER_MAX_WRITERS 64\n')
if hashlib.sha256(after).hexdigest() != expected_after:
    raise RuntimeError('Unexpected replacement content')
expected_patch = ''.join(difflib.unified_diff(
    before.decode().splitlines(keepends=True), after.decode().splitlines(keepends=True),
    fromfile='a/bench/sink_metering.h', tofile='b/bench/sink_metering.h'))
patch = (root / 'writer-metering.patch').read_bytes()
if patch.decode() != expected_patch:
    raise RuntimeError('Patch differs from the reviewed single-header change')
test_sources = list((root / 'writer/bench').glob('test*')) + list((root / 'writer/tests').rglob('test*'))
direct_tests = [str(path.relative_to(root)) for path in test_sources
                if path.is_file() and path.suffix in ('.c', '.h', '.cpp', '.cu', '.py')
                and any(word in path.read_text() for word in
                        ('metering_sink', 'sink_metering', 'METER_MAX_WRITERS'))]
if direct_tests:
    raise RuntimeError(f'Unreviewed direct metering tests found: {direct_tests}')
(attempt / 'source-hashes.before.json').write_bytes(hash_bytes)
(attempt / 'writer-identity.before.json').write_bytes(identity_bytes)
(attempt / 'sink_metering.h.before').write_bytes(before)
change = {
    'source_file': name, 'before_sha256': expected_before, 'after_sha256': expected_after,
    'old_capacity': 32, 'new_capacity': 64,
    'patch_path': str(root / 'writer-metering.patch'),
    'patch_sha256': hashlib.sha256(patch).hexdigest(),
    'previous_binary_sha256': identity['sha256'],
    'original_failure_job': '3836189',
    'original_failure_record': '046-fast-target54-r4-sample',
    'scope': 'Study benchmark metering wrapper capacity only',
    'direct_metering_tests': direct_tests,
    'build_targets': ['bench_stream_microscopy', 'test_bench_coverage',
                      'test_bench_report', 'test_bench_reset',
                      'test_json_writer', 'test_zarr_array'], 'build_jobs': 8,
    'gpu_tests_run': False,
}
(attempt / 'change.json').write_text(json.dumps(change, indent=2) + '\n')
print('Pinned original header and binary verified; no direct metering tests are present', flush=True)
PY
patch --batch --forward --fuzz=0 -p1 --directory "$study_root/writer" \
    --input "$study_root/writer-metering.patch" > "$attempt/apply.log" 2>&1
cmake --build "$study_root/build/writer" -j8 --target \
    bench_stream_microscopy test_bench_coverage test_bench_report test_bench_reset \
    test_json_writer test_zarr_array \
    > "$attempt/writer-build.log" 2>&1
python3 - "$study_root" "$attempt" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import sys

root, attempt = map(Path, sys.argv[1:])
change = json.loads((attempt / 'change.json').read_text())
name = change['source_file']
if hashlib.sha256((root / name).read_bytes()).hexdigest() != change['after_sha256']:
    raise RuntimeError('Built metering header differs from the reviewed replacement')
old_hash_bytes = (attempt / 'source-hashes.before.json').read_bytes()
if (root / 'source-hashes.json').read_bytes() != old_hash_bytes:
    raise RuntimeError('Source manifest changed during the rebuild')
old_identity_bytes = (attempt / 'writer-identity.before.json').read_bytes()
if (root / 'writer-identity.json').read_bytes() != old_identity_bytes:
    raise RuntimeError('Writer identity changed during the rebuild')
previous = json.loads(old_identity_bytes)
hashes = json.loads(old_hash_bytes)
hashes[name] = change['after_sha256']
new_hash_bytes = (json.dumps(hashes, indent=2) + '\n').encode()
binary = root / 'build/writer/bench/bench_stream_microscopy'
binary_hash = hashlib.sha256(binary.read_bytes()).hexdigest()
if binary_hash == previous['sha256']:
    raise RuntimeError('Rebuilt binary is unchanged after the wrapper capacity change')
identity = {
    **previous, 'path': str(binary), 'sha256': binary_hash,
    'slurm_build_job': os.environ['SLURM_JOB_ID'],
    'page_alignment': os.sysconf('SC_PAGE_SIZE'),
    'metering_limit_fix': change,
    'previous_identity': previous,
    'previous_identity_path': str(attempt / 'writer-identity.before.json'),
    'previous_identity_sha256': hashlib.sha256(old_identity_bytes).hexdigest(),
    'source_hashes_sha256': hashlib.sha256(new_hash_bytes).hexdigest(),
}
identity_bytes = (json.dumps(identity, indent=2) + '\n').encode()
(attempt / 'source-hashes.json').write_bytes(new_hash_bytes)
(attempt / 'writer-identity.json').write_bytes(identity_bytes)
(attempt / 'validation.json').write_text(json.dumps({
    'status': 'pass', 'build_passed': True,
    'direct_metering_tests': [], 'gpu_tests_run': False,
    'changed_source_hashes': [name], 'writer_sha256': binary_hash,
}, indent=2) + '\n')
(root / 'source-hashes.json').write_bytes(new_hash_bytes)
(root / 'writer-identity.json').write_bytes(identity_bytes)
(root / 'metering-limit-fix.json').write_text(json.dumps(change, indent=2) + '\n')
PY
printf '%s\n' "$attempt" > "$study_root/meter-fix-complete.txt"
printf '%s\n' 'Metering wrapper capacity raised to 64; CPU build passed; GPU validation remains pending'
