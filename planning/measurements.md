# Writing readable Zarrs: measurement plan

## Goal

Produce evidence for a layout and writer policy that balances:

- useful random access;
- compression and codec cost;
- read and write amplification;
- pyramid depth and construction cost;
- sustained conversion/acquisition throughput;
- peak memory;
- distinct-shard concurrency;
- dataset shard count; and
- whole-dataset operational cost.

The output is not one globally optimal tuple. It is a measured policy with an explicit validity scope.

## 1. Questions the measurements must answer

1. Which chunk shapes minimize irrelevant transfer and decode for Idetik, Neuroglancer, and Katamari/Damacy workloads?
2. At what chunk size does compression improvement flatten for representative imaging data?
3. How do fixed nominal chunks, array anisotropy, and builder stopping rules
   affect pyramid depth and coarse-level access?
4. How many shards does each layout create at each multiscale level and for the complete dataset?
5. How many distinct shards are touched by a viewport, model batch, or writer scheduling wave?
6. How does shard size affect cold-index, warm-index, and no-range reads?
7. How do write throughput and memory scale with active shards for Acquire Zarr, TensorStore, zarr-python, and iohub pipelines?
8. How much read/modify/write amplification results from partial random writes into sharded arrays?
9. What are the practical costs of listing, indexing, copying, validating, and retrying the produced objects?

## 2. Experimental principles

- Use production-like data, sizes, codecs, stores, and access traces.
- Fix all non-tested variables within a comparison.
- Run candidate A/B configurations in repeated interleaved order to reduce thermal, cache, and storage drift.
- Separate cold, index-warm, and data-warm reads.
- Include misaligned and boundary selections.
- Report distributions and repetition counts, not only best runs.
- Keep application scheduling, physical I/O concurrency, and distinct-shard concurrency separate.
- Verify correctness after every write benchmark with metadata validation, sampled chunk checks, and whole-array checksums where feasible.

## 3. Dataset corpus

Use at least four content classes:

| Class | Why it is needed | Required properties |
|---|---|---|
| Real acquisition | Represents actual signal, noise, and spatial correlation | Production dtype, channels, Z depth, and time behavior |
| Sparse/mostly zero | Exposes zero-chunk elision and misleading stored-size ratios | Known nonzero fraction and spatial distribution |
| High entropy | Establishes a compression/throughput lower bound | Seeded random or suitably noisy content |
| Structured synthetic | Makes geometry effects reproducible | Ramps, blobs, edges, and repeated features with a fixed seed |

For each dataset record:

- logical shape and axis order;
- dtype and raw logical bytes;
- physical pixel/voxel scale;
- per-axis source acquisition order;
- channel and time semantics;
- required coarsest resolution, multiscale shapes, cumulative per-axis scale
  factors, and downsampling method;
- source format and source file/object count; and
- content hash or immutable dataset identifier.

Do not extrapolate a compression result from one tissue, modality, or sparsity regime to all imaging data.

## 4. Workload traces

### 4.1 Idetik viewport trace

Record a representative interactive session containing:

- pan and zoom at several pyramid levels;
- channel toggles;
- time-point changes if applicable;
- viewport resize;
- cold start and revisit; and
- visible versus prefetch requests.

Capture logical selections before cache lookup and physical reads after cache/coalescing.

### 4.2 Neuroglancer trace

Record:

- 2D slice navigation in each orientation;
- 3D camera movement;
- level-of-detail transitions;
- channel/layer toggles;
- cold index, warm index, and warm data states; and
- request priorities if available.

### 4.3 Katamari/Damacy trace

Use representative training or analysis batches:

- the production architecture's fixed spatial and temporal sample shape;
- its declared channel set and channel encoding;
- actual sample-origin distribution;
- spatially local and dispersed batches of that same sample shape; and
- repeated samples that exercise any real cache behavior.

Record a separate profile for each architecture with a different fixed sample
shape. Add variable-size, variable-time, or variable-channel traces only when a
concrete model uses them. If tokenization permits variable inputs but the
training pipeline does not exercise them, keep that flexibility outside the
required workload.

Record Damacy planning and execution counters, especially chunks planned, chunks loaded, reads issued, cache hits/misses, bytes by stage, and distinct shards per wave.

### 4.4 Pyramid-builder traces

Build the same requested pyramid from the same base array with each relevant
builder. Record:

- requested and emitted cumulative per-axis scale factors;
- per-level shapes and nominal chunk shapes;
- the level at which each axis stops changing;
- source and intermediate arrays read for every output level;
- whether downsampling and writing are fused, streamed, or materialized;
- task order, concurrency, and temporary storage; and
- odd-dimension and edge handling.

Include current Acquire Zarr, the next-generation Acquire Zarr backbone,
ngff-zarr, and ome-zarr-py where they are viable producer paths. Pin exact
versions and configuration; do not infer equivalent behavior from a shared
OME-NGFF output format.

### 4.5 Writer traces

Use the same logical output with these arrival orders:

1. monotonic acquisition order;
2. chunk-major order;
3. shard-major order;
4. randomized chunks;
5. randomized small patches; and
6. repeated updates to a subset of already written shards.

The ordered trace is the natural Acquire Zarr case. The others quantify when random-access writers are required and how scheduling affects their memory and amplification.

## 5. Candidate layout sweep

Treat these as an initial search grid, not recommendations.

### Chunk candidates

- Keep `T=1` and `C=1` in the primary sweep.
- Add explicit `T>1` and `C>1` controls to quantify their penalty.
- Raw chunk-byte targets: approximately 256 KiB, 1 MiB, 4 MiB, and 16 MiB.
- At each byte target, include different shapes:
  - shallow XY tile;
  - moderate XYZ tile;
  - near-isotropic XYZ tile where physical sampling permits; and
  - source-native chunk/plane shape.
- Include edge chunks and non-divisible array dimensions.

### Pyramid candidates

Hold the base array, codec, and base-level chunk shape fixed while varying:

- a category-independent factor-of-two schedule that retires each finished
  axis independently;
- the current Acquire Zarr strategy, which stops its coupled in-plane axes
  together and treats spatial depth separately;
- an aspect-preserving schedule that stops when the first active axis reaches
  one chunk;
- an explicit application-required schedule independent of automatic stopping;
  and
- a coarse-level chunk-shape change when fixed nominal chunks would prevent the
  required depth or violate a read limit.

Include strongly anisotropic shapes and cases where array dimensions are not
divisible by the reduction factor. Use the same requested schedule across
builders wherever their APIs permit it, and record unsupported requests rather
than silently substituting a different schedule.

### Shard candidates

- Unsharded baseline.
- Stored shard-size targets: approximately 64 MiB, 256 MiB, 1 GiB, and 4 GiB.
- For each target, vary the chunk-packing vector rather than only total bytes.
- Include packings that spread along XY, Z, and the source/write-order axis.
- Reject candidates that exceed format, store, process-memory, retry, or upload constraints before expensive benchmarks.

### Concurrency candidates

- Reader/writer task counts: 1, 2, 4, 8, 16, and 32 where the system supports them.
- Record actual simultaneous physical operations and distinct active shards.
- Stop increasing concurrency after throughput plateaus or memory/tail latency becomes unacceptable.

## 6. Metrics and accounting

### 6.1 Chunk and shard inventory

```text
raw_chunk_bytes = element_bytes * product(chunk_shape)
chunk_count = product(ceil(array_shape / chunk_shape))
chunks_per_shard = product(shard_shape_in_chunks)
shard_count = product(ceil(array_shape / (chunk_shape * shard_shape_in_chunks)))
```

Report by array and pyramid level:

- cumulative per-axis scale factors;
- configured nominal chunk shape and actual edge-chunk extents;
- logical chunks;
- nonempty chunks;
- shards;
- metadata objects;
- shard index bytes;
- median, p05, p95, and maximum stored chunk payload;
- median, p05, p95, and maximum stored shard bytes; and
- edge fill or padding fraction.

### 6.2 Byte accounting

Record these separately:

- source bytes read;
- raw logical array bytes;
- raw bytes submitted to the codec;
- codec output bytes;
- bytes omitted through all-zero or fill-value elision;
- shard index and checksum bytes;
- metadata bytes;
- final stored payload bytes;
- protocol bytes transferred; and
- bytes rewritten during updates.

Derived values:

```text
codec_fraction = codec_output_bytes / codec_input_bytes
storage_fraction = final_stored_bytes / raw_logical_array_bytes
estimated_useful_encoded_bytes = useful_logical_bytes * measured_codec_fraction
transfer_amplification = transferred_storage_bytes / estimated_useful_encoded_bytes
decode_amplification = decoded_logical_bytes / useful_logical_bytes
write_amplification = all_payload_bytes_written / final_changed_payload_bytes
```

Never use `final_stored_bytes / raw_logical_bytes` alone to claim codec effectiveness when chunks may be skipped.

### 6.3 Requests and concurrency

For each logical selection or batch:

- chunks intersected;
- shards intersected;
- index reads;
- payload range reads;
- full-object reads;
- coalesced reads;
- physical reads issued;
- distinct shards per scheduling wave;
- peak simultaneous operations per shard and across shards;
- cache hits/misses by index and data cache; and
- bytes over-fetched because of range coalescing.

### 6.4 Timing

- end-to-end conversion time;
- sustained and instantaneous useful input/output throughput;
- tile/transpose, codec, index, and delivery time;
- time blocked on queue capacity or writeback;
- per-selection p50, p95, and p99 latency;
- time to first useful view; and
- time until each resolution level becomes readable; and
- flush/commit/finalize duration.

Report both useful logical throughput and physical stored/network throughput.

### 6.5 Memory and resource use

- process peak RSS;
- anonymous RSS versus file-backed/page-cache memory where the platform exposes them;
- allocator high-water mark if available;
- queued source bytes;
- resident downsampling, rechunking, and pyramid-intermediate bytes;
- resident uncompressed chunk bytes;
- resident compressed bytes;
- cache-pool or transaction bytes;
- active shard/write-unit count;
- per-shard index and transport state;
- open files/connections/uploads; and
- CPU and GPU memory when those paths are used.

Also record source rereads and intermediate bytes materialized; RSS alone does
not reveal whether a builder traded memory for extra I/O or temporary storage.

Sample memory frequently enough to capture flush and commit peaks. A single before/after RSS measurement is insufficient.

## 7. Writer memory experiment

### Hypotheses

**H1 — Acquire Zarr:** With a fixed chunk shape and pipeline configuration, peak memory is dominated by fixed queues plus the current chunk layer/band and in-flight codec/multiscale buffers. It should not grow in proportion to complete shard payload bytes when compressed chunks are delivered incrementally.

**H2 — TensorStore:** For sharded Zarr partial writes, memory and writeback cost can grow with the size and number of active outer write chunks (shards), depending on cache pool, transaction boundaries, write coverage, and arrival order.

**H3 — zarr-python:** Partial shard updates can incur shard read/modify/write work; concurrent or poorly ordered updates may multiply temporary memory and bytes rewritten.

**H4 — iohub:** Peak memory is the sum of source decoding/conversion state and the selected backend's working set. Its result should be attributed to the complete pipeline and pinned backend/version.

These are hypotheses. The experiment should be capable of disproving them.

### Controlled variables

- identical logical dataset and codec;
- identical final chunk and shard layout;
- same store and machine;
- same durability/flush requirement;
- same data order for each paired comparison; and
- explicit cache, transaction, and concurrency settings.

### Independent variables

- writer and exact version;
- ordered, shard-major, chunk-major, or random arrival;
- shard stored-size target;
- chunks updated per shard before switching shards;
- active shard count;
- write concurrency;
- full-shard versus partial-shard coverage;
- TensorStore cache pool and transaction scope;
- zarr-python store/codec configuration; and
- iohub backend and source reader.

### Required outputs

- peak RSS and memory-over-time trace;
- memory per active shard/write unit;
- slope of peak memory versus shard size;
- slope of peak memory versus active shard count;
- useful and physical write throughput;
- bytes read back during writes;
- bytes written and rewritten;
- commit/finalize latency; and
- correctness result.

### Key plots

1. Peak memory versus stored shard size, one line per writer/write order.
2. Peak memory versus active shards, one line per writer.
3. Write amplification versus fraction of each shard updated before switching.
4. Throughput versus active shards, with memory budget overlaid.
5. Memory timeline for one representative flush or commit.

## 8. Read-amplification experiment

For every candidate chunk/shard layout, replay the same logical traces under:

- cold process and cold index/data caches;
- warm shard-index cache but cold data cache;
- warm index and data cache;
- object store with efficient ranges;
- filesystem or network filesystem; and
- explicit no-range/full-object control where possible.

Measure:

- useful logical bytes;
- transferred bytes;
- decoded bytes;
- index bytes;
- requests;
- shards touched;
- latency distribution; and
- CPU time.

Report results by selection class as well as a workload-weighted aggregate. Do not let a high-volume easy trace hide a poor single-plane or single-channel case.

## 9. Compression experiment

For each candidate chunk geometry:

- encode identical content with a fixed codec configuration;
- randomize candidate execution order across repetitions;
- report codec input, output, time, and throughput;
- retain per-chunk distributions rather than only dataset totals;
- stratify by level, channel, and sparsity where appropriate; and
- repeat with zero-elision disabled or separately accounted where possible.

Use the measured encoded fractions to apply the policy's explicit `compression_tolerance` relative to the best candidate. Report the complete curve so the team can revise that tolerance; do not infer an unrecorded “compression knee.”

## 10. Downsampling and pyramid-layout experiment

Use the same base arrays, base-level chunks, codec, requested coarsest
resolution, and numerical reduction method for paired comparisons. Cross these
layout policies:

1. retire finished axes independently using the same category-independent rule
   for every scheduled axis;
2. stop a declared coupled group when the first member reaches one chunk,
   including the current Acquire Zarr in-plane strategy;
3. stop all active axes together to preserve their reduction aspect; and
4. change chunk shape on coarse levels to reach the required resolution.

Run each policy through every relevant builder that can express it. Treat an
unsupported schedule as a capability result, not as a failed performance run.

Measure:

- emitted level count, shapes, cumulative factors, and coarsest resolution;
- per-level nominal and actual edge-chunk shapes, decoded bytes, shard packing,
  object count, and stored bytes;
- build throughput, peak RSS, resident pyramid state, source rereads,
  intermediate bytes, and time until each level is readable;
- cold time to first useful thumbnail or viewport at the selected level;
- viewer decode and transfer amplification at every emitted level; and
- numerical correctness for odd dimensions and edges using ramps, impulses,
  and label regions with known expected reductions.

Keep the reduction kernel constant when comparing layout and builder costs.
Test intensity and label reductions separately when both are in scope. The
layout conclusion should state whether fixed nominal chunks passed at every
required level, whether the producer used independent axes or declared coupled
groups, and what change was necessary only if the required outcome did not
pass.

Key plots:

1. Level shape and chunk grid by cumulative scale factor for an anisotropic
   array.
2. Cold first-view latency versus coarsest emitted resolution.
3. Build throughput and peak memory by builder and schedule.
4. Per-level shard count and stored bytes for fixed versus adapted chunks.

## 11. Shard concurrency experiment

### Reader side

- Fix total useful bytes requested.
- Vary how requests map to one, a few, or many shards.
- Compare adjacent/coalescible and dispersed reads.
- Measure throughput, tail latency, physical overlap, and distinct shards per wave.

### Writer side

- Fix total output and layout.
- Vary active shards and ordering.
- Measure throughput, blocking time, memory, open state, and finalize time.

The expected result is not “more is always better.” Identify the smallest active-shard count at the throughput plateau and the largest count within memory and tail-latency limits.

## 12. Operational experiment

For complete representative datasets, measure:

- recursive listing/inventory time and requests;
- stat/head validation time;
- manifest or search-index construction;
- whole-dataset copy throughput and request count;
- delete/cleanup time where safe;
- incremental backup behavior;
- bytes and elapsed time to retry one failed shard; and
- time to locate and validate one known chunk.

Model monetary request cost separately from measured elapsed time. State pricing date and region if monetary estimates are included.

## 13. Experiment matrix

Run a screening phase followed by a focused confirmation phase.

### Screening

| Dimension | Initial levels |
|---|---|
| Data | one real, one sparse, one high-entropy subset |
| Chunk | four raw-byte targets × representative geometries |
| Pyramid | independent axis retirement, coupled stop, required schedule, coarse chunk change |
| Pyramid builder | current Acquire Zarr, next-generation Acquire Zarr, ngff-zarr, ome-zarr-py where viable |
| Shard | unsharded + four stored-size targets |
| Writer | Acquire Zarr, TensorStore, zarr-python, relevant iohub backend(s) |
| Write order | ordered, shard-major, random |
| Active shards | 1, 4, 16, 32 or platform-safe subset |
| Store | local filesystem + one production-like object store |
| Read cache | cold, index-warm, data-warm |

### Confirmation

- Retain only feasible and near-Pareto candidates.
- Run full-size production-like datasets.
- Add network filesystem if it is a deployment target.
- Repeat interleaved A/B runs across multiple sessions.
- Confirm on the intended compute and storage environment.

## 14. Acceptance gates

Define numeric values with the team before final policy selection:

| Gate | Policy variable |
|---|---|
| Sustained output exceeds maximum source rate with safety margin | `minimum_write_rate` |
| Peak process memory stays within deployment budget | `maximum_peak_memory` |
| Dataset shard count stays within operational budget | `maximum_shard_count` |
| Pyramid reaches the application-required overview | `required_coarsest_shape` or `minimum_cumulative_scale` |
| Every level passes structural and numerical checks | `require_valid_level_geometry`, `require_downsample_correctness` |
| Common batches expose enough independent work | `minimum_distinct_shards_per_wave` |
| Active write state remains bounded | `maximum_active_shards` |
| Interactive and training traces stay within amplification limits | `maximum_p95_wire_amp`, `maximum_p95_decode_amp` |
| Shard retry/full-fetch cost remains acceptable | `maximum_stored_shard_bytes` |
| Compression is near the measured knee | `minimum_codec_efficiency` or relative tolerance |
| Tail latency meets client needs | workload-specific `maximum_p95/p99_latency` |

Rejecting a candidate should name the failed gate. Do not silently bury hard constraints inside a weighted score.

## 15. Reporting schema

For every benchmark run record:

```yaml
run:
  timestamp:
  repetitions:
  git_revisions: {}
  library_versions: {}
  machine: {}
  operating_system:
  store:
  network:
dataset:
  id:
  shape:
  axes:
  dtype:
  raw_logical_bytes:
layout:
  chunks:
  shards_in_chunks:
  codec: {}
pyramid:
  builder:
  required_coarsest_shape:
  requested_cumulative_scale_factors: []
  axis_retirement_or_coupling:
  emitted_levels: []
  reduction_method:
writer:
  name:
  backend:
  write_order:
  concurrency:
  cache_or_transaction: {}
workload:
  trace_id:
  cache_state:
metrics:
  codec_input_bytes:
  codec_output_bytes:
  zero_skipped_bytes:
  index_bytes:
  stored_bytes:
  transferred_bytes:
  rewritten_bytes:
  useful_bytes:
  physical_reads:
  distinct_shards_per_wave:
  peak_rss_bytes:
  source_reread_bytes:
  intermediate_bytes:
  time_to_first_readable_level_ms: {}
  useful_throughput_bytes_per_second:
  latency_ms: {p50: null, p95: null, p99: null}
correctness:
  metadata_valid:
  checksums_match:
```

Keep raw run records immutable. Generate summary CSV/JSON for Typst figures from those records, and retain the transformation code with the report.

## 16. Minimum evidence before making a recommendation

- At least one real dataset from each important modality or content regime.
- Repeated interleaved comparisons on the intended storage class.
- Both read and write traces.
- Cold and warm sharded-read behavior.
- Peak-memory scaling by shard size and active shards.
- Explicit ordered versus random write comparison.
- At least one strongly anisotropic pyramid comparison covering automatic
  stopping, independent axis retirement, and a coarse-level chunk alternative.
- Per-level layout inventory, pyramid-build resource costs, cold first-view
  latency, and downsampling correctness.
- Whole-dataset object count and at least one operational timing.
- Correctness validation.
- Pinned source revisions and library versions.
- A short limitations section naming untested environments and clients.

## Cross-references

- Narrative and policy: [outline.md](outline.md)
- Presentation sequence: [presentation-outline.md](presentation-outline.md)
- Figure specifications: [figure-outline.md](figure-outline.md)
- Executable planner design: [planner-design.md](planner-design.md)
