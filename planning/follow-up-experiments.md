# BBBC022 follow-up results and analytical scope

Updated 2026-09-25. The primary measurements are complete for shared BBBC022
MitoTracker read/write layouts and the extended streaming shard-count sweep.
The [new evidence](../bbbc022-evidence/README.md) contains 18 shared-layout
writes, all 144 scheduled read observations, and 36 primary shard-count samples
with 12 separate references. The later 30/54 comparison adds six samples and
six references as a separate series. The
[original collection](../readable-zarrs-evidence/README.md) remains unchanged.
Conversion memory and final-size accounting are addressed through reasoning;
the broader experiment program is not required.

## Use drain capacity to compare writers

Measure how quickly a writer processes logical input when input is continuously
available, under the recorded machine, codec, layout and storage conditions.
Call this **maximum drain rate** or **drain capacity** in the article. Preserve
the benchmark's measured interval: append plus final drain and close. A quoted
capacity is a median with an observed range across valid repetitions, not the
single fastest repetition or the rate during shutdown alone.

The completed preloaded replay measurements answer this question for the
recorded conditions. They exclude source loading and TIFF decoding. Keep
logical input GiB/s, encoded output bytes, filesystem results and discard
results distinct. I/O completion and file close do not establish durability
on the storage device.

Sustained acquisition rates will be lower and need headroom for network/storage
variation, stalls and finite buffers. The current data supply no universal
percentage reduction from drain capacity. The article should state this limit
without requiring a separate long-duration acquisition experiment. Compare
chunk, codec and shard choices using drain capacity and its observed variation.

## Experiment 1: read and write the same microscopy layouts

**Question:** Which layouts offer useful read performance at an acceptable
write drain rate and output size on the same actual microscopy data?

The retained input contains 16 independent, complete 520 × 696 uint16 fields.
Each layout repeats them from plane zero to form `[32768,520,696]`: 22.08984375 GiB
of logical pixels and 2,048 source cycles. The append axis represents replay,
not a biological volume. The [source manifest](../experiments/bbbc022/input-source.json)
preserves the image selection and hashes.

The six depth-one chunk shapes are `[1,64,128]`, `[1,128,128]`, `[1,128,256]`,
`[1,256,256]`, `[1,256,512]` and `[1,512,512]`. They share `[2048,512,512]`
shards, 1 GiB raw capacity per shard and four files per append layer. All use
GPU Blosc-Zstd, bitshuffle, level hint 3 and a 16 KiB block setting. Spatial
padding makes submitted data 27, 30, 30, 36, 48 and 64 GiB respectively.
Each layout has three interleaved writes; one validated array per layout
supplies the reads.

Both CPU readers use 32 decode/copy workers and 16 I/O workers on 48 physical
cores, returning contiguous float32 host arrays from the same saved traces.
Three interleaved repetitions cover translated 256 × 256 crops, aligned and
translated 512 × 512 crops, and complete scans. Rates count useful uint16
source bytes; float32 output contains twice as many bytes. Shard indexes are
warm, file-specific client cache eviction is verified before each pass, and
server cache state is uncontrolled. The [protocol](../experiments/bbbc022/README.md)
records the timing, correctness and coverage checks.

The following values are medians of three repetitions. Final size includes
all store file lengths and is divided by logical uint16 input bytes. Full
observed ranges are in the [write summaries](../bbbc022-evidence/shared-layout-summary.csv)
and [read summaries](../bbbc022-evidence/read-summary.csv); they are not confidence
intervals.

| Raw chunk, KiB | Write, logical GiB/s | Final size / input | Damacy translated 256², useful GiB/s | TensorStore translated 256², useful GiB/s |
|---:|---:|---:|---:|---:|
| 16 | 2.510 | 0.5319 | 0.164 | 0.135 |
| 32 | 2.365 | 0.5302 | 0.249 | 0.235 |
| 64 | 2.639 | 0.5345 | 0.399 | 0.345 |
| 128 | 2.267 | 0.5345 | 0.407 | 0.367 |
| 256 | 2.420 | 0.5392 | 0.587 | 0.510 |
| 512 | 2.496 | 0.5403 | 0.599 | 0.543 |

For translated 256 × 256 crops, 256–512 KiB improves on 32 KiB in both readers.
The larger pair's observed ranges overlap: 0.481–0.592 versus 0.345–0.638 GiB/s
for Damacy and 0.495–0.537 versus 0.390–0.555 GiB/s for TensorStore. This series
does not justify a stable ordering within that pair or a general 32 KiB crop
preference.

Full scans give a different choice for each reader. Damacy's best median is
at 32 KiB: 2.930 GiB/s, range 2.853–2.968. TensorStore's is at 128 KiB:
2.454 GiB/s, range 2.424–2.498. Larger chunks do not consistently improve full
scans. Padding is part of the work, but it does not alone explain the
differences: the 32 and 64 KiB layouts submit the same padded volume. This
study has no matched local-storage control, so the causes remain unresolved.

Aligned 512 × 512 crops favor larger candidates, with the highest medians at
512 KiB: 3.451 GiB/s for Damacy and 2.326 GiB/s for TensorStore. Translated
512 × 512 crops show little consistent benefit above the middle candidates.
The aligned and translated traces use matching frame lists but different XY
coverage and reuse. Aligned selections touch one shard; translated selections
touch two or four. Their [paired summary](../bbbc022-evidence/read-alignment-summary.csv)
therefore does not isolate chunk alignment from these other changes.

All six final sizes are within 2% of the smallest, so every layout satisfies
the write-side 10% size tolerance. Applying that rule to write medians alone
would choose 64 KiB. Its 2.286–2.725 GiB/s observed range overlaps every other
layout's range, so the measurements do not establish a stable write ordering.
The [joint table](../bbbc022-evidence/joint-layouts.csv) lets read requirements
distinguish candidates with similar measured write cost. The 10% write-size
tolerance is not a scalar read-selection rule.

These conclusions concern the recorded CPU readers, repeated BBBC022 fields,
codec and NFS conditions. They do not establish GPU-reader, training-loop or
viewer performance. Keep older synthetic and other microscopy measurements
separate, with their original machines, traces and timing policies. Further
experiments are not required to state these scoped results.

## Experiment 2: extend the streaming shard-count sweep

**Question:** At fixed chunk/codec settings, how does drain capacity change
below and above approximately sixteen append-layer shards?

The primary GPU Blosc-LZ4 series uses 64 KiB `[4,64,128]` chunks and 16 KiB
blocks at 4, 9, 15 and 30 actual files per layer. A limited Blosc-Zstd control
uses 256 KiB `[4,128,256]` chunks and 256 KiB blocks at four and fifteen files.
Both use bitshuffle and level hint 3. Compare gains within each series; the
control changes chunks and blocks as well as codec.

Six interleaved rounds retain the same machine, destination, worker counts,
four output buffers, per-file limits and NFS mount with `nconnect=16`. The
timed interval includes final drain and close, with a 32 GiB logical minimum,
at least two generation transitions and a final drain fraction no greater
than 10%. Raw shard capacity stays near 1 GiB. Changing count also changes
grouping, append-axis extent and work per file; this measures realizable
layouts, not an isolated file-count effect.

| Codec | Actual shards per layer | Drain median [min, max], logical GiB/s |
|---|---:|---:|
| LZ4 | 4 | 3.238 [1.779, 3.440] |
| LZ4 | 9 | 4.793 [4.437, 5.551] |
| LZ4 | 15 | 5.616 [5.042, 6.166] |
| LZ4 | 30 | 6.120 [5.157, 6.637] |
| Zstd | 4 | 2.659 [2.580, 2.760] |
| Zstd | 15 | 2.734 [2.721, 2.750] |

The [paired comparisons](../bbbc022-evidence/shard-paired-summary.csv) show a
large LZ4 gain from four to fifteen shards: median +76.1%, range +64.9% to
+194.7% across six rounds. Fifteen to thirty gives a smaller, variable gain:
median +10.1%, range −14.1% to +22.4%. The Zstd control gains a median +2.8%
from four to fifteen, with paired changes from −0.8% to +5.5%. These are
medians of paired rate ratios, not ratios of the summary medians.

Fifteen-shard reference runs before and after each round show substantial
drift: the after/before rate ratio ranges from 0.515 to 1.292, including a
48.5% drop in round two. References are reported separately and do not
normalize away that variation. The results support a strong LZ4 benefit
through fifteen and an uncertain incremental benefit at thirty; they do not
establish a stable throughput ceiling or an optimum tied to NFS connections.

The primary rule would add 54 shards only if the first three paired 30/15
ratios had a median above 1.05 and enough time remained. Their median was
0.995528, so the primary experiment stopped at thirty. The later
six-round median of 1.101446 motivated a separate follow-up, preserving that
original decision.

The separate 30-versus-54 follow-up completed all twelve observations in job
`3837212`. Three paired rounds use a common 96 GiB minimum for all samples
and fifteen-shard references, sufficient for two complete generations at 54
shards. The [protocol](../bbbc022-evidence/shard-extension-protocol.json)
preserves the schedule and rationale saved before measurement. Its later job,
adaptive selection and larger minimum volume remain separate from the primary
32 GiB series; the primary artifacts and stopping decision are unchanged.

All three 54-shard samples are slower than their paired 30-shard samples.
The [paired 54/30 ratio](../bbbc022-evidence/shard-extension-paired-summary.csv)
has median 0.8661 and range 0.8471–0.8897: median 13.4% lower drain capacity,
with individual reductions of 11.0–15.3%. Thirty-shard rates have median
5.258 GiB/s, range 5.100–5.691; 54-shard rates have median 4.678 GiB/s, range
4.417–4.821. The [reference after/before ratios](../bbbc022-evidence/shard-extension-reference-drift.csv)
range from 0.942 to 1.123, with median 1.065. This follow-up finds no benefit
from extending to 54 under its recorded conditions; it does not establish a
universal optimum or justify pooling the two volume policies.

The benchmark's metering wrapper initially had only 32 file slots. After a
54-shard startup failed, its bookkeeping capacity was raised to 64 and the
entire primary shard series restarted. The 28 interrupted records remain in
a [supplementary table](../bbbc022-evidence/supplementary-interrupted-shards.csv);
they are not pooled with the restarted series. The 18 completed shared-layout
writes retain their earlier source and binary identities. No connection-count
or shard-capacity sweep is needed for the article.

## Reason through conversion memory

Explain memory from the buffers live at the same time under a stated
implementation and processing order: source decoding, retained input blocks,
queues, unfinished output chunks, codec workspaces, pending encoded writes,
indexes and caches. Distinguish host, pinned-host and device allocations when
applicable. Shared buffers are counted once; queue and cache bounds matter.

For rechunking, show source/destination overlap and processing-block shape.
Explain how retaining source blocks versus reading them again trades memory
for extra I/O. For TIFF streaming, include the decoder's source-buffer needs.
Do not assume that every implementation buffers a whole output shard.

Use layout geometry and implementation evidence to give conditional estimates
or bounds. Label these as reasoning, not measured process peaks. No conversion
memory experiment, input-scale sweep or v2-to-v3 performance study is required
to make this explanation useful for the article.

## Reason through final output size

The [accounting audit](../experiments/bbbc022/size-accounting.md) traces the
writer's source and checks existing file metadata for the six retained
fixed-volume stores. Let `W` be metered shard-write bytes, `L_j` each final
shard length, `A = 4096` bytes the write alignment, and `M` the total final
metadata length. Then:

```text
P = sum((-L_j) % A)
W = sum(ceil(L_j / A) * A)
S = W - P + M
```

`P` is footer padding removed by truncation and `S` is the final length of all
store files. Both identities have zero residual for every retained store.
Each contains 64 shards and two metadata files, so `P` is bounded by
`64 * 4095 = 262080` bytes. Observed footer padding is 124,028–146,261 bytes
and metadata totals 797–798 bytes. The meter exceeds final file length by
123,231–145,463 bytes, below 0.0012% of final size. This correction cannot
change the 10% threshold for these layouts.

Each index is serialized once in the closing footer and is already counted
in both `W` and `S`. Padding between earlier writes remains in the file and
must not be subtracted. Metadata updates use a separate path; `M` counts
their final versions. File lengths, allocated space (`st_blocks * 512`) and
storage traffic are different quantities.

This reasoning audit uses existing source, counters and file metadata, not
a separate output-size experiment. It applies to successful fixed-volume
stores with a fresh measured stream and separate discard warmup. Dynamic
shard runs retain warmup data, so whole-store accounting would also add
`warmup_output_bytes`; their final-size ratios are not inferred here. Keep
the stated proxy and any unresolved terms for other historical write paths.

## Execution boundary

Execution was authorized on 2026-09-25 with CPU and single-L40 allocation
budgets of approximately two hours each. The frozen matrix, harnesses, source
patches and execution protocol are in [experiments/bbbc022](../experiments/bbbc022/README.md).
Keep the earlier collected evidence as its original snapshot; export new
observations separately with their own source and timing-policy identities.
The [BBBC022 findings](../bbbc022-evidence/findings.md),
[validation](../bbbc022-evidence/validation.json), raw observations and portable
analysis retain failures, exclusions, references and phase-specific provenance.
