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

Working argument: Start with the read workloads. The reported measurements
favor small chunks for translated crops and larger chunks for full-array or
aligned reads. Shards group chunks into files and expose file parallelism.
Then consider how to produce that layout: streaming for acquisition or TIFF
conversion, and rechunking for Zarr-to-Zarr conversion. Acquisition emphasizes
sustained throughput; conversions emphasize memory use.

The numerical results below are the author's reported findings. Supporting
records still need to be assembled; this outline does not independently
validate their scope or ranking. No conversion-memory result has been supplied
yet. Random subvolume writes are outside this article's scope.

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
- Show the reported result near 32 KiB separately for Damacy and TensorStore,
  with actual chunk shapes, crop settings, caches, and concurrency visible.
  Recover each analysis's Pareto objectives and selection rule.
- Put the full-array and aligned-crop results beside it: the author reports
  larger chunks doing better there. Reduced per-chunk overhead is an
  explanation to assess. Array-edge padding and other overheads may remain.
- If those controls are absent, retain the workload distinction and label the
  speed comparison as unverified. Small chunks are a workload-specific result.
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
- State that shards were held near 1 GiB in the reported tests. Verify whether
  this is uncompressed capacity or stored bytes. It is a test setting, not
  evidence that 1 GiB is optimal.

### D. Introduce the two write workloads

Having identified the desired reads and a candidate layout, ask how the data
arrive and what limits writing them.

| Write workload | Source and setting | Main concern here |
|---|---|---|
| Streaming | Images arriving during acquisition | Sustain the acquisition rate |
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

### E. Streaming at acquisition time: sustain throughput

- Ask whether the candidate layout keeps up with the source over a sustained
  run, including shard turnover and finalization. Use Chucky's microscopy
  measurements, with timing and source-input boundaries made explicit.
- Define **concurrent shards** as the shards in the `D-1` dimensional layer
  currently receiving appended data. They are typically opened, written,
  and closed over the same interval.
- Illustrate a `Z, Y, X` array appended along Z with a `4 x 4` shard grid across
  Y and X: 16 concurrent shards. Label it as illustrative geometry.
- Show the author's working target near 16, with the actual shard-count
  sweep, repetitions, and work balance where available. Separate layer count
  from worker count and measured I/O overlap. Its proximity to `nconnect=16`
  does not establish that the optimum tracks connection count.
- Plot write throughput against output size. Explain the Pareto frontier and
  the author's selection: highest throughput within 10% of the smallest
  measured output for the same logical input and comparison group.
- For comparable sizes `S_i` and throughputs `T_i`, select the largest `T_i`
  satisfying `S_i <= 1.10 * min(S)`. This is an output-size tolerance.
- Show the reported 16–64 KiB range, identifying raw chunk bytes and shapes,
  codecs, datasets, and machines. Check whether the read-derived candidates
  also meet the acquisition requirement; do not select solely on write speed.
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
- Record host memory and device memory where applicable, processing-block
  sizes, queue limits, and any intermediate storage. Distinguish measured
  peaks, configured budgets, and modeled allocations.
- Present measured memory versus concurrency or processing-block size if
  available, alongside throughput and source rereads or temporary I/O. A
  lower memory setting may move work elsewhere; identify what was measured.
- Keep acquisition replay, complete TIFF conversion, and complete rechunking
  results separate. The write throughput/size frontier alone does not
  establish an efficient conversion or a bounded memory requirement.
- If conversion measurements are missing, explain the quantities to check
  without claiming a measured memory advantage for a tool or layout.

### G. Put the choices together

- Identify the required reads and choose candidate chunk shapes. For the
  measured translated-crop workloads, include 32 KiB and nearby 16–64 KiB
  candidates; full-array or aligned workloads warrant larger candidates.
- Group chunks into shards and expose enough balanced file work for the
  storage system. Use approximately 1 GiB shards and near 16 concurrent
  streaming shards when reproducing the reported setup, with verified units.
- For acquisition, check sustained throughput against the source rate. For
  TIFF conversion and rechunking, check complete-pipeline memory against the
  available budget and report the associated throughput.
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
| E. Acquisition throughput | 600 |
| F. Conversion memory | 500 |
| G. Putting it together | 200 |
| **Total** | **2,500** |

Plan three main figures: (1) crop/chunk geometry with translated, aligned,
and full-array read results; (2) shard-layer geometry and concurrency sweep,
with read and streaming counts labeled separately; (3) the write frontier
and 10% size band. Use a compact table for conversion memory evidence. Add
or substitute a source/destination-grid figure if the rechunking explanation
needs it. Put complete per-machine/dataset panels in supporting material,
including exceptions rather than selecting only results that fit the story.

## 4. Evidence needed before drafting numerical claims

| Claim or question | Evidence to recover | Cluster prompt |
|---|---|---|
| About 32 KiB is best for translated XY crops | Traces/settings and layout sweeps for each reader | 2 |
| Larger chunks help full or aligned reads | Matched workload controls | 2 |
| File concurrency helps; about 16 streaming shards was useful | Actual counts, work balance, repetitions, mount context | 4 |
| 16–64 KiB gives the preferred streaming tradeoff | Microscopy output sizes, throughput, timing scope, full frontier | 3 |
| Blosc block size has little effect here | Matched block-size comparisons and effective block sizes | 3 |
| What memory do TIFF conversion and rechunking require? | Source/destination layouts, complete-pipeline memory, concurrency, throughput | 5 |
| Findings repeat across systems | Per-system results and exceptions with run variability | 1–5 |

Use [cluster-data-prompts.md](cluster-data-prompts.md) to collect existing
records first. Missing evidence should narrow a claim or identify a focused
follow-up; it should not expand this into the earlier measurement program.

## 5. Draft, then edit

Draft after the audience, outline, target length, and central evidence are
settled. Keep reproducible methods in an appendix. During editing, check that
each layout choice follows from a read workload, and each write result names
its workload and performance or memory objective.

Defer multiscale/downsampling policy, conversion-tool selection, a general
layout planner, and the DCA standards review. The earlier plans retain that
background; their arbitrary-region write comparisons are outside this scope.
