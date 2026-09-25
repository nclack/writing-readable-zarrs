For the six retained BBBC022 fixed-volume stores, the writer's metered
output and the final file lengths agree exactly after accounting for
truncated footer padding and final metadata. This follows from the write
path and was checked using existing file metadata and writer records in
CPU job `3836384`.

Let `W` be native `measurement.output_bytes`, `L_j` each final shard file's
`st_size`, `A` the writer's alignment, and `M` the combined final metadata
file lengths. For these stores, `A = 4096` bytes:

```text
P = sum((-L_j) % A)
W = sum(ceil(L_j / A) * A)
S = W - P + M
```

Here `P` is the discarded final footer padding and `S` is the sum of all
regular-file lengths in the store, including the parent group metadata.
Both identities have a zero-byte residual for every retained layout.
Each store contains 64 shard files and two `zarr.json` files. Therefore
`0 <= P <= 64 * 4095 = 262080` bytes. Observed `P` is 124,028–146,261 bytes;
`M` is 797–798 bytes. The metered count exceeds `S` by
123,231–145,463 bytes, or 0.000977%–0.001147% of final file length.

| Raw chunk, KiB | Final file bytes, S | Metered excess, W − S | Source record |
| ---: | ---: | ---: | --- |
| 16 | 12,616,482,465 | 123,231 | `004-c16-r1-sample` |
| 32 | 12,576,335,610 | 129,286 | `005-c32-r1-sample` |
| 64 | 12,677,130,185 | 145,463 | `006-c64-r1-sample` |
| 128 | 12,678,537,665 | 130,623 | `002-c128-r1-sample` |
| 256 | 12,789,588,770 | 134,366 | `003-c256-r1-sample` |
| 512 | 12,815,568,446 | 127,426 | `001-c512-r1-sample` |

The meter adds the submitted lengths of shard writes in
[sink_metering.c:6](/mnt/main0/home/nclack/tmp/2026-09-25-bbbc022-read-write/writer/bench/sink_metering.c:6).
Writes advance a contiguous cursor, and the closing footer is rounded to
the required alignment before truncation to its logical end in
[shard_write_plan.c:357](/mnt/main0/home/nclack/tmp/2026-09-25-bbbc022-read-write/writer/src/zarr/shard_write_plan.c:357).
Padding between earlier payload updates remains inside the final shard
and is already included in both `W` and `S`; it must not be subtracted.

Each shard index contains 16 bytes per chunk slot plus a four-byte CRC.
It is allocated and updated in RAM, then serialized once in the closing
footer; this path does not write an initial disk index and repeatedly
rewrite it. See
[index allocation](/mnt/main0/home/nclack/tmp/2026-09-25-bbbc022-read-write/writer/src/zarr/shard_delivery.c:80),
[index updates](/mnt/main0/home/nclack/tmp/2026-09-25-bbbc022-read-write/writer/src/zarr/shard_write_plan.c:123),
and [footer construction](/mnt/main0/home/nclack/tmp/2026-09-25-bbbc022-read-write/writer/src/zarr/shard_delivery.c:128).
The index is already included once in both byte counts. Across 64 shards,
index-plus-CRC totals are respectively 64, 32, 16, 8, 4 and 2 MiB, each
plus 256 bytes. Logical file presizing uses unmetered `ftruncate` in
[shard_pool_fs.c:165](/mnt/main0/home/nclack/tmp/2026-09-25-bbbc022-read-write/writer/src/zarr/shard_pool_fs.c:165).

Metadata creation and replacement use a separate path in
[metadata_io.c:7](/mnt/main0/home/nclack/tmp/2026-09-25-bbbc022-read-write/writer/src/zarr/metadata_io.c:7).
Their traffic is absent from `W`; `M` includes only their final versions.
Allocated file bytes, reported separately as `st_blocks * 512`, are
distinct from `st_size`. These counters do not measure NFS traffic or
storage-device writes.

The retained arrays were written in job `3836189` using binary SHA-256
`5f3c23b481f6d9279d547b828554873042cd92698defb7570dfe05cc2ae8d881`
(build job `3836168`). Their identity is pinned at
[source-phases.json](/mnt/main0/home/nclack/tmp/2026-09-25-bbbc022-read-write/source-phases.json)
`#/shared_layouts/writer_identity`, independently of the later shard-sweep
binary. Full file inventories, source-record paths and hashes, index
counts, and checks are in
[retained-store-accounting.json](/mnt/main0/home/nclack/tmp/2026-09-25-bbbc022-read-write/retained-store-accounting.json)
(SHA-256 `15e42d6136fd92d0f84903d80bf55d57bb6d8c1369c1ea7315d1d7fdd45caf69`).
The table's records are under
`jobs/gpu-3836189/measurements/<record>/result.json` in that study root.

This validation applies to completed fixed-volume stores with a fresh
stream and separate discard warmup. Dynamic measurements subtract
`warmup_output_bytes` while their files retain warmup data. For their
whole-output census the corresponding expression is
`S = output_bytes + warmup_output_bytes - P_whole + M`.
The meter also counts submitted lengths when a write returns an error,
so these equalities do not establish final sizes for failed I/O attempts.
