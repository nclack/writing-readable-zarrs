# Local reads and microscopy writes: the compromise

Updated 2026-09-25. The author selected local NVMe as the intended read
deployment and excluded NFS read speeds from article recommendations. The
suspected NFS IOPS limit is a hypothesis; diagnosing and engineering that
path is deferred. Retain its records, but do not use its crop/scan rankings
to choose chunks. NFS writing remains relevant to acquisition.

**Starting recommendation: 128 KiB raw chunks**, `[1,256,256]` for uint16,
for one persisted layout balancing cropped reads and scans. Give cropped
reads greater priority. Keep 32 KiB as a crop-first Damacy alternative;
TensorStore can favor larger chunks. This is a reasoned compromise, not
the result of a measured combined-workload objective.

## Local read comparison

Filter [read-summary.csv](../../readable-zarrs-evidence/read-summary.csv) to:

- `phase = cpu-chunk-blocks`, `storage_type = local block storage`;
- `codec = zstd`, `block_bytes = 16384`;
- Damacy `implementation = chunks256-random`, or TensorStore;
- workloads `random-1x256x256` and `full-scan`.

This holds the phase, codec and block size fixed. Damacy uses the same
readahead-disabled mode for crops and scans. All rates below are medians of
three repetitions in **useful uint16 GiB/s**, using
`useful_active_gib_s_median`; the source's float32-output rates are twice these.

| Raw chunk, KiB | Damacy crops | Damacy scan | TensorStore crops | TensorStore scan |
|---:|---:|---:|---:|---:|
| 32 | 2.007 | 5.690 | 1.346 | 4.250 |
| 128 | 1.749 | 11.246 | 1.394 | 4.928 |
| 512 | 1.276 | 12.765 | 1.614 | 5.312 |

Relative to 32 KiB, 128 KiB retains 87.1% of Damacy's crop rate and gives
1.98 times its scan rate. TensorStore improves by 3.6% on crops and 15.9%
on scans. Moving from 128 to 512 KiB loses 27.0% of Damacy's crop rate for
a 13.5% scan gain, while TensorStore gains 15.8% on crops and 7.8% on scans.
This supports 128 KiB as a balance across workloads and readers. A workload
served only by TensorStore could reasonably favor larger chunks.

The separate `cpu-small-chunks` fixed-block study also supports the direction
of this compromise: 128 KiB keeps 89% of Damacy's 32 KiB crop rate with twice
its scan rate; TensorStore's crop and scan rates both improve. Keep this phase
separate. Larger-block results from the extended sweep remain relevant codec
tuning evidence and must not be silently folded into a chunk-only comparison.

The local arrays contain synthetic smooth4 uint16 data, shape
`[512,4096,4096]`, with sixteen approximately 1 GiB raw shards. These are CPU
reads to contiguous float32 host output, with 32 decode/copy participants,
16 file workers, warm indexes and verified cold client file pages before
each pass. Within-pass reuse is allowed and the dataset fits RAM. These
conditions differ from the microscopy writing study below.

## Writing and stored size

The [BBBC022 write summaries](../../bbbc022-evidence/shared-layout-summary.csv)
measure GPU Blosc-Zstd with bitshuffle, a 16 KiB block setting, four
approximately 1 GiB raw shards per append layer, and NFS output. They replay
actual microscopy fields. Their NFS read columns are not used here.

| Raw chunk, KiB | Write median [min, max], logical GiB/s | Final bytes / logical byte |
|---:|---:|---:|
| 32 | 2.365 [2.351, 2.429] | 0.530227 |
| 64 | 2.639 [2.286, 2.725] | 0.534476 |
| 128 | 2.267 [2.196, 2.735] | 0.534536 |
| 512 | 2.496 [2.375, 2.517] | 0.540313 |

The 128 KiB final size is only 0.81% above the smallest, at 32 KiB, well inside
the author's 10% allowance. Its write median is lower than the 64 KiB median,
but their ranges overlap; the study does not establish a stable penalty or
equivalence. Check that its observed drain capacity is sufficient for the
intended acquisition rate. The writing evidence does not force the local-read
compromise toward 512 KiB.

This is a synthesis across different datasets, machines and shard geometries,
not one matched read/write frontier. Keep the separate acquisition shard-count
results as writer tuning evidence, including codec-specific gains.

## Application workload

The author confirmed that Katamari uses native 224 × 224 crops, extendable
across Z and channels, with 16 × 16 token patches. A uint16 XY plane is 98 KiB
of useful pixels. Translation, Z/channel extents and reuse determine which
storage chunks are needed; token dimensions do not determine storage chunks.
The 256-square read benchmark is a nearby proxy, not a Katamari measurement.
