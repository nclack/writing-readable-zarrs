# Review of the collected evidence

Snapshot: commit `80bde95`, before the BBBC022 follow-up. The
[review of commit 4fccbfe](bbbc022-evidence-review-4fccbfe.md) supersedes the
drafting recommendations and evidence-gap assessment below. Retain this
review for the original collection's findings and verification record.

Reviewed 2026-09-25. The collection supports a workload-specific article, with
narrower numerical recommendations than the current outline. No numerical
discrepancy was found in the checks below. The main issues are claim scope,
incomplete comparisons, and missing conversion measurements.

## Verification

- Verified all 70 entries in the bundle's checksum manifest, the archive's
  checksum, and agreement between its 71 file members and the extracted files.
- Ran the supplied validator on a temporary copy. All 21 regenerated exports
  were byte-identical; the original bundle was preserved.
- Independently recomputed all 1,308 read-frontier flags across 255 objective
  groups. Checked the declared read-group fields across 284 groups; none mixed
  those fields.
- Independently recomputed byte totals and throughput medians for all 1,293
  write summaries, then the exact 10% threshold, frontier membership, and
  winners across 92 eligible groups. All agreed.
- Inspected both overview figures and their selection/plotting code. Checked
  the NFS write winners against smaller eligible alternatives and the paired
  concurrency records.

This verifies exported calculations and their interpretation. It does not
independently re-extract every original cluster log or rerun a benchmark.

## What can be said

### Read layout results depend on reader and workload

The local synthetic smooth4 crop studies support a Damacy CPU preference near
32 KiB with readahead disabled. In the fixed-block study, TensorStore's 32 KiB
point remains on the compression/throughput frontier, but 128 KiB is faster:
2.685 versus 2.775 returned float32 GiB/s. In the extended chunk/block sweep,
TensorStore's fastest crop setting is 512/256 KiB chunk/block at 3.364 GiB/s;
Damacy's is 32/32 KiB at 4.107 GiB/s.

These are synthetic-input, local-storage results. The four-encoding NFS spot
check favors 512 KiB among its tested configurations, but changes block size
and sometimes codec along with chunk size. It cannot isolate a chunk-size
effect. The archive does not contain the matched microscopy/NFS small-chunk
read sweep needed for the original broad claim.

Full-array scans support larger chunks in several settings. Keep the aligned
crop claim narrower: the retained XY alignment controls do not always select
whole chunks in every dimension. See [read findings](../../readable-zarrs-evidence/read-findings.md).

### Write winner counts need coverage and variation alongside them

Of the current report's 14 NFS input/backend conditions, eight select
16–64 KiB and six select 256 KiB under the measured-byte proxy. The all-sink
count of 15/28 additionally includes discard results. Neither tally is a set
of independent demonstrations that chunk size alone caused the result.

The six larger NFS winners break down as follows:

| Condition | 256 KiB winner, logical GiB/s | Best eligible smaller alternative | Assessment |
|---|---:|---|---|
| BBBC022 GPU | 4.214 | 64 KiB, 4.192 | Smaller point is only 0.5% slower; observed ranges overlap |
| COSEM CPU | 4.925 | 16 KiB, 4.866 | Smaller point is only 1.2% slower; observed ranges overlap |
| COSEM GPU | 4.358 | 64 KiB, 2.434 | Substantial measured larger-chunk advantage among tested eligible settings |
| JUMP GPU | 3.524 | None within the size allowance | Small-chunk Blosc-Zstd, the winning codec, was not tested in this selected group |
| OpenCell DNA GPU | 3.463 | None within the size allowance | Same codec-coverage gap |
| OpenCell protein GPU | 3.105 | None within the size allowance | Same codec-coverage gap |

These comparisons use [write-summary.csv](../../readable-zarrs-evidence/write-summary.csv).
The first three winner/rival summary IDs are respectively
`f881343f300fb40229fd` / `c45d85eaa0d226045586`,
`dd201c35f97383efb19b` / `133cbdfc229ab2c16d2d`, and
`8d47c40ab906d42b6664` / `1b70d2cad3e0e075973f`.

Thus small chunks are often competitive, and there are both substantive
counterexamples and unresolved comparisons. These grids do not directly
measure a 32 KiB write setting.

The size proxy is measured shard-write bytes per logical input byte. It is
useful evidence for that cost; label it explicitly rather than calling it a
final stored-file census. Timings cover preloaded replay through final drain,
with current sample windows of roughly 3–17 seconds. They do not measure TIFF
conversion or indefinite acquisition. See [write findings](../../readable-zarrs-evidence/write-findings.md).

### Concurrency evidence supports a larger layer, not a sixteen-shard optimum

The paired microscopy study compares four with 15 actual BBBC022 shards or
16 COSEM shards. GPU LZ4 gains are about 52% in both datasets; the larger layer
wins all eight paired rounds for each. Compressed CPU gains are much smaller.
There are no points above sixteen in this experiment.

The separate CHAMMI read sweep peaks at 32 shards per array. Its much smaller
shards and different workload prevent transferring that optimum to streaming.
No matched `nconnect` sweep establishes a connection-count relationship. See
[concurrency findings](../../readable-zarrs-evidence/concurrency-findings.md).

### Blosc block size cannot be dismissed generally

At a fixed 16 KiB chunk, a BBBC022 GPU LZ4 discard comparison drops from 16.846
to 7.137 logical GiB/s when the requested block changes from 4 to 16 KiB.
The NFS comparison has overlapping ranges. This supports a backend/storage
qualification, not a general claim that block size matters little. Effective
block sizes are not directly measured from encoded headers.

### Conversion memory remains an evidence gap

The 11 located Zarr v3-to-v3 executions establish completed transformations
and layouts, but none supplies a measured conversion-memory peak or a
per-layout conversion timer. The DynaCell input-block geometry helps explain
memory demand; multiplying nominal block bytes by workers would still be a
model, not a measured peak. Complete TIFF and v2-to-v3 performance evidence
was not located. See [conversion findings](../../readable-zarrs-evidence/conversion-findings.md).

## Changes needed before drafting

Keep the read-first structure. Frame the argument around matching chunk
geometry, codec settings, and file concurrency to the workload and execution
path. Present 32 KiB and sixteen streaming shards as scoped results or starting
candidates, with the comparisons above alongside them.

Update the [article outline](../article-outline.md): its evidence-collection
status is stale, its two-reader 32 KiB claim is too broad, and the aligned-read
claim needs qualification. Keep conversion memory as an explanation and an
open measurement question until measurements support a numerical comparison.

For the figures, keep the distinctions visible in the panels themselves:
the NFS read panel varies block size with chunk size, and the local crop and
scan panels use different Damacy readahead modes. Use matched modes and the
adjacent local controls when making a causal workload or storage comparison.
The write panels use separate CPU/GPU machines and minimum-byte baselines.

The most useful additional evidence is a matched real-microscopy read sweep
on the target NFS setup, followed by instrumented conversion measurements if
the memory section will make quantitative claims. Fill the three small-chunk
Blosc-Zstd write gaps if those conditions are central examples. A sweep above
sixteen or across `nconnect` is needed only to strengthen the corresponding
optimum or causal claim; the existing paired improvement can already be reported.
