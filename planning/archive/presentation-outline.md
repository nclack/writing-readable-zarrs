# Writing readable Zarrs: presentation outline

Archived 2026-09-25. This is historical planning for the broader guide.
Its requirements and recommendations do not govern the current article;
see [archive status](README.md) and the [current plan](../article-outline.md).

## Communication job

The imaging data science team should leave able to select a downsampling
schedule, per-level chunk and shard shapes, chunks per shard, and Zarr writer
from a concrete workload—and explain the decision in terms of decode and
transfer amplification, the shard parallelism target, writer working memory,
process peak RSS, the required coarsest level, and storage-object count.

Target length: 25–30 minutes plus discussion. Use claim-led slide titles and one primary visual per slide. The visible presentation should call the streaming Zarr writer **Acquire Zarr**; reserve the temporary name **Chucky** for source notes.

## Narrative arc

The talk moves through one decision:

```text
required selections -> chunk shape -> resolution levels -> shard shape and chunks per shard -> Zarr writer behavior -> measured policy
```

## Slide 1 — A readable Zarr is designed from the reads backward

**Purpose:** Establish the problem and the central recommendation.

**Visible content:**

- Subtitle: “Chunk for access; shard for storage-object count and I/O grouping.”
- One array shown as the same logical data with two array layouts.

**Visual:** Simplified nested chunk and shard grid from Figure 1.

**Speaker point:** Format validity and metadata correctness do not guarantee efficient browsing, training, copying, or repair.

## Slide 2 — Layout decisions create a long-lived access tax

**Purpose:** Motivate making the decision during conversion.

**Visible content:** Four downstream consumers around one written dataset:

- Idetik / interactive 2D browsing
- Neuroglancer / multiscale 3D browsing
- Damacy — model sample loading
- whole-dataset operations — copy, list, index, validate

**Visual:** One source feeding four consumers, each highlighting a different
selection or whole-dataset operation.

**Evidence:** Idetik camera-driven chunk requests; Neuroglancer
visible/prefetch priorities; Damacy planning of storage read requests.

## Slide 3 — Chunks and shards solve different problems

**Purpose:** Establish vocabulary.

**Visible content:**

- Chunk = independently encoded and decoded inner block
- Shard = outer chunk stored as one value, containing inner chunks and an index
- Chunk shape controls irrelevant decode
- Shard shape and chunks per shard control storage-object count and exposed I/O work

**Visual:** Nested-grid explainer from Figure 1.

**Speaker point:** Treating a shard as merely “a bigger chunk” collapses two separate decisions.

## Slide 4 — Equal-byte chunks can have unequal read cost

**Purpose:** Break the habit of choosing chunks from raw chunk bytes alone.

**Visible content:** Two candidate chunks with equal raw chunk bytes,
intersected by the same XY viewport and XYZ model sample.

**Visual:** Small multiples from Figure 2 with useful and decoded voxels labeled.

**Evidence to add:** Measured transfer and decode amplification for representative traces.

## Slide 5 — Span only values consumers usually request together

**Purpose:** Make independently selected axes concrete.

**Visible content:**

- Usually start with `T=1`, `C=1`.
- Select `Z` depth and XY extent from plane and viewport traces and from each
  model architecture's fixed spatial/temporal sample shape.
- Treat variable sample shapes or channel encodings as separate workloads only
  when a production model uses them.
- Grow raw chunk bytes only while every policy limit still passes; the tie-break
  then prefers the passing chunk with the greatest raw chunk byte count.

**Visual:** Penalty from `C>1` or `T>1` chunks in Figure 3.

**Evidence:** Idetik notes that source chunks spanning multiple channels or time points cause duplicate fetch/decompression when mapped to its access model.

## Slide 6 — Cache helps only when later selections reuse the over-read

**Purpose:** Separate a layout's cold geometry from application-specific cache
benefit.

**Visible content:**

- A pan or playback trace with locality can reuse values fetched by an earlier selection.
- Dispersed fixed-shape model samples usually cannot.
- State the complete cache configuration: layers, capacity, initial state,
  admission, eviction, expiration, and prefetch.
- Constrain cold first display separately from steady-state viewer or model
  throughput.

**Visual:** Cache-reusing-viewer versus dispersed-model traces from Figure 4.

**Speaker point:** A cache does not reduce the first selection's amplification.
Credit over-read only when the ordered trace reuses it before eviction.

## Slide 7 — One chunk policy must survive every resolution level

**Purpose:** Show that the required coarsest level and chunk layout cannot be selected
independently.

**Visible content:**

- Declare the required coarsest level before choosing a pyramid builder.
- Begin with the same chunk shape at every level.
- Preferred general rule: apply the same per-axis stopping rule to every
  axis selected for downsampling.
- A declared coupled-axis schedule is also valid when its coarsest level passes.
- Recheck decode and transfer amplification, writer working memory, shard count,
  and storage-object count at every level.

**Visual:** The anisotropic pyramid comparison from Figure 5.

**Speaker point:** The number of automatically emitted levels is pyramid-builder behavior, not a portable
format promise. The next-generation Acquire Zarr rule stops each axis
separately; that per-axis stopping is the preferred planning default. Current
Acquire Zarr's coupled in-plane schedule remains a reasonable supported path
when it reaches the required coarsest level. Preserve a fixed chunk shape only while
the required coarsest level remains feasible.

## Slide 8 — Sharding preserves small chunks while reducing storage-object count

**Purpose:** Show the reason to shard.

**Visible content:** Many chunks grouped into fewer storage objects, with inner
chunks still independently addressable.

**Visual:** Before/after object inventory plus the key equation:

```text
shard_shape = chunk_shape * chunks_per_shard
shard_count = product(ceil(array_shape / shard_shape))
```

**Speaker point:** Sharding works this way only when the client can resolve the index and issue efficient inner-chunk range reads.

## Slide 9 — Range support decides whether a large shard is cheap or expensive

**Purpose:** Explain the client/store dependency.

**Visible content:** Three read paths:

1. cold shard-index cache + encoded chunk payload range;
2. cached shard index + encoded chunk payload range;
3. complete stored shard value fallback.

**Visual:** Figure 6, with transferred storage bytes under each path.

**Evidence:** Zarr v3 indexed sharding codec specification and Neuroglancer's
index/range-read path.

## Slide 10 — Distinct shards expose independently schedulable work

**Purpose:** Reframe concurrency.

**Visible content:**

- Coalesce adjacent reads within a shard.
- Interleave reads across shards.
- Bound active shards.

**Visual:** Scheduling lanes from Figure 7.

**Evidence:** Damacy coalesces nearby reads within one shard and interleaves across shards because same-file access may serialize on network filesystems.

## Slide 11 — Larger shards lower object cost but raise other risks

**Purpose:** Present the shard tradeoff.

**Visible content:** A measured Pareto frontier with:

- storage-object count and listing cost decreasing;
- retry and complete stored shard value read cost increasing;
- distinct shards touched by a parallel batch eventually decreasing.

**Visual:** Figure 8.

**Speaker point:** Start with a shard-count budget, then impose writer working
memory, range-read, maximum stored shard bytes, and shard parallelism limits.

## Slide 12 — The write pattern determines the writer working memory

**Purpose:** Connect tool choice to memory.

**Visible content:**

- **Single-pass streaming write:** queues + current chunk layer/band + pipeline state
- **Arbitrary-region write:** writer state for each active shard
- **Process peak RSS:** writer working memory + source and metadata layer
- Hypothesis: in a sharded TensorStore array, the active shard is the outer shard.

**Visual:** Comparison of writer working memory from Figure 9.

**Speaker point:** “TensorStore holds shards” is a useful hypothesis for our
workloads, not a universal implementation guarantee. Measure writer working
memory and process peak RSS against stored shard bytes, write order, transaction
scope, cache configuration, and active shards.

## Slide 13 — Select the Zarr writer from the data's arrival pattern

**Purpose:** Give the team a usable tool decision.

**Visible content:** Decision flow from Figure 10:

1. Single-pass streaming write? → **Acquire Zarr**
2. Concurrent arbitrary-region writes, transactions, or remote stores? → **TensorStore**
3. Direct Python/NumPy with bounded single-process irregular writes? → **zarr-python**
4. Diverse microscopy input and OME-Zarr/HCS semantics? → **iohub**, then record its Zarr writer

**Speaker point:** iohub is a high-level source and metadata layer; its low-level write behavior follows the selected Zarr writer. Tools may be composed rather than treated as exclusive alternatives.

Treat pyramid construction as a separate capability decision: use integrated
Acquire Zarr downsampling when the levels can be produced in the ordered
stream; use a batch builder such as ngff-zarr or ome-zarr-py when the required
schedule or per-level layout needs that flexibility. Verify the exact builder
version and emitted metadata.

## Slide 14 — Acquire Zarr trades random updates for a bounded stream

**Purpose:** Explain the specific streaming advantage.

**Visible content:** Source-order input passing through tiling, encoding, shard
assembly, and delivery.

**Visual:** Figure 11, the Acquire Zarr streaming pipeline.

**Speaker point:** The current implementation flushes a layer/band of chunks
incrementally and writes encoded chunks to shard sinks while retaining index
state. Process peak RSS still includes input queues, codec buffers, multiscale
state, and in-flight write operations.

## Slide 15 — Choose a multiscale layout with a staged constrained search

**Purpose:** Turn the principles into an algorithm.

**Visible content:**

```text
1. Declare workloads and the required coarsest level.
2. Enumerate chunks from required selections; reject excessive amplification.
3. Generate the downsampling schedule and recheck chunks at every level.
4. Group surviving chunks into shards; reject failures of maximum shard count, writer working memory, maximum stored shard bytes, and the shard parallelism target.
5. Reject builders that cannot emit the required schedule.
6. Benchmark the feasible frontier.
```

**Visual:** Staged decision flow from Figure 12.

**Evidence:** Adapted from the next-generation Acquire Zarr benchmark layout policy, which already decouples chunk and shard selection.

## Slide 16 — Select from a measured feasible frontier, not a universal layout

**Purpose:** Show how evidence selects a policy.

**Visible content:** Candidate layouts plotted by transfer amplification, object
storage-object count, writer working memory, and conversion throughput. Highlight feasible and
rejected candidates.

**Visual:** Measured Pareto plot from Figure 13.

**Speaker point:** The selected candidate should state which production
constraint made it preferable.

## Slide 17 — Every conversion should emit a layout decision record

**Purpose:** Close with an operational action.

**Visible content:** Compact checklist:

- required workloads and ordered traces;
- required coarsest level, downsampling schedule, and pyramid builder;
- chunks and shards by level;
- source and metadata layer, Zarr writer, version, and write order;
- decode, transfer, and write amplification;
- writer working memory, process peak RSS, and sustained conversion throughput;
- total shard count and verified range-read behavior.

**Visual:** Figure 14, a one-page layout decision record rather than a summary table of the
entire talk.

**Closing line:** “Design from the reads, constrain from the store, and verify through the Zarr writer.”

## Optional appendix slides

### A1 — Terms and equations

Raw chunk bytes, chunks per shard, shard count, transfer amplification, decode amplification, and write amplification.

### A2 — Tool comparison details

Expanded comparison of Acquire Zarr, TensorStore, zarr-python, and iohub, plus
ngff-zarr and ome-zarr-py as pyramid builders, including limitations and
supported workflows.

### A3 — Benchmark matrix

Stores × downsampling schedules × layouts × pyramid builders × Zarr writers ×
write orders × reader request concurrency × writer active-shard count × cache
configuration.

### A4 — Worked layout example

One real dataset carried from source trace through required resolution levels,
recommended per-level chunk and shard shapes, chunks per shard, and Zarr writer configuration.

### A5 — Source snapshots

Pinned Idetik and Neuroglancer commits, local Acquire Zarr/Damacy revisions, library versions, and documentation links.

## Presentation evidence requirements

- Replace illustrative numbers with measurements from `measurements.md` before presenting recommendations as policy.
- Put the dataset scope, store, client and tool versions, cache configuration,
  and repetition count in speaker notes for every benchmark chart.
- Use medians and tail distributions where latency matters; show variation, not only a single best run.
- Label modeled results as modeled and measured results as measured.
- Keep the main deck focused on decisions; move implementation detail and full matrices to the appendix or document.

## Cross-references

- Full narrative: [outline.md](outline.md)
- Figure specifications: [figure-outline.md](figure-outline.md)
- Measurement plan: [measurements.md](measurements.md)
- Executable planner design: [planner-design.md](../../code/planner-design.md)
- Canonical terms: [glossary.md](glossary.md)
