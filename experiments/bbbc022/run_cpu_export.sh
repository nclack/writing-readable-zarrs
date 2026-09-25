#!/usr/bin/env bash
set -euo pipefail
study_root="$(realpath "$1")"
evidence_output="$2"
script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
test -n "${SLURM_JOB_ID:-}"
test -f "$study_root/reads-complete.txt"
test -f "$study_root/shard-extension-complete.txt"
export PATH="$HOME/.pixi/bin:$PATH"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export PYTHONDONTWRITEBYTECODE=1
export MPLCONFIGDIR="$(mktemp -d /tmp/bbbc022-final-plots.XXXXXXXX)"
python_bin="$HOME/tmp/2026-09-25-damacy-l40-nfs/environment/bin/python"
attempt="$study_root/jobs/export-$SLURM_JOB_ID"
mkdir "$attempt"
date -u +%FT%TZ > "$attempt/started.txt"
finish() {
    result=$?
    date -u +%FT%TZ > "$attempt/finished.txt"
    printf '%s\n' "$result" > "$attempt/exit-code.txt"
}
trap finish EXIT
scontrol show job -d "$SLURM_JOB_ID" > "$attempt/slurm-job.txt"
cp "$script_directory/source-manifest.json" "$attempt/"
"$python_bin" - "$study_root" "$script_directory" "$attempt" <<'PY'
from datetime import datetime, timezone
import hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path
root, scripts, attempt = map(Path, sys.argv[1:])
for name, expected in json.loads((scripts / 'source-manifest.json').read_text()).items():
    assert hashlib.sha256((scripts / name).read_bytes()).hexdigest() == expected, name
allocated = re.search(r'\bAllocTRES=([^\s]+)', (attempt / 'slurm-job.txt').read_text())
assert allocated and 'gres/gpu' not in allocated.group(1)
assert len(os.sched_getaffinity(0)) == 4
shutil.copyfile(scripts / 'size-accounting.md', root / 'size-accounting.md')
requests = json.loads((root / 'allocation-jobs.json').read_text())
jobs = requests['jobs'] + [{
    'job_id': os.environ['SLURM_JOB_ID'], 'budget': 'cpu', 'phase': 'final evidence export',
}]
assert len({row['job_id'] for row in jobs}) == len(jobs)
fields = ['JobIDRaw', 'JobName', 'Partition', 'State', 'ElapsedRaw', 'AllocCPUS',
          'AllocTRES', 'NodeList', 'Start', 'End', 'TimelimitRaw']
raw = subprocess.check_output([
    'sacct', '-X', '-j', ','.join(row['job_id'] for row in jobs),
    '--parsable2', '--noheader', '--format=' + ','.join(fields),
], text=True)
(attempt / 'sacct.txt').write_text(raw)
captured = {}
for line in raw.splitlines():
    values = line.split('|')
    assert len(values) == len(fields), line
    row = dict(zip(fields, values, strict=True))
    captured[row['JobIDRaw']] = row
assert set(captured) == {row['job_id'] for row in jobs}
totals = {key: {'allocated_seconds_at_capture': 0, 'upper_bound_seconds': 0,
                'budget_seconds': value}
          for key, value in requests['allocated_wall_budgets_seconds'].items()}
for job in jobs:
    row = captured[job['job_id']]
    elapsed = int(row['ElapsedRaw'])
    active = row['State'] in ('PENDING', 'RUNNING', 'COMPLETING', 'CONFIGURING')
    bound = max(elapsed, 60 * int(row['TimelimitRaw'])) if active else elapsed
    if job['budget'] == 'cpu':
        assert 'gres/gpu' not in row['AllocTRES'], row
    job.update(slurm=row, allocated_seconds_at_capture=elapsed,
               allocated_seconds_upper_bound=bound)
    totals[job['budget']]['allocated_seconds_at_capture'] += elapsed
    totals[job['budget']]['upper_bound_seconds'] += bound
for row in totals.values():
    row['within_budget'] = row['upper_bound_seconds'] <= row['budget_seconds']
    assert row['within_budget'], row
ledger = {
    'created_utc': datetime.now(timezone.utc).isoformat(),
    'method': 'Slurm allocation records only (-X), ElapsedRaw in seconds; steps are not added again. Queue time is excluded. Failed allocations count. Active jobs use their entire time limit for the conservative upper bound.',
    'scope': 'CPU and single-L40 allocated wall time, separately; not core-hours or billed cost',
    'jobs': jobs, 'totals': totals,
    'final_export_job_running_at_capture': os.environ['SLURM_JOB_ID'],
}
(root / 'allocation-ledger.json').write_text(json.dumps(ledger, indent=2) + '\n')
print(json.dumps(totals), flush=True)
PY
read_output="$(cat "$study_root/reads-complete.txt")"
"$python_bin" "$script_directory/export_evidence.py" --root "$study_root" \
    --reads "$read_output" --output "$evidence_output" > "$attempt/export.log" 2>&1
"$python_bin" "$evidence_output/export_evidence.py" --from-bundle "$evidence_output" \
    --output "$attempt/regenerated" --no-plots > "$attempt/regeneration.log" 2>&1
"$python_bin" - "$attempt" "$evidence_output" <<'PY'
from datetime import datetime, timezone
import gzip, hashlib, json, os, tarfile, sys
from pathlib import Path
attempt, evidence = map(Path, sys.argv[1:])
regenerated = attempt / 'regenerated'
audit = json.loads((evidence / 'validation.json').read_text())
assert audit['writer_complete'] and audit['reader_complete']
assert audit['reader_accepted_primary'] == 144
assert audit['writer_accepted_shared_samples'] == 18
assert audit['writer_accepted_shard_samples'] == 36
extension = json.loads((evidence / 'shard-extension-validation.json').read_text())
assert extension['complete'] and extension['rows'] == 12
assert extension['paired_54_over_30_rounds'] == 3
assert not extension['primary_pooling']
assert extension['primary_extension_decision']['include_actual54'] is False
names = [path.name for path in sorted(evidence.glob('*.csv'))]
names += ['findings.md', 'validation.json', 'shard-extension-validation.json',
          'shard-extension-protocol.json', 'source-phases.json', 'input-source.json',
          'retained-store-accounting.json', 'allocation-ledger.json', 'size-accounting.md',
          'reader.patch', 'reader-source.md', 'run_cpu_build.sh']
checked = {}
for name in names:
    original = (evidence / name).read_bytes()
    assert original == (regenerated / name).read_bytes(), name
    checked[name] = hashlib.sha256(original).hexdigest()
proof = {
    'status': 'pass', 'created_utc': datetime.now(timezone.utc).isoformat(),
    'slurm_job_id': os.environ['SLURM_JOB_ID'],
    'method': 'Regenerate tables, findings and validation from the portable bundle with --from-bundle --no-plots, then compare exact bytes.',
    'identical_files_sha256': checked,
    'primary_writer_complete': True, 'reader_complete': True,
    'separate_extension_complete': True,
}
(evidence / 'portable-verification.json').write_text(json.dumps(proof, indent=2) + '\n')
(attempt / 'portable-verification.json').write_text(json.dumps(proof, indent=2) + '\n')
checksums = {
    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(evidence.iterdir())
    if path.is_file() and path.name != 'output-checksums.json'
}
(evidence / 'output-checksums.json').write_text(json.dumps(checksums, indent=2, sort_keys=True) + '\n')
files = sorted(path for path in evidence.rglob('*') if path.is_file())
assert not any(path.is_symlink() for path in evidence.rglob('*'))
assert max(path.stat().st_size for path in files) < 95 * (1 << 20)
archive_path = evidence.with_suffix('.tar.gz')
archived_hashes = {}
with archive_path.open('wb') as output:
    with gzip.GzipFile(filename='', mode='wb', fileobj=output, mtime=0, compresslevel=9) as zipped:
        with tarfile.open(fileobj=zipped, mode='w|', format=tarfile.PAX_FORMAT) as archive:
            for path in files:
                name = evidence.name + '/' + path.relative_to(evidence).as_posix()
                item = tarfile.TarInfo(name)
                item.size = path.stat().st_size
                item.mode = 0o644
                item.mtime = 0
                with path.open('rb') as stream:
                    archive.addfile(item, stream)
                archived_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
verified = {}
with tarfile.open(archive_path, 'r:gz') as archive:
    for item in archive:
        assert item.isfile() and item.name in archived_hashes
        verified[item.name] = hashlib.sha256(archive.extractfile(item).read()).hexdigest()
assert verified == archived_hashes
with archive_path.open('rb') as stream:
    archive_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
evidence.with_suffix('.sha256').write_text(archive_hash + '  ' + archive_path.name + '\n')
report = {'status': 'pass', 'identical_files': len(checked), 'archive_files': len(files),
          'archive_bytes': archive_path.stat().st_size, 'archive_sha256': archive_hash}
(attempt / 'package-verification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report), flush=True)
PY
printf '%s\n' "$attempt" > "$study_root/evidence-complete.txt"
