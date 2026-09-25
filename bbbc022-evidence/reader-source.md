The measured Damacy reader is revision
`8d0931e7d131fd5d4c565458736ab586012c78c1` plus [reader.patch](reader.patch).
Apply this single patch once to a clean checkout of that revision:

```sh
git apply --check /path/to/reader.patch
git apply /path/to/reader.patch
```

The retained copy is byte-for-byte
[experiment.patch](/mnt/main0/home/nclack/tmp/2026-09-25-damacy-nfs-spot/experiment.patch)
from the original frozen reader study: 28,489 bytes, SHA-256
`8ee9c7d3e2d239ad0e8ea929e2269cdc07c14ebce95f7a8589635294ab08d75d`.
The earlier patch files overlap:

| Original file | Relationship to the retained patch |
| --- | --- |
| `experiment.patch` | Complete cumulative changes against the recorded revision. |
| `benchmark-controls.patch` | Byte-identical duplicate of `experiment.patch`. |
| `baseline.patch` | Earlier cumulative snapshot; its CPU executor and pipeline test start from older Git blobs. Its changes are included in the retained patch. |
| `common-lz4.patch` | Earlier CPU Blosc-LZ4 decoding and test changes, already included in the retained patch. |

These files are snapshots, not successive patches to apply in order.
Only `reader.patch` is needed. The original
[freeze.py](/mnt/main0/home/nclack/tmp/2026-09-25-damacy-nfs-spot/freeze.py)
writes hash manifests; it does not apply patches or transform native sources.
All four original patch hashes and the script hash match that study's
[sources.sha256](/mnt/main0/home/nclack/tmp/2026-09-25-damacy-nfs-spot/sources.sha256).

The patch adds CPU Blosc-LZ4 decoding, file-handle lifetime and readahead
controls through `DAMACY_BENCH_READ_MODE`, reader I/O counters, and CPU
buffer-setting inspection. It changes five implementation/header files
and three test/fixture files. The two 256-chunk input buffers are already
part of the base revision.

Static reconstruction from Git objects, with exact hunk-context checks,
matches every SHA-256 in
[reader-native-files.json](/mnt/main0/home/nclack/tmp/2026-09-25-bbbc022-read-write/reader-native-files.json):
eight changed files and 302 unchanged files, 310 matches and zero mismatches.
The manifest's SHA-256 is
`c61ad8833a27607c80325f849dfde8b38c5c542a92b2c98c1ea9b5f5430bce41`.
The original and BBBC022 frozen source copies also match all 310 hashes.
The same hashes appear in `reader-native-sources.sha256` and the
`reader/` entries of `source-hashes.json`. A separate `git apply --check`
passed against temporary copies of the eight pristine base files;
applying the duplicate patch after reconstruction correctly failed.

The recorded CPU build is job `3835899`, with native library SHA-256
`7253dd4d69764cd4597b82b60e79cdfe323bfa040567e1185e2794f8c0c82bad`;
see its [reader identity](/mnt/main0/home/nclack/tmp/2026-09-25-bbbc022-read-write/jobs/build-3835899/reader-identity.json)
and [build recipe](run_cpu_build.sh). This provenance check reconstructed
source bytes only; it did not rebuild the library or run tests or measurements.
