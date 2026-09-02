# Zarr layout planner design

Status: initial single-level executable design; multiscale extension specified
below but not yet implemented.

This design follows the project’s [writing and review criteria](writing-guidelines.md) and adapts the two-phase layout procedure used by the next-generation Acquire Zarr benchmark.

## Communication goal

Given an array, required resolution levels, read workloads, pyramid-builder and
write-engine models, storage behavior, and explicit policy limits, the planner
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

- the required and emitted resolution-level schedule;
- the recommended chunk shape at every level;
- the recommended shard shape in chunks at every level;
- raw and estimated encoded sizes;
- chunk, shard, and storage-object counts;
- workload-specific p50, p95, and maximum decode amplification;
- workload-specific request, transfer, and distinct-shard estimates;
- estimated writer memory;
- the source of compression and throughput values;
- all rejected candidates and their rejection reasons; and
- machine-readable JSON and a Markdown report when requested.

When no pair passes, failure is the result. The planner reports which limits made the policy infeasible.

## Three kinds of values

The planner labels values by provenance.

### Exact geometry

These values follow from array, selection, chunk, and shard shapes:

- intersected chunk coordinates;
- decoded bytes;
- chunk count;
- shard count;
- chunks per shard;
- shards touched by a selection or batch; and
- edge-chunk and edge-shard extents.

### Modeled values

These use explicit assumptions:

- encoded chunk and shard bytes from an encoded fraction;
- range-read transfer bytes;
- shard-index bytes;
- physical request count before implementation-specific coalescing; and
- writer memory from fixed, per-chunk, and per-active-shard terms.

### Measured values

These may override model defaults for a particular chunk shape:

- encoded fraction; and
- encoding throughput.

Future measurements can add decoder throughput, write throughput, and writer-memory observations without changing the geometry model.

## Inputs

The TOML policy contains:

- array axes, shape, and element size;
- required coarsest resolution, allowed per-axis downsampling factors, and any
  declared axis coupling;
- generated selection workloads and their limits;
- chunk aspect profiles;
- shard aspect profiles;
- chunk-byte search range;
- minimum acceptable encoding throughput;
- storage limits and range-read behavior;
- pyramid-builder capabilities and working-set model;
- write-engine memory model;
- optional per-chunk measurements; and
- deterministic search and tie-break settings.

The initial implementation generates repeatable uniformly distributed selections from a seed. A later trace adapter should load actual Idetik, Neuroglancer, and Damacy selections into the same internal `SelectionBatch` model. A modeling profile should normally declare one architecture's fixed spatial and temporal sample shape, channel set, sample-origin distribution, and batch construction. Variable-shape or variable-channel profiles are separate inputs only when a real model exercises them.

## Feasible space

Let `C` be a chunk shape and `S` a shard shape measured in chunks.

```text
feasible = {
  (C, S)
  where chunk_limits(C) pass
    and pair_limits(C, S) pass
}
```

Chunk limits include decode amplification, encoding throughput, and compression tolerance. Pair limits include requests, transferred bytes, object count, efficient object size, shard-size maximum, read-shard parallelism, and writer memory.

No weighted sum determines feasibility.

## Aspect-guided candidate generation

Searching every integer shape is unnecessary and difficult to explain. An aspect profile generates one family of candidates from a byte-budget sweep.

Each profile has:

```text
base_shape[d]      preferred linear aspect
growth_weight[d]   how the dimension absorbs additional byte budget
```

For scale `k`:

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

- single-plane XY viewport;
- one model architecture's fixed-shape sample and batch;
- source-plane or acquisition order; and
- physically isotropic access when required.

Every candidate must pass every required workload. Profile names remain attached to results so the recommendation is explainable.

## Multiscale planning

The application requirement is a coarsest usable resolution, not “whatever
levels this writer happens to emit.” The policy therefore declares:

- the required maximum shape or minimum cumulative scale along each spatial
  axis;
- allowed per-axis reduction factors;
- whether an axis may retire independently after reaching its target; and
- any level-specific application workloads.

For a base chunk candidate, generate a small family of schedules:

1. fixed nominal chunks with category-independent, per-axis retirement as the
   default candidate;
2. fixed nominal chunks with coupled or aspect-preserving stopping, when
   requested or implemented by a preferred builder; and
3. a coarse-level chunk-shape change when fixed chunks cannot reach the
   required resolution or violate a per-level limit.

For each level `l`, the target design computes:

```text
array_shape[l]
chunk_shape[l]
chunk_grid[l]
shard_shape_in_chunks[l]
```

It then replays the workloads appropriate to that level and applies chunk,
shard, object-count, memory, and range-read constraints. The default prior is
the same nominal chunk shape at every level because this gives readers a stable
decode unit and simplifies planning. It is a preference, not a hard rule: a
candidate fails if fixed chunks stop the pyramid before the required coarsest
resolution or make any required level infeasible.

The candidate space becomes:

```text
feasible = {
  (schedule, {chunk[l]}, {shard[l]})
  where required_coarsest_resolution is reached
    and every required level passes its workload and resource limits
    and the selected builder can emit the schedule
}
```

Builder capability is a feasibility check, not a reason to weaken the
application requirement. A coupled-axis schedule passes when it reaches the
required coarsest view and every emitted level passes. Only when coupling or
early stopping prevents that outcome should the planner report the first
unsupported level and suggest one of three explicit remedies: retire axes
independently, change coarse-level chunks, or use a different builder.

## Ordered workloads and caching

The initial planner does not model these yet. Its generated samples are independent: chunks touched by one sample are not retained for the next. The `index_cache` setting is only an all-cold or all-warm shard-index assumption. It is not a stateful payload or decoded-chunk cache.

That omission affects applications differently:

- A visualization trace often has spatial coherence while panning and temporal coherence while playing frames. Chunk over-read may become useful on a later query if the relevant encoded payload or decoded chunk remains cached.
- A modeling sampler is often closer to independent random access, so its cache reuse may be much lower. Any locality created by batching, stratification, or repeated augmentation still needs to come from the real trace.
- Visualization needs a cold-start constraint such as time to first displayed pixel. Modeling usually cares about sample or batch throughput and completion latency instead.

A future trace model should preserve query order and simulate separate bounded caches for:

1. shard indexes;
2. encoded chunk payloads; and
3. decoded chunks.

For each query it should report both cold cost and incremental cost after reuse. A visualization workload can then constrain time to first displayed pixel and steady-state viewport or frame latency, while a modeling workload can constrain batch latency and samples per second. Cache capacity and policy must remain explicit inputs; “warm” is not a sufficient policy description.

## Chunk evaluation

For one selection, the chunk range on dimension `d` is:

```text
first[d] = floor(start[d] / chunk[d])
last[d]  = floor((start[d] + shape[d] - 1) / chunk[d])
```

For a batch, the planner forms the union of intersected chunk coordinates. Each chunk is decoded once within that batch.

```text
decode amplification = decoded bytes / useful bytes
```

For each workload, the planner reports p50, p95, and maximum values.

Transfer amplification is evaluated with the shard:

```text
estimated useful encoded bytes = useful logical bytes * encoded fraction
transfer amplification = transferred payload and index bytes / estimated useful encoded bytes
```

This keeps compression benefit separate from storage over-fetch. It is modeled until real trace accounting supplies the numerator and a content-specific encoded fraction.

A chunk passes when:

- every workload’s p95 decode amplification is within its limit;
- encoding throughput is at least the required rate; and
- its encoded fraction is within `compression_tolerance` of the best candidate value.

The initial physical-request estimate is evaluated with the shard because a shard can add index requests or replace several chunk requests with a complete-object read.

## Shard evaluation

For a chosen chunk:

```text
chunk_grid[d] = ceil(array_shape[d] / chunk_shape[d])
shard_count[d] = ceil(chunk_grid[d] / shard_shape_in_chunks[d])
total_shards = product(shard_count[d])
```

The minimum candidate shard size is the larger of:

```text
estimated_dataset_bytes / maximum_shards
minimum_efficient_object_bytes
```

Shard aspect profiles generate candidates from that lower bound through the maximum permitted shard size.

### Range-read model

With range reads:

- one payload request is modeled per selected inner chunk;
- a cold index adds one request and index bytes per touched shard; and
- only selected inner-chunk payload bytes are transferred.

Without range reads:

- one request is modeled per touched shard; and
- the complete estimated shard payload and index are transferred.

This is a declared model, not a claim about every client. Measurements should eventually replace request-coalescing assumptions.

### Independent shards

For each selection batch, the planner counts distinct touched shards. A workload may require a minimum p05 distinct-shard count, meaning at least 95% of its generated batches expose that much independent work.

Exposed independent work does not guarantee physical parallelism.

## Writer-memory model

The initial common model is:

```text
writer memory
  = fixed bytes
  + unfinished chunks * raw chunk bytes
  + active shards * (
      fixed bytes per active shard
      + shard payload fraction retained * estimated shard bytes
    )
```

For Acquire Zarr, the retained shard-payload fraction should normally be zero and unfinished chunks represent the layer/band and pipeline state.

For TensorStore or zarr-python experiments, a nonzero retained fraction can model a shard-scale hypothesis. The configuration must label it as modeled until replaced by measurement.

## Selection objective

All constraints are applied first. Passing pairs are ordered lexicographically:

1. largest raw chunk bytes;
2. lowest worst decode-limit utilization;
3. lowest worst request-limit utilization;
4. smallest average stored shard bytes;
5. greatest minimum distinct-shard count; and
6. deterministic shape and profile ordering.

Maximizing chunk bytes is appropriate only because decode and request limits are hard policy boundaries. It spends the permitted access budget to reduce per-chunk overhead. The result report exposes the margins so this objective can be reconsidered.

The shard tie-break chooses the smallest shard satisfying the object-count and storage-efficiency requirements. This differs from the benchmark objective that grows shards to the backend part limit.

## Relationship to the Acquire Zarr benchmark solver

Reuse:

- separate chunk and shard candidate phases;
- byte-budget sweeps;
- pinned dimensions;
- deterministic rounding and tie-breaks;
- explicit hard-versus-soft diagnostics; and
- backend part and byte limits when they are added.

Change:

- distinguish base aspect from dimensional growth weights;
- filter chunks using reader workloads;
- retain every passing chunk until shard feasibility is known;
- model writer-dependent shard memory;
- distinguish open write shards from distinct read shards;
- plan a declared downsampling schedule and evaluate every required level; and
- choose the smallest passing shard rather than the largest allowed shard.

The generalized problem is nested rather than fully separable. Decode amplification is chunk-only, but object count, transfer, request count, and random-write memory depend on both chunk and shard choices.

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

1. chunk bytes versus worst normalized decode amplification;
2. average shard bytes versus total shard count;
3. normalized per-axis chunk and shard extents;
4. workload metric tables; and
5. explicit pass/fail reasons.

The multiscale extension should add a level strip showing cumulative scale,
array shape, nominal chunk grid, shard count, and the point at which each axis
retires. A side-by-side anisotropic example can compare automatic early stop,
independent axis retirement, and coarse-level chunk adaptation without drawing
the full high-dimensional array.

This is more interpretable than drawing a five-dimensional array. A later view can add a selectable two-axis chunk/shard grid projection for teaching spatial alignment.

## Files

```text
planner-design.md       design and assumptions
layout_planner.py       PEP 723 core and Rich CLI
layout_explorer.py      PEP 723 NiceGUI/Plotly app
example-policy.toml     executable example
```

## Initial limitations

- Workloads are generated rectangular selections, not imported real traces.
- Workload samples are independent rather than ordered spatial or temporal traces.
- Compression is a global model unless overridden for an exact chunk shape.
- Payload and decoded-chunk caches are not modeled; shard indexes are only all-cold or all-warm.
- Latency, scheduling, and time to first displayed pixel are not modeled.
- Range requests are not coalesced.
- The executable does not yet generate or jointly evaluate multiscale levels;
  the `Multiscale planning` section is the required next extension.
- Pyramid-builder capability, downsampling correctness, rereads, intermediate
  storage, and time until a level is readable are not yet modeled.
- Object-store part limits are not yet modeled.
- End-to-end writer throughput is a confirmation measurement; the initial planner gates only encoding throughput.
- The writer-memory equation is a hypothesis, not a measurement.
- Very large batches that intersect millions of chunks are rejected by a safety limit rather than approximated.

These limitations must remain visible in every report.
