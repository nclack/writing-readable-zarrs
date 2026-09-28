# Writing readable Zarrs: article outline

Updated 2026-09-26. This is the current writing plan. The earlier, broader
[guide outline](archive/outline.md) remains reference material.

## 1. Audience

Engineers choosing Zarr layouts for microscopy acquisition, model training,
and visualization. They understand multidimensional arrays and throughput,
but need not know Zarr sharding or NFS internals.

The article should help them identify the reads a dataset must serve, choose
an initial layout, and produce it through acquisition or conversion within
throughput and memory constraints.

## 2. Outline

Working title: **Writing readable Zarrs**.

Central question: What single persisted layout balances the required reads,
and how do we write it efficiently?

Working argument: Start with the read workloads. Chunk choices depend on the
reader, data, storage and selection shape; small translated crops and full-array
reads can favor different layouts. Usually one chunk layout must serve both;
for visualization and modeling, give cropped reads greater priority while
retaining acceptable full-scan performance. Shards group chunks into files
and expose file parallelism.
Then consider how to produce that layout: streaming for acquisition or TIFF
conversion, and rechunking for Zarr-to-Zarr conversion. Acquisition emphasizes
drain capacity and headroom for lower sustained rates; conversions emphasize
memory use, explained through processing order and buffer lifetimes.

The [evidence bundle](../readable-zarrs-evidence/README.md) contains the collected
records, scoped findings and counterexamples. The new
[BBBC022 evidence](../bbbc022-evidence/README.md) completes the primary read/write
layout and streaming shard-count experiments; [results and scope](follow-up-experiments.md)
connect these measurements and the separate 30/54 follow-up to the article.
Use local NVMe measurements for read recommendations: this is the intended
reader deployment. Exclude NFS read rates from layout selection and the
article's performance figures. The author suspects an NFS IOPS limitation;
its cause and engineering remedy remain deferred. Retain those records as
diagnostics. NFS write, shard-count and final-size evidence remains in scope.
The [compromise analysis](reference/local-read-write-compromise.md) combines
local read trends with separate microscopy write constraints.
Conversion memory and final-size accounting will be handled through
reasoning; separate conversion-memory, sustained-acquisition and output-size
experiments are not prerequisites. Random subvolume writes remain outside scope.

### A. Read workloads

- Introduce the problem through visualization, model training and processing
  with arrays. Explain the approach before stating the layout recommendation:
  characterize the two main read patterns, define Pareto frontiers and use
  them to find a compromise, then check writing and conversion constraints.
- Distinguish two main read patterns before discussing layout:

  | Read workload | What to specify | Why it matters |
  |---|---|---|
  | Random, unaligned crops | Crop shape, other-axis extents, position distribution, batches, reuse | Crop boundaries can cut across the chunk grid |
  | Full arrays | Array extent, traversal, concurrency | All logical values are needed |

- Introduce chunk-aligned crops as a control that removes crop-boundary waste,
  rather than a third main application workload. Define every technical term
  before use, within the narrative where possible.
- Relate translated crops to training data loaders and some visualization
  reads. They do not measure a full training loop or interactive viewer.
- Use a hypothetical vision transformer as the narrative example:
  224 × 224 XY inputs, extendable across Z and channels, with 16 × 16
  vision-transformer patches (14 × 14 patch positions across a native crop).
  Record the requested Z/channel extents and origin distribution separately.
  Token size does not establish storage-chunk size or crop-origin alignment.
- Specify cache state and reuse where they change the workload. Rechunking
  also reads a source array, but its processing selections depend on the
  source and destination layouts; do not assume it is one sequential scan.

### B. Chunk size

- Define a chunk as the independently encoded/decoded region in this
  article's indexed-sharding model. Both its shape and byte count matter.
- Overlay the same translated crop on coarse and fine chunk grids. Show
  values decoded outside the requested crop.
- Explain read amplification in plain language, then label the quantities:
  decoded bytes / useful bytes for geometry, and transferred bytes separately
  for storage traffic. Compression and coalescing can change the latter.

**Figure 1a — what a crop makes us decode.** Insert here, at the A/B
transition after defining chunks. Overlay the same translated 256 × 256 crop
on 128 × 128 and 256 × 256 chunk grids (32 and 128 KiB for one uint16 plane).
Distinguish requested pixels, intersected chunks and unused decoded pixels.
Include small whole-chunk-aligned and full-array controls. Label the measured
256-square workload separately from the hypothetical 224-square input;
16 × 16 token patches are not the storage grid.

- Lead with the local NVMe CPU studies on synthetic smooth4 input. Damacy's
  translated-crop preference near 32 KiB trades against faster full scans at
  larger chunks. TensorStore's choices differ with chunk and block settings.
  Keep the synthetic input, chunk shapes, reader modes and cache policy visible.
- Use the same phase, codec, block setting and reader mode for a crop/scan
  comparison. The fixed-16-KiB-block Zstd subset of `cpu-chunk-blocks` gives
  a useful example: moving from 32 to 128 KiB retains 87% of Damacy's crop
  rate while nearly doubling scan rate. TensorStore improves by about 4%
  on crops and 16% on scans. Damacy readahead is disabled for both workloads.
- Recommend 128 KiB (`[1,256,256]` for uint16) as the initial mixed-workload
  compromise, with greater priority on cropped reads. In that same subset,
  moving to 512 KiB loses 27% of Damacy's crop rate for a 14% scan gain;
  TensorStore improves on both. Keep 32 KiB as the crop-first Damacy
  alternative, and show reader-specific reasons to move larger.
- Explain that less geometric over-reading does not alone predict speed.
  Use the local [read summaries](../readable-zarrs-evidence/read-summary.csv)
  and the [compromise analysis](reference/local-read-write-compromise.md).
  Present larger block sizes as separate tuning comparisons, not as a
  chunk-only effect. Aligned XY controls with multi-plane chunks do not
  eliminate unused values in other dimensions.
- Compare layout trends within each reader first. Absolute reader speeds
  require matched selections and explicit CPU/GPU output and timing boundaries.
  Normalize local float32-output rates to useful uint16 bytes when sharing
  units with the writing discussion; the output rates are twice as large.
- Keep the actual 224 × 224 workload distinct from the measured 256 × 256
  proxy. Smaller crops and different Z/channel extents can change the balance.
  A uint16 224 × 224 plane is 98 KiB of useful input, but a translated crop
  can intersect multiple chunks. A byte-size target alone does not specify
  the layout across Z, channels and XY.
- Compare time spent on the representative mix, with explicit crop priority
  and an acceptable scan cost. Averaging workload throughputs does not give
  the elapsed time for that mix. No current scalar objective establishes a
  single 128 KiB optimum across readers and workloads.

**Figure 1b–c — why 128 KiB is a compromise.** Place at the end of B beside
the recommendation. Use one local NVMe panel per reader, with crop throughput
on the horizontal axis and full-scan throughput on the vertical axis. Label
the 32, 128 and 512 KiB points and their shapes; highlight 128 KiB as the
proposed balance. Show medians and observed min–max for each workload, with
three repetitions per point/workload. Use the fixed-block subset in the
[compromise analysis](reference/local-read-write-compromise.md), in useful
uint16 GiB/s. This combines workload geometry and its measured tradeoff in
one figure. NFS reads are excluded.

### C. Shards

- Define a shard as a group of chunks in one stored file. With indexed range
  reads, small chunks do not require one small file per chunk.
- Explain why distributing reader work across several files may expose more
  parallelism. Distinguish files touched by a batch from files with active I/O;
  balance of work matters as well as the count.
- Introduce the measurement context alongside the results: local NVMe reads
  on synthetic input, and separate microscopy writes to a busy cluster
  filesystem mounted over NFS with `nconnect=16`.
- Use read-side file-concurrency results only where their storage and workload
  fit the local-read scope. Keep the measured NFS streaming count in section E;
  it does not establish a local-read file-count optimum.
- State that recent streaming and CPU read tests use shards near 1 GiB raw
  capacity. The older CHAMMI read comparison uses much smaller shards. These are
  test settings, not evidence that 1 GiB is optimal.

**Figure 2a — chunks inside files.** Introduce here. Draw distinct chunk and
shard boundaries in a Z/Y/X array, show the append direction and highlight a
4 × 4 active shard layer. Label sixteen as illustrative; the measured primary
counts are 4, 9, 15 and 30. Use this same schematic again in E to define
concurrent shards. A file touched by a read is not necessarily doing I/O at
the same instant as the other files.

### D. Write workloads

Having identified the desired reads and a candidate layout, ask how the data
arrive and what limits writing them.

| Write workload | Source and setting | Main concern here |
|---|---|---|
| Streaming | Images arriving during acquisition | Drain capacity and headroom for lower sustained rates |
| Streaming | A collection of TIFFs converted to Zarr | Memory use during conversion |
| Rechunking | An existing Zarr transformed into another Zarr, such as v2 to v3 | Memory use across source and destination layouts |

- Streaming covers acquisition and TIFF conversion. Distinguish the two
  settings even when they use the same writer.
- Rechunking is the Zarr-to-Zarr transformation considered here. Record both
  layouts and format versions; a version migration need not always change
  chunk shape. The source can be revisited, and traversal is a conversion
  choice rather than an acquisition arrival order.
- These are workload categories, not claims that all implementations use the
  same buffering or scheduling. Random subvolume updates are out of scope.

The workload table is sufficient here; no separate figure is needed.

### E. Acquisition

- Use Chucky's microscopy replay measurements to compare how quickly writers
  process logical input when input is continuously available. Call this
  maximum drain rate or drain capacity under the measured conditions. Preserve
  append plus final-drain/close timing and report repetition medians and ranges.
- Explain that sustained acquisition rates will be lower and need headroom
  for network/storage variation, stalls and finite buffers. No universal
  reduction factor is established. A separate sustained-rate study is not
  required to compare chunk, codec and sharding choices using drain capacity.
- Define **concurrent shards** as the shards in the `D-1` dimensional layer
  currently receiving appended data. They are typically opened, written,
  and closed over the same interval.
- Illustrate a `Z, Y, X` array appended along Z with a `4 x 4` shard grid across
  Y and X: 16 concurrent shards. Label it as illustrative geometry.
- Show the completed BBBC022 LZ4 series with 4, 9, 15 and 30 actual shards.
  The median paired 15/4 gain is 76.1%; 30/15 gains 10.1%, with an observed
  range from −14.1% to +22.4%. The Zstd 15/4 control gains about 2.8%; its chunk
  and block settings differ, so compare gains within each codec series.
  Include reference drift. Layer count differs from worker count and measured
  I/O overlap; these data establish neither a stable ceiling nor an optimum
  tied to `nconnect=16`.
- Keep the later 96 GiB comparison separate from the primary 32 GiB series.
  All three 54-shard samples are slower than their paired 30-shard samples:
  median 13.4% lower, range 11.0–15.3% lower. Preserve its adaptive selection,
  later job and smaller repetition count in the
  [paired result](../bbbc022-evidence/shard-extension-paired-summary.csv).

**Figure 2b–c — how much file parallelism helps.** Place after the shard-count
results and refer back to 2a. Plot measured drain capacity against actual
append-layer shard count for the primary study, separating the fixed LZ4 and
Zstd configurations. Include variability and paired gains. Put the later
30/54 result in a visibly separate panel with its 96 GiB minimum and n=3;
do not extend the primary curve through it. Adapt the existing
[primary plot](../bbbc022-evidence/shard-count.svg) and
[follow-up plot](../bbbc022-evidence/shard-extension.svg). Keep reference
drift visible in the caption, with the complete round/reference plot in
supporting material.

- Plot write drain capacity against output cost. Explain the Pareto frontier and
  the author's selection: highest throughput within 10% of the smallest
  comparable output cost for the same logical input and comparison group.
- Name the measured size metric in each series. The shared BBBC022 layouts
  have final file lengths as well as metered shard-write bytes. Their source
  and file-metadata audit accounts exactly for truncated footer padding and
  final metadata: the correction is below 0.0012% of final file length.
  Index bytes are already counted once. Other series keep their proxy label
  wherever the relation is unresolved; no separate output-size experiment is
  required. File close and I/O completion do not establish durable storage.
- For comparable sizes `S_i` and throughputs `T_i`, select the largest `T_i`
  satisfying `S_i <= 1.10 * min(S)`. This is an output-size tolerance.
- Show the older 16–64 KiB choices alongside larger winners, identifying raw
  chunk bytes and shapes, codecs, datasets, and machines. In the shared BBBC022
  study all six final sizes are within 2% of the smallest. The 64 KiB candidate
  has the highest write median, but overlapping ranges do not establish a
  stable ordering. The read-derived candidates also satisfy the 10% size rule;
  compare their drain capacity and output cost without selecting solely on
  write speed. Use the
  [write summaries](../bbbc022-evidence/shared-layout-summary.csv), with local
  read evidence shown separately. Different inputs, machines and shard
  geometries prevent treating these as one matched read/write experiment.
- Keep filesystem results separate from discard-sink or codec-only results.
  Normalize output size to a common logical volume where necessary. Include
  Blosc block size only as far as matched comparisons support its effect.

**Figure 3 — microscopy input and writing capacity.** Place after
the output-size selection rule and the shared-layout comparison. Panel a shows
the fixed first BBBC022 benchmark field (plate 20585, well A14, site 1, w5),
with a calibrated scale bar outside the image. Link the original dataset and
record display-only contrast; preserve native pixels and source attribution.
Panels b–c show all fourteen CPU and thirteen GPU configurations from the
retained BBBC022 NFS comparisons, in separate panels with their own thresholds.
These use measured shard-write bytes as a stored-size proxy; ten configurations
in each panel fail the 10% allowance. Highlight the highest median that qualifies.
Panel d plots the newer fixed-block comparison's median logical write GiB/s
against compression fold (unpadded logical input / final stored bytes) on a
logarithmic axis. Mark its own 10% allowance. Panel e gives each chunk size its
own rate-interval row and prints its compression fold, avoiding overlapping
ranges. Highlight 128 KiB; distinguish it from 64 KiB, the highest write
median. All six sizes are within 2% of the smallest. Replot the
[write summaries](../bbbc022-evidence/shared-layout-summary.csv); the existing
[shared-layout plot](../bbbc022-evidence/shared-layout.svg) supplies the same
measurements in a different arrangement. Keep this microscopy/NFS write
studies separate from each other and from Figure 1's synthetic/local read study.
Other datasets' historical frontiers and codec comparisons belong in supporting material.

### F. Conversion memory

- Return to TIFF streaming and Zarr-to-Zarr rechunking. Throughput still
  matters, but the question here is how much memory the conversion needs.
- For TIFF streaming, account for source decoding, queued input, unfinished
  chunks, codec buffers, and active-shard state. Do not equate writer memory
  alone with the memory required by the conversion process.
- For rechunking, show source and destination grids plus the regions processed
  together. Examine how traversal, concurrency, and source/destination overlap
  affect retained input and unfinished output buffers.
- Reason through the buffers live at the same time under the stated
  implementation, traversal, processing-block size and queue/cache bounds.
  Distinguish host/device memory, shared buffers and intermediate storage.
  Give conditional estimates or bounds; label measured peaks separately.
- Explain how concurrency, block size and retained source data change memory
  needs and source rereads or temporary I/O. A lower memory setting may move
  work elsewhere. Do not assume that a whole output shard must be buffered.
- Keep acquisition replay, complete TIFF conversion, and complete rechunking
  results separate. The write throughput/size frontier alone does not
  establish an efficient conversion or a bounded memory requirement.
- The located conversion records have no measured process peaks. Analytical
  reasoning is sufficient for this article; a conversion-memory experiment
  is not required. Do not describe the resulting estimates as measurements.

**Figure 4 — what must stay in memory during conversion.** Place after
introducing source/destination overlap and live buffers. Show a small worked
rechunking example: different source and destination grids, the processing
block and traversal, then which input blocks and partial output chunks remain
live at successive steps. Include a compact buffer-lifetime strip or table
for source decoding, retained input, codec workspaces and pending writes;
mark the TIFF decoder as specific to TIFF streaming. Count shared allocations
once and state queue limits. Label the example analytical, with explicit
dtype and shapes; do not depict a whole shard as necessarily buffered or
present an estimated memory maximum as a measured process peak.

### G. Layout recommendations

- Identify the required reads and choose candidate chunk shapes. Include
  small chunks and the larger alternatives supported by the relevant reader,
  storage and workload. Choose one persisted layout that prioritizes the
  expected crops while preserving acceptable scans. Start the compromise
  discussion at 128 KiB and show the measured reasons to move smaller or
  larger for the actual reader and workload. Use local NVMe read evidence
  and separate microscopy write evidence to assess drain capacity and output
  cost; preserve each study's conditions.
- Group chunks into shards and expose enough balanced file work for the
  storage system. Preserve the approximately 1 GiB raw shard capacity and
  actual layer counts when reproducing the reported setup. The LZ4 gain above
  fifteen is variable, and 54 is slower than 30 in the separate follow-up.
  The useful count depends on codec and resource limits.
- For acquisition, compare drain capacity and explain the headroom required
  for lower sustained rates. For TIFF conversion and rechunking, reason through
  complete-pipeline memory under explicit buffering and traversal assumptions.
- Close with what changes the choice: read workload, storage, source layout,
  and resource budget. Keep variation and unsupported claims visible.

Refer back to Figures 1–4. A short recommendation table can collect the
choices; no additional summary plot is needed.

## 3. Target length, after the outline

Proposed target remains **2,500 words**, excluding captions and a short methods
appendix. Revisit the budget after reviewing this revised outline.

| Section | Approximate words |
|---|---:|
| A. Read workloads | 200 |
| B. Chunks and read results | 500 |
| C. Shards and read parallelism | 300 |
| D. Two write workloads | 200 |
| E. Acquisition drain capacity | 600 |
| F. Conversion memory | 500 |
| G. Putting it together | 200 |
| **Total** | **2,500** |

Plan four main figures, with six insertion points marked above. Caption text
and supporting methods are outside the 2,500-word body target.
Produce figures with Python or Typst and follow the shared
[Nature figure guidelines](writing-guidelines.md#figure-style-and-delivery).

| Figure | Placement | Reader question | Preparation |
|---|---|---|---|
| 1a | A/B transition, after read amplification | Why can one crop require extra decoding? | New chunk/crop diagram |
| 1b–c | End of B, beside the compromise recommendation | What read performance do we trade for one persisted layout? | New plots from the selected local NVMe summaries |
| 2a | C; referenced again in E | How do chunks, shard files and the active append layer relate? | New geometry diagram |
| 2b–c | E, after the shard-count results | Where do extra concurrent files stop helping? | Adapt primary and separate follow-up write plots |
| 3 | E, after the size rule and shared-layout comparison | Is the read-friendly choice affordable in write speed and size? | Replot BBBC022 final-size/write-rate summaries |
| 4 | F, after introducing conversion buffering | Which buffers coexist, and how does traversal change memory? | New analytical worked example and buffer table |

Keep the existing workload table in D and use at most a short recommendation
table in G. Supporting material can hold block-size comparisons, other datasets,
reference drift and full per-round results. NFS read plots remain diagnostics
outside the article. Preserve settings and observed ranges in captions;
do not turn the selected comparison into a universal optimum.

## 4. Evidence and reasoning supporting the article

| Claim or question | Evidence or reasoning | Cluster prompt |
|---|---|---|
| Chunk choices for translated XY crops | Local NVMe CPU comparisons; 128 KiB mixed-workload starting point, 32 KiB crop-first Damacy alternative | 2 |
| How full and aligned reads change the choice | Matched local crop/scan comparisons; preserve reader mode and qualifications on XY alignment | 2 |
| Useful streaming shard counts and diminishing gains | Primary LZ4 4/9/15/30 and Zstd 4/15 series, paired gains and reference drift; separate series finds 54 slower than 30 | 4 |
| Streaming layout tradeoffs | BBBC022 write summaries, measured final sizes, accounting audit and historical frontiers; local reads remain a separate study | 3 |
| When Blosc block size matters | Matched comparisons and effective block sizes, including counterexamples | 3 |
| What memory do TIFF conversion and rechunking require? | Source/destination layouts, traversal, live buffers, queue/cache bounds; analytical treatment | 5 |
| Findings repeat across systems | Per-system results and exceptions with run variability | 1–5 |

Existing records were collected with [cluster-data-prompts.md](cluster-data-prompts.md).
The [follow-up results](follow-up-experiments.md) record the completed primary
experiments, the separate 30/54 follow-up and the questions handled through
reasoning. Missing evidence should narrow a claim; it should not expand this
into the earlier measurement program.

## 5. Draft, then edit

Draft after the audience, outline, target length, and central evidence are
settled. Keep reproducible methods in an appendix. During editing, check that
each layout choice follows from a read workload, and each write result names
its workload and performance or memory objective.

Defer multiscale/downsampling policy, conversion-tool selection, a general
layout planner, and the DCA standards review. The earlier plans retain that
background; their arbitrary-region write comparisons are outside this scope.
