# DCA v0.2 chunking and sharding review: outline

## Purpose

Review only the chunking and sharding recommendations in the DCA v0.2 array
standard. The review should identify what is incorrect, internally conflicting,
ambiguous, or insufficiently supported; explain the consequence; and propose a
replacement that can be tested and implemented.

This is a review of the rules, not their authorship. The current values were
reasonable proxies for concerns such as request overhead, compression, and
storage-object count. The goal is to replace those proxies with the quantities
we actually need to control.

The review is based on the following snapshot and project material:

- [DCA v0.2 array standard](https://github.com/chanzuckerberg/dynamic-cell-atlas-specs/blob/501ba4170304b2be554fc66938c2f91a263f4d69/docs/v0.2/array-standard.rst)
- [DCA v0.2 validator documentation](https://github.com/chanzuckerberg/dynamic-cell-atlas-specs/blob/501ba4170304b2be554fc66938c2f91a263f4d69/docs/v0.2/validator.rst)
- [DCA layout helper](https://github.com/chanzuckerberg/dynamic-cell-atlas-specs/blob/501ba4170304b2be554fc66938c2f91a263f4d69/helpers/src/dca_helpers/writer.py)
- [Zarr v3 indexed-sharding specification](https://zarr-specs.readthedocs.io/en/latest/v3/codecs/sharding-indexed/)
- [External collaborator feedback](dca-feedback.md)
- [Proposed layout-selection procedure](outline.md)
- [Measurements needed to set policy values](measurements.md)
- [Executable planner design](planner-design.md)

The review should cite a newer DCA revision instead if the source changes
before publication.

## Scope

Include:

- chunk shape and decoded chunk bytes;
- shard shape, stored shard bytes, and shard count;
- read behavior that materially changes a layout recommendation, including
  range reads and caching;
- write-engine behavior that materially changes shard memory or feasible write
  order;
- conversion-tool constraints that make a recommended layout unattainable;
- downsampling schedules and pyramid-builder behavior where they determine
  level count or per-level chunk and shard layout;
- related validator rules and migration effects; and
- examples needed to make the corrected rules reproducible.

Exclude except where needed to calculate layout costs:

- axis order and general OME-NGFF conformance;
- detailed downsampling-filter selection beyond correctness and edge handling;
- dtype policy;
- codec selection; and
- general conversion-tool guidance unrelated to chunk or shard layout.

## Intended conclusion

The corrected standard should not prescribe one universal chunk byte floor,
spatial chunk tuple, shard byte floor, or time-shard extent. It should prescribe
a reproducible selection procedure:

1. Describe the required reads, ordered query traces, writes, clients, storage,
   and resource limits.
2. Reject chunk shapes that violate cold-read, cache-aware application,
   compression, throughput, or memory limits.
3. Declare the required coarsest resolution and per-axis downsampling schedule,
   then evaluate the surviving chunk shapes at every required level.
4. For every surviving per-level chunk shape, reject shard shapes that violate
   storage-object count, range-read, parallelism, write-memory, throughput, or
   retry limits.
5. Select one passing multiscale layout with a documented deterministic
   tie-break.
6. Record the policy inputs, measurements, selected layout, and rejected
   alternatives.

If no multiscale layout passes, the requirements conflict. The standard should
require an explicit policy change or a separate derived representation rather
than call an untested fixed layout “reasonable.”

## Concepts required before the findings

Keep this section short. Define only terms that are used to resolve an issue.

- A **selection** is the array region requested by one application operation.
- A **resolution level** is one array in a multiscale pyramid.
- A **downsampling schedule** gives the cumulative reduction along each axis at
  every resolution level.
- A **chunk shape** is the independently decoded extent along each array axis.
- A **nominal chunk shape** is the configured chunk shape before an array edge
  truncates or pads a chunk.
- **Decoded logical bytes** are the complete uncompressed chunks decoded for a
  selection.
- **Useful logical bytes** are the uncompressed values in the selection.
- **Decode amplification** is `decoded logical bytes / useful logical bytes`.
- A **shard** is one storage object containing multiple independently decodable
  chunks and an index.
- A **shard shape in chunks** is the number of chunks grouped along each axis.
- **Encoded payload bytes** are the codec outputs stored for chunks.
- **Transferred storage bytes** include payload, index, and any whole-object
  over-read.
- A **range read** retrieves a byte interval rather than a complete storage
  object.
- **Query coherence** means that ordered operations reuse chunks before those
  chunks are evicted from a stated cache.

Use `KiB`, `MiB`, `GiB`, and `TiB` for binary byte limits. Never use “chunk
size” or “shard size” without saying whether it means an axis shape, decoded
bytes, encoded bytes, or a count of chunks.

## Issue inventory

| # | Issue | Classification | Proposed disposition |
|---:|---|---|---|
| 1 | Named use cases are not testable workloads | Ambiguous recommendation | Require selections, ordered traces, and limits |
| 2 | Byte terms and read costs are conflated | Ambiguous concepts and units | Use the explicit byte ledger above |
| 3 | The 512 KiB/1 MiB chunk floor is universal | Unsupported hard threshold | Replace it with workload and throughput constraints |
| 4 | `T=1` conflicts with growing time to meet the byte floor | Conflicting recommendations | Default to `T=1`; admit `T>1` only from measured temporal reuse |
| 5 | `128×128×128` is treated as a universal spatial shape | Unsupported fixed geometry | Generate shapes from required selection geometries |
| 6 | Query order and caches are absent | Incomplete performance model | Require cold and bounded-cache ordered evaluations |
| 7 | A shard is described as the basic write unit | Implementation-dependent claim | Separate the format object from write-engine behavior |
| 8 | Fixed decoded shard-byte limits stand in for operational goals | Wrong proxy and unsupported thresholds | Constrain stored bytes, object count, memory, and retries directly |
| 9 | Shard-axis recommendations are ambiguous and omit concurrency | Ambiguous fixed geometry | Choose packing in chunks from write order and parallelism constraints |
| 10 | Efficient range reads are assumed rather than required | Missing condition | Make client-and-store range capability a policy input |
| 11 | Conversion-tool feasibility is not part of the recommendation | Compatibility gap | Test a versioned capability matrix and document a feasible path |
| 12 | Examples, helpers, and validator behavior obscure the rules | Documentation and enforcement mismatch | Use paired examples and align generation, conformance, and policy lint |
| 13 | Fixed-chunk preference, isotropic factors, and automatic stopping can couple pyramid depth to writer behavior | Ambiguous recommendation and implementation dependency | Declare the required coarsest level; prefer category-independent axis retirement while accepting declared coupled schedules that meet it |

## 1. Named use cases are not testable workloads

### Existing normative text

The introduction names full-array writes and reads, visualization, random model
training reads, and copying, then says one on-disk array should cover them all
reasonably well.

### Classification

Ambiguous recommendation and unsupported premise. “Reasonably well” has no
selection shapes, query order, frequency distribution, cache state, latency or
throughput limit, or storage environment.

### Failure mode and affected consumers

- Plane viewing, orthographic slicing, volume rendering, thumbnail generation,
  model patches, and whole-array processing can prefer different chunks.
- A layout can appear efficient for a coherent viewer trace and perform poorly
  for independent random model samples.
- There is no way to decide whether a compromise passes or merely moves an
  unmeasured cost to another consumer.

### Draft replacement rule

> A layout MUST be evaluated against a declared required workload. Each
> workload MUST specify selections or an ordered trace, its application limit,
> and any cache used in the evaluation. Every selected chunk/shard pair MUST
> pass every required limit.

The desire to retain one canonical stored array is a design objective, not an
assumption that guarantees a feasible layout.

For modeling, the default required workload should use the architecture's
fixed spatial and temporal sample extent, declared channel set, actual sample
origin distribution, and batch composition. Add variable-size, variable-time,
or variable-channel profiles only when a concrete architecture requires them;
do not make every layout pay for hypothetical flexibility.

### Evidence needed

- Cold and ordered visualization traces for plane, orthographic, volume, and
  thumbnail consumers that DCA actually supports.
- Selections or sampler traces for representative modeling applications.
- At least one fixed-shape modeling trace using the production sample shape,
  channels, origin distribution, and batch construction.
- Whole-array processing and conversion write traces.
- The application limits to apply to each trace.

### Validator and migration consequences

- A shape-only validator cannot prove application performance.
- Fixed-shape warnings should not be treated as conformance failures.
- A policy checker or attached decision report may record the workload and
  candidate results separately from structural DCA validation.

## 2. Byte terms and read costs are conflated

### Existing normative text

The standard discusses uncompressed chunk bytes, limited compression ratios,
uncompressed shard bytes, file count, and grouped reads, but does not define the
byte boundaries between the application, decoder, codec payload, and storage
request. It uses `MB`, `GB`, and `TB`, while the validator implements binary
powers of 1024.

### Classification

Ambiguous concepts and units.

### Failure mode and affected consumers

- A compression gain can be mistaken for a reduction in irrelevant decoding.
- A shard can be judged by decoded bytes even when the operational concern is
  actual stored-object size.
- A reader with range support and one without range support can be assigned the
  same apparent cost.
- Policy boundaries differ depending on whether decimal or binary units are
  intended.

### Draft replacement rule

> Every evaluated layout MUST report useful logical bytes, decoded logical
> bytes, encoded payload bytes, transferred storage bytes, and requests per
> workload sample separately for each required workload. Every shard inventory
> MUST report shard shape in chunks, encoded storage-object bytes, and
> storage-object count.

Use decode amplification only for the chunk/selection mismatch. Report storage
over-read and requests separately. Use binary unit names when binary values are
intended.

### Evidence needed

This correction is primarily definitional. Validate the byte ledger against one
instrumented reader and one instrumented writer before making it normative.

### Validator and migration consequences

- Validator output should label shape units and byte units explicitly.
- Report nominal full-shard bytes separately from the actual distribution of
  encoded edge and interior objects.
- Changing labels and reports requires no data rewrite.

## 3. The 512 KiB/1 MiB chunk floor is universal

### Existing normative text

Base-level decoded chunk bytes `MUST` be at least 512 KiB and `SHOULD` be at
least 1 MiB, except when the image itself is smaller.

### Classification

Unsupported universal threshold and overly strong conformance rule.

### Failure mode and affected consumers

- Shallow or two-dimensional data must grow along time or in-plane space merely
  to satisfy a byte target.
- A cold plane, thumbnail, small model patch, or independent time sample may
  decode values it cannot use.
- The rule indirectly constrains shape without bounding p95 decode
  amplification for any named selection.
- Larger chunks can reduce request overhead or improve compression, but those
  benefits are not guaranteed by one decoded-byte minimum.

### Draft replacement rule

> Generate a bounded family of chunk shapes. Reject a chunk if any required
> workload exceeds its maximum p95 decode amplification or chunk-memory limit,
> or if it cannot meet required encoding-throughput and compression limits.
> Carry every surviving chunk into shard search. Reject a chunk/shard pair if it
> exceeds request, transfer, application-latency, or total-memory limits. Apply
> a documented deterministic tie-break to the passing pairs.

Do not retain a universal minimum decoded chunk byte count as a `MUST`. If a
deployment needs to limit request overhead, state that request or throughput
limit directly.

### Evidence needed

- Candidate sweeps below and above the current floor.
- Cold p95 decode amplification and requests for each required selection.
- Compression fraction, encoding/decoding throughput, and peak memory.
- End-to-end modeling throughput and visualization latency.

### Validator and migration consequences

- Retire the 512 KiB error and 1 MiB warning as universal conformance checks.
- Preserve the values temporarily as informational comparisons during a
  transition, clearly labeled as legacy heuristics.
- Existing datasets should not require rewriting solely because chunks fall on
  either side of the old floor.

## 4. `T=1` conflicts with growing time to meet the byte floor

### Existing normative text

Time and channel chunk extents `SHOULD` be one. For shallow `Z`, however, the
edge-case algorithm first grows time by powers of two until the 512 KiB floor
is reached. The typical 2D+time chunk is `(16, 1, 1, 128, 128)` in `TCZYX`
order.

### Classification

Conflicting recommendations with an implicit, unexplained priority. The example
also depends on dtype: it is 256 KiB for `uint8` and 512 KiB for `uint16`.

### Failure mode and affected consumers

- A reader must decode 16 time points to display a cold single-time plane or
  direct thumbnail.
- Independent random time samples receive the same amplification without the
  reuse expected from playback.
- Temporal playback may reuse the additional values, but only if query order,
  cache capacity, and eviction permit it.
- Producers cannot infer whether the singleton-time recommendation or the byte
  floor has priority.

### Draft replacement rule

> Begin candidate generation with `T=1` when any required workload selects time
> independently. Include `T>1` candidates only for a declared temporal-window
> or ordered-playback workload. A packed-time candidate MUST pass the cold
> first-frame and random-jump limits and MUST demonstrate a measured benefit on
> the bounded-cache ordered trace.

Apply the same independent-axis reasoning to channels. Remove the instruction
to grow time solely to reach a decoded-byte floor.

### Evidence needed

- Compare `T=1, 2, 4, 8, 16, ...` for first-frame latency, playback latency,
  random jumps, encoded fraction, and writer throughput.
- State encoded- and decoded-cache capacities and policies.
- Test both `uint8` and `uint16` examples.

### Validator and migration consequences

- Remove the unconditional `T!=1` warning or make it conditional on a declared
  workload profile.
- Do not automatically reject existing `T>1` arrays; require evidence for new
  conversions and re-evaluate old arrays only when their consumers suffer.

## 5. `128×128×128` is treated as a universal spatial shape

### Existing normative text

Spatial chunk extents `SHOULD` be `128×128×128`, with reduced `Z` for shallow
arrays and subsequent growth driven by the byte floor.

### Classification

Unsupported fixed geometry.

### Failure mode and affected consumers

- Plane and thumbnail reads can decode unnecessary depth.
- Orthographic slices and volume rendering favor different spatial packings.
- Model patch geometry depends on the model and sampler.
- Voxel anisotropy and the array's short dimensions are not enough to predict
  the application selection shape.

### Draft replacement rule

> Generate spatial candidates from the shapes of the required selections. Pin
> independently selected axes, preserve several incompatible workload profiles
> rather than averaging them, and reject candidates using the declared access,
> throughput, compression, and memory limits.

For the initial modeling profile, use the production architecture's fixed
spatial and temporal sample extent, channel set, origin distribution, and batch
construction. A second model shape is a second workload; variable-shape or
variable-channel candidates need a concrete consumer and acceptance limit.

`128×128×128` may remain as a candidate or worked comparison; it should not be
a universal warning threshold.

### Evidence needed

- XY planes, each orthographic orientation, volume viewports, and actual model
  patches.
- Misaligned and boundary selections, not only chunk-aligned examples.
- Results for physically anisotropic and nearly isotropic datasets.

### Validator and migration consequences

- Retire the exact `128×128×128` shape warning as a universal policy check.
- Retain only structural checks that are properties of the stored array, such as
  positive extents and valid chunk/shard nesting.

## 6. Query order and caches are absent

### Existing normative text

The layout recommendation treats partial and random reads as use cases but does
not distinguish a cold selection from an ordered sequence or identify any
cache.

### Classification

Incomplete performance model.

### Failure mode and affected consumers

- Spatial panning and time playback may reuse chunks before eviction, so a cold
  read alone can overstate steady-state cost.
- The same assumed reuse can understate cost for random model sampling.
- A shard-index cache, encoded-payload cache, and decoded-chunk cache avoid
  different work and consume different memory.
- Time to first displayed pixel remains important even when later viewer
  operations are cache-efficient.

### Draft replacement rule

> Evaluate a cold operation before crediting reuse. For every cache-aware
> workload, preserve query order and declare cache tier, byte capacity, initial
> state, admission, and eviction. Credit over-read only when a later operation
> uses those bytes before eviction. Packed candidates MUST satisfy both the
> cold limit and the ordered-trace limit.

Treat model selections as independent unless the real sampler trace measures
repeatable locality.

### Evidence needed

- Ordered pan, zoom, and time-playback traces, including random jumps.
- Actual modeling sampler traces.
- Per-cache hit/miss, occupancy, transfer, decode, and latency measurements.

### Validator and migration consequences

Static metadata validation cannot infer cache benefit. Cache-aware results
belong in a versioned decision report or policy-planner output.

## 7. A shard is described as the basic write unit

### Existing normative text

The shard context says shards are the basic write unit.

### Classification

Implementation-dependent mechanism stated as a format property.

### Failure mode and affected consumers

- Random-access write engines may retain or update shard-scale state.
- A streaming write engine can assemble chunks in arrival order and retain a
  layer of unfinished chunks without retaining every complete shard payload.
- Partial updates may require read/modify/write behavior, depending on the
  engine and store.
- Inferring writer memory directly from shard bytes can therefore be wrong in
  either direction.

### Draft replacement rule

> A shard is a storage object and indexed grouping of chunks. The selected
> write engine MUST document the accepted write order, unfinished-chunk state,
> active-shard state, partial-update behavior, and measured memory at the
> required concurrency. Shard candidates that exceed the write-memory or
> throughput limit MUST be rejected for that engine.

The correction document should mention Acquire Zarr, TensorStore, zarr-python,
and iohub only where their behavior changes the feasible layout. The general
tool-choice discussion remains in the main document.

### Evidence needed

- Peak memory and throughput versus active shards for each supported write
  path.
- Forward-only, shard-major, randomized chunk, and randomized patch writes.
- Bytes read and rewritten for partial updates.
- Test, rather than assume, the current hypothesis that TensorStore memory
  scales with retained shard state while Acquire Zarr memory scales with a
  layer of unfinished chunks.

### Validator and migration consequences

The data validator should not assert write-engine behavior. A conversion policy
checker may combine a layout with a versioned engine capability profile.

## 8. Fixed decoded shard-byte limits stand in for operational goals

### Existing normative text

For arrays at least 1 GiB, decoded shard bytes `MUST` be at least 1 GiB. Decoded
shard bytes `SHOULD` be below 5 GiB and `MUST` be below 5 TiB.

### Classification

Wrong proxy for some stated goals and unsupported universal thresholds.

### Failure mode and affected consumers

- Listing, copying, indexing, deletion, and other management costs depend
  primarily on storage-object count and actual stored-object bytes, not decoded
  shard bytes.
- Compression makes decoded and encoded shard sizes diverge by dataset and
  level.
- The 1 GiB floor does not directly cap the number of shards in a dataset.
- Sharding is not required, and the validator skips shard checks when no shard
  codec is present, so the floor does not enforce the stated low-object-count
  goal for unsharded arrays.
- A backend object limit or retry bound applies to bytes actually stored or
  transferred and differs by target environment.
- Writer memory may depend on decoded unfinished chunks, encoded buffered
  payload, active shard indexes, or some combination specific to the engine.

### Draft replacement rule

For estimated encoded dataset bytes `D` and maximum allowed shard count
`N_max`, begin shard candidates at:

```text
minimum average encoded shard bytes = max(
  D / N_max,
  measured minimum efficient storage-object bytes,
)
```

> For every passing chunk shape, select the smallest shard that meets the
> shard-count and measured storage-efficiency requirements without violating
> maximum encoded object bytes, complete-object read cost, retry cost, required
> distinct-shard parallelism, writer memory, or write throughput.

Decoded shard bytes may remain an input to a measured writer-memory model; they
should not stand in for storage-object management cost.

### Evidence needed

- Actual encoded shard-size distributions for representative content.
- Listing, copying, validating, deleting, and retrying time versus object count
  and stored object bytes.
- Storage throughput versus object size to identify the smallest efficient
  object for each target environment.
- Writer memory and throughput versus shard size and active shard count.

### Validator and migration consequences

- Retire the universal 1 GiB decoded-shard error and 5 GiB warning.
- Express backend maxima in a named storage profile and apply them to actual or
  conservatively bounded encoded object bytes.
- A post-write policy audit can count objects and inspect actual encoded sizes;
  a pre-write planner must label them as estimates.
- Existing smaller shards should not be invalidated without evidence that they
  violate the dataset's object-count or efficiency policy.

## 9. Shard-axis recommendations are ambiguous and omit concurrency

### Existing normative text

Spatial shard extents `SHOULD` equal the entire array but also be no greater
than 2048. Time shard extent `SHOULD` be at least 16. No corresponding rationale
or rule is given for channel packing.

### Classification

Ambiguous and unsupported fixed geometry.

### Failure mode and affected consumers

- “Equal to the array but no greater than 2048” does not say what to do when an
  array extent exceeds 2048 or how to round to whole chunks.
- A fixed time extent does not guarantee an acceptable object count, stored
  object size, write order, cache benefit, or number of independent shards.
- Packing too much of the array into one shard can reduce the distinct shards
  available to a parallel reader or writer.
- Packing across channels or time can affect active-shard state and operational
  grouping even when range reads preserve chunk-level decoding.

### Draft replacement rule

> Express shard shape in whole chunks. Enumerate packings that meet the encoded
> byte lower bound, then reject any packing that violates object count, minimum
> distinct-shard parallelism, required write order, active-shard memory, or
> complete-shard read limits. Use dimension preference only as a deterministic
> tie-break after these constraints pass.

As required by the
[Zarr v3 indexed-sharding specification](https://zarr-specs.readthedocs.io/en/latest/v3/codecs/sharding-indexed/),
the inner chunk extent must evenly divide the shard extent on every axis. Array
edges may end partway through the final nominal shard.

### Evidence needed

- Distinct shards touched per viewer request, model batch, and writer scheduling
  wave.
- Actual simultaneous physical operations, not only exposed tasks.
- Candidate packings along spatial, time, channel, and source-arrival axes.

### Validator and migration consequences

- Validate the chunk/shard nesting invariant and label whether a tuple is in
  array elements or chunks.
- Remove unconditional 2048-spatial and 16-time warnings.
- A policy checker may report parallelism and writer-memory failures for a
  declared workload and engine.

## 10. Efficient range reads are assumed rather than required

### Existing normative text

The shard context says shards potentially allow grouped chunk reads, but the
recommendations do not condition shard size on the client and storage system's
ability to retrieve indexed byte ranges efficiently.

### Classification

Missing condition in the causal argument.

### Failure mode and affected consumers

- With efficient range reads, one contained chunk can be transferred and
  decoded after locating it in the shard index.
- Without them, one small selection may transfer the complete shard even though
  it decodes only one chunk.
- Index requests, payload request coalescing, and cache behavior differ across
  clients and stores.
- A shard size that is safe for one required reader can be unusable for another.

### Draft replacement rule

> List every required client/storage pair and verify its range-read behavior.
> If any required path lacks efficient range reads, reject shard candidates
> whose complete encoded object exceeds that path's per-selection transfer or
> latency limit. Measure cold-index and cached-index cases separately.

### Evidence needed

- Range correctness, request counts, transferred bytes, and latency for every
  required client/storage pair.
- Cold and cached shard-index reads.
- Effects of request coalescing and whole-object fallback.

### Validator and migration consequences

Range-read support is an environment capability, not an intrinsic property of
the array metadata. Keep it in a deployment profile and decision report; do not
claim it from shape alone.

## 11. Conversion-tool feasibility is not part of the recommendation

### Existing normative text

The standard recommends output shapes without stating whether commonly used
conversion paths can produce them or what post-processing is required.

### Classification

Compatibility and adoption gap.

### Failure mode and affected consumers

- The collaborator feedback reports that bioformats2raw fixes chunk and shard
  extents in time and channel to one. That cannot produce the recommended
  `T=16` chunk or a time-shard extent of at least 16 directly.
- A large shallow array may also fail the 1 GiB decoded-shard `MUST` when the
  producer cannot grow time or channel packing.
- `SHOULD` warnings become pipeline failures when the validator is run with
  `--strict`, so nominally advisory guidance can become an interoperability
  gate.

### Draft replacement rule

> Every normative layout rule MUST have a tested production path for each
> required source class, or the standard MUST document a supported rewrite step
> and its cost. Tool limitations MUST be recorded by version and separated from
> Zarr format requirements.

Do not weaken a workload requirement merely because one tool cannot implement
it. Instead, decide explicitly whether to change the policy, change the write
path, or add a verified rewrite.

### Evidence needed

- Verify the reported bioformats2raw behavior against the exact versions used
  by IDR and BIA.
- Produce canonical 2D+time and 3D datasets with every supported conversion
  path and inspect emitted metadata.
- Measure any post-conversion rewrite in time, temporary storage, object count,
  and peak memory.

### Validator and migration consequences

- Validator messages should distinguish format errors, DCA policy failures,
  and advisory heuristics.
- Publish a versioned producer capability matrix and a migration path before
  making a new recommendation enforceable.

## 12. Examples, helpers, and validator behavior obscure the rules

### Existing normative text

The standard lists chunk tuples and shard tuples separately. The tuples do not
consistently state dtype, array shape, whether shard dimensions are in elements
or chunks, or the paired chunk shape. The validator documentation says the
array-level rules apply to every scale, while the prose and implementation
limit the 512 KiB/1 MiB chunk-byte checks to level 0. The DCA layout helper
computes shard packing without dtype and does not apply the 1 GiB decoded-shard
minimum.

### Classification

Ambiguous examples and documentation/enforcement mismatch.

### Failure mode and affected consumers

- `(16, 1, 1, 128, 128)` passes the 512 KiB floor for `uint16` but not `uint8`.
- A shard tuple cannot be checked for legal chunk nesting without its paired
  chunk tuple.
- A shard tuple below 1 GiB may comply for a small array and fail for a larger
  array, so the standalone examples do not teach the conditional rule.
- Readers cannot know whether validator documentation, prose, or behavior is
  authoritative for downsampled levels.
- For a sufficiently large shallow array, the DCA layout helper can emit shards
  below the 1 GiB minimum that the validator then rejects.
  For example, its algorithm gives a 128 MiB nominal decoded shard for a
  2 GiB `uint16` array shaped `(4096, 1, 1, 512, 512)`.
- `--strict` changes `SHOULD` diagnostics into a nonzero exit status, increasing
  the practical force of ambiguous recommendations.

### Draft replacement rule

Every worked example should report:

1. axis order, array shape, dtype, and level;
2. required selections or ordered trace and cache policy;
3. chunk shape and decoded chunk bytes;
4. shard shape in chunks and nominal array-element extent;
5. estimated and measured encoded shard bytes and total shard count;
6. relevant reader, store, and write engine;
7. each policy limit and whether the candidate passes; and
8. at least one rejected alternative with its rejection reason.

The normative prose, validator documentation, tests, and implementation should
share one rule table generated from or checked against a single source.

### Evidence needed

- Recalculate every current example for both `uint8` and `uint16` where both are
  supported.
- Pair every shard with a legal chunk shape and representative array shape.
- Add round-trip tests requiring the DCA layout helper's output to pass the
  corresponding DCA validator rules for large 2D+time and 3D arrays.
- Add tests that compare prose scope, severity, and validator behavior for base
  and downsampled levels.

### Validator and migration consequences

- Correct the “every scale level” statement for the current chunk-byte checks.
- Keep structural conformance errors separate from workload-policy failures and
  legacy heuristic notices in both text and exit behavior.
- Provide old-to-new diagnostic mappings so pipeline owners can update strict
  validation intentionally.

## 13. Downsampling schedule and per-level chunks are under-specified

### Existing normative text

The standard requires at least one level of detail whose spatial dimensions are
at most 2048 elements. It recommends a factor of two along every spatial axis
and a factor of one along time and channel. It also recommends
`128×128×128` spatial chunks, while allowing chunks at downsampled levels to be
any size and applying the base-level chunk-byte guidance only to level 0.

### Classification

Ambiguous recommendation, incomplete per-level policy, and
implementation-dependent outcome.

### Failure mode and affected consumers

- “Any size” does not say whether it means chunk shape, decoded bytes, or both.
- Keeping one nominal chunk shape across levels makes layout and reader
  behavior easier to reason about, but it also changes when an axis reaches one
  chunk.
- In a strongly anisotropic array, a builder that stops several axes together
  can end the pyramid when the shortest axis is exhausted even though a longer
  axis still needs downsampling for a useful overview.
- Builders can instead retire finished axes independently, stop the whole
  schedule, or change chunk shape on coarse levels. These choices produce
  different level counts from the same base array and chunk shape.
- An automatically generated pyramid can therefore miss the level needed for
  cold-start visualization or thumbnail generation even though its base-level
  chunks satisfy the standard.
- Current Acquire Zarr and the next-generation Acquire Zarr backbone implement
  different stopping policies, so automatic level count is not a portable
  property of an output request.

The difference does not make current Acquire Zarr unsuitable. Its coupled
in-plane rule is a reasonable streaming strategy when its emitted pyramid
meets the application's declared overview requirement.

### Draft replacement rule

> A producer MUST declare the required coarsest resolution and cumulative
> per-axis downsampling schedule independently of the selected pyramid builder.
> A producer MAY retire scheduled axes independently or use declared coupled
> axis groups, including current Acquire Zarr's in-plane schedule. Either
> strategy conforms when the resulting pyramid reaches the required coarsest
> resolution and passes every per-level limit.
> It SHOULD begin with the same nominal chunk shape at every level, then
> evaluate read amplification, chunk memory, shard count, and writer
> feasibility at every required level. It MUST NOT preserve that nominal shape
> if doing so prevents the required pyramid depth or violates a required
> workload limit.

When an axis reaches one chunk before the others, the decision procedure must
choose and record one of these actions:

1. retire that axis and continue downsampling longer axes;
2. stop its declared coupled group because the overview requirement already
   passes;
3. change the nominal chunk shape on coarser levels; or
4. select a different pyramid builder capable of the required schedule.

Stopping the entire pyramid is acceptable only when the resulting coarsest
level already passes its declared application requirement. “Same nominal chunk
shape” does not imply equal stored bytes or equal actual edge extents. The
producer must also record the reduction method, odd-dimension edge behavior,
and coordinate transforms needed to preserve spatial correctness.

Candidate generation should evaluate category-independent, per-axis retirement
first because the rule generalizes without interpreting axis categories. This
is a planner tie-break, not a structural conformance requirement or a warning
against a passing coupled schedule.

### Evidence needed

- Per-level array, nominal chunk, edge-chunk, shard, and object-count
  inventories for anisotropic 2D+time, shallow 3D, and deep 3D datasets.
- A controlled comparison of coupled-axis stopping, independent axis
  retirement, and coarse-level chunk changes.
- Source-pinned behavior for current Acquire Zarr and the next-generation
  Acquire Zarr backbone.
- Capability and output checks for batch pyramid builders such as
  [ngff-zarr](https://github.com/fideus-labs/ngff-zarr/blob/main/docs/python.md#generate-multiscales)
  and
  [ome-zarr-py](https://github.com/ome/ome-zarr-py/blob/master/ome_zarr/writer.py).
- Pyramid-build throughput, peak memory, source rereads, intermediate storage,
  and cold time to first useful view.
- Correctness checks using odd array dimensions, ramps, impulses, and labeled
  regions with known expected reductions.

### Validator and migration consequences

- Validate that the declared pyramid reaches the required coarsest resolution
  and that level shapes, scale factors, and coordinate transforms agree.
- Apply structural chunk and shard validation at every level, but do not
  require identical chunk shapes as a universal conformance rule.
- Accept current Acquire Zarr's declared coupled in-plane schedule when the
  required overview and per-level rules pass; do not encode the preferred
  category-independent retirement rule as the only valid implementation.
- Add a policy diagnostic when a writer-generated pyramid stops before the
  declared application requirement.
- Record per-level exceptions explicitly so existing arrays can be assessed
  without retroactively invalidating structurally correct data.

## Replacement recommendation section

After presenting the issues and evidence, the correction document should state
one consolidated recommendation rather than repeat fragments throughout:

> Choose chunks from the cold and ordered application workloads. Credit cache
> reuse only under a declared bounded cache. Group those chunks into the
> smallest shards that satisfy measured storage-object efficiency and the
> dataset shard-count target without violating range-read, distinct-shard
> parallelism, write-memory, throughput, or retry limits.

Apply that procedure at every required resolution level. Declare the coarsest
required resolution and per-axis downsampling schedule before choosing a
pyramid builder. Prefer category-independent, per-axis retirement and one
nominal chunk shape across levels, while accepting declared coupled schedules
that reach the same required outcome. Preserve the nominal shape only while it
passes all per-level limits.

The final version must name:

- the exact required inputs;
- every hard rejection condition;
- the deterministic tie-break among passing pairs;
- which values are measured, modeled, or policy choices; and
- what change in workload, client, store, or write engine requires replanning.

## Evidence program

Use [measurements.md](measurements.md) as the detailed protocol. The correction
document needs, at minimum:

1. A small corpus spanning 2D+time, shallow anisotropic 3D, and deeper 3D data.
2. Cold plane/thumbnail, ordered viewer, random-jump, and actual fixed-shape
   model-sampler traces, with extra variable-shape profiles only where used.
3. A chunk sweep that includes values below and above the legacy floor and
   several spatial aspects at equal decoded bytes.
4. A shard sweep that varies encoded bytes and packing independently.
5. Range and no-range reader paths with cold and cached indexes.
6. Stored-object operations measured against both object count and object size.
7. Write throughput and peak memory versus active shards for supported engines.
8. A versioned conversion-tool capability matrix.
9. A downsampling sweep covering coupled-axis stopping, independent axis
   retirement, and per-level chunk changes on anisotropic arrays.
10. Per-builder pyramid throughput, peak memory, rereads, temporary storage,
    output-level inventory, and cold first-view latency.

Report distributions, not only means. Keep codec input/output, fill-value
elision, index bytes, metadata bytes, final stored bytes, and transferred bytes
separate.

## Proposed change sequence

1. Correct definitions, units, contradictory examples, and validator
   documentation without changing data validity.
2. Downgrade the unsupported universal byte and shape rules from conformance
   checks to clearly labeled legacy diagnostics.
3. Correct the downsampling outcome requirements and distinguish them from
   writer-specific automatic level generation.
4. Collect the workload, storage, pyramid-builder, and write-engine
   measurements.
5. Publish the replacement selection procedure with provisional policy values
   labeled as such.
6. Validate the procedure on representative existing DCA datasets and producer
   paths.
7. Set normative policy values only where the evidence supports a shared DCA
   requirement.
8. Publish validator changes, producer compatibility, and migration guidance
   together.

## Review checklist for this correction document

- Is every concept defined before it is used to criticize a rule?
- Does each finding quote or precisely paraphrase the existing rule?
- Is the classification accurate: contradiction, ambiguity, unsupported
  threshold, implementation-dependent claim, compatibility gap, or enforcement
  mismatch?
- Does each replacement constrain the actual cost rather than an indirect
  proxy?
- Are cold and cache-aware behavior kept separate?
- Are decoded, encoded, transferred, and stored bytes kept separate?
- Are format properties separated from client, store, and write-engine
  behavior?
- Is the required coarsest resolution defined independently of automatic
  pyramid-builder behavior?
- Are chunk and shard consequences evaluated at every required resolution
  level?
- Is the fixed-shape modeling baseline stated before optional variable-shape or
  variable-channel workloads are introduced?
- Is each numeric value either supported by evidence or visibly unresolved?
- Could two teams apply the replacement procedure to the same inputs and reach
  the same result?
- Are validator and migration consequences stated beside every proposed change?
