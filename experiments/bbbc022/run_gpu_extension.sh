#!/usr/bin/env bash
#SBATCH --partition=l40-reserved
#SBATCH --qos=dev
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --gres=gpu:l40:1
#SBATCH --threads-per-core=1
#SBATCH --time=00:20:00
#SBATCH --job-name=bbbc022-extension
set -euo pipefail
study_root="$(realpath "$1")"
test -n "${SLURM_JOB_ID:-}"
test -f "$study_root/reads-complete.txt"
test -f "$study_root/writes-complete.txt"
test ! -e "$study_root/shard-extension-complete.txt"
export PATH="$HOME/.pixi/bin:$HOME/.pixi/envs/cuda-toolkit/bin:$PATH"
export CUDAToolkit_ROOT="$HOME/.pixi/envs/cuda-toolkit"
export LD_LIBRARY_PATH="$HOME/opt/chucky-deps/.pixi/envs/default/lib:$HOME/opt/nvcomp-5.3.0.16/lib:$HOME/opt/lib"
export OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 BLOSC_NTHREADS=1
export PYTHONDONTWRITEBYTECODE=1
for setting in $(compgen -A variable CHUCKY_BENCH_); do unset "$setting"; done
attempt="$study_root/jobs/gpu-extension-$SLURM_JOB_ID"
mkdir "$attempt"
date -u +%FT%TZ > "$attempt/started.txt"
finish() {
    result=$?
    cat /proc/self/mountstats > "$attempt/mountstats-after.txt"
    date -u +%FT%TZ > "$attempt/finished.txt"
    printf '%s\n' "$result" > "$attempt/exit-code.txt"
}
trap finish EXIT
cp "$study_root/jobs/run_gpu_extension.sh" "$study_root/sources/extend_shards.py" \
    "$study_root/sources/write_benchmark.py" "$study_root/plan.json" \
    "$study_root/writer-identity.json" "$study_root/writer-run-hashes.json" \
    "$study_root/extension-run-hashes.json" \
    "$study_root/source-hashes.json" "$study_root/provenance.json" \
    "$study_root/writer.patch" "$study_root/writer-fill-value.patch" \
    "$study_root/writer-metering.patch" "$attempt/"
scontrol show job -d "$SLURM_JOB_ID" > "$attempt/slurm-job.txt"
lscpu > "$attempt/lscpu.txt"
nvidia-smi -q -x > "$attempt/gpu.xml"
findmnt -J -T "$study_root" > "$attempt/filesystem.json"
cat /proc/self/mountstats > "$attempt/mountstats-before.txt"
python_bin="$HOME/tmp/2026-09-25-damacy-l40-nfs/environment/bin/python"
"$python_bin" - "$study_root" "$attempt" <<'PY'
import hashlib, json, os, subprocess, sys
from importlib.metadata import version
from pathlib import Path
root, attempt = map(Path, sys.argv[1:])
affinity = sorted(os.sched_getaffinity(0))
physical = {(Path(f'/sys/devices/system/cpu/cpu{cpu}/topology/physical_package_id').read_text().strip(),
             Path(f'/sys/devices/system/cpu/cpu{cpu}/topology/core_id').read_text().strip())
            for cpu in affinity}
assert len(physical) == len(affinity) == int(os.environ['SLURM_CPUS_PER_TASK']) == 8
assert int(os.environ['SLURM_MEM_PER_NODE']) == 65536
visible = os.environ.get('CUDA_VISIBLE_DEVICES', '').split(',')
assert len(visible) == 1 and visible[0] not in ('', '-1', 'NoDevFiles')
gpu = subprocess.check_output(['nvidia-smi', '--id=' + visible[0], '--query-gpu=name,uuid',
                               '--format=csv,noheader'], text=True).strip()
assert len(gpu.splitlines()) == 1 and gpu.split(',')[0].strip() == 'NVIDIA L40'
assert version('numpy') == '2.3.3' and version('tensorstore') == '0.1.85'
mount = json.loads((attempt / 'filesystem.json').read_text())['filesystems'][0]
assert mount['fstype'] in ('nfs', 'nfs4') and 'nconnect=16' in mount['options'].split(',')
for manifest in ('source-hashes.json', 'writer-run-hashes.json', 'extension-run-hashes.json'):
    for name, expected in json.loads((root / manifest).read_text()).items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
identity = json.loads((root / 'writer-identity.json').read_text())
assert hashlib.sha256(Path(identity['path']).read_bytes()).hexdigest() == identity['sha256'] == '9702c7bb6089c69449553fa4a42e9ff96af7c4a5461acbb86bccbf8a32288ed9'
assert os.sysconf('SC_PAGE_SIZE') == identity['page_alignment']
paths = {
    'run_gpu_extension.sh': root / 'jobs/run_gpu_extension.sh',
    'extend_shards.py': root / 'sources/extend_shards.py',
    'write_benchmark.py': root / 'sources/write_benchmark.py',
}
hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
(attempt / 'harness-hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
environment = {
    'cpu_affinity': affinity, 'physical_cpu_count': len(physical), 'memory_mib': 65536,
    'page_alignment': os.sysconf('SC_PAGE_SIZE'), 'writer': identity,
    'python': sys.version, 'numpy': version('numpy'), 'tensorstore': version('tensorstore'),
    'slurm_job_id': os.environ['SLURM_JOB_ID'], 'node': os.environ['SLURM_JOB_NODELIST'],
    'cuda_visible_devices': os.environ['CUDA_VISIBLE_DEVICES'], 'gpu': gpu,
    'slurm_job_gpus': os.environ.get('SLURM_JOB_GPUS'), 'harness_sha256': hashes,
    'filesystem': mount,
}
(attempt / 'environment.json').write_text(json.dumps(environment, indent=2) + '\n')
print('Frozen writer, one L40, eight physical CPUs, 64 GiB and NFS nconnect=16 verified', flush=True)
PY
"$python_bin" "$study_root/sources/extend_shards.py" --root "$study_root" \
    --output "$attempt" --deadline-seconds 1000 > "$attempt/extension.log" 2>&1
"$python_bin" - "$attempt" <<'PY'
import hashlib, json, sys
from pathlib import Path
attempt = Path(sys.argv[1])
protocol = json.loads((attempt / 'protocol.json').read_text())
claimed = protocol.pop('protocol_sha256')
assert hashlib.sha256(json.dumps(protocol, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest() == claimed
complete = json.loads((attempt / 'complete.json').read_text())
assert complete['status'] == 'pass' and complete['observations'] == complete['planned_observations'] == 12
assert complete['protocol_sha256'] == claimed and complete['primary_artifacts_unchanged']
records = [json.loads(line) for line in (attempt / 'measurements/observations.jsonl').read_text().splitlines()]
assert len(records) == 12 and all(row['status'] == 'pass' and row['returncode'] == 0 for row in records)
assert all(row['case']['experiment'] == row['case']['family'] == 'shard-count-extension'
           and row['case']['protocol_sha256'] == claimed
           and row['native']['measurement']['logical_input_bytes'] >= 96 * (1 << 30)
           for row in records)
PY
printf '%s\n' "$attempt" > "$study_root/shard-extension-complete.txt"
printf '%s\n' 'Separately labeled 96 GiB shard follow-up complete'
