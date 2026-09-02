# Writing readable Zarrs: presentation outline

## Communication job

The imaging data science team should leave able to select a downsampling
schedule, per-level chunk shape, shard packing, and writer from a concrete
workload—and explain the decision in terms of amplification, concurrency,
memory, pyramid depth, and object count.

Target length: 25–30 minutes plus discussion. Use claim-led slide titles and one primary visual per slide. The visible presentation should call the streaming writer **Acquire Zarr**; reserve the temporary name **Chucky** for source notes.

## Narrative arc

The talk moves through one decision:

```text
consumer selections -> chunk geometry -> resolution levels -> shard geometry -> writer behavior -> measured policy
```

## Slide 1 — A readable Zarr is designed from the reads backward

**Purpose:** Establish the problem and the central recommendation.

**Visible content:**

- Subtitle: “Chunk for access; shard for concurrency and operational scale.”
- One array shown as the same logical data with two physical layouts.

**Visual:** Simplified nested chunk/shard grid from Figure 1.

**Speaker point:** Format validity and metadata correctness do not guarantee efficient browsing, training, copying, or repair.

## Slide 2 — Layout decisions create a long-lived access tax

**Purpose:** Motivate making the decision during conversion.

**Visible content:** Four downstream consumers around one written dataset:

- Idetik / interactive 2D browsing
- Neuroglancer / multiscale 3D browsing
- Katamari / patch and sample loading
- dataset operations / copy, list, index, validate

**Visual:** One source feeding four consumers, each highlighting a different region or operation.

**Evidence:** Idetik camera-driven chunk requests; Neuroglancer visible/prefetch priorities; Damacy physical-read planning.

## Slide 3 — Chunks and shards solve different problems

**Purpose:** Establish vocabulary.

**Visible content:**

- Chunk = independently decoded region
- Shard = storage object containing many chunks
- Chunk shape controls irrelevant decode
- Shard shape controls object count and independent I/O

**Visual:** Nested-grid explainer from Figure 1.

**Speaker point:** Treating shard size as merely “a bigger chunk” collapses two separate decisions.

## Slide 4 — Equal-byte chunks can have unequal read cost

**Purpose:** Break the habit of choosing chunks from byte size alone.

**Visible content:** Two candidate chunks with equal raw bytes, intersected by the same XY viewport and XYZ patch.

**Visual:** Small multiples from Figure 2 with useful and decoded voxels labeled.

**Evidence to add:** Measured wire and decode amplification for representative traces.

## Slide 5 — Pack only what consumers usually request together

**Purpose:** Make low-dimensional chunking concrete.

**Visible content:**

- Usually start with `T=1`, `C=1`.
- Select `Z` depth and XY tile from plane and viewport traces and from each
  model architecture's fixed spatial/temporal sample shape.
- Treat variable sample shapes or channel encodings as separate workloads only
  when a production model uses them.
- Increase bytes only until compression/request benefits plateau.

**Visual:** `C`/`T` packing penalty from Figure 3.

**Evidence:** Idetik notes that source chunks spanning multiple channels or time points cause duplicate fetch/decompression when mapped to its access model.

## Slide 6 — Cache helps only when later queries reuse the over-read

**Purpose:** Separate a layout's cold geometry from application-specific cache
benefit.

**Visible content:**

- A coherent pan or playback can reuse values fetched by an earlier query.
- Dispersed fixed-shape model samples usually cannot.
- State cache tier, capacity, initial state, and eviction policy.
- Constrain cold first display separately from steady-state viewer or model
  throughput.

**Visual:** Coherent-viewer versus dispersed-model traces from Figure 4.

**Speaker point:** A cache does not reduce the first query's amplification.
Credit over-read only when the ordered trace reuses it before eviction.

## Slide 7 — One chunk policy must survive every resolution level

**Purpose:** Show that pyramid depth and chunk layout cannot be selected
independently.

**Visible content:**

- Declare the coarsest useful resolution before choosing a builder.
- Begin with the same nominal chunk shape at every level.
- Preferred general rule: apply the same independent-retirement rule to every
  axis selected for downsampling.
- A declared coupled-axis schedule is also valid when its coarsest level passes.
- Recheck amplification, memory, shards, and object count at every level.

**Visual:** The anisotropic pyramid comparison from Figure 5.

**Speaker point:** Automatic level count is writer behavior, not a portable
format promise. The next-generation Acquire Zarr rule is category-independent
and retires axes separately; that is the preferred planning default. Current
Acquire Zarr's coupled in-plane schedule remains a reasonable supported path
when it reaches the declared overview. Preserve fixed nominal chunks only while
the required depth remains feasible.

## Slide 8 — Sharding preserves small chunks while reducing object count

**Purpose:** Show the reason to shard.

**Visible content:** Many small chunks grouped into fewer large objects, with inner chunks still independently addressable.

**Visual:** Before/after object inventory plus the key equation:

```text
shard_count = product(ceil(array_shape / (chunk_shape * chunks_per_shard_axis)))
```

**Speaker point:** Sharding works this way only when the client can resolve the index and issue efficient inner-chunk range reads.

## Slide 9 — Range support decides whether a large shard is cheap or expensive

**Purpose:** Explain the client/store dependency.

**Visible content:** Three read paths:

1. cold index + chunk range;
2. cached index + chunk range;
3. full-shard fallback.

**Visual:** Figure 6, with transferred bytes under each path.

**Evidence:** Zarr sharding-indexed specification and Neuroglancer's index/range-read path.

## Slide 10 — Useful concurrency comes from distinct shards

**Purpose:** Reframe concurrency.

**Visible content:**

- Coalesce adjacent reads within a shard.
- Interleave reads across shards.
- Bound concurrent write shards.

**Visual:** Scheduling lanes from Figure 7.

**Evidence:** Damacy coalesces nearby reads within one shard and interleaves across shards because same-file access may serialize on network filesystems.

## Slide 11 — Larger shards lower object cost but raise other risks

**Purpose:** Present the shard tradeoff.

**Visible content:** A curve or frontier with:

- object count and listing cost decreasing;
- retry/full-shard-read cost increasing;
- usable concurrency eventually decreasing.

**Visual:** Figure 8.

**Speaker point:** Start with a shard-count budget, then impose memory, range, retry, and concurrency bounds.

## Slide 12 — The write model determines what must remain resident

**Purpose:** Connect tool choice to memory.

**Visible content:**

- **Ordered stream:** queues + current chunk layer/band + pipeline state
- **Random access:** state for each active write unit + source buffers
- In a sharded TensorStore array, the efficient write unit is the outer shard.

**Visual:** Writer-residency comparison from Figure 9.

**Speaker point:** “TensorStore holds shards” is a useful hypothesis for our workloads, not a universal implementation guarantee. Measure memory against shard size, update order, transaction/cache settings, and active shards.

## Slide 13 — Select the writer from the data's arrival pattern

**Purpose:** Give the team a usable tool decision.

**Visible content:** Decision flow from Figure 10:

1. Ordered and write-once? → **Acquire Zarr**
2. Arbitrary regions, concurrency, transactions, remote stores? → **TensorStore**
3. Direct Python/NumPy and modest irregular writes? → **zarr-python**
4. Diverse microscopy input and OME-NGFF/HCS semantics? → **iohub**, then record its backend

**Speaker point:** iohub is a high-level source and metadata layer; its low-level write behavior follows the selected backend. Tools may be composed rather than treated as exclusive alternatives.

Treat pyramid construction as a separate capability decision: use integrated
Acquire Zarr downsampling when the levels can be produced in the ordered
stream; use a batch builder such as ngff-zarr or ome-zarr-py when the required
schedule or per-level layout needs that flexibility. Verify the exact builder
version and emitted metadata.

## Slide 14 — Acquire Zarr trades random updates for a bounded stream

**Purpose:** Explain the specific streaming advantage.

**Visible content:** An ordered input passing through tiling, compression, shard aggregation, and delivery.

**Visual:** Figure 11, the Acquire Zarr streaming pipeline.

**Speaker point:** The current implementation flushes a layer/band of chunks incrementally and writes compressed chunks to shard sinks while retaining index state. Peak memory still includes input queues, codec buffers, multiscale state, and concurrency.

## Slide 15 — Choose a multiscale layout with a staged constrained search

**Purpose:** Turn the principles into an algorithm.

**Visible content:**

```text
1. Declare workloads and the coarsest useful resolution.
2. Enumerate chunks from access geometry; reject excessive amplification.
3. Generate the level schedule and recheck chunks at every level.
4. Pack surviving chunks into shards; reject count, memory, retry, and concurrency failures.
5. Reject builders that cannot emit the required schedule.
6. Benchmark the feasible frontier.
```

**Visual:** Staged decision flow from Figure 12.

**Evidence:** Adapted from the next-generation Acquire Zarr benchmark layout policy, which already decouples chunk and shard selection.

## Slide 16 — The recommendation is a frontier, not a magic tuple

**Purpose:** Show how evidence selects a policy.

**Visible content:** Candidate layouts plotted by read amplification, object count, peak writer memory, and throughput. Highlight feasible and rejected candidates.

**Visual:** Measured Pareto plot from Figure 13.

**Speaker point:** The chosen point should state which production constraint made it preferable.

## Slide 17 — Every conversion should emit a layout report

**Purpose:** Close with an operational action.

**Visible content:** Compact checklist:

- workload traces and weights;
- required coarsest resolution, per-axis schedule, and pyramid builder;
- chunks and shards by level;
- writer, backend, version, and write order;
- read/decode/write amplification;
- peak memory and sustained ingest rate;
- total shard count and range-read assumptions.

**Visual:** Figure 14, a one-page report card rather than a summary table of the
entire talk.

**Closing line:** “Design from the reads, constrain from the store, and verify through the writer.”

## Optional appendix slides

### A1 — Terms and equations

Raw chunk bytes, chunks per shard, shard count, wire amplification, decode amplification, and write amplification.

### A2 — Tool comparison details

Expanded comparison of Acquire Zarr, TensorStore, zarr-python, and iohub, plus
ngff-zarr and ome-zarr-py as pyramid builders, including limitations and
supported workflows.

### A3 — Benchmark matrix

Stores × level schedules × layouts × pyramid builders × writers × write orders
× concurrency × cache state.

### A4 — Worked layout example

One real dataset carried from source trace through required resolution levels,
recommended per-level chunks, shard packing, and writer configuration.

### A5 — Source snapshots

Pinned Idetik and Neuroglancer commits, local Acquire Zarr/Damacy revisions, library versions, and documentation links.

## Presentation evidence requirements

- Replace illustrative numbers with measurements from `measurements.md` before presenting recommendations as policy.
- Put the dataset, store, client/tool version, cache state, and repetition count in speaker notes for every benchmark chart.
- Use medians and tail distributions where latency matters; show variation, not only a single best run.
- Label modeled results as modeled and measured results as measured.
- Keep the main deck focused on decisions; move implementation detail and full matrices to the appendix or document.

## Cross-references

- Full narrative: [outline.md](outline.md)
- Figure specifications: [figure-outline.md](figure-outline.md)
- Measurement plan: [measurements.md](measurements.md)
- Executable planner design: [planner-design.md](planner-design.md)
