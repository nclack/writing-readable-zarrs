# TensorStore chunk costs and cache scope

Reviewed 2026-09-28. This audit explains the local NVMe comparison used in
Figure 1; it does not use NFS read timings or add new measurements.

## Matched comparison

Select `phase=cpu-chunk-blocks`, TensorStore, local block storage, Zstd,
16 KiB compression blocks and 128/512 KiB raw chunks. The chunk shapes are
`[1,256,256]` uint16 and `[1,512,512]` uint16. Each configuration/workload
has three accepted repetitions. Rates below count useful uint16 bytes,
not the twice-larger returned float32 arrays.

| Quantity | 128 KiB | 512 KiB |
|---|---:|---:|
| Crop rate, median [min, max], GiB/s | 1.394 [1.365, 1.412] | 1.614 [1.554, 1.633] |
| Full-array rate, median [min, max], GiB/s | 4.928 [4.541, 5.634] | 5.312 [4.461, 5.361] |
| Modeled query–chunk intersections per crop pass | 65,253 | 34,682 |
| Modeled chunks processed, deduplicated within each batch | 65,125 | 34,543 |
| Modeled decoded / useful bytes | 3.975× | 8.433× |
| Modeled encoded bytes per crop pass, GiB | 4.339 | 9.219 |
| TensorStore file-driver bytes per crop pass, median GiB | 4.327 | 9.168 |
| Process local-storage bytes per crop pass, median GiB | 4.512 | 7.175 |

The crop median improves 15.8%, with separated observed ranges. The full-array
median improves only 7.8%, with substantially overlapping ranges. Three
repetitions do not establish a reliable full-array advantage or equivalence.
These are observed ranges, not confidence intervals.

## Cache interpretation

The logical array is 16 GiB; encoded shards occupy approximately 8.74 GiB.
The job allocates 64 GiB of memory, so the data fit in RAM. Each crop pass
requests 16,384 selections of `[1,256,256]` uint16 values: 2 GiB useful input,
in batches of 128. Selections may overlap and the query list is reused.

The saved TensorStore settings specify a zero-byte data cache, a separate
64 MiB metadata cache, and fresh data and metadata pools before every pass.
Both recheck flags are false; that does not enable a retained data cache
when its byte limit is zero. This interpretation agrees with the
[Zarr 3 driver documentation][ts-zarr3]. [Shard-index caching][ts-shard-index]
is distinct from retaining decoded image chunks.

Client file pages were verified nonresident before each pass. This removes
warm-across-pass file-cache reuse under the recorded protocol, but allows
operating-system file-cache reuse during the pass. A zero TensorStore data
cache also does not exclude sharing of concurrently outstanding work.

File-driver traffic is about 99.7% and 99.4% of the respective modeled
encoded-byte totals. That provides little evidence of substantial retained
decoded-chunk reuse across batches. At 512 KiB, storage traffic is lower
than file-driver traffic, consistent with within-pass file-cache reuse.
Their difference is not an exact cache-hit measurement: page granularity,
readahead and counter scope also matter.

## Interpretation and next measurement

The larger chunks approximately halve the modeled number of chunks processed
while more than doubling modeled decoded bytes. Fewer chunk lookups, requests
and scheduling operations could outweigh the extra byte processing. This is
a hypothesis supported by the direction of the counters, not a profile of
where TensorStore spends its time. Actual TensorStore decoded bytes and read
request/syscall counts are unavailable in this portable comparison.

The geometry model counts each chunk once per batch, then sums across batches.
Its `unique_chunks_per_pass` field is therefore not a globally unique count:
34,543 exceeds the 32,768 chunks in the 512 KiB layout. Do not label that field
as measured TensorStore I/O operations or measured decode calls.

A follow-up should preserve the reader, chunk shapes, block size and output
type while separately varying cache conditions and crop overlap. Use a
compressed working set comfortably larger than available file-cache memory,
and compare the existing repeated-crop pattern with a controlled low-reuse
query list. Record file-driver bytes, storage bytes, resident pages, actual
decode counts and a CPU profile. Keep verification and eviction outside the
reported active interval. Randomize configuration order and add repetitions.
No such follow-up has been run here.

## Source locators

The [selected summaries][summaries] and [contributing rows][runs] preserve
the Figure 1 filter and the original source locators. The full
[read metadata][metadata] resolves each row's `metadata_id` through `records`;
reference fields resolve through `shared_objects`.

For the first TensorStore crop repetition, metadata IDs are
`5c78a3e26b63c32989d7dd3a` (128 KiB) and
`0f255f18f5d66308fb251ab0` (512 KiB). Cache settings are in the resolved
`backend_settings_ref`; geometry is in `geometry`. Original measurement
files are under
`/mnt/main0/home/nclack/tmp/2026-09-24-damacy-cold-blocks/job-3822266/results/`,
with cases `smooth4-zstd-c128-b16` and `smooth4-zstd-c512-b16`, then
`random-1x256x256/cold/repeat-1/tensorstore/measurements.json`, record
`/measurements/0`. Other repetitions are enumerated in the contributing rows.
The [read findings][findings] define byte counters and cold-pass scope.

[summaries]: ../../article/figures/data/read-selected-summary.csv
[runs]: ../../article/figures/data/read-selected-runs.csv
[metadata]: ../../readable-zarrs-evidence/read-metadata.json
[findings]: ../../readable-zarrs-evidence/read-findings.md
[ts-zarr3]: https://google.github.io/tensorstore/driver/zarr3/index.html
[ts-shard-index]: https://google.github.io/tensorstore/kvstore/zarr3_sharding_indexed/index.html
