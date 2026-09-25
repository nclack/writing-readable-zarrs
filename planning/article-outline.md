# Writing readable Zarrs: article outline

Updated 2026-09-25. This is the current writing plan. The earlier, broader
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

Central question: What layout serves the required reads, and how do we write
it efficiently?

Working argument: Start with the read workloads. Chunk choices depend on the
reader, data, storage and selection shape; small translated crops and full-array
reads can favor different layouts. Shards group chunks into files and expose file parallelism.
Then consider how to produce that layout: streaming for acquisition or TIFF
conversion, and rechunking for Zarr-to-Zarr conversion. Acquisition emphasizes
drain capacity and headroom for lower sustained rates; conversions emphasize
memory use, explained through processing order and buffer lifetimes.

The [evidence bundle](../readable-zarrs-evidence/README.md) contains the collected
records, scoped findings and counterexamples. The new
[BBBC022 evidence](../bbbc022-evidence/README.md) completes the primary read/write
layout and streaming shard-count experiments; [results and scope](follow-up-experiments.md)
connect these measurements and the separate 30/54 follow-up to the article.
Conversion memory and final-size accounting will be handled through
reasoning; separate conversion-memory, sustained-acquisition and output-size
experiments are not prerequisites. Random subvolume writes remain outside scope.

### A. Identify the read workloads

- Open with the regions applications will request, their order, and their
  concurrency. Use randomly translated XY crops as the main example.
- Distinguish three workloads before discussing layout:

  | Read workload | What to specify | Why it matters |
  |---|---|---|
  | Translated XY crops | Crop shape, other-axis extents, position distribution, batches, reuse | Crop boundaries cut across the chunk grid |
  | Chunk-aligned crops | Origins and extents aligned to whole chunks | Removes the same interior crop-boundary waste |
  | Full arrays | Array extent, traversal, concurrency | All logical values are needed |

- Relate translated crops to training data loaders and some visualization
  reads. They do not measure a full training loop or interactive viewer.
- Specify cache state and reuse where they change the workload. Rechunking
  also reads a source array, but its processing selections depend on the
  source and destination layouts; do not assume it is one sequential scan.

### B. Choose chunks from those reads

- Define a chunk as the independently encoded/decoded region in this
  article's indexed-sharding model. Both its shape and byte count matter.
- Overlay the same translated crop on coarse and fine chunk grids. Show
  values decoded outside the requested crop.
- Explain read amplification in plain language, then label the quantities:
  decoded bytes / useful bytes for geometry, and transferred bytes separately
  for storage traffic. Compression and coalescing can change the latter.
- Lead with the shared BBBC022 layouts: translated 256 × 256 crops favor
  256–512 KiB candidates in both CPU readers on NFS. Their observed ranges
  overlap, so do not insist on an ordering within that pair. Put the older
  local synthetic Damacy preference near 32 KiB alongside this counterexample.
  Keep chunk shapes, crop settings, caches, concurrency and read objectives
  visible; frontier membership does not itself select a scalar winner.
- Put the complete-array and 512 × 512 crop controls beside them. Damacy's
  full-scan median peaks at 32 KiB (2.930 useful GiB/s), TensorStore's at
  128 KiB (2.454 GiB/s). Larger chunks do not consistently improve full scans.
  The aligned crops favor larger candidates; translated 512 × 512 crops show
  little consistent gain beyond the middle of the tested range. Their frame
  lists match, but aligned and translated selections differ in XY coverage,
  reuse and shard crossings; this comparison does not isolate chunk alignment.
- Explain that less geometric over-reading does not alone predict speed.
  Per-chunk work and array-edge padding matter, but these measurements do not
  isolate their individual costs. The 32 and 64 KiB layouts have the same
  padded volume and different full-scan rates, so padding is not a complete
  explanation. Use the [read summaries](../bbbc022-evidence/read-summary.csv)
  and observed ranges rather than a general small- or large-chunk rule.
- Compare layout trends within each reader first. Absolute reader speeds
  require matched selections and explicit CPU/GPU output and timing boundaries.

### C. Group chunks into shards and distribute read work

- Define a shard as a group of chunks in one stored file. With indexed range
  reads, small chunks do not require one small file per chunk.
- Explain why distributing reader work across several files may expose more
  parallelism. Distinguish files touched by a batch from files with active I/O;
  balance of work matters as well as the count.
- Introduce the measurement context alongside the results: real microscopy,
  several machines, and mostly a busy cluster filesystem mounted over NFS
  with `nconnect=16`. Keep local-storage and NFS results identifiable.
- Show available read-side file-concurrency evidence and diminishing gains.
  Treat a relationship to NFS connection count as a hypothesis, not a
  one-file-per-socket mechanism or a portable rule.
- State that recent streaming and CPU read tests use shards near 1 GiB raw
  capacity. The older CHAMMI read sweep uses much smaller shards. These are
  test settings, not evidence that 1 GiB is optimal.

### D. Introduce the two write workloads

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

### E. Streaming at acquisition time: compare drain capacity

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
  write speed. Use the [joint layout table](../bbbc022-evidence/joint-layouts.csv).
- Keep filesystem results separate from discard-sink or codec-only results.
  Normalize output size to a common logical volume where necessary. Include
  Blosc block size only as far as matched comparisons support its effect.

### F. Conversions: produce the layout within a memory budget

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

### G. Put the choices together

- Identify the required reads and choose candidate chunk shapes. Include
  small chunks and the larger alternatives supported by the relevant reader,
  storage and workload. Use the common microscopy read/write study to connect
  those choices to write drain capacity and output cost.
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

Plan three main figures: (1) crop/chunk geometry with translated, aligned,
and full-array read results; (2) shard-layer geometry and concurrency sweep,
with read and streaming counts labeled separately; (3) the write frontier
and 10% size band. Use a compact table for reasoned conversion-memory accounting. Add
or substitute a source/destination-grid figure if the rechunking explanation
needs it. Put complete per-machine/dataset panels in supporting material,
including exceptions rather than selecting only results that fit the story.

## 4. Evidence and reasoning supporting the article

| Claim or question | Evidence or reasoning | Cluster prompt |
|---|---|---|
| Chunk choices for translated XY crops | Existing scoped frontiers; completed BBBC022 series favors 256–512 KiB for 256 × 256 crops | 2 |
| How full and aligned reads change the choice | Completed controls: full-scan optima differ by reader; aligned crops favor larger candidates | 2 |
| Useful streaming shard counts and diminishing gains | Primary LZ4 4/9/15/30 and Zstd 4/15 series, paired gains and reference drift; separate series finds 54 slower than 30 | 4 |
| Streaming layout tradeoffs | Shared BBBC022 read/write table, measured final sizes, exact accounting audit and historical frontiers | 3 |
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
