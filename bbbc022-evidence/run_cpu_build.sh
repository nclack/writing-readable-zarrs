#!/usr/bin/env bash
set -euo pipefail
study_root="$(realpath "$1")"
test -n "${SLURM_JOB_ID:-}"
export PATH="$HOME/.pixi/bin:$PATH"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 BLOSC_NTHREADS=1
attempt="$study_root/jobs/build-$SLURM_JOB_ID"
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
findmnt -T "$study_root" > "$attempt/filesystem.txt"
python_bin="$HOME/tmp/2026-09-25-damacy-l40-nfs/environment/bin/python"
"$python_bin" - "$study_root" <<'PY'
import hashlib, json, sys
from pathlib import Path
root = Path(sys.argv[1])
record = json.loads((root / 'provenance.json').read_text())
source = Path(record['input_path'])
assert source.stat().st_size == 16 * 520 * 696 * 2
assert hashlib.sha256(source.read_bytes()).hexdigest() == record['input_sha256']
files = {}
for name in ('writer', 'reader', 'sources'):
    for path in sorted((root / name).rglob('*')):
        generated = any(part in ('__pycache__', '.pytest_cache', '.ruff_cache')
                        or part.startswith('.coverage') for part in path.parts)
        if path.is_file() and not generated:
            files[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
(root / 'source-hashes.json').write_text(json.dumps(files, indent=2) + '\n')
print('BBBC022 input and frozen source hashes recorded', flush=True)
PY
export CMAKE_PREFIX_PATH="$HOME/opt:$HOME/.pixi/envs/damacy-cpu-deps"
export PKG_CONFIG_PATH="$HOME/opt/lib/pkgconfig:$HOME/.pixi/envs/damacy-cpu-deps/lib/pkgconfig"
export LD_LIBRARY_PATH="$HOME/opt/lib:$HOME/.pixi/envs/damacy-cpu-deps/lib"
cmake -S "$study_root/reader" -B "$study_root/build/reader" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DDAMACY_CUDA=OFF -DDAMACY_PYTHON=ON \
    -DPython_EXECUTABLE="$python_bin" -DCMAKE_DISABLE_FIND_PACKAGE_CUDAToolkit=ON \
    > "$attempt/reader-configure.log" 2>&1
cmake --build "$study_root/build/reader" -j16 > "$attempt/reader-build.log" 2>&1
ctest --test-dir "$study_root/build/reader" --output-on-failure --timeout 180 -j4 \
    > "$attempt/reader-tests.log" 2>&1
export PYTHONPATH="$study_root/build/reader/python:$study_root/sources"
"$python_bin" - "$attempt" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path
from importlib.metadata import version
from damacy import _native
import tensorstore
assert not _native.CUDA_ENABLED
assert hasattr(_native, 'bench_reader_stats') and hasattr(_native, 'bench_cpu_settings')
dependencies = subprocess.check_output(['ldd', _native.__file__], text=True)
assert all(name not in dependencies.lower() for name in ('libcuda', 'libcudart', 'libnvcomp'))
assert version('numpy') == '2.3.3' and version('tensorstore') == '0.1.85'
Path(sys.argv[1], 'reader-identity.json').write_text(json.dumps({
    'python': sys.version, 'damacy_native': _native.__file__,
    'native_sha256': hashlib.sha256(Path(_native.__file__).read_bytes()).hexdigest(),
    'dependencies': dependencies, 'tensorstore_version': version('tensorstore'),
    'numpy_version': version('numpy'), 'cuda_enabled': False,
}, indent=2) + '\n')
print('CPU reader build and tests passed', flush=True)
PY
export PATH="$HOME/.pixi/bin:$HOME/.pixi/envs/cuda-toolkit/bin:$PATH"
export CUDAToolkit_ROOT="$HOME/.pixi/envs/cuda-toolkit"
chucky_deps="$HOME/opt/chucky-deps/.pixi/envs/default"
cmake -S "$study_root/writer" -B "$study_root/build/writer" -G Ninja \
    -DCHUCKY_ENABLE_GPU=ON -DCMAKE_CUDA_ARCHITECTURES=89 \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCHUCKY_OUTPUT_BUFFERS=4 -DCHUCKY_IO_WORKERS=32 \
    -DCMAKE_PREFIX_PATH="$chucky_deps;$HOME/opt/nvcomp-5.3.0.16;$HOME/.pixi/envs/cuda-toolkit" \
    > "$attempt/writer-configure.log" 2>&1
cmake --build "$study_root/build/writer" -j16 --target \
    bench_stream_microscopy bench_stream_smallepoch_single test_bench_coverage \
    test_bench_report test_bench_reset test_bench_multiscale \
    > "$attempt/writer-build.log" 2>&1
sha256sum "$study_root/build/writer/bench/bench_stream_microscopy" > "$attempt/writer-binary.sha256"
printf '%s\n' "$attempt" > "$study_root/build-complete.txt"
printf '%s\n' 'CPU reader and L40 writer builds complete'
