# Writing readable Zarrs: figure outline

Archived 2026-09-25. This is historical planning for the broader guide.
Its requirements and recommendations do not govern the current article;
see [archive status](README.md) and the [current plan](../article-outline.md).

## Figure system

All diagrams and data figures should be authored in Typst and rendered as vector output.

Suggested layout:

```text
figures/
  src/
    fig-01-chunks-and-shards.typ
    fig-02-equal-bytes.typ
    ...
  rendered/
    fig-01-chunks-and-shards.svg
    fig-01-chunks-and-shards.pdf
    ...
  data/
    measurement-summary.csv
  lib.typ
```

Use `figures/lib.typ` for shared colors, labels, axes, legends, and chunk and
shard primitives. Prefer Typst-native blocks, grids, paths, and plots; if a
drawing or plotting package is needed, pin its version.

### Visual language

- **Useful/requested data:** saturated blue
- **Decoded but unused data:** pale blue or gray
- **Chunk boundaries:** thin dark lines
- **Shard boundaries:** heavy dark lines
- **Active-shard state:** amber
- **Rejected or amplified work:** red hatch or outline
- **Metadata and shard-index state:** violet

Do not rely on hue alone. Pair colors with labels, line weight, hatch, or icons. Figures must remain legible in grayscale and at presentation size.

## Figure 1 — Chunks are decode units; shards are storage units

**File:** `fig-01-chunks-and-shards.typ`

**Purpose:** Establish the two-level hierarchy and the central recommendation.

**Construction:**

- Draw one 2D array grid.
- Use thin lines for chunks and a heavy 2×2 or 4×4 grouping for shards.
- Highlight one chunk and one shard.
- Add two short callouts:
  - “chunk: independently decoded”
  - “shard: outer chunk stored as one value”
- Label chunk shape and shard shape in array elements, then show their quotient
  as chunks per shard.
- Under the grid, place “Chunk for access” and “Shard for storage-object count
  and I/O grouping.”

**Data dependency:** None; explicitly label as conceptual.

**Used in:** Document §§1 and 3; presentation slides 1 and 3.

## Figure 2 — Equal bytes do not imply equal access cost

**File:** `fig-02-equal-bytes.typ`

**Purpose:** Show why geometry and axis semantics precede byte targets.

**Construction:**

- Make two or three small multiples representing equal raw chunk bytes.
- Candidate A: shallow XY-oriented chunk shape with `T=1, C=1`.
- Candidate B: deep Z slab.
- Candidate C: chunk spanning several `C` or `T` values.
- Overlay the same logical 2D viewport and small model sample.
- Label useful voxels, total intersected chunk voxels, and decode amplification.

**Data dependency:** Initially illustrative; replace ratios with measured trace medians and p95 values.

**Used in:** Document §§1 and 4; presentation slide 4.

**Validation:** All candidates must have equal raw chunk bytes in the final
example. Include edge and misaligned selections, not only centered selections.

## Figure 3 — Chunks spanning C or T can create duplicate work

**File:** `fig-03-ct-extent.typ`

**Purpose:** Make the independently selected-axis recommendation memorable.

**Construction:**

- Represent four channels or time points as parallel strips.
- Left: one independently chunked strip is fetched for a one-channel request.
- Right: all four are contained in the same source chunk; highlight one useful strip and three decoded-but-unused strips.
- Add a compact decode-amplification label such as `4× decoded / 1× useful`.
  Add transfer amplification separately when measured.

**Data dependency:** Idetik behavior provides the motivating example; benchmark data supplies final byte ratios.

**Used in:** Document §§2 and 4; presentation slide 5.

## Figure 4 — Over-read helps only when a later selection reuses it

**File:** `fig-04-cache-reuse.typ`

**Purpose:** Show why cache benefit depends on reuse before eviction and cannot
be inferred from chunk shape alone.

**Construction:** Use the same chunk layout, cold initial state, bounded cache,
and number of operations in two aligned traces.

### Panel A: cache-reusing viewer trace

- Begin with one cold view selection that decodes useful and adjacent unused values.
- Pan into some of those values before eviction.
- Mark encoded-payload and decoded-chunk hits separately.
- Show cold time to first displayed pixel and later incremental viewport cost.

### Panel B: dispersed modeling trace

- Replay the same fixed-shape model sample at randomized, separated origins.
- Show the cache filling and evicting without useful cross-sample hits.
- Report samples per second, batch latency, and p95 decode amplification; do not use
  time to first displayed pixel.

Add a small temporal inset only if the measured trace distinguishes sequential
playback from random time jumps. Label the cache layers, byte capacity, initial
state, admission, eviction, expiration, and prefetch directly on the figure.

**Data dependency:** Ordered Idetik and Neuroglancer traces and the actual
Damacy sampler trace under the same declared cache configuration.

**Used in:** Document §3.4; presentation slide 6.

**Validation:** Separate the first cold selection from later selections. Credit
only bytes actually reused before eviction, and do not combine shard-index,
encoded-payload, and decoded-chunk hits into one “warm” rate.

## Figure 5 — Axis-stopping policy changes an anisotropic pyramid

**File:** `fig-05-anisotropic-pyramid.typ`

**Purpose:** Make the interaction among anisotropy, the required coarsest level,
chunk shape, and builder stopping policy immediately visible.

**Construction:** Use three aligned level strips for the same anisotropic base
array. A simple illustrative shape is `Y=512, X=16384` with `128×128` chunks;
replace it with a representative DCA shape for the final
figure.

### Panel A: declared coupled-axis stop

- Halve both axes until `Y` reaches one chunk.
- Stop the pyramid and show that `X` still spans many chunks.
- Label this as a reasonable passing outcome when the required coarsest level is at
  this level or finer; show a coarser requirement only as one this
  schedule would not meet.

### Panel B: per-axis stopping

- Hold `Y` once it reaches its target.
- Continue halving `X` until the required coarsest level is reached.
- Label the cumulative downsampling factor for each axis at every level.
- Mark this as the preferred general planning rule because it does not infer
  special behavior from the dimension's category.

### Panel C: explicit schedule with coarse-level chunk adaptation

- Continue the requested coupled reductions.
- Change the `Y` chunk extent on coarse levels so the schedule remains
  feasible.
- Mark the chunk-shape change clearly; do not imply that fixed chunks are a
  format requirement.

Under all panels, show level shape, chunk-grid shape, and the level a
cold viewer would select. A short caption should state: “Declare the required coarsest level
first; accept any recorded schedule that reaches it and passes its limits.”

**Data dependency:** Initially geometric. Replace the illustrative dimensions
with an anisotropic corpus case and annotate measured cold time to first displayed pixel,
per-level shard count, and builder output.

**Used in:** Document §4.4 and the DCA correction; presentation slide 7.

**Validation:** Show that edge chunks retain the declared chunk shape while
their in-bounds extents are smaller. Label current Acquire Zarr,
next-generation Acquire Zarr, or another
builder only when the shown stopping behavior has been verified at a pinned
revision. Do not depict current Acquire Zarr's coupled in-plane strategy as
intrinsically erroneous.

## Figure 6 — One selection from a shard has three transfer paths

**File:** `fig-06-range-read-paths.typ`

**Purpose:** Explain why a large shard is safe only with client/store support.

**Construction:** Three horizontal paths from a one-chunk selection to the
store:

1. read the shard index, then read the encoded inner-chunk payload range;
2. use the cached shard index, then read the encoded inner-chunk payload range;
3. fetch the complete stored shard value.

For each path, show:

- storage read request count;
- shard-index bytes;
- encoded chunk payload bytes;
- transferred storage bytes; and
- latency distribution when measured.

**Data dependency:** Cold and index-warm shard-index cache states plus no-range
measurements from `measurements.md`.

**Used in:** Document §5.3; presentation slide 9.

**Validation:** Separate transferred storage bytes from decoded chunk bytes. Do
not label a complete stored shard value fallback unless the client exhibits it.

## Figure 7 — Read work is scheduled across distinct shards

**File:** `fig-07-shard-concurrency.typ`

**Purpose:** Translate Damacy's coalescing/interleaving lesson into a general scheduling model.

**Construction:**

- Draw a short time axis with four shard lanes.
- Show adjacent chunk reads merged within one lane.
- Show work from several shard lanes overlapping.
- Add a contrasting mini-panel where many logical tasks all queue behind one shard.
- Label chunks touched, storage read requests, and distinct shards touched per
  selection or batch separately.

**Data dependency:** Damacy counters plus storage trace timing.

**Used in:** Document §§5.3 and 7; presentation slide 10.

**Validation:** Do not infer observed storage concurrency from task overlap
alone; use file/range timing or storage-system instrumentation.

## Figure 8 — Stored shard bytes trade storage-object count against parallel work and retry cost

**File:** `fig-08-shard-tradeoff.typ`

**Purpose:** Show why “make shards large” needs upper bounds.

**Construction:**

- X-axis: median stored shard bytes on a logarithmic scale.
- Left Y-axis: total shard count, storage-object count, and whole-dataset
  operation time.
- Right Y-axis or aligned panels: distinct shards touched per selection or
  batch, bytes transferred by one shard retry, and no-range storage over-read.
- Shade the feasible region satisfying all policy limits.

**Data dependency:** Whole-dataset operation, ordered-trace, and shard-retry
measurements.

**Used in:** Document §§5.1–5.4; presentation slide 11.

**Validation:** Prefer aligned panels over a multi-axis chart if scales become hard to read.

## Figure 9 — Zarr writer choice changes writer working memory

**File:** `fig-09-writer-residency.typ`

**Purpose:** Explain the memory consequence behind tool selection.

**Construction:** Two primary panels plus a high-level wrapper:

### Panel A: Acquire Zarr single-pass streaming write

- incoming planes/frames;
- bounded input queue;
- current layer or band of chunks;
- codec buffers;
- encoded chunks flowing into shard sinks;
- per-shard index and transport state, labeled with measured bytes.

Use amber only for items resident at the illustrated instant. Show completed payload leaving memory.

### Panel B: arbitrary-region sharded writes

- arbitrary regions targeting several shards;
- one writeback/cache box per active shard;
- commit/flush to storage;
- arrows indicating possible read-modify-write.

Label this as a **working model to measure**, not a universal TensorStore implementation diagram.

### Wrapper: iohub

- draw iohub above the Zarr writer panels as source parsing plus OME-Zarr/HCS
  metadata construction;
- connect it to a selectable Zarr writer;
- do not present it as a fifth buffering model.

**Data dependency:** Writer working memory and process peak RSS experiments by
stored shard bytes and active shards.

**Used in:** Document §6; presentation slide 12.

**Validation:** Match the Acquire Zarr side to current band/layer flush
behavior. Match the arbitrary-region side to measured writer working memory,
process peak RSS, and Zarr writer configuration.

## Figure 10 — Zarr writer and pyramid-builder decision flow

**File:** `fig-10-writer-decision.typ`

**Purpose:** Give readers a fast, non-exclusive way to choose Zarr writers
and pyramid builders.

**Construction:** A compact decision tree:

```text
Need microscopy parsing or OME-Zarr/HCS construction?
  yes -> iohub source and metadata layer -> choose/record Zarr writer

Can the output use a single-pass streaming write?
  yes -> Acquire Zarr
  no  -> Need concurrent arbitrary-region writes or transactions?
           yes -> TensorStore
           no  -> zarr-python

Need a multiscale pyramid?
  required schedule supported in the stream -> integrated Acquire Zarr path
  explicit batch graph or different per-level layout -> ngff-zarr / ome-zarr-py
```

Draw the pyramid choice as a second lane rather than as another Zarr writer
peer. Add a side note: “Compositions are valid; benchmark the complete
pipeline.”

**Data dependency:** None, but tool/version capabilities must be checked before publication.

**Used in:** Document §§6.1–6.3; presentation slide 13.

**Validation:** Avoid implying that iohub and the three Zarr writers are mutually exclusive peers.

## Figure 11 — Acquire Zarr bounds a single-pass streaming write

**File:** `fig-11-acquire-zarr-stream.typ`

**Purpose:** Show how ordered input enables incremental delivery.

**Construction:**

```text
source -> frame queue -> tile/transpose -> chunk layer/band
       -> codec pipeline -> shard payload + index assembly -> store
                         \-> multiscale stages
```

Label each retained buffer and its lifetime. Show a shard payload receiving
encoded chunks incrementally while its index remains open.

**Data dependency:** Current Acquire Zarr implementation and measured bytes in
each queue and buffer.

**Used in:** Document §§6.2–6.3; presentation slide 14.

**Validation:** Distinguish implementation facts from next-generation design goals. Call the product Acquire Zarr in visible labels.

## Figure 12 — Multiscale layout selection is a staged constrained search

**File:** `fig-12-layout-search.typ`

**Purpose:** Visualize the adapted Acquire Zarr layout algorithm.

**Construction:**

- Left funnel: chunk candidates generated from axis semantics, trace geometry,
  codec limits, and the raw chunk byte range.
- First policy limits: decode amplification, encoding throughput, and
  compression tolerance.
- Middle fan-out: required downsampling schedules, fixed per-level chunk shapes, and
  explicit coarse-level chunk alternatives.
- Second policy limits: required coarsest level, per-level decode
  amplification, downsampling correctness, and pyramid-builder capability.
- Right fan-out: configurations of chunks per shard for every surviving
  per-level chunk plan.
- Third policy limits: storage read requests, transfer amplification, maximum
  shard count, minimum efficient stored-value bytes, shard parallelism target,
  writer working memory, maximum stored shard bytes, and range-read behavior.
- Output: passing layouts and the deterministic tie-break; benchmark the
  retained subset to validate the measured Pareto frontier.

**Data dependency:** Candidate counts and rejection reasons from the solver.

**Used in:** Document §8; presentation slide 15.

## Figure 13 — The measured frontier selects the policy

**File:** `fig-13-pareto-frontier.typ`

**Purpose:** Replace a universal layout with an explicit feasible
frontier and tie-break.

**Construction:**

- X-axis: p95 decode and transfer amplification per workload, in separate aligned panels.
- Y-axis: sustained conversion throughput.
- Point area: total shard count.
- Point color or shape: Zarr writer.
- Outline: layouts within limits on writer working memory, process peak RSS,
  and maximum stored shard bytes.
- Label the recommended point and two passing alternatives that trade different
  named objectives.

**Data dependency:** Full benchmark results.

**Used in:** Document §8; presentation slide 16.

**Validation:** A point is Pareto-optimal only relative to all reported objectives. Do not mix modeled and measured candidates without distinct marks.

## Figure 14 — Layout decision record

**File:** `fig-14-layout-report.typ`

**Purpose:** Make the required output of a conversion concrete.

**Construction:** One compact card with:

- dataset scope and workload identity;
- required coarsest level, downsampling schedule, and pyramid
  builder/version;
- chunk and shard shapes by level;
- median/p95 stored shard bytes and total count;
- p50/p95 transfer and decode amplification;
- source and metadata layer, Zarr writer, version, and write order;
- writer working memory, process peak RSS, and sustained conversion throughput;
- verified client/store range-read behavior; and
- policy version/status.

**Data dependency:** One worked dataset.

**Used in:** Document §10; presentation slide 17.

## Data-figure conventions

- Plot individual repetitions faintly and a summary statistic prominently.
- Show p50 and p95/p99 where tail behavior affects interaction or acquisition safety.
- Use logarithmic axes for byte quantities and sweeps of storage-object count.
- Put selection or batch count, repetition count, and uncertainty definition in
  the caption.
- State cache configuration, store, Zarr writer version, codec, and workload beside or
  immediately below the chart.
- Never derive encoded fraction from stored bytes alone.
- Label omitted fill chunks, logical bytes represented by them, metadata, and
  shard-index bytes independently.

## Typst rendering and QA

Render both SVG for Markdown and PDF for presentation-quality reuse:

```sh
typst compile figures/src/fig-01-chunks-and-shards.typ figures/rendered/fig-01-chunks-and-shards.svg
typst compile figures/src/fig-01-chunks-and-shards.typ figures/rendered/fig-01-chunks-and-shards.pdf
```

For each figure:

1. Render at the final document width and at 16:9 slide scale.
2. Inspect for clipped labels, collisions, and unreadably small text.
3. Verify all numeric labels against the source CSV or generated data table.
4. Confirm grayscale and color-vision legibility.
5. Keep source, rendered artifact, and exact input data under version control.

## Cross-references

- Full narrative: [outline.md](outline.md)
- Slide assignments: [presentation-outline.md](presentation-outline.md)
- Measurement inputs: [measurements.md](measurements.md)
- Executable search and result schema: [planner-design.md](../../code/planner-design.md)
- Canonical terms: [glossary.md](glossary.md)
