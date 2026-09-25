# Zarr layout planner design

Separate planner project. The objectives, tie-breaks, and proposed extensions
below describe this design; they do not set the recommendations or evidence
requirements for the [current article](../planning/article-outline.md).

Status: initial single-level executable design; multiscale extension specified
below but not yet implemented.

This design follows the project’s [writing and review criteria](../planning/archive/writing-guidelines.md) and [glossary](../planning/archive/glossary.md), and adapts the two-phase layout procedure used by the next-generation Acquire Zarr benchmark.

## Communication goal

Given an array, required resolution levels, read workloads, pyramid-builder and
Zarr writer models, storage behavior, and explicit policy limits, the planner
should:

1. generate a small, interpretable family of downsampling schedules, chunk
   shapes, and shard shapes;
2. reject every multiscale layout that violates a named limit at any required
   level;
3. select one layout using documented tie-breaks; and
4. explain every calculation, estimate, unsupported builder capability, and
   rejection.

It is a policy calculator, not an autonomous benchmark or a black-box optimizer.

## Outputs

The target command-line planner produces the following. The current executable
produces the single-level subset and labels that limitation in its report.

- the required and emitted downsampling schedule;
- the recommended chunk shape at every level;
- the recommended shard shape and chunks per shard at every level;
- raw chunk bytes, estimated encoded chunk payload bytes, and estimated stored
  shard bytes;
- logical chunk-grid-cell count and shard count, plus storage-object count when
  the deployment maps each shard value to one object;
- workload-specific p50, p95, and maximum decode amplification;
- workload-specific storage read request, transfer amplification, and distinct
  shards touched estimates;
- estimated writer working memory;
- the source of encoded-fraction and throughput values;
- all rejected candidates and their rejection reasons; and
- machine-readable JSON and a Markdown report when requested.

When no candidate layout passes, failure is the result. The planner reports
which limits made the policy infeasible.

## Three kinds of values

The planner labels values by provenance.

### Exact geometry

These values follow from array, selection, chunk, and shard shapes:

- intersected chunk coordinates;
- decoded chunk bytes;
- logical chunk-grid-cell count;
- shard count;
- chunks per shard;
- shards touched by a selection or batch; and
- in-bounds extents of edge chunks and edge shards.

### Modeled values

These use explicit assumptions:

- encoded chunk payload bytes and stored shard bytes from an encoded fraction;
- transferred storage bytes for range reads;
- shard-index bytes;
- storage read request count before implementation-specific coalescing; and
- writer working memory from fixed, per-chunk, and per-active-shard terms.

### Measured values

These may override model defaults for a particular chunk shape:

- encoded fraction; and
- encoding throughput.

Future measurements can add decoding throughput, conversion throughput, and
observations of writer working memory without changing the geometry model.

## Inputs

The TOML policy contains:

- array axes, shape, and element size;
- required coarsest level, allowed per-axis downsampling factors, and any
  declared axis coupling;
- generated selection workloads and their limits;
- candidate-generation profiles for chunk shape;
- candidate-generation profiles for chunks per shard;
- raw chunk byte search range;
- minimum acceptable encoding throughput;
- storage limits and range-read behavior;
- pyramid-builder capabilities and resource model;
- Zarr writer working memory model;
- optional measurements for exact chunk shapes; and
- deterministic search and tie-break settings.

The initial implementation generates repeatable, uniformly distributed
selection batches from a seed. A later trace adapter should load actual Idetik,
Neuroglancer, and Damacy selections into the same internal `SelectionBatch`
model. A modeling profile should normally declare one architecture's fixed
spatial and temporal sample shape, channel set, sample-origin distribution, and
batch construction. Variable-shape or variable-channel profiles are separate
inputs only when a real model exercises them.

## Feasible space

Let `C` be a chunk shape, `K` the tuple of chunks per shard, and `H = C * K` the
shard shape in array elements.

```text
feasible = {
  (C, K)
  where chunk_limits(C) pass
    and pair_limits(C, K) pass
}
```

Chunk limits include decode amplification, encoding throughput, and compression
tolerance. Layout limits include storage read requests, transferred storage
bytes, maximum shard and storage-object counts, minimum efficient stored-value
bytes, maximum stored shard bytes, the shard parallelism target, and writer
working memory.

No weighted sum determines feasibility.

## Aspect-guided candidate generation

Searching every integer shape is unnecessary and difficult to explain. An aspect profile generates one family of candidates from a byte-budget sweep.

Each profile has:

```text
base_shape[d]      preferred linear aspect
growth_weight[d]   how the dimension absorbs additional byte budget
```

For log-space step `k`:

```text
continuous_shape[d] = base_shape[d] * 2 ** (k * growth_weight[d])
```

The planner solves for `k` so the shape approaches the target element count, clamps it to the array, rounds to powers of two, and evaluates neighboring shapes formed by halving or doubling one participating dimension.

### Fixed aspect

Use equal positive growth weights. The base shape controls the linear aspect as the target byte budget changes.

### Pinned dimension

Use growth weight zero. A base value of one pins independently selected axes such as `T` and `C` to one.

### Directional growth

Use unequal growth weights when larger candidates should grow faster along selected dimensions. This matches the intent of the current Acquire Zarr benchmark bit-budget weights.

The existing `chunk_ratios` are growth weights in log space, not literal linear aspect ratios. Keeping base aspect and growth separate makes that distinction visible.

## Why selection aspect is a useful prior

For a rectangular selection with extent `r[d]`, a chunk with extent `c[d]`, and a uniformly random alignment:

```text
expected decode amplification ~= product(1 + c[d] / r[d])
```

At fixed chunk volume, the continuous approximation is minimized when `c[d] / r[d]` is constant. A chunk resembling the selection is therefore a useful candidate seed.

The approximation does not decide policy. The planner scores the generated integer shapes against the actual deterministic selections, including boundary and misaligned cases.

## Multiple workloads

One blended aspect can hide incompatible requirements. The planner generates candidates from separate profiles, such as:

- single-plane XY view selection;
- one model architecture's fixed-shape sample and batch;
- source-plane selection or acquisition order; and
- near-isotropic physical-region selection when required.

Every candidate must pass every required workload. Profile names remain attached to results so the recommendation is explainable.

## Multiscale planning

The application requirement is a required coarsest level, not “whatever
levels this pyramid builder happens to emit.” The policy therefore declares:

- the required maximum shape or minimum cumulative downsampling factor along each spatial
  axis;
- allowed per-axis downsampling factors;
- whether an axis may stop independently after reaching its target; and
- any level-specific application workloads.

For a base chunk candidate, generate a small family of schedules:

1. a fixed chunk shape with per-axis stopping as the
   default candidate;
2. a fixed chunk shape with coupled or aspect-preserving stopping, when
   requested or implemented by a preferred builder; and
3. a coarse-level chunk-shape change when fixed chunks cannot reach the
   required coarsest level or violate a per-level limit.

For each level `l`, the target design computes:

```text
array_shape[l]
chunk_shape[l]
chunk_grid[l]
chunks_per_shard[l]
shard_shape[l] = chunk_shape[l] * chunks_per_shard[l]
```

It then replays the workloads appropriate to that level and applies limits on
chunks, shards, storage-object count, writer working memory, and range reads.
The default prior is
the same chunk shape at every level because this gives readers a stable
decode unit and simplifies planning. It is a preference, not a hard rule: a
candidate fails if a fixed chunk shape stops the pyramid before the required
coarsest level or makes any required level infeasible.

The candidate space becomes:

```text
feasible = {
  (schedule, {chunk_shape[l]}, {chunks_per_shard[l]})
  where required_coarsest_level is reached
    and every required level passes its workload and resource limits
    and the selected builder can emit the schedule
}
```

Builder capability is a feasibility check, not a reason to weaken the
application requirement. A coupled-axis schedule passes when it reaches the
required coarsest level and every emitted level passes. Only when coupling or
early stopping prevents that outcome should the planner report the first
unsupported level and suggest one of three explicit remedies: stop axes
independently, change coarse-level chunk shapes, or use a different builder.

## Ordered workloads and caching

The initial planner does not model these yet. Its generated selection batches
are independent: chunks touched by one batch are not retained for the next. The
`index_cache` setting gives the shard-index cache only a cold or warm state. It
does not model an encoded-payload or decoded-chunk cache.

That omission affects applications differently:

- A visualization trace often has spatial locality while panning and temporal
  locality while playing frames. Chunk over-read becomes useful only if a later
  selection reuses the encoded payload or decoded chunk before eviction.
- A modeling sampler is often closer to independent random access, so its cache
  reuse may be much lower. Any locality created by batching, stratification, or
  repeated augmentation still needs to come from the real trace.
- Visualization needs a cold-selection constraint such as time to first
  displayed pixel. Modeling usually cares about samples per second, batch
  throughput, and batch latency instead.

A future trace model should preserve trace order and simulate separate bounded caches for:

1. shard indexes;
2. encoded chunk payloads; and
3. decoded chunks.

For each selection it should report both cold cost and incremental cost after
reuse. A visualization workload can then constrain time to first displayed
pixel and steady-state viewport or frame latency, while a modeling workload can
constrain batch latency and samples per second. The complete cache configuration
must remain an explicit input; “warm” is not sufficient.

## Chunk evaluation

For one selection, the chunk range on dimension `d` is:

```text
first[d] = floor(start[d] / chunk[d])
last[d]  = floor((start[d] + shape[d] - 1) / chunk[d])
```

For a batch, the planner forms the union of intersected chunk coordinates. Each
chunk is decoded once within that batch. Edge chunks contribute their complete
declared chunk shape and raw chunk bytes, not only their in-bounds extent.

```text
decode amplification = decoded chunk bytes / useful logical bytes
```

For each workload, the planner reports p50, p95, and maximum values.

Transfer amplification is evaluated with the shard:

```text
estimated useful encoded bytes = useful logical bytes * encoded fraction
transfer amplification = transferred storage bytes / estimated useful encoded bytes
```

This keeps the encoded-fraction effect separate from storage over-read. It is
modeled until real trace accounting supplies the numerator and a
content-specific encoded fraction.

A chunk passes when:

- every workload’s p95 decode amplification is within its limit;
- encoding throughput is at least the required rate; and
- its encoded fraction is within `compression_tolerance` of the best candidate value.

The initial storage read request estimate is evaluated with the shard because a
shard can add index requests or replace several chunk requests with one
complete stored-value read.

## Shard evaluation

For a passing chunk candidate:

```text
chunk_grid[d] = ceil(array_shape[d] / chunk_shape[d])
shard_count[d] = ceil(chunk_grid[d] / chunks_per_shard[d])
total_shards = product(shard_count[d])
```

Candidate generation begins at this lower bound on average stored shard bytes:

```text
estimated_encoded_chunk_payload_bytes =
    total_chunks * raw_chunk_bytes * encoded_fraction
lower_bound_shard_index_bytes = total_chunks * index_bytes_per_chunk

minimum_average_stored_shard_bytes = max(
    (estimated_encoded_chunk_payload_bytes + lower_bound_shard_index_bytes)
        / maximum_shard_count
        + checksum_bytes_per_shard,
    minimum_efficient_stored_value_bytes,
)
```

Candidate-generation profiles for chunks per shard generate candidates from
that lower bound through the maximum permitted stored shard bytes.

### Range-read model

With range reads:

- one encoded chunk payload request is modeled per selected inner chunk;
- a cold shard-index cache adds one request and shard-index bytes per touched
  shard; and
- only selected encoded chunk payload bytes and any cold shard-index bytes are
  transferred.

Without range reads:

- one storage read request is modeled per touched shard; and
- the complete estimated stored shard value is transferred.

This is a declared model, not a claim about every client. Measurements should eventually replace request-coalescing assumptions.

### Independent shards

For each selection batch, the planner counts distinct shards touched. A
workload may require a minimum p05 count, meaning at least 95% of its generated
batches expose that many distinct shards.

Exposed independent work does not guarantee observed concurrent storage
operations.

## Model of writer working memory

The initial common model is:

```text
writer working memory
  = fixed bytes
  + unfinished chunks * raw chunk bytes
  + active shards * (
      fixed bytes per active shard
      + shard payload fraction retained * estimated stored shard bytes
    )
```

For Acquire Zarr, the retained shard-payload fraction should normally be zero and unfinished chunks represent the layer/band and pipeline state.

For TensorStore or zarr-python experiments, a nonzero retained fraction can
model the hypothesis that writer working memory grows with stored shard bytes.
The configuration must label it as modeled until replaced by measurement.

## Selection objective

All constraints are applied first. Passing layouts are ordered lexicographically:

1. greatest raw chunk byte count;
2. lowest worst decode-limit utilization;
3. lowest worst utilization of the storage read request limit;
4. smallest average stored shard bytes;
5. greatest minimum p05 distinct shards touched; and
6. deterministic shape and profile ordering.

Maximizing raw chunk bytes is appropriate only because decode and request limits
are hard policy boundaries. It spends the permitted access budget to reduce
per-chunk overhead. The result report exposes the margins so this objective can
be reconsidered.

The shard tie-break chooses the smallest average stored shard bytes satisfying
maximum shard count and minimum efficient stored-value byte requirements. This
differs from the benchmark objective that grows shards to the object-store part
limit.

## Relationship to the Acquire Zarr benchmark solver

Reuse:

- separate chunk and shard candidate phases;
- byte-budget sweeps;
- pinned dimensions;
- deterministic rounding and tie-breaks;
- explicit hard-versus-soft diagnostics; and
- object-store part and byte limits when they are added.

Change:

- distinguish base aspect from dimensional growth weights;
- filter chunks using reader workloads;
- retain every passing chunk until shard feasibility is known;
- model shard memory for each Zarr writer;
- distinguish active shards from distinct shards touched by reads;
- plan a declared downsampling schedule and evaluate every required level; and
- choose the smallest passing shard rather than the largest allowed shard.

The generalized problem is nested rather than fully separable. Decode
amplification is chunk-only, but shard count, transferred storage bytes,
storage read requests, and arbitrary-region writer working memory depend on
both chunk and shard choices.

## Command-line interface

The planner is a PEP 723 script using Pydantic, Typer, and Rich.

```sh
uv run layout_planner.py plan example-policy.toml
uv run layout_planner.py plan example-policy.toml --json report.json
uv run layout_planner.py plan example-policy.toml --markdown report.md
uv run layout_planner.py validate example-policy.toml
uv run layout_planner.py schema
```

The script uses standard-library TOML parsing. Pydantic validates all dimensionality, positivity, bounds, and cross-field requirements before search.

## Interactive explorer

The explorer is a second PEP 723 script using NiceGUI and Plotly:

```sh
uv run layout_explorer.py
uv run layout_explorer.py another-policy.toml
```

High-dimensional layouts are shown through coordinated projections:

1. raw chunk bytes versus worst normalized decode amplification;
2. average stored shard bytes versus total shard count;
3. normalized per-axis chunk and shard extents;
4. workload metric tables; and
5. explicit pass/fail reasons.

The multiscale extension should add a level strip showing cumulative downsampling factor,
array shape, chunk grid, shard count, and the point at which each axis stops
being downsampled. A side-by-side anisotropic example can compare builder-selected stopping,
per-axis stopping, and coarse-level chunk adaptation without drawing
the full high-dimensional array.

This is more interpretable than drawing a five-dimensional array. A later view
can add a selectable two-axis chunk and shard grid projection for teaching
spatial alignment.

## Files

```text
planner-design.md       design and assumptions
layout_planner.py       PEP 723 core and Rich CLI
layout_explorer.py      PEP 723 NiceGUI/Plotly app
example-policy.toml     executable example
```

## Initial limitations

- Workloads are generated rectangular selections, not imported real traces.
- Generated selections or batches are independent rather than ordered spatial
  or temporal traces.
- Encoded fraction is a global model unless overridden for an exact chunk
  shape.
- Encoded-payload and decoded-chunk caches are not modeled; the shard-index
  cache is only cold or warm.
- Latency, scheduling, and time to first displayed pixel are not modeled.
- Storage read requests for adjacent ranges are not coalesced.
- The executable does not yet generate or jointly evaluate resolution levels;
  the `Multiscale planning` section is the required next extension.
- Pyramid-builder capability, downsampling correctness, rereads, intermediate
  storage, and time until a level is readable are not yet modeled.
- Object-store part limits are not yet modeled.
- End-to-end conversion throughput is a confirmation measurement; the initial
  planner limits only encoding throughput.
- The equation for writer working memory is a hypothesis, not a measurement.
- Batches that exceed `maximum_enumerated_chunks_per_sample` are rejected rather
  than approximated.

These limitations must remain visible in every report.
