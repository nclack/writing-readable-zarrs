# Read findings

The archive supports a local-storage, synthetic-input result near 32 KiB for
the measured Damacy CPU crop workload. It does **not** establish a common 32 KiB
optimum for Damacy and TensorStore, real microscopy, or NFS. Full-array controls
support larger chunks in several tested configurations. The aligned-crop
evidence is narrower than a general claim about whole-chunk reads.

The export contains 3,182 rows: 1,927 accepted timing observations,
551 duplicate exports, 474 preflight observations, 228 separate
traces, and two superseded pilot observations. It produces 719
configuration summaries, 1,308 descriptive frontier rows and 210
workload comparisons. [Exclusions](read-exclusions.csv) also preserve
38 failure/guard/allocation/incomplete-status records, including partial
cache-check failures with no usable timing. These counts overlap the root
concurrency export where the same native run or diagnostic was used for both
analyses; they must not be added as independent experiments.

## What the layout sweeps show

All rates in this table are **returned host float32 GiB/s**. Useful
uint16-equivalent rates are half these values. Entries are medians of three
observations; bracketed limits are observed minima and maxima, not confidence
intervals. Each row identifies a separate reader mode and phase.

| Experiment and storage | Reader/mode | Workload | Highest-throughput tested layout | Median [min, max] | Interpretation |
|---|---|---|---|---:|---|
| Small-chunk sweep, local | Damacy, readahead disabled | translated 256-square crops | Zstd, 32 KiB chunk / 16 KiB block | 3.932 [3.908, 3.943] | Supports 32 KiB for this setup; 16 KiB is close |
| Small-chunk sweep, local | Damacy, default readahead | same crops | Zstd, 16 / 16 KiB | 3.712 [3.698, 3.717] | The mode changes the fastest observed chunk size |
| Small-chunk sweep, local | TensorStore | same crops | Zstd, 128 / 16 KiB | 2.775 [2.735, 2.782] | 32 KiB is a compression/frontier alternative, not its fastest point |
| Extended chunk/block sweep, local | Damacy, readahead disabled | same crops | Zstd, 32 / 32 KiB | 4.107 [4.057, 4.131] | Repeats the small-chunk crop result in a later matched phase |
| Extended chunk/block sweep, local | TensorStore | same crops | Zstd, 512 / 256 KiB | 3.364 [3.308, 3.413] | Does not reproduce the Damacy 32 KiB speed preference |
| Extended chunk/block sweep, local | Damacy, readahead disabled | complete scans | Zstd, 512 / 512 KiB | 27.803 [27.708, 27.938] | Larger chunks can favor complete scans |
| Extended chunk/block sweep, local | TensorStore | complete scans | LZ4, 128 / 64 KiB | 12.274 [11.856, 12.715] | Largest tested chunk is not always the fastest whole configuration |
| Four-encoding spot check, NFS | Damacy, default readahead | translated crops | LZ4, 512 / 512 KiB | 1.344 [1.180, 1.345] | The local small-chunk preference does not transfer directly |
| Four-encoding spot check, NFS | TensorStore | translated crops | LZ4, 512 / 512 KiB | 1.519 [1.295, 1.590] | Larger tested layouts also lead here, with wide ranges |

These are maxima among tested whole configurations, **not scalar Pareto
winners**. The NFS spot check changes block size with chunk size for its
Zstd series, so it does not isolate a chunk-only cause. It covers four chosen
encodings, not a full NFS frontier. The fresh adjacent local controls are
available in the same phase and are the appropriate storage comparison; earlier
local results are not additional repetitions of that experiment.

TensorStore's small-chunk compression/throughput frontier has two points:
Zstd 32/16 KiB gives 2.685 GiB/s and 1.8367-fold compression; Zstd 128/16 KiB
gives 2.775 GiB/s and 1.8318-fold compression. No retained read selection rule
chooses between them. In the broader block sweep its crop compression frontier
consists of Zstd 512/256 and 512/512 KiB. The latter trades a slightly lower
median, 3.332 GiB/s, for 1.9709-fold compression. Thus a claim that both readers
"favored 32 KiB" needs a specified phase, objective and selection rule.

The original PR160 four-shard study also differs. Its warm translated
smooth-input maximum is LZ4 64/16 KiB, at 6.004 GiB/s output. Its cold
smooth-input maximum is Zstd 256/16 KiB, at 1.092 GiB/s complete-wall output;
random12 instead peaks at Zstd 1024/16 KiB, at 0.976 GiB/s. The cold study's
fastest full-scan median is LZ4 1024/8 KiB, at 9.114 GiB/s complete-wall output.
Those shapes include extra Z planes at 256 KiB and 1 MiB, and the smaller
four-shard corpus permits substantial reuse within a pass. These are useful
counterexamples to a universal byte-size optimum.

Exact configurations, source locators and all alternatives are in
[read-summary.csv](read-summary.csv). [read-frontiers.csv](read-frontiers.csv)
exposes compression, encoded-byte and local-storage-byte objectives separately.
[read-plot-data.csv](read-plot-data.csv) is ready for workload panels without
combining different systems or phases.

## Workloads and byte definitions

The author clarified the smooth4 generator on 2026-09-29: it blends two
smooth random 3D fields at different spatial scales, rounds the result to
12-bit intensities stored as uint16, then replaces the lowest four bits with
independent random values from 0–15. The name denotes four noise bits per
value, combining spatial structure with noise for compression tests. This
description supplements the archived metadata; it is not a new measurement.

The recent CPU studies use deterministic synthetic smooth4 input: one
`[512,4096,4096]` uint16 array, 16 GiB logical size, partitioned into
sixteen `[512,1024,1024]` shards in a `[1,4,4]` grid. Each shard has **1 GiB
uncompressed capacity**. Encoded sizes differ. Blosc uses LZ4 or Zstd, level
3, bitshuffle, one internal thread and the audited never-split encoding.
Compression divides logical uint16 bytes by **stored shard-file bytes including
indexes**, not returned float32 bytes or filesystem allocation size; Zarr
metadata files are outside that denominator.

Small chunk shapes are 16 KiB `[1,64,128]`, 32 KiB `[1,128,128]`, 64 KiB
`[1,128,256]`, 128 KiB `[1,256,256]`, and 512 KiB `[1,512,512]`. The original
256 KiB and 1024 KiB shapes are `[2,256,256]` and `[8,256,256]`. Preserve shape
alongside bytes: increasing depth has a different crop cost than increasing
XY extent.

Each recent crop pass requests 16,384 `[1,256,256]` selections, in batches
of 128 that touch all sixteen shards. The sampler cycles through shard start
regions, draws uniform valid XY starts within each region and random Z planes,
and allows overlap and shard-boundary crossings. It is not simply a globally
uniform sampler. Frozen source uses `SEED=20260916` and query RNG seed
`SEED+2000=20262916`. The same saved query list is reused on every pass and
across matched encodings/readers. A crop pass requests 2 GiB useful uint16 bytes
from a 16 GiB corpus that fits RAM.

Full scans use `[8,256,256]` tiles and cover every logical value, including the
final edge. The recorded dimensions divide exactly and do not require array-edge
padding. Within-batch sharing affects how often chunks are decoded; full-scan
geometry is checked against decoded/useful counts rather than inferred from the
tile name.

Aligned controls keep the crop `[1,256,256]` and use a 256-grid in XY. In the
original four-array study, aligned XY positions are generated independently
while Z planes are shared with translated crops; in later controls XY
origins are rounded down from the translated positions. Z remains random.
Original multi-plane chunks therefore still decode unused Z values, so
these controls are **not a matched sweep of crops whose origins and extents
span whole chunks in every dimension**. The later aligned controls largely
hold the 64 KiB layout fixed. They measure an alignment penalty but do not
establish the optimal chunk size for arbitrary whole-chunk crops. [Workload
comparisons](read-workload-comparisons.csv) retain the distinct selection shapes
and source summaries.

## Frontiers, timing and cache scope

The recorded read objectives differ. Original warm full scans compare
compression and useful throughput; original warm queries minimize encoded
bytes per useful byte while maximizing useful throughput. Original cold queries
minimize actual local-storage bytes per useful byte while maximizing useful
throughput. The recent small-chunk report was revised from a traffic axis to
compression; both interpretations remain in the archive. The extended block
sweep uses compression and output throughput. The write-side rule "fastest
within 10% of smallest output" is **not** applied to any read group. All scalar
winner fields remain undefined.

Recent primary timings include planning, file reads, decoding, dtype conversion
and assembly. They exclude correctness checks, metadata/index preparation,
file eviction and counter preparation; complete-wall values remain in the rows.
Original PR160 cold primary figures instead include eviction/residency checks.
Do not pool those intervals or compare them without naming the difference. Both
readers in the recent CPU studies return host float32 data, use 32 decode/copy
participants and sixteen file workers, and consume matching source/query hashes.
Damacy includes benchmark-only persistent-handle/readahead controls and two
256-chunk input buffers in the PR168 layout sweeps. These are measured benchmark
configurations, not an assertion about default production behavior.

Cold local passes start with verified zero resident pages in their own input
files and allow buffered reuse within the pass. Recent runs use two residency
checks 20 ms apart and independent minimum page-coverage bounds. Their datasets
fit RAM; these are repeated cold passes, not an uninterrupted larger-than-memory
scan. The original warm phases are separate warmed-file workloads.

The NFS spot run records contemporary `nconnect=16` mount options in its raw
storage object. NFS server caches were uncontrolled and could be warm from
copying/validation. NFS payload and latency counters cover the shared client
mount, not the benchmark process or server disk. The export never treats
Linux process `read_bytes` as NFS storage traffic. Shared payload counters are
separate columns and retain their scope; background traffic is not subtracted.
Local block-storage counters, encoded reader counters and modeled decoding
geometry remain separate as well. TensorStore's actual decoded-byte count is
unavailable in these records; the geometry-derived column is explicitly modeled.

## Microscopy coverage and exclusions

The June archives add real-microscopy evidence: native GPU crop runs for CHAMMI,
Allen Cell, Jacobo and Dynacell, thread sweeps with TensorStore, 128-square
controls, and original/reformatted layouts. They establish useful workload and
layout contrasts, but a matched real-microscopy read sweep around 16–64 KiB
was not located. Current payload metadata for some historical sharded copies
is absent; raw timings and scenarios remain. The sparse and dense CHAMMI
confirmation phases are separate, retain all observations and are mapped to
their logged nodes. The root concurrency analysis covers their shard-count
interpretation.

Do not reuse the old absolute Damacy/TensorStore comparison blocks directly.
Some TensorStore JSONs count native/source `patch_bytes` without a recorded
output dtype, while Damacy counts float32 output. Their comparison block can
divide samples pushed **including warmup** by steady-state wall time. Some
paired records also use different timed sample counts. The export preserves
those old quantities in metadata, computes native timed sample counts from the
saved sampling scenario, and leaves unverified source/output byte conversions
null. RNG warmup consumption and trace identity are not proven merely by sharing
a seed. GPU output placement also differs from TensorStore host output.

Likewise, historical CHAMMI "decode amplification" notes divided decoded
source bytes by returned float32 bytes. Where the source is uint8, that is not
decoded/useful source-byte amplification. This export names that legacy quantity
`decoded_per_output_byte`; it does not silently reproduce the old geometry
interpretation. DynaCell reformat preparation can reorder arrays, so identical
URI sets do not establish identical timed samples.

Setup/guard failures, the two original storage-residency interruptions,
canceled/partial allocations, superseded pilot records, repeated exports,
preflight observations and traces remain discoverable. Completed cases retained
after an interrupted allocation are not discarded; byte-identical copied
results are not counted again. Reports rendered again for labels/axes are
reports, not new measurements. [read-exclusions.csv](read-exclusions.csv),
[read-attempts.csv](read-attempts.csv) and the [source
manifest](read-source-manifest.json) expose this history.

The L40 study was incomplete at the inventory snapshot: a preparation job
had started, despite stale root status text, and no completed read timing was
present. It was not polled for new measurements. No GPU claim is filled in from
its plan.

The smallest remaining questions are whether the CPU layout trends hold on
representative microscopy, how a fuller matched NFS layout/block sweep changes
the frontier, and whether whole-chunk crop controls support a distinct optimum.
No missing experiment was run. Crop throughput alone does not establish
training-loop or viewer performance.

## Reproduction

From the evidence directory, recover source rows and summaries on the cluster:

```bash python3 scripts/aggregate_reads.py --home /mnt/main0/home/nclack --output . ```

Rebuild summaries and plot tables elsewhere using only the shipped rows:

```bash python3 scripts/aggregate_reads.py --from-rows read-runs.csv --output reproduced-reads ```

Only the Python standard library is required. The script does not import
benchmark packages or execute measurement code. All five portable outputs
were reproduced byte for byte, and 1,698 accepted modern rate records
were checked against archived rate fields and their byte counters.
[Validation](read-validation.json) and [counts/checks](read-export-checks.json)
record the verification. Blank CSV fields mean unknown/unavailable;
JSON uses null. Repeated metadata objects are stored once in
[read-metadata.json](read-metadata.json); each row's `metadata_id` resolves
through `records`, with `*_ref` values pointing to `shared_objects`.
