# Writing readable Zarrs: document outline

Archived 2026-09-25. This is historical planning for the broader guide.
Its requirements and recommendations do not govern the current article;
see [archive status](README.md) and the [current plan](../article-outline.md).

Status, 2026-09-24: retained as the earlier broad guide. The current audience,
article scope, and writing plan are in [article-outline.md](../article-outline.md).
Earlier figure, talk, and planner cross-references still refer to this outline.

This outline follows the project’s [writing and review criteria](writing-guidelines.md) and the canonical terms in the [glossary](glossary.md).

## Audience and outcome

This document is for imaging data scientists who convert diverse external data into our internal OME-Zarr standard.

After reading it, a team member should be able to:

- describe the reads and writes a dataset must support;
- choose a downsampling schedule and multiscale layout from those requirements;
- select a conversion path;
- predict the effects on data transfer, decompression, memory, throughput, and
  storage-object count; and
- record enough evidence for another person to reproduce the decision.

The document should teach one running example from beginning to end. Alternative examples should appear only when they change a decision.

## 1. Start with one selection

### Running example

Begin with a five-dimensional image array ordered `T, C, Z, Y, X`:

- `T`: time;
- `C`: channel;
- `Z`: depth; and
- `Y, X`: the image plane.

An interactive viewer asks for one channel, one time point, one plane, and a
rectangular viewport. Call the requested array region a **selection**. The
uncompressed values belonging to that region are the **useful logical bytes**
for that selection, shortened to useful bytes after this definition.

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
required model actually uses it. Damacy's constant-shape selections are the
initial implementation precedent; the need to generalize them did not arise in
its target workloads.

A **required workload** is an ordered trace or a representative distribution of
independent selections or writes that the layout must support, together with
its policy criteria and cache configuration. Preserve order when earlier
selections can affect later selections through caching or prefetch. Include
boundary and misaligned cases.

### Question to carry through the document

For each cold selection:

> How much data must the system locate, transfer, and decompress to return the useful bytes?

For an ordered sequence:

> Which work is reused before it is evicted, and how does that change the first result versus later results?

Do not recommend a layout yet. First show how Zarr turns a selection into work.

## 2. Define the array and multiscale layout

Introduce these terms with one nested-grid figure.

### Chunk

A **chunk** is the independently encoded and decoded array block in the
reader-facing model. With Zarr v3 indexed sharding, this is the inner chunk; the
outer chunk-grid cell is the shard. Its **chunk shape** gives its declared
extent along each array axis.

If a selection touches any part of a chunk, the reader must decode the complete
chunk unless it is already in a decoded-chunk cache. The client may also need to
transfer the chunk's complete encoded payload. Values outside the selection
therefore create extra work.

### Storage object

A Zarr **store** maps keys to byte values. One stored value commonly maps to one
file on a filesystem or one object in an object store; call that deployment
unit a **storage object**. Whole-dataset operations such as listing, copying,
indexing, validating, and deleting can have a cost per key or storage object.

### Shard

A **shard** is an outer Zarr chunk-grid cell containing independently encoded
inner chunks and an index that maps each possible inner chunk to its byte offset
and length. **Shard shape** is its extent in array elements. **Chunks per shard**
is the per-axis quotient of shard shape divided by inner chunk shape.

### Range read

A **range read** retrieves only a specified byte interval from a stored value.

With an indexed shard and efficient client-and-store range reads, a reader can
retrieve one contained chunk without transferring the complete stored shard
value. Otherwise, the reader may need to fetch the complete stored shard value.

### Resolution level and downsampling schedule

A **resolution level** is one array in a multiscale pyramid. Each coarser level
contains fewer spatial samples representing the same field of view. A
**downsampling schedule** states which axes are reduced, by what cumulative
factor, and when an axis stops being reduced.

Each resolution level has its own array shape, chunk shape, shard shape, and
chunks per shard. A regular-grid **edge chunk** retains the declared chunk shape
but has a smaller **in-bounds chunk extent** where its grid cell overhangs the
logical array.

### Relationship

Establish three consequences:

1. Chunk shape determines the minimum region that must be decoded.
2. Sharding can reduce storage-object count without changing that decode unit, but only when the required clients and stores can read the indexed chunk ranges efficiently.
3. A multiscale layout contains chunk and shard decisions at every level; a
   good base-level shape does not guarantee a useful cold view at a coarser
   level.

A shard cannot repair a chunk that already contains irrelevant channels, time points, or spatial extent.

## 3. Account for a cold read before crediting cache

Trace the running viewport through four steps:

1. Find every chunk intersecting the selection.
2. Locate those chunks, using a shard index when applicable.
3. Issue the required storage read requests for complete values or byte ranges.
4. Decode the complete intersecting chunks and return the selected region.

### 3.1 Keep the byte stages separate

For a cold selection or batch, record:

1. **useful logical bytes**: the uncompressed values requested by the application;
2. **decoded chunk bytes**: the complete decoded chunk representations required;
3. **encoded chunk payload bytes**: the final encoded representations of those chunks;
4. **transferred storage bytes**: encoded chunk payload bytes, shard-index
   bytes, coalescing gaps, and any whole-value over-read; and
5. the number of **storage read requests** issued.

Do not report an unqualified “read amplification.” It can conceal several different mechanisms.

| Quantity | Calculation | What it isolates |
|---|---|---|
| **Decode amplification** | decoded chunk bytes / useful logical bytes | Chunk shape versus selection or model sample shape |
| **Encoded fraction** | encoded chunk payload bytes / decoded chunk bytes | Codec and image-content effect |
| **Storage over-read** | transferred storage bytes / encoded chunk payload bytes | Shard, range-read, and index effect |

Compression is not itself amplification. Encoded fraction is normally less than one and reduces bytes moved, but it does not undo the CPU or memory required to decode irrelevant values in an intersected chunk.

The planner’s **transfer amplification** combines the two layout effects while factoring compression out:

```text
estimated useful encoded bytes = useful logical bytes * encoded fraction
transfer amplification = transferred storage bytes / estimated useful encoded bytes

transfer amplification = decode amplification * storage over-read
    when every term uses the same measured chunk set
```

Use measured bytes for final reporting. Record omitted fill chunks, logical bytes
represented by those chunks, shard-index bytes, metadata, and protocol overhead
separately rather than forcing them into a codec claim.

**Key figure:** a horizontal cold-read ledger that carries one useful selection
through intersected chunks, codec output, shard/range reads, and transferred
storage bytes. Label the multiplier introduced at each boundary.

### 3.2 Requests and latency are separate costs

Two layouts can move the same bytes with different request counts and latency.
Report storage read requests independently. For visualization, also measure the
critical path through metadata and shard-index lookup, first payload read,
first decode, and rendering; total bytes alone do not predict time to first
displayed pixel.

A client without range reads may transfer a complete stored shard value but
decode only one contained chunk. A decoded-chunk cache may avoid both transfer
and decode. These are different paths and must not share one number.

### 3.3 Equal-byte example

Compare chunk shapes with the same raw chunk bytes:

- one channel and one time point with a broad, shallow spatial selection;
- one channel and one time point with a deeper `Z` extent; and
- several channels or time points in a smaller spatial selection.

Replay the running selections. Show that equal raw chunk bytes do not imply
equal storage read requests, transferred storage bytes, decoded chunk bytes, or
time to first displayed pixel.

### 3.4 Locality helps only when data are reused before eviction

An ordered trace has useful **spatial locality** or **temporal locality** only
when later selections reuse chunks or speculatively fetched data before they are
evicted from the declared cache.

Keep three cache effects distinct:

- a **shard-index cache** avoids repeated shard-index requests and bytes;
- an **encoded-payload cache** avoids repeated storage reads but may still require decoding; and
- a **decoded-chunk cache** avoids both repeated transfer and repeated decoding at a higher memory cost.

Cache capacity, initial state, admission/eviction policy, and trace order are required inputs. Do not call a workload simply “warm.” Credit over-read as useful prefetch only when the ordered trace reuses those bytes before eviction.

Apply this distinction to the running workloads:

| Workload | Expected order and reuse | Required view of performance |
|---|---|---|
| Spatial visualization | Overlapping viewports during pan; revisits during zoom | Cold time to first displayed pixel plus steady-state viewport latency and bytes under a bounded cache |
| Temporal visualization | Repeated spatial footprint across nearby time points; possible reuse from chunks with `T>1` or explicit prefetch | Cold time to first displayed pixel plus steady-state frame latency; include random time jumps as a control |
| Modeling | Usually one fixed space/time sample shape and declared channel set at randomized positions, with little cross-batch reuse | Batch latency and samples per second using the actual sampler; treat variable shapes/channels as separate profiles and cache benefit as measured, not assumed |

Caching does not change a layout’s cold-read geometry. A larger chunk may look
expensive for the first selection but cheaper across an ordered trace that
reuses it before eviction; it must satisfy both the cold requirement and the
bounded-cache trace requirement.

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

> If every selection in every required workload selects one value independently along an axis,
> set the chunk extent on that axis to one. If an ordered trace may reuse
> neighboring values, also test explicit larger extents, then require each such
> candidate to pass the limits for cold selections and bounded-cache ordered
> traces.

For channels, begin with `C=1` when channels are toggled independently. For
time, begin with `T=1`, but include named `T>1` candidates when sequential
playback is required. Each `T>1` candidate must demonstrate lower sequence cost
without violating first-frame or random-access limits.

This replaces the ambiguous recommendation to use “low-dimensional” chunks.

### 4.2 Spatial shape

#### Mechanism

Small spatial chunks reduce irrelevant decompression but can increase requests. Large spatial chunks reduce request count but decode more unused data near selection boundaries.

#### Required policy inputs

Before filtering chunks, set:

- maximum cold p95 decode and transfer amplification for each workload;
- maximum p95 storage read requests per selection or batch;
- for visualization, maximum cold time to first displayed pixel and steady-state viewport/frame latency;
- for modeling, minimum samples per second and maximum batch latency using the
  actual sampler;
- cache layers, byte capacity, initial state, and admission/eviction policy for
  every cache-aware trace;
- minimum required encoding throughput, defined as the maximum source rate times a stated safety factor; and
- maximum decoded chunk bytes per selection or batch and maximum decoded-chunk
  cache bytes.

Values not yet supported by measurements remain explicit unresolved policy parameters; they are not replaced with words such as “small” or “reasonable.”

#### Rule

> Replay cold selections and ordered cache-aware traces against each candidate
> shape. Reject a shape when either its cold requirement or its
> application-specific ordered-trace requirement fails.

Use real trace order and positions, including edges, misalignment, spatial pans, temporal playback and jumps, and the modeling sampler. Do not average visualization and modeling into one blended workload.

For the initial modeling workload, replay one fixed sample shape at the actual
origin distribution. If several required architectures use different fixed
shapes, keep them as separate workload profiles. Do not enlarge the baseline
search space for hypothetical variable-size token sequences or variable-channel
encodings; add those only with a concrete consumer and acceptance limit.

The current executable planner implements independent selection batches and a
shard-index cache state of either cold or warm. It does not yet enforce bounded
caches over ordered traces or time to first displayed pixel. Treat those as
external policy limits until the trace simulator described in
[planner-design.md](../../code/planner-design.md) is implemented.

### 4.3 Compression and encoding

Encoded fraction was defined in the cold-read byte ledger. Lower is better. A
source may instead report a compression ratio; retain that source term only
with its numerator and denominator.

For every surviving chunk shape:

- measure encoded fraction on representative image content;
- measure encoding throughput;
- report decoded chunk bytes, any named codec-stage bytes, encoded chunk payload
  bytes, omitted fill chunks, shard-index bytes, metadata bytes, and final stored bytes
  separately; and
- reject candidates that cannot sustain the required source rate with the chosen headroom.

#### Do not select the chunk yet

Set a `compression_tolerance` relative to the best measured encoded fraction and
retain every chunk candidate within it that passes the access, throughput, and
memory limits. A chunk that looks best in isolation may admit no feasible
configuration of chunks per shard, so final selection waits until both chunk and
shard constraints have been evaluated.

This turns the visually chosen knee of a compression curve into a reproducible
tolerance test.

### 4.4 Carry the chunk policy through the resolution levels

#### Mechanism

Viewers usually request a similarly sized viewport in level-local pixels after
choosing a resolution level. Keeping the same chunk shape across levels
therefore tends to keep request geometry predictable, makes layouts easier to
inspect, and avoids making coarse levels a separate tuning problem.

That preference interacts with the number of resolution levels. As an array is
downsampled, an axis eventually fits within one chunk. A pyramid builder may
then:

- stop the whole pyramid;
- stop that axis while continuing to reduce longer axes;
- stop a declared group of axes while other axes continue; or
- continue creating levels whose array extent is smaller than the chunk shape.

All four are valid layout strategies when their coordinate transforms and
data are correct. They produce different level counts and coarse-level access
behavior for strongly anisotropic array shapes. This is a pyramid-builder choice, not a
Zarr requirement.

#### Implementation cases to explain

Use the two Acquire Zarr implementations as a concrete contrast:

- The current implementation preserves chunk shape, reduces `X` and
  `Y` as a coupled pair until the shorter in-plane dimension reaches its chunk
  extent, and handles spatial `Z` separately. A short `X` or `Y` can therefore
  stop reduction of the longer in-plane axis.
- The next-generation implementation also preserves chunk shape. By
  default it stops downsampling each configured axis independently when that axis reaches
  one chunk, allowing longer axes to continue; an aspect-preserving option
  stops when the first configured axis reaches one chunk.

Prefer the next-generation rule as the general planning default: every axis
named in the downsampling schedule follows the same per-axis stopping
rule, without special behavior inferred from whether it is called spatial,
temporal, or in-plane. This is a policy preference, not a conformance rule.
Current Acquire Zarr remains the recommended single-pass streaming writer, and its
coupled `X`/`Y` schedule is a reasonable supported strategy whenever the
emitted levels reach the required coarsest level and pass the per-level limits.

Record these as implementation facts from
`~/src/acquire-zarr/src/streaming/downsampler.cpp` and
`~/src/LANG/c/chucky/src/lod/lod_plan.c`. In reader-facing text, call the latter
the next-generation Acquire Zarr implementation.

Batch conversion tools provide other choices. `ngff-zarr` builds an out-of-core
multiscale task graph with explicit per-axis downsampling factors and output
chunk shapes:
[multiscale example](https://github.com/fideus-labs/ngff-zarr/blob/main/docs/python.md#generate-multiscales).
Current `ome-zarr-py` can also generate a pyramid, accept per-axis downsampling-factor
dictionaries, and accept storage options per level:
[writer API](https://github.com/ome/ome-zarr-py/blob/master/ome_zarr/writer.py).

#### Rule

> Set the required coarsest level and downsampling schedule before
> accepting a pyramid builder's automatically chosen levels. Begin candidate generation
> with one per-axis stopping rule that stops downsampling each scheduled axis
> separately when it reaches its target. A producer MAY instead use declared
> coupled axis groups, including current Acquire Zarr's in-plane strategy, when
> the emitted pyramid reaches the required coarsest level. Both strategies pass
> the layout policy under the same outcome constraints. Begin with the same
> chunk shape at every level. For each level, replay the required viewer
> selections and recompute chunk count, shard shape, chunks per shard, shard
> count, and stored bytes. Preserve the common chunk shape only while the
> required coarsest level is reached and all per-level access limits pass.

If a fixed shape prevents the required coarse representation, choose explicitly
among:

1. stopping short axes while continuing to downsample long axes;
2. changing chunk shape at the affected coarse levels; or
3. using a different integrated or batch pyramid builder.

No change is needed when a coupled-axis builder already satisfies the required
coarsest level and per-level limits.

Do not silently accept fewer resolution levels because one implementation
stopped at a chunk boundary. Conversely, do not force additional levels that no
required viewer uses. Record the downsampling method, boundary handling for odd
array extents, per-axis downsampling factors, and coordinate transforms; image
correctness is a prerequisite even when filter selection is not the focus of
the layout policy.

#### Required evidence

- level shapes, physical sample spacing, chunk shapes, and configurations of
  chunks per shard;
- the reason each axis is reduced or stops being downsampled at each transition;
- cold time to first displayed pixel for thumbnails and viewports at the levels viewers actually choose;
- conversion throughput for integrated builders or pyramid-build throughput
  for batch builders, writer working memory, process peak RSS, and source bytes
  reread; and
- correctness controls for odd dimensions, intensity data, and labels.

### Chunk recommendation

> Keep independently selected axes separate. Credit a larger extent on such an
> axis only when an ordered trace demonstrates reuse under a declared cache
> budget. Start with one chunk shape across resolution levels, but do not let
> that preference prevent the required coarsest level. Retain every shape and
> downsampling schedule that meets cold access, steady-state latency on each
> ordered trace and its limits on decoded chunk bytes, encoding throughput, and
> encoded fraction; select one only after evaluating its
> possible configurations of chunks per shard.

At this point the reader should be able to predict why the candidate set begins with `T=1` and `C=1`, and why a temporal playback trace may justify adding `T>1` candidates.

## 5. Explain why chunks are grouped into shards

### 5.1 Storage-object count

If every chunk is a separate storage object, a small raw chunk byte count can produce
a storage-object count that violates whole-dataset operation limits.

When the target store maps each shard value to one storage object, shard count
equals the array-data storage-object count. If the store maps values to storage
objects differently, measure that mapping and constrain storage-object count
separately.

Set a maximum shard count, `N_max`, for a stated dataset scope from measured
limits on the operations below. For each operation, find the largest count that
meets its time or cost limit; `N_max` is the lowest of those counts. Account for
metadata objects separately.

- listing or inventory;
- metadata lookup or validation;
- complete-dataset copy;
- indexing or manifest construction; and
- deletion or repair.

Let `D_payload` be estimated total encoded chunk payload bytes, `I_min` be the
lower bound on total shard-index bytes, and `F` be fixed bytes per shard in the
same scope. The shard-count target imposes this candidate-generation lower
bound:

```text
lower bound on average stored shard bytes =
    (D_payload + I_min) / N_max + F
```

This relationship explains why small raw chunk bytes do not require small
stored values.

### 5.2 Range-read condition

An indexed shard preserves chunk-level transfer only when every required
reader/store combination can fetch the shard index and selected encoded chunk
payload ranges efficiently.

Compare:

1. cold shard-index cache plus an encoded chunk payload range;
2. cached shard index plus an encoded chunk payload range; and
3. complete stored shard value fetch.

Do not treat a cached shard index as a cached chunk. Index caching removes lookup work; encoded-payload and decoded-chunk caches determine whether payload transfer and decompression repeat.

Neuroglancer’s Zarr sharding path reads and caches the index, then reads contained chunk ranges: [indexed-shard decoder](https://github.com/google/neuroglancer/blob/122edd90b366f50d8c695e366bb7c88f55de3759/src/datasource/zarr/codec/sharding_indexed/decode.ts#L50-L176). The storage format is defined by the [Zarr v3 indexed sharding codec specification](https://zarr-specs.readthedocs.io/en/latest/v3/codecs/sharding-indexed/index.html).

### 5.3 Independent work

A batch that touches several distinct shards exposes independent storage operations. This permits parallel I/O but does not guarantee it; the client, protocol, network, and storage system may still serialize work.

Define the **shard parallelism target** as the smallest number of concurrent,
independent shards that reaches within `throughput_tolerance` of measured peak
throughput on the target system. Then verify separately that representative
selections or batches expose at least that much independently schedulable work.

Damacy combines adjacent reads within one shard and distributes reads across distinct shards. Use its counters for storage read requests and distinct shards to measure this behavior: `~/src/LANG/c/damacy/src/planner/coalesce.h` and `damacy.h`.

### 5.4 Retry and full-fetch bounds

Set maximum stored shard bytes to the lowest limit imposed by:

- the most data the system may retry after a failed write or copy;
- the most data a required no-range client may fetch for one chunk;
- transport or upload limits; and
- the time allowed to repair or replace one damaged shard.

Do not recommend a shard shape until writer working memory has also been explained.

## 6. Explain write order, memory, and tool roles

### 6.1 Two write patterns

A **Zarr writer** is the library or component that creates or updates Zarr
store values.

A **single-pass streaming write** produces every output region once. After a
region is finalized, later input never modifies it. Its traversal and
finalization order are separate properties that must be stated for the selected
Zarr writer.

An **arbitrary-region write** may target any output region or revisit previously
written data. Its arrival order is recorded separately.

The **write order** is the traversal or arrival order, such as source order,
chunk-major, shard-major, or randomized. It is independent of whether regions
may be revisited.

An **active shard** is a shard with buffered state or I/O currently in progress.
Active-shard count—not merely task count—can determine writer working memory
and observed storage concurrency.

### 6.2 Why write order changes memory

#### Single-pass streaming

Acquire Zarr can retain a bounded set of unfinished chunks, then write encoded
chunks into their destination shard values while retaining shard-index and
open-output state. It need not retain all encoded chunk payloads for every
completed shard.

Its writer working memory still includes:

- input queues;
- unfinished decoded chunks;
- codec buffers;
- pyramid-generation state; and
- shard-index and open-output state for active shards.

Implementation evidence: `~/src/acquire-zarr/src/streaming/acquire.zarr.cpp`, `array.cpp`, `chunk.cpp`, and `shard.cpp`.

#### Arbitrary-region writes

For sharded Zarr, an arbitrary-region Zarr writer may need to retain, read,
merge, or rewrite state associated with each active shard. Writer working
memory, payload bytes reread or rewritten, and index bytes rewritten therefore
depend on stored shard bytes, active-shard count, write order, cache
configuration, and the implementation.

### 6.3 Separate source handling, pyramid construction, and the Zarr writer

Make three decisions. A single library may fill more than one role, but record
the role and behavior separately.

#### Source and metadata layer

Use **iohub** when the conversion needs its microscopy readers or construction
of an OME-Zarr image or HCS hierarchy and metadata. Record the exact iohub
version and the Zarr writer it uses. iohub adds source-decoding and metadata
state; the selected Zarr writer determines chunk and shard buffering.

#### Pyramid builder

Use integrated Acquire Zarr downsampling when a single-pass source should
produce resolution levels without rereading the completed base array. Verify
the implementation's per-axis or coupled-axis stopping rules, but do not reject
its coupled in-plane schedule merely because the general planning default is
per-axis stopping.

Use a batch pyramid builder such as `ngff-zarr` or `ome-zarr-py` when the source
is already randomly readable or when explicit per-axis factors or per-level
chunks require that flexibility. Include Dask/task-graph state, intermediate
storage, input rereads, and the selected Zarr writer in memory and
throughput measurements. Report writer working memory, process peak RSS, and
conversion throughput separately.

#### Zarr writer

| Zarr writer | Choose it when | Main condition to verify |
|---|---|---|
| **Acquire Zarr** | Output can use a single-pass streaming write | Required ordering and pyramid outcome are achievable; conversion throughput and writer working memory pass |
| **TensorStore** | Output requires asynchronous or concurrent arbitrary-region writes, remote storage, or several updates that must commit together | Writer working memory, payload bytes reread or rewritten, and index bytes rewritten pass for the selected stored shard bytes, active-shard limit, cache configuration, and write order |
| **zarr-python** | Writes occur in one process through NumPy-style indexed assignment, without the TensorStore requirements above | Process peak RSS, overlap coordination, payload bytes reread or rewritten, and index bytes rewritten for partial shard updates pass |

For arbitrary-region writes, schedule work shard-by-shard when possible and cap
active shards using measured writer working memory and process peak RSS. Random
scheduling is a control case, not the default.

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

For each surviving chunk shape and the selected Zarr writer, record:

- estimated total encoded chunk payload bytes, `D`;
- maximum shard count, `N_max`;
- shard parallelism target;
- maximum stored shard bytes for retry or a complete stored shard value fetch;
- maximum process peak RSS;
- minimum conversion throughput; and
- range-read capability of every required reader/store combination.

### Selection procedure

1. Compute the lower bound on average stored shard bytes implied by encoded
   chunk payloads, shard-index bytes, fixed per-shard bytes, and `N_max`.
2. Raise that lower bound if storage measurements show larger minimum efficient
   stored-value bytes: the smallest stored value after which larger values
   improve throughput by less than `throughput_tolerance`.
3. Enumerate tuples of chunks per shard whose estimated average stored shard
   bytes meet or exceed the lower bound, then derive each shard shape in array
   elements.
4. Reject a candidate when any required reader without efficient range reads
   would exceed its limit on transferred storage bytes by fetching complete
   stored shard values.
5. Reject a candidate when representative parallel batches expose fewer distinct shards than the shard parallelism target.
6. Reject a candidate when the selected Zarr writer exceeds its writer working
   memory, process peak RSS, or conversion throughput limit at the required
   active-shard count.
7. Reject a candidate whose maximum observed stored shard bytes exceed the retry or transport limit.
8. Retain every passing layout for the final deterministic selection.

### Shard recommendation

> For every passing chunk, form the smallest shards that meet the shard-count
> target and measured minimum efficient stored-value bytes while preserving
> required range reads, the shard parallelism target, writer working memory,
> conversion throughput, and maximum stored shard bytes.

Do not make shards larger merely because the format permits it. A larger shard
needs evidence that it reduces whole-dataset operation time or increases
storage throughput.

If no candidate passes, the requirements conflict. Reconsider the target for
storage-object count, storage system, Zarr writer, or required client
behavior rather than hiding the conflict in a weighted score.

## 8. State the complete recommendation

The reader now has enough mechanism to understand the headline:

> **Choose chunks for cold selections and ordered traces, then carry that policy
> through the required resolution levels. Credit cache reuse only under a
> declared cache configuration. Group those chunks into the smallest shards
> that meet the shard-count target without violating limits on storage read
> requests, transfer amplification, shard parallelism, writer working memory,
> or stored shard bytes. Choose the pyramid builder and Zarr writer from the
> required downsampling schedule, write pattern, and write order; then verify
> writer working memory and process peak RSS.**

### End-to-end procedure

1. Record independent selections, fixed-shape model profiles, ordered traces,
   application latency and throughput limits, cache configuration, write
   pattern, source rate, target store and storage environment, and required
   clients.
2. Choose whether iohub is needed for source interpretation or OME-Zarr/HCS construction.
3. Set the required coarsest level and per-axis downsampling schedule, then choose an integrated or batch pyramid builder.
4. Choose the Zarr writer from single-pass streaming versus arbitrary-region
   writes, then state its required write order separately.
5. Generate chunk shapes using independent axes, cold and cache-aware trace
   replay, access limits, encoding throughput, and the encoded-fraction
   tolerance.
6. Apply each candidate across the proposed levels; reject schedules that stop
   before the required coarsest level or fail any per-level policy criterion.
7. Set the maximum shard count, range-read requirements, shard parallelism
   target, writer working memory and process peak RSS limits, minimum conversion
   throughput, and maximum stored shard bytes.
8. Generate and filter per-level configurations of chunks per shard for every
   surviving combination of chunk shape and downsampling schedule.
9. Select one passing layout lexicographically: greatest raw chunk byte count,
   lowest worst decode-limit utilization, lowest worst storage-read-request
   limit utilization, smallest average stored shard bytes, then greatest
   minimum p05 distinct shards touched.
10. Benchmark the complete conversion plus cold, cache-reusing, and dispersed
    read paths on the target storage.
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
- every output region is written once; and
- resolution levels are produced incrementally with a stated downsampling schedule and
  fixed chunk shape where feasible.

### Derivation

1. Show why independently toggled channels imply `C=1`; compare `T=1` with
   explicit `T>1` candidates for playback.
2. Show the cold byte ledger and factor chunk mismatch, encoded fraction, and storage over-read.
3. Replay spatial and temporal viewer traces with declared caches, then replay the modeling sampler without assuming reuse.
4. Reject candidates that fail cold time to first displayed pixel, steady-state
   viewer latency, modeling samples per second, batch latency, or amplification
   limits.
5. Apply the encoding-tolerance filter and retain every passing chunk.
6. Generate the downsampling schedule; show where each axis stops being
   downsampled and verify the required coarsest level is present.
7. Replay the cold viewer selections at the actual level selected for first display and thumbnails.
8. Set `N_max` from measured whole-dataset operations and compute the lower
   bound on average stored shard bytes by level.
9. Verify range reads, the shard parallelism target, maximum stored shard bytes,
   and Acquire Zarr writer working memory including its downsampling state.
10. State the selected layout and identify the exact observation supporting each decision.

### Alternative A: arbitrary-region derived image

Add this example only to change the Zarr writer decision:

- workers produce arbitrary spatial regions;
- compare shard-major and random scheduling;
- choose TensorStore or zarr-python from required observed storage concurrency,
  writer working memory, process peak RSS, and bytes reread or rewritten; and
- retain the same chunk and shard reasoning.

### Alternative B: external microscopy conversion

Add this example only to introduce the source and metadata layer:

- iohub interprets the source and constructs the required hierarchy and metadata;
- the pinned iohub version determines which Zarr writers can be used directly; and
- an ordered adapter into Acquire Zarr is considered only when the output can
  satisfy its single-pass streaming contract.

## 10. Require a layout decision record

Every converted dataset or conversion recipe records:

- array shape, axes, dtype, and resolution levels;
- required coarsest level, per-axis downsampling factors, method, boundary
  handling for odd array extents, per-axis or coupled-axis stopping rule, and
  pyramid builder;
- independent selections, ordered traces, and write pattern;
- fixed model sample shapes, declared channel sets, origin distributions, and
  batch construction;
- chunk shape by level;
- chunks per shard by level;
- expected and observed logical chunk-grid cells, stored and omitted chunks,
  shards, and total storage-object counts;
- useful logical, raw chunk, decoded chunk, encoded chunk payload, shard-index,
  transferred storage, and final stored bytes;
- encoded fraction, storage over-read, transfer amplification, and decode
  amplification by workload;
- cache configuration, hit/miss accounting, and trace order;
- cold time to first displayed pixel, steady-state viewer latency, model batch
  latency, and samples per second;
- client and store range-read behavior;
- source and metadata layer, Zarr writer, versions, and relevant settings;
- active-shard limit, writer working memory, process peak RSS, and sustained
  conversion throughput;
- stored shard byte distribution and maximum stored shard bytes for retry and
  complete stored shard value reads;
- policy limits, tie-breaks, and rejection reasons; and
- conditions that require the decision to be repeated.

The decision record is the final recommendation, not merely a benchmark table.

## Appendix A. Compact equations

Introduce symbols only after the concepts are familiar.

For array shape `n_i`, chunk shape `c_i`, tuple of chunks per shard `k_i`, and
fixed element size `b`:

```text
raw_chunk_bytes = b * product(c_i)
chunk_count = product(ceil(n_i / c_i))
shard_shape_i = c_i * k_i
chunk_count_per_shard = product(k_i)
shard_count = product(ceil(n_i / shard_shape_i))
```

For measured reads:

```text
decode_amplification = decoded_chunk_bytes / useful_logical_bytes
encoded_fraction = encoded_chunk_payload_bytes / decoded_chunk_bytes
storage_over_read = transferred_storage_bytes / encoded_chunk_payload_bytes
estimated_useful_encoded_bytes = useful_logical_bytes * encoded_fraction
transfer_amplification = transferred_storage_bytes / estimated_useful_encoded_bytes
```

Count storage read requests per selection or batch directly; do not describe
them as physical device reads.

For ordered traces, also report byte-weighted hit/miss fractions for the
encoded-payload cache and decoded-chunk cache. Compute transferred storage
bytes and decoded chunk bytes from the actual misses; do not apply one
undifferentiated “warm-cache” multiplier to the cold-read equations.

For updates:

```text
write_amplification = all_storage_bytes_written_for_update
                    / final_encoded_payload_bytes_for_changed_chunks
```

Define edge handling and denominators precisely in the measurement method.

## Appendix B. Evidence inventory

### Local implementation evidence

- Acquire Zarr streaming API and settings: `~/src/acquire-zarr/README.md`
- Acquire Zarr writer working memory and flush behavior: `~/src/acquire-zarr/src/streaming/`
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
- [Executable planner design](../../code/planner-design.md)
- [Glossary](glossary.md)
- [Guide to the planning documents](../README.md)
