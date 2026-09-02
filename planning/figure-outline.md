# Writing readable Zarrs: figure outline

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

Use `figures/lib.typ` for shared colors, labels, axes, legends, and chunk/shard primitives. Prefer Typst-native blocks, grids, paths, and plots; if a drawing or plotting package is needed, pin its version.

### Visual language

- **Useful/requested data:** saturated blue
- **Decoded but unused data:** pale blue or gray
- **Chunk boundaries:** thin dark lines
- **Shard boundaries:** heavy dark lines
- **Active/resident write state:** amber
- **Rejected or amplified work:** red hatch or outline
- **Metadata/index state:** violet

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
  - “shard: independently stored/accessed object”
- Under the grid, place “Chunk for access” and “Shard for concurrency + operations.”

**Data dependency:** None; explicitly label as conceptual.

**Used in:** Document §§1 and 3; presentation slides 1 and 3.

## Figure 2 — Equal bytes do not imply equal access cost

**File:** `fig-02-equal-bytes.typ`

**Purpose:** Show why geometry and axis semantics precede byte targets.

**Construction:**

- Make two or three equal-area small multiples representing equal raw chunk bytes.
- Candidate A: shallow XY tile with `T=1, C=1`.
- Candidate B: deep Z slab.
- Candidate C: chunk spanning several `C` or `T` values.
- Overlay the same logical 2D viewport and small 3D patch.
- Label useful voxels, total intersected chunk voxels, and decode amplification.

**Data dependency:** Initially illustrative; replace ratios with measured trace medians and p95 values.

**Used in:** Document §§1 and 4; presentation slide 4.

**Validation:** All candidates must have equal raw bytes in the final example. Include edge/misaligned selections, not only centered selections.

## Figure 3 — Packing C or T creates duplicate work

**File:** `fig-03-ct-packing.typ`

**Purpose:** Make the low-dimensional chunk recommendation memorable.

**Construction:**

- Represent four channels or time points as parallel strips.
- Left: one independently chunked strip is fetched for a one-channel request.
- Right: all four are contained in the same source chunk; highlight one useful strip and three decoded-but-unused strips.
- Add a compact amplification label such as `4× decoded / 1× useful`, using measured values if compression makes byte amplification differ.

**Data dependency:** Idetik behavior provides the motivating example; benchmark data supplies final byte ratios.

**Used in:** Document §§2 and 4; presentation slide 5.

## Figure 4 — Over-read helps only when a later query reuses it

**File:** `fig-04-query-coherence.typ`

**Purpose:** Show why cache benefit depends on ordered query coherence and
cannot be inferred from chunk shape alone.

**Construction:** Use the same chunk layout, cold initial state, bounded cache,
and number of operations in two aligned traces.

### Panel A: coherent viewer trace

- Begin with one cold viewport that decodes useful and adjacent unused values.
- Pan into some of those values before eviction.
- Mark encoded-payload and decoded-chunk hits separately.
- Show cold time to first displayed pixel and later incremental viewport cost.

### Panel B: dispersed modeling trace

- Replay the same fixed-shape model sample at randomized, separated origins.
- Show the cache filling and evicting without useful cross-sample hits.
- Report batch throughput/latency and p95 decode amplification; do not use
  time-to-first-pixel.

Add a small temporal inset only if the measured trace distinguishes sequential
playback from random time jumps. Label cache tier, byte capacity, initial state,
and eviction policy directly on the figure.

**Data dependency:** Ordered Idetik/Neuroglancer traces and the actual
Katamari/Damacy sampler trace under the same declared cache model.

**Used in:** Document §3.4; presentation slide 6.

**Validation:** Separate the first cold operation from later operations. Credit
only bytes actually reused before eviction, and do not combine shard-index,
encoded-payload, and decoded-chunk hits into one “warm” rate.

## Figure 5 — Axis-retirement policy changes an anisotropic pyramid

**File:** `fig-05-anisotropic-pyramid.typ`

**Purpose:** Make the interaction among anisotropy, pyramid depth, nominal
chunk shape, and builder stopping policy immediately visible.

**Construction:** Use three aligned level strips for the same anisotropic base
array. A simple illustrative shape is `Y=512, X=16384` with nominal
`128×128` chunks; replace it with a representative DCA shape for the final
figure.

### Panel A: declared coupled-axis stop

- Halve both axes until `Y` reaches one nominal chunk.
- Stop the pyramid and show that `X` still spans many chunks.
- Label this as a reasonable passing outcome when the required overview is at
  this level or finer; show a farther overview only as a requirement this
  schedule would not meet.

### Panel B: category-independent axis retirement

- Hold `Y` once it reaches its target.
- Continue halving `X` until the required overview is reached.
- Label the cumulative per-axis scale at each level.
- Mark this as the preferred general planning rule because it does not infer
  special behavior from the dimension's category.

### Panel C: explicit schedule with coarse-level chunk adaptation

- Continue the requested coupled reductions.
- Change the nominal `Y` chunk on coarse levels so the schedule remains
  feasible.
- Mark the chunk-shape change clearly; do not imply that fixed chunks are a
  format requirement.

Under all panels, show level shape, nominal chunks per axis, and the level a
cold viewer would select. A short caption should state: “Declare the overview
first; accept any recorded schedule that reaches it and passes its limits.”

**Data dependency:** Initially geometric. Replace the illustrative dimensions
with an anisotropic corpus case and annotate measured cold first-view latency,
per-level shard count, and builder output.

**Used in:** Document §4.4 and the DCA correction; presentation slide 7.

**Validation:** Distinguish configured nominal chunks from truncated edge
chunks. Label current Acquire Zarr, next-generation Acquire Zarr, or another
builder only when the shown stopping behavior has been verified at a pinned
revision. Do not depict current Acquire Zarr's coupled in-plane strategy as
intrinsically erroneous.

## Figure 6 — A sharded random read has three possible costs

**File:** `fig-06-range-read-paths.typ`

**Purpose:** Explain why shard size is safe only with client/store support.

**Construction:** Three horizontal paths from “request one chunk” to the store:

1. read shard index, then read inner-chunk byte range;
2. use cached shard index, then read inner-chunk byte range;
3. fetch the entire shard.

For each path, show:

- request count;
- index bytes;
- payload bytes;
- total transferred bytes; and
- latency distribution when measured.

**Data dependency:** Cold, index-warm, and no-range measurements from `measurements.md`.

**Used in:** Document §5.3; presentation slide 9.

**Validation:** Separate protocol payload bytes from decoded bytes. Do not label a full-object fallback unless the client actually exhibits it.

## Figure 7 — Concurrency is scheduled across distinct shards

**File:** `fig-07-shard-concurrency.typ`

**Purpose:** Translate Damacy's coalescing/interleaving lesson into a general scheduling model.

**Construction:**

- Draw a short time axis with four shard lanes.
- Show adjacent chunk reads merged within one lane.
- Show work from several shard lanes overlapping.
- Add a contrasting mini-panel where many logical tasks all queue behind one shard.
- Label logical chunks, physical reads, and distinct shards per wave separately.

**Data dependency:** Damacy counters plus storage trace timing.

**Used in:** Document §§5.3 and 7; presentation slide 10.

**Validation:** Do not infer physical parallelism from task overlap alone; use actual file/range timing or backend instrumentation.

## Figure 8 — Shard size trades object count for concurrency and risk

**File:** `fig-08-shard-tradeoff.typ`

**Purpose:** Show why “make shards large” needs upper bounds.

**Construction:**

- X-axis: median stored shard size on a logarithmic scale.
- Left Y-axis: total shard/object count and whole-dataset operation time.
- Right Y-axis or aligned panels: distinct shards per common batch, retry bytes, and no-range read amplification.
- Shade the feasible region satisfying all policy limits.

**Data dependency:** Object-operation, trace, and retry measurements.

**Used in:** Document §§5.1–5.4; presentation slide 11.

**Validation:** Prefer aligned panels over a multi-axis chart if scales become hard to read.

## Figure 9 — Writer choice changes the resident write unit

**File:** `fig-09-writer-residency.typ`

**Purpose:** Explain the memory consequence behind tool selection.

**Construction:** Two primary panels plus a high-level wrapper:

### Panel A: Acquire Zarr ordered stream

- incoming planes/frames;
- bounded input queue;
- current layer or band of chunks;
- codec buffers;
- compressed chunks flowing into shard sinks;
- small per-shard index/transport state.

Use amber only for items resident at the illustrated instant. Show completed payload leaving memory.

### Panel B: random-access sharded writes

- arbitrary patches targeting several shards;
- one writeback/cache box per active shard;
- commit/flush to storage;
- arrows indicating possible read/modify/write.

Label this as a **working model to measure**, not a universal TensorStore implementation diagram.

### Wrapper: iohub

- draw iohub above the writer panels as source parsing + OME-NGFF/HCS metadata;
- connect it to a selectable backend;
- do not present it as a fifth buffering model.

**Data dependency:** Memory scaling experiments by shard size and active shards.

**Used in:** Document §6; presentation slide 12.

**Validation:** Match the Acquire Zarr side to current band/layer flush behavior. Match the random-access side to observed memory and backend configuration.

## Figure 10 — Writer and pyramid-builder decision flow

**File:** `fig-10-writer-decision.typ`

**Purpose:** Give readers a fast, non-exclusive way to choose storage writers
and pyramid builders.

**Construction:** A compact decision tree:

```text
Need microscopy parsing / NGFF-HCS construction?
  yes -> iohub source + metadata layer -> choose/record backend

Output arrives monotonically and is write-once?
  yes -> Acquire Zarr
  no  -> Need async remote concurrency or transactions?
           yes -> TensorStore
           no  -> zarr-python

Need a multiscale pyramid?
  required schedule supported in the stream -> integrated Acquire Zarr path
  explicit batch graph or different per-level layout -> ngff-zarr / ome-zarr-py
```

Draw the pyramid choice as a second lane rather than as another storage-writer
peer. Add a side note: “Compositions are valid; benchmark the complete
pipeline.”

**Data dependency:** None, but tool/version capabilities must be checked before publication.

**Used in:** Document §§6.1–6.3; presentation slide 13.

**Validation:** Avoid implying that iohub and the three storage writers are mutually exclusive peers.

## Figure 11 — Acquire Zarr bounds a write-once stream

**File:** `fig-11-acquire-zarr-stream.typ`

**Purpose:** Show how ordered input enables incremental delivery.

**Construction:**

```text
source -> frame queue -> tile/transpose -> chunk layer/band
       -> compress -> shard aggregation/index -> storage
                         \-> multiscale stages
```

Annotate where memory is held and where buffers are released. Show a shard payload receiving compressed chunks incrementally while its index remains open.

**Data dependency:** Current Acquire Zarr implementation and measured queue/buffer sizes.

**Used in:** Document §§6.2–6.3; presentation slide 14.

**Validation:** Distinguish implementation facts from next-generation design goals. Call the product Acquire Zarr in visible labels.

## Figure 12 — Multiscale layout selection is a staged constrained search

**File:** `fig-12-layout-search.typ`

**Purpose:** Visualize the adapted Acquire Zarr layout algorithm.

**Construction:**

- Left funnel: chunk candidates generated from axis semantics, trace geometry, codec limits, and raw byte range.
- First gate: read/decode amplification, compression knee, and request rate.
- Middle fan-out: required level schedules, fixed nominal per-level chunks, and
  explicit coarse-level chunk alternatives.
- Second gate: required coarsest resolution and every level's amplification,
  memory, and structural limits.
- Right fan-out: shard packings for every surviving per-level chunk plan.
- Third gate: shard count, distinct-shard concurrency, memory, retry size,
  range behavior, and pyramid-builder capability.
- Output: a small Pareto frontier for empirical validation.

**Data dependency:** Candidate counts and rejection reasons from the solver.

**Used in:** Document §8; presentation slide 15.

## Figure 13 — The measured frontier selects the policy

**File:** `fig-13-pareto-frontier.typ`

**Purpose:** Replace a magic layout tuple with explicit tradeoffs.

**Construction:**

- X-axis: weighted p95 wire/decode amplification or separate aligned panels.
- Y-axis: sustained write throughput.
- Point area: total shard count.
- Point color or shape: writer.
- Outline: layouts within peak-memory and retry bounds.
- Label the recommended point and two nearby alternatives.

**Data dependency:** Full benchmark results.

**Used in:** Document §8; presentation slide 16.

**Validation:** A point is Pareto-optimal only relative to all reported objectives. Do not mix modeled and measured candidates without distinct marks.

## Figure 14 — Layout report card

**File:** `fig-14-layout-report.typ`

**Purpose:** Make the required output of a conversion concrete.

**Construction:** One compact card with:

- dataset and workload identity;
- required coarsest resolution, cumulative per-axis schedule, and pyramid
  builder/version;
- chunk and shard shapes by level;
- median/p95 stored shard size and total count;
- p50/p95 read and decode amplification;
- writer/backend/version and write order;
- peak memory and sustained throughput;
- range-read capability; and
- policy version/status.

**Data dependency:** One worked dataset.

**Used in:** Document §10; presentation slide 17.

## Data-figure conventions

- Plot individual repetitions faintly and a summary statistic prominently.
- Show p50 and p95/p99 where tail behavior affects interaction or acquisition safety.
- Use logarithmic axes for byte size and object count sweeps.
- Put sample count and uncertainty definition in the caption.
- State cache state, store, writer version, codec, and workload beside or immediately below the chart.
- Never derive compression ratio from final stored size alone.
- Label zero-chunk elision, metadata, and shard-index bytes independently.

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
- Executable search and result schema: [planner-design.md](planner-design.md)
