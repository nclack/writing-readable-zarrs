# Writing readable Zarrs: document outline

This outline follows the project’s [writing and review criteria](writing-guidelines.md).

## Audience and outcome

This document is for imaging data scientists who convert diverse external data into our internal OME-Zarr standard.

After reading it, a team member should be able to:

- describe the reads and writes a dataset must support;
- choose a downsampling schedule and physical layout from those requirements;
- select a conversion and write path;
- predict the effects on data transfer, decompression, memory, throughput, and object count; and
- record enough evidence for another person to reproduce the decision.

The document should teach one running example from beginning to end. Alternative examples should appear only when they change a decision.

## 1. Start with one selection

### Running example

Begin with a five-dimensional image array ordered `T, C, Z, Y, X`:

- `T`: time;
- `C`: channel;
- `Z`: depth; and
- `Y, X`: the image plane.

An interactive viewer asks for one channel, one time point, one plane, and a rectangular viewport. Call the requested array region a **selection**. The bytes belonging to that region are the **useful bytes** for that selection.

Use two viewer cases throughout the document:

- a cold first view; and
- an ordered pan, zoom, or time-playback sequence.

Define **time to first displayed pixel** as the elapsed time from issuing the cold view request until the application can render the first correct visible image data. It is a visualization requirement, not a general read-throughput metric.

Then introduce a modeling workload from the same dataset. Begin with one
**model sample shape**: a fixed extent in space and time with a declared channel
set. Replay that shape at the positions and in the batches produced by the
sampler:

- one fixed-shape model sample; and
- a batch of spatially dispersed samples with the same shape.

This is the default modeling profile, not a claim that every architecture
requires one shape. Token-based vision models can accept varying spatial
extents, and channel encodings can vary, but each adds a separate model
contract. Add a variable-shape or variable-channel workload only when a
required model actually uses it. Damacy's constant-shape queries are the
initial implementation precedent; the need to generalize them did not arise in
its target workloads.

A **required workload** is either an ordered sequence of operations or a representative distribution of independent operations that the layout must support. Preserve order when earlier queries can affect later queries through caching or prefetch. Include boundary and misaligned cases.

### Question to carry through the document

For each cold selection:

> How much data must the system locate, transfer, and decompress to return the useful bytes?

For an ordered sequence:

> Which work is reused before it is evicted, and how does that change the first result versus later results?

Do not recommend a layout yet. First show how Zarr turns a selection into work.

## 2. Define the physical layout

Introduce these terms with one nested-grid figure.

### Chunk

A **chunk** is the smallest array region that can be decoded independently. Its **chunk shape** gives its extent along each array axis.

If a selection touches any part of a chunk, the reader normally transfers and decodes that complete chunk payload. A chunk that contains data outside the selection therefore creates extra work.

### Storage object

A **storage object** is one file on a filesystem or one object in an object store. Whole-dataset operations such as listing, copying, indexing, validating, and deleting have a cost per storage object.

### Shard

A **shard** is one storage object containing multiple chunks and an index that maps each contained chunk to its byte offset and length. The **shard shape in chunks** gives the number of chunks grouped along each array axis.

### Range read

A **range read** retrieves only a specified byte interval from a storage object.

With an indexed shard and working range reads, a reader can retrieve one contained chunk without transferring the complete shard. Without working range reads, the reader may need to fetch the whole shard.

### Resolution level and downsampling schedule

A **resolution level** is one array in a multiscale pyramid. Each coarser level
contains fewer spatial samples representing the same field of view. A
**downsampling schedule** states which axes are reduced, by what cumulative
factor, and when an axis stops being reduced.

Each resolution level has its own array shape, chunk shape, and shard packing.
The **nominal chunk shape** is the shape recorded for the level; an edge or a
whole level smaller than that shape may contain fewer real values.

### Relationship

Establish two consequences:

1. Chunk shape determines the minimum region that must be decoded.
2. Sharding can reduce storage-object count without changing that decode unit, but only when the required clients and stores can read the indexed chunk ranges efficiently.
3. A multiscale layout is a sequence of chunk/shard decisions; a good base-level
   shape does not guarantee a useful cold view at a coarser level.

A shard cannot repair a chunk that already contains irrelevant channels, time points, or spatial extent.

## 3. Account for a cold read before crediting cache

Trace the running viewport through four steps:

1. Find every chunk intersecting the selection.
2. Locate those chunks, using a shard index when applicable.
3. Read the required storage objects or byte ranges.
4. Decompress the complete intersecting chunks and return the selected region.

### 3.1 Keep the byte stages separate

For a cold selection or batch, record:

1. **useful logical bytes**: the uncompressed values requested by the application;
2. **decoded logical bytes**: the complete chunks that must be decompressed;
3. **encoded payload bytes**: the stored codec output for those chunks;
4. **transferred storage bytes**: payload, shard-index, and any whole-object over-fetch; and
5. **requests per workload sample**: the physical reads for one replayed selection or batch.

Do not report an unqualified “read amplification.” It can conceal several different mechanisms.

| Quantity | Calculation | What it isolates |
|---|---|---|
| **Decode amplification** | decoded logical bytes / useful logical bytes | Chunk/selection or chunk/model-sample mismatch |
| **Encoded fraction** | encoded payload bytes / decoded logical bytes | Codec and image-content effect |
| **Storage over-read** | transferred storage bytes / encoded payload bytes | Shard, range-read, and index effect |
| **Wire fraction** | transferred storage bytes / useful logical bytes | End-to-end bytes moved relative to useful uncompressed data |

Compression is not itself amplification. Encoded fraction is normally less than one and reduces bytes moved, but it does not undo the CPU or memory required to decode irrelevant values in an intersected chunk.

The planner’s **transfer amplification** combines the two layout effects while factoring compression out:

```text
estimated useful encoded bytes = useful logical bytes * encoded fraction
transfer amplification = transferred storage bytes / estimated useful encoded bytes

transfer amplification ~= decode amplification * storage over-read
wire fraction ~= encoded fraction * transfer amplification
```

Use measured bytes for final reporting. Record fill-value elision, index bytes, metadata, and protocol overhead separately rather than forcing them into a codec claim.

**Key figure:** a horizontal cold-read ledger that carries one useful selection through intersected chunks, codec output, shard/range reads, and transferred bytes. Label the multiplier introduced at each boundary.

### 3.2 Requests and latency are separate costs

Two layouts can move the same bytes with different request counts and latency. Report requests independently. For visualization, also measure the critical path through metadata/index lookup, first payload read, first decode, and rendering; total bytes alone do not predict time to first displayed pixel.

A client without range reads may transfer a complete shard but decode only one contained chunk. A decoded-chunk cache may avoid both transfer and decode. These are different paths and must not share one number.

### 3.3 Equal-byte example

Compare chunk shapes with the same raw byte count:

- one channel and one time point with a broad, shallow spatial tile;
- one channel and one time point with a deeper `Z` extent; and
- several channels or time points in a smaller spatial tile.

Replay the running selections. Show that equal raw bytes do not imply equal requests, transferred bytes, decoded bytes, or time to first displayed pixel.

### 3.4 Query coherence determines whether over-read is reused

Define **query coherence** as successive workload operations touching some of the same chunks—or data fetched speculatively becoming useful—before that data is evicted from cache.

Keep three cache effects distinct:

- a **shard-index cache** avoids repeated index requests and index bytes;
- an **encoded-payload cache** avoids repeated storage reads but may still require decoding; and
- a **decoded-chunk cache** avoids both repeated transfer and repeated decoding at a higher memory cost.

Cache capacity, initial state, admission/eviction policy, and query order are required inputs. Do not call a workload simply “warm.” Credit over-read as useful prefetch only when the ordered trace reuses those bytes before eviction.

Apply this distinction to the running workloads:

| Workload | Expected order and reuse | Required view of performance |
|---|---|---|
| Spatial visualization | Overlapping viewports during pan; revisits during zoom | Cold time to first displayed pixel plus steady-state viewport latency and bytes under a bounded cache |
| Temporal visualization | Repeated spatial footprint across nearby time points; possible reuse of deliberately packed or prefetched time data | First-frame latency plus steady-state frame latency; include random time jumps as a control |
| Modeling | Usually one fixed space/time sample shape and declared channel set at randomized positions, with little cross-batch reuse | Batch latency and samples/second using the actual sampler; treat variable shapes/channels as separate profiles and cache benefit as measured, not assumed |

Caching does not change a layout’s cold-read geometry. A larger chunk may look expensive for the first query but cheaper across a coherent sequence; it must satisfy both the cold requirement and the bounded-cache sequence requirement.

**Key figure:** two short traces using the same layout. A pan or playback trace reuses cached chunks before eviction; a random model-sampling trace repeatedly misses. Show cold first-result cost, later incremental cost, and cache occupancy separately.

### Evidence beside the mechanism

- Idetik selects chunks from the current view and maps source chunks into an internal access model. Source chunks spanning several channels or time points can cause repeated transfer and decompression for independent selections: [Idetik image loader](https://github.com/chanzuckerberg/idetik/blob/93ca5f2a40d8a1e22a5d619d16ae84d9ac580414/src/data/ome_zarr/image_loader.ts#L46-L97).
- Neuroglancer prioritizes visible and nearby chunks under download and memory limits: [Neuroglancer chunk manager](https://github.com/google/neuroglancer/blob/122edd90b366f50d8c695e366bb7c88f55de3759/src/chunk_manager/README.md).

Use those implementations to explain the mechanism. Use our own ordered visualization traces and actual modeling sampler traces to set policy limits.

## 4. Derive the chunk recommendation

### 4.1 Axes selected independently

#### Mechanism

If a chunk spans four channels and a reader selects one channel, all four channels must be decoded. The same is true for time points or any other axis selected independently. Sequential time playback is a possible exception only when the extra time points are reused soon enough to outweigh the cold-read penalty.

#### Rule

> If every required operation selects one value independently along an axis, set the chunk extent on that axis to one. If an ordered trace may reuse neighboring values, include singleton and packed candidates, then require the packed candidate to pass both cold and bounded-cache sequence limits.

For channels, begin with `C=1` when channels are toggled independently. For time, begin with `T=1`, but include `T>1` when sequential playback is required. Any packed candidate must demonstrate lower sequence cost without violating first-frame or random-access limits.

This replaces the ambiguous recommendation to use “low-dimensional” chunks.

### 4.2 Spatial shape

#### Mechanism

Small spatial chunks reduce irrelevant decompression but can increase requests. Large spatial chunks reduce request count but decode more unused data near selection boundaries.

#### Required policy inputs

Before filtering chunks, set:

- maximum cold p95 decode and transfer amplification for each workload;
- maximum p95 requests per workload sample;
- for visualization, maximum cold time to first displayed pixel and steady-state viewport/frame latency;
- for modeling, minimum samples/second and maximum batch latency using the actual sampler;
- cache tier, byte capacity, initial state, and admission/eviction policy for every cache-aware trace;
- minimum required encoding throughput, defined as the maximum source rate times a stated safety factor; and
- maximum memory allowed for unfinished chunks and reader caches.

Values not yet supported by measurements remain explicit unresolved policy parameters; they are not replaced with words such as “small” or “reasonable.”

#### Rule

> Replay cold operations and ordered cache-aware traces against each candidate shape. Reject a shape when either its cold requirement or its application-specific sequence requirement fails.

Use real query order and positions, including edges, misalignment, spatial pans, temporal playback and jumps, and the modeling sampler. Do not average visualization and modeling into one blended workload.

For the initial modeling workload, replay one fixed sample shape at the actual
origin distribution. If several required architectures use different fixed
shapes, keep them as separate workload profiles. Do not enlarge the baseline
search space for hypothetical variable-size token sequences or variable-channel
encodings; add those only with a concrete consumer and acceptance limit.

The current executable planner implements cold or independent sample geometry plus an all-cold/all-warm shard-index assumption. It does not yet enforce ordered-cache or time-to-first-pixel limits. Treat those as external acceptance gates until the trace simulator described in [planner-design.md](planner-design.md) is implemented.

### 4.3 Compression and encoding

Encoded fraction was defined in the cold-read byte ledger. Lower is better. Avoid the directionally ambiguous term “compression ratio.”

For every surviving chunk shape:

- measure encoded fraction on representative image content;
- measure encoding throughput;
- report raw bytes submitted to compression, encoded output bytes, skipped fill-value chunks, metadata/index bytes, and final stored bytes separately; and
- reject candidates that cannot sustain the required source rate with the chosen headroom.

#### Do not select the chunk yet

Set a `compression_tolerance` relative to the best measured encoded fraction and retain every chunk candidate within it that passes the access, throughput, and memory limits. A chunk that looks best in isolation may require an infeasible shard packing, so final selection waits until both chunk and shard constraints have been evaluated.

This replaces the undefined “compression knee” with a reproducible filter.

### 4.4 Carry the chunk policy through the resolution levels

#### Mechanism

Viewers usually request a similarly sized viewport in level-local pixels after
choosing a resolution level. Keeping the same nominal chunk shape across levels
therefore tends to keep request geometry predictable, makes layouts easier to
inspect, and avoids making coarse levels a separate tuning problem.

That preference interacts with pyramid depth. As an array is downsampled, an
axis eventually fits in one nominal chunk. A writer may then:

- stop the whole pyramid;
- stop that axis while continuing to reduce longer axes;
- stop a declared group of axes while other axes continue; or
- continue creating levels whose array extent is smaller than the nominal
  chunk.

All four are valid layout strategies when their coordinate transforms and
data are correct. They produce different level counts and coarse-level access
behavior for strongly anisotropic array shapes. This is a writer choice, not a
Zarr requirement.

#### Implementation cases to explain

Use the two Acquire Zarr implementations as a concrete contrast:

- The current implementation preserves nominal chunk shape, reduces `X` and
  `Y` as a coupled pair until the shorter in-plane dimension reaches its chunk
  scale, and handles spatial `Z` separately. A short `X` or `Y` can therefore
  stop reduction of the longer in-plane axis.
- The next-generation implementation also preserves nominal chunk shape. By
  default it retires each configured axis independently when that axis reaches
  one chunk, allowing longer axes to continue; an aspect-preserving option
  stops when the first configured axis reaches one chunk.

Prefer the next-generation rule as the general planning default: every axis
named in the downsampling schedule follows the same independent-retirement
rule, without special behavior inferred from whether it is called spatial,
temporal, or in-plane. This is a policy preference, not a conformance rule.
Current Acquire Zarr remains the recommended forward-only producer, and its
coupled `X`/`Y` schedule is a reasonable supported strategy whenever the
emitted levels reach the declared coarsest view and pass the per-level limits.

Record these as implementation facts from
`~/src/acquire-zarr/src/streaming/downsampler.cpp` and
`~/src/LANG/c/chucky/src/lod/lod_plan.c`. In reader-facing text, call the latter
the next-generation Acquire Zarr implementation.

Batch conversion tools provide other choices. `ngff-zarr` builds an out-of-core
multiscale task graph with explicit scale factors and output chunks:
[multiscale example](https://github.com/fideus-labs/ngff-zarr/blob/main/docs/python.md#generate-multiscales).
Current `ome-zarr-py` can also generate a pyramid, accept per-axis scale-factor
dictionaries, and accept storage options per level:
[writer API](https://github.com/ome/ome-zarr-py/blob/master/ome_zarr/writer.py).

#### Rule

> Set the required coarsest resolution and downsampling schedule before
> accepting a writer's automatically chosen levels. Begin candidate generation
> with one category-independent rule that retires each scheduled axis
> separately when it reaches its target. A producer MAY instead use declared
> coupled axis groups, including current Acquire Zarr's in-plane strategy, when
> the emitted pyramid reaches the required coarsest view. Both strategies pass
> the layout policy under the same outcome constraints. Begin with the same
> nominal chunk shape at every level. For each level, replay the required viewer
> selections and recompute chunk count, shard packing, object count, and stored
> bytes. Preserve the common chunk shape only while the required pyramid depth
> and per-level access limits still pass.

If a fixed shape prevents the required coarse representation, choose explicitly
among:

1. retiring short axes while continuing to downsample long axes;
2. changing chunk shape at the affected coarse levels; or
3. using a different integrated or post-hoc pyramid builder.

No change is needed when a coupled-axis builder already satisfies the declared
overview and per-level requirements.

Do not silently accept fewer resolution levels because one implementation
stopped at a chunk boundary. Conversely, do not force additional levels that no
required viewer uses. Record the downsampling method, odd-edge behavior, axis
factors, and coordinate transforms; image correctness is a prerequisite even
when filter selection is not the focus of the layout policy.

#### Required evidence

- level shapes, physical scales, nominal chunk shapes, and shard packings;
- the reason each axis is reduced or retired at each transition;
- cold thumbnail and viewport latency at the levels viewers actually choose;
- pyramid-build throughput, peak memory, and source bytes reread; and
- correctness controls for odd dimensions, intensity data, and labels.

### Chunk recommendation

> Keep independently selected axes separate. Credit packed or larger chunks for reuse only when an ordered trace demonstrates it under a declared cache budget. Start with one nominal chunk shape across resolution levels, but do not let that preference prevent the required pyramid depth. Retain every shape and level schedule that meets cold access, sequence latency, memory, throughput, and compression limits; select one only after evaluating its possible shard packings.

At this point the reader should be able to predict why the candidate set begins with `T=1` and `C=1`, and why a temporal playback trace may justify adding `T>1` candidates.

## 5. Explain why chunks are grouped into shards

### 5.1 Object count

If every chunk is a separate storage object, small chunks can produce an impractically large object count.

Set a maximum shard count, `N_max`, from measured limits for the payload objects below. For each operation, find the largest count that meets its time or cost limit; `N_max` is the lowest of those counts. Account for metadata objects separately.

- listing or inventory;
- metadata lookup or validation;
- complete-dataset copy;
- indexing or manifest construction; and
- deletion or repair.

For estimated final payload size `D`, the shard-count target imposes a lower bound:

```text
minimum average stored shard size ~= D / N_max
```

This relationship explains why small decode units do not require small storage objects.

### 5.2 Range-read condition

An indexed shard preserves chunk-level transfer only when every required reader/storage combination can fetch the index and the selected chunk ranges efficiently.

Compare:

1. cold index plus chunk range;
2. cached index plus chunk range; and
3. complete-shard fetch.

Do not treat a cached shard index as a cached chunk. Index caching removes lookup work; encoded-payload and decoded-chunk caches determine whether payload transfer and decompression repeat.

Neuroglancer’s Zarr sharding path reads and caches the index, then reads contained chunk ranges: [indexed-shard decoder](https://github.com/google/neuroglancer/blob/122edd90b366f50d8c695e366bb7c88f55de3759/src/datasource/zarr/codec/sharding_indexed/decode.ts#L50-L176). The storage format is defined by the [Zarr sharding-indexed codec specification](https://zarr-specs.readthedocs.io/en/latest/v3/codecs/sharding-indexed/index.html).

### 5.3 Independent work

A batch that touches several distinct shards exposes independent storage operations. This permits parallel I/O but does not guarantee it; the client, protocol, network, and storage system may still serialize work.

Define the **target shard parallelism** as the smallest number of distinct shards after which adding more improves throughput by less than a stated `throughput_tolerance` on the target system.

Damacy combines adjacent reads within one shard and distributes reads across distinct shards. Use its counters for physical reads and distinct shards to measure this behavior: `~/src/LANG/c/damacy/src/planner/coalesce.h` and `damacy.h`.

### 5.4 Retry and full-fetch bounds

Set a maximum stored shard size to the lowest limit imposed by:

- the most data the system may retry after a failed write or copy;
- the most data a required no-range client may fetch for one chunk;
- transport or upload limits; and
- the time allowed to repair or replace one damaged shard.

Do not recommend a shard shape until writer memory has also been explained.

## 6. Explain write order, memory, and tool roles

### 6.1 Two write patterns

A **write engine** is the library that creates or updates the Zarr storage.

A **forward-only write** produces every output region once, in the order required by the write engine. After a region is flushed, later input never modifies it.

An **arbitrary-region write** may target any output region, arrive out of order, or revisit a previously written region.

An **active shard** is a shard with buffered state or I/O currently in progress. Active-shard count—not merely task count—can determine writer memory and storage concurrency.

### 6.2 Why write order changes memory

#### Forward-only streaming

Acquire Zarr can retain a bounded set of unfinished chunks, then write encoded chunks into their destination objects while retaining shard-index and open-output state. It need not retain the complete finished shard payload.

Peak memory still includes:

- input queues;
- unfinished uncompressed chunks;
- compression buffers;
- pyramid-generation state; and
- shard-index and open-output state for active shards.

Implementation evidence: `~/src/acquire-zarr/src/streaming/acquire.zarr.cpp`, `array.cpp`, `chunk.cpp`, and `shard.cpp`.

#### Arbitrary-region writes

For sharded Zarr, an arbitrary-region write engine may need to retain, read, merge, or rewrite state associated with each active shard. Memory and bytes reread or rewritten therefore depend on shard size, active-shard count, write order, cache settings, and implementation.

### 6.3 Separate source handling, pyramid construction, and the write engine

Make three decisions. A single library may fill more than one role, but record
the role and behavior separately.

#### Source and metadata layer

Use **iohub** when the conversion needs its microscopy readers or its construction of OME-NGFF/HCS hierarchy and metadata. Record the exact iohub version and the write engine it uses. iohub adds source-decoding and metadata state; it is not a separate chunk/shard memory model.

#### Pyramid builder

Use integrated Acquire Zarr downsampling when a forward-only source should
produce resolution levels without rereading the completed base array. Verify
the implementation's axis-retirement and level-stop rules, but do not reject
its coupled in-plane schedule merely because the general planning default is
category-independent.

Use a batch pyramid builder such as `ngff-zarr` or `ome-zarr-py` when the source
is already randomly readable or when explicit per-axis factors or per-level
chunks require that flexibility. Include Dask/task-graph state, intermediate
storage, input rereads, and the selected low-level Zarr writer in memory and
throughput measurements.

#### Write engine

| Write engine | Choose it when | Main condition to verify |
|---|---|---|
| **Acquire Zarr** | Output is forward-only | Required ordering and pyramid outcome are achievable; sustained rate and unfinished-chunk memory pass |
| **TensorStore** | Output requires asynchronous or concurrent arbitrary-region writes, remote storage, or several updates that must commit together | Memory and bytes reread or rewritten pass for the chosen shard size, active-shard limit, cache, and write order |
| **zarr-python** | Writes occur in one process through NumPy-style indexed assignment, without the TensorStore requirements above | Peak memory, overlap coordination, and bytes reread or rewritten for partial shard updates pass |

For arbitrary-region writes, schedule work shard-by-shard when possible and cap active shards from measured memory. Random scheduling is a control case, not the default.

Treat the statement “TensorStore retains shards” as a scaling hypothesis for our workloads, not as a universal guarantee that every shard is always held completely uncompressed.

Supporting references:

- [TensorStore chunk-layout model](https://google.github.io/tensorstore/schema.html)
- [TensorStore Zarr v3 driver](https://google.github.io/tensorstore/driver/zarr3/index.html)
- [TensorStore write API](https://google.github.io/tensorstore/python/api/tensorstore.TensorStore.write.html)
- [TensorStore sharded-write guidance](https://google.github.io/tensorstore/kvstore/zarr3_sharding_indexed/index.html)
- [zarr-python array guide](https://zarr.readthedocs.io/en/latest/user-guide/arrays/)
- [zarr-python sharding codec implementation](https://github.com/zarr-developers/zarr-python/blob/main/src/zarr/codecs/sharding.py)
- [iohub conversion API](https://czbiohub-sf.github.io/iohub/stable/api/converter/)

## 7. Derive the shard recommendation

### Required policy inputs

For each surviving chunk shape and the selected write engine, record:

- estimated stored payload size, `D`;
- maximum shard count, `N_max`;
- target shard parallelism;
- maximum stored shard size for retry or complete-shard fetch;
- maximum process memory;
- minimum write throughput; and
- range-read capability of every required reader/storage combination.

### Selection procedure

1. Compute the minimum average stored shard size implied by `D / N_max`.
2. Raise that lower bound if storage measurements show a larger minimum efficient object size: the smallest size after which larger objects improve throughput by less than `throughput_tolerance`.
3. Enumerate shard shapes in whole chunks at or above the lower bound.
4. Reject a candidate when any required reader without efficient range reads would fetch more than the complete-shard limit.
5. Reject a candidate when representative parallel batches expose fewer distinct shards than the target shard parallelism.
6. Reject a candidate when the selected write engine exceeds memory or throughput limits at the required active-shard count.
7. Reject a candidate whose maximum observed stored shard size exceeds the retry or transport limit.
8. Retain every passing chunk/shard pair for the final deterministic selection.

### Shard recommendation

> For every passing chunk, form the smallest shards that meet the shard-count target and measured minimum efficient object size while preserving required range reads, shard parallelism, writer memory, throughput, and retry bounds.

Do not make shards larger merely because the format permits it. A larger shard needs evidence that it reduces whole-dataset operation time or increases throughput.

If no candidate passes, the requirements conflict. Reconsider the object-count target, storage system, write engine, or required client behavior rather than hiding the conflict in a weighted score.

## 8. State the complete recommendation

The reader now has enough mechanism to understand the headline:

> **Choose chunks for cold and ordered application workloads, then carry that policy through the required resolution levels. Credit cache reuse only under a declared budget. Group those chunks into the smallest shards that meet the shard-count target without violating access, parallelism, memory, or retry limits. Choose the pyramid builder and write engine from the required level schedule and write order, then verify their memory.**

### End-to-end procedure

1. Record independent selections, fixed-shape model profiles, ordered query traces, application latency/throughput limits, cache configuration, write pattern, source rate, target storage, and required clients.
2. Choose whether iohub is needed for source interpretation or OME-NGFF/HCS construction.
3. Set the required coarsest resolution and per-axis downsampling schedule, then choose an integrated or post-hoc pyramid builder.
4. Choose the write engine from forward-only versus arbitrary-region writes.
5. Generate chunk shapes using independent axes, cold and cache-aware trace replay, access limits, encoding throughput, and the compression filter.
6. Apply each candidate across the proposed levels; reject schedules that stop too early or fail a per-level access, correctness, memory, or throughput limit.
7. Set the shard-count, range-read, parallelism, memory, throughput, and retry limits.
8. Generate and filter per-level shard packings for every surviving chunk/schedule pair.
9. Select one passing layout lexicographically: largest raw chunk, lowest worst decode-limit use, lowest worst request-limit use, smallest average stored shard, then greatest minimum distinct-shard count.
10. Benchmark the complete conversion plus cold, coherent, and random-access read paths on the target storage.
11. Record the decision, measured evidence, unresolved assumptions, and conditions requiring re-evaluation.

Use hard rejection limits and explicit tie-breaks. Do not combine unrelated costs into an unexplained weighted score.

## 9. Complete the running example

Apply the procedure to one real dataset. Populate every unresolved value from [measurements.md](measurements.md).

### Required selections

- cold one-channel, one-time-point XY viewport;
- ordered spatial pan and temporal-playback traces, including a random time jump;
- one fixed space/time model sample with a declared channel set; and
- dispersed batches of that same shape generated by the actual sampler.

### Write pattern

- source planes arrive in a known order;
- every output value is written once; and
- multiscale levels are produced incrementally with a stated axis schedule and
  fixed nominal chunk shape where feasible.

### Derivation

1. Show why independently toggled channels imply `C=1`; compare `T=1` with packed-time candidates for playback.
2. Show the cold byte ledger and factor chunk mismatch, encoded fraction, and storage over-read.
3. Replay spatial and temporal viewer traces with declared caches, then replay the modeling sampler without assuming reuse.
4. Reject candidates that fail cold time to first displayed pixel, steady-state viewer latency, model throughput/latency, or amplification limits.
5. Apply the encoding-tolerance filter and retain every passing chunk.
6. Generate the level schedule; show where axes retire and verify the coarsest required view is present.
7. Replay the cold viewer selections at the actual level selected for first display and thumbnails.
8. Set `N_max` from measured whole-dataset operations and compute the shard-size lower bound by level.
9. Verify range reads, target shard parallelism, retry size, and Acquire Zarr memory including its downsampling state.
10. State the selected layout and identify the exact observation supporting each decision.

### Alternative A: out-of-order derived image

Add this example only to change the write-engine decision:

- workers produce arbitrary spatial patches;
- compare shard-major and random scheduling;
- choose TensorStore or zarr-python from required concurrency, memory, and bytes reread or rewritten; and
- retain the same chunk and shard reasoning.

### Alternative B: external microscopy conversion

Add this example only to introduce the source/metadata layer:

- iohub interprets the source and constructs the required hierarchy and metadata;
- the pinned iohub version determines which write engines can be used directly; and
- an ordered adapter into Acquire Zarr is considered only when the output can satisfy its forward-only contract.

## 10. Require a layout decision record

Every converted dataset or conversion recipe records:

- array shape, axes, dtype, and multiscale levels;
- required coarsest resolution, per-axis downsampling factors, method, odd-edge
  behavior, axis-retirement or coupling rule, and pyramid builder;
- independent selections, ordered query traces, and write pattern;
- fixed model sample shapes, declared channel sets, origin distributions, and
  batch construction;
- chunk shape by level;
- shard shape in chunks by level;
- expected and observed chunk, shard, and total storage-object counts;
- useful, decoded, encoded-payload, index, and transferred bytes;
- encoded fraction, storage over-read, wire fraction, transfer amplification, and decode amplification by workload;
- cache tier, byte capacity, initial state, admission/eviction policy, hit/miss accounting, and trace order;
- cold time to first displayed pixel, steady-state viewer latency, model batch latency, and samples/second;
- client and storage range-read behavior;
- source/metadata layer, write engine, versions, and relevant settings;
- active-shard limit, peak memory, and sustained throughput;
- shard-size distribution and retry/full-fetch bound;
- policy limits, tie-breaks, and rejection reasons; and
- conditions that require the decision to be repeated.

The decision record is the final recommendation, not merely a benchmark table.

## Appendix A. Compact equations

Introduce symbols only after the concepts are familiar.

For array shape `n_i`, chunk shape `c_i`, shard shape in chunks `s_i`, and element size `b`:

```text
raw_chunk_bytes = b * product(c_i)
chunk_count = product(ceil(n_i / c_i))
chunks_per_shard = product(s_i)
shard_count = product(ceil(n_i / (c_i * s_i)))
```

For measured reads:

```text
decode_amplification = decoded_bytes / useful_bytes
encoded_fraction = encoded_payload_bytes / decoded_bytes
storage_over_read = transferred_storage_bytes / encoded_payload_bytes
estimated_useful_encoded_bytes = useful_bytes * encoded_fraction
transfer_amplification = transferred_storage_bytes / estimated_useful_encoded_bytes
wire_fraction = transferred_storage_bytes / useful_bytes
requests_per_workload_sample = physical_reads / replayed_selections_or_batches
```

For ordered traces, also report byte-weighted payload-cache and decoded-cache hit/miss fractions. Compute observed transferred and decoded bytes from the actual misses; do not apply one undifferentiated “warm-cache” multiplier to the cold-read equations.

For updates:

```text
write_amplification = all_payload_bytes_written / final_encoded_bytes_changed
```

Define edge handling and denominators precisely in the measurement method.

## Appendix B. Evidence inventory

### Local implementation evidence

- Acquire Zarr streaming API and settings: `~/src/acquire-zarr/README.md`
- Acquire Zarr memory and flush behavior: `~/src/acquire-zarr/src/streaming/`
- Current Acquire Zarr pyramid schedule: `~/src/acquire-zarr/src/streaming/downsampler.cpp`
- Next-generation Acquire Zarr pyramid schedule: `~/src/LANG/c/chucky/src/lod/lod_plan.c`
- Next-generation Acquire Zarr layout search: `~/src/LANG/c/chucky/docs/bench-layout-policy.md`
- Damacy read combination, shard distribution, and counters: `~/src/LANG/c/damacy/src/planner/coalesce.h` and `damacy.h`

### Naming note

Use **Acquire Zarr** in reader-facing text. **Chucky** is only the temporary name of its next-generation backbone and appears only when identifying source provenance.

### Supporting plans

- [Presentation outline](presentation-outline.md)
- [Figure outline](figure-outline.md)
- [Measurement plan](measurements.md)
- [Writing and review criteria](writing-guidelines.md)
- [Executable planner design](planner-design.md)
