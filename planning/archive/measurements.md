# Writing readable Zarrs: measurement plan

Archived 2026-09-25. This is historical planning for the broader guide.
Its requirements and recommendations do not govern the current article;
see [archive status](README.md) and the [current plan](../article-outline.md).

Status, 2026-09-24: this is the earlier broad measurement program. For the
current article, first aggregate existing evidence using
[cluster-data-prompts.md](../cluster-data-prompts.md). The experiments below are
background, not prerequisites for that article.

## Goal

Produce evidence for a layout and Zarr writer policy that balances:

- useful random access;
- compression and codec cost;
- decode, transfer, and write amplification;
- required coarsest level, emitted level count, and pyramid construction cost;
- sustained conversion throughput and maximum source rate;
- writer working memory and process peak RSS;
- distinct shards touched per selection or batch;
- shard count for the stated dataset scope; and
- whole-dataset operational cost.

The output is not one globally optimal layout. It is a measured
policy with an explicit validity scope.

## 1. Questions the measurements must answer

1. Which chunk shapes minimize irrelevant transfer and decode for Idetik,
   Neuroglancer, and Damacy workloads?
2. At which raw chunk byte counts does encoded fraction stop improving by more
   than `compression_tolerance` for representative imaging data?
3. How do fixed chunk shapes, array anisotropy, and builder stopping rules
   affect the required coarsest level, emitted level count, and coarse-level
   access?
4. How many shards does each layout create at each resolution level and for the complete dataset?
5. How many distinct shards are touched by a viewport, model batch, or Zarr writer scheduling wave?
6. How do stored shard bytes affect cold and warm shard-index cache states and
   no-range reads?
7. How do conversion throughput and writer working memory scale with active
   shards for Acquire Zarr, TensorStore, zarr-python, and iohub pipelines?
8. How much write amplification results from partial arbitrary-region writes into sharded arrays?
9. What are the practical costs of listing, indexing, copying, validating, and
   retrying the produced storage objects?

## 2. Experimental principles

- Use production-like data, array shapes, byte volumes, codecs, stores, and
  access traces.
- Fix all non-tested variables within a comparison.
- Run candidate A/B configurations in repeated interleaved order to reduce thermal, cache, and storage drift.
- Separate cold, index-warm, payload-warm, and decoded-warm reads.
- Include misaligned and boundary selections.
- Report distributions and repetition counts, not only best runs.
- Keep application scheduling, exposed independent work, and observed
  concurrency at the client, protocol, store, and device layers separate.
- Verify correctness after every write benchmark with metadata validation, sampled chunk checks, and whole-array checksums where feasible.

## 3. Dataset corpus

Use at least four content classes:

| Class | Why it is needed | Required properties |
|---|---|---|
| Real acquisition | Represents actual signal, noise, and spatial correlation | Production dtype, channels, Z depth, and time behavior |
| Sparse/mostly fill-valued | Exposes omitted fill chunks and why stored bytes divided by raw logical bytes is not codec efficiency | Known non-fill fraction, fill value, and spatial distribution |
| High entropy | Establishes a worst-case encoded fraction and a baseline for encoding throughput | Seeded random or suitably noisy content |
| Structured synthetic | Makes geometry effects reproducible | Ramps, blobs, edges, and repeated features with a fixed seed |

For each dataset record:

- logical shape and axis order;
- dtype and raw logical bytes;
- per-axis physical sample spacing and units;
- per-axis source acquisition order;
- channel and time semantics;
- required coarsest level, multiscale shapes, cumulative per-axis downsampling
  factors, and downsampling method;
- source format, source file count, and source object count; and
- content hash or immutable dataset identifier.

Do not extrapolate a compression result from one tissue, modality, or sparsity regime to all imaging data.

## 4. Required workload traces

### 4.1 Idetik viewport trace

Record a representative interactive session containing:

- pan and zoom at several resolution levels;
- channel toggles;
- time-point changes if applicable;
- viewport resize;
- cold start and revisit; and
- visible versus prefetch requests.

Capture selections before cache lookup and storage read requests after cache/coalescing.

### 4.2 Neuroglancer trace

Record:

- 2D slice navigation in each orientation;
- 3D camera movement;
- resolution-level transitions;
- channel/layer toggles;
- cold, index-warm, payload-warm, and decoded-warm states; and
- request priorities if available.

### 4.3 Damacy trace

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

Record Damacy planning and execution counters, especially chunks planned,
chunks loaded, storage read requests issued, cache hits and misses, bytes at
each named stage, and distinct shards per scheduling wave (Damacy's counter for
distinct shards touched per selection or batch).

### 4.4 Pyramid-builder traces

Build the same requested pyramid from the same base array with each relevant
builder. Record:

- requested and emitted cumulative per-axis downsampling factors;
- per-level shapes and chunk shapes;
- the level at which each axis stops changing;
- source and intermediate arrays read for every output level;
- whether downsampling and writing are fused, streamed, or materialized;
- task order, observed concurrency, and temporary storage; and
- boundary handling for odd array extents.

Include current Acquire Zarr, the next-generation Acquire Zarr backbone,
ngff-zarr, and ome-zarr-py where they are viable conversion paths. Pin exact
versions and configuration; do not infer equivalent behavior from a shared
OME-Zarr output format.

### 4.5 Write-order traces

Use the same logical output with these arrival orders:

1. source acquisition order suitable for a single-pass streaming write;
2. chunk-major order;
3. shard-major order;
4. randomized chunks;
5. randomized small regions; and
6. repeated updates to a subset of already written shards.

The source-order trace is the natural Acquire Zarr case. The others quantify
when arbitrary-region Zarr writers are required and how scheduling affects
their writer working memory and write amplification.

## 5. Candidate layout sweep

Treat these as an initial search grid, not recommendations.

### Chunk candidates

- Keep `T=1` and `C=1` in the primary sweep.
- Add explicit `T>1` and `C>1` controls to quantify their penalty.
- Raw chunk byte targets: approximately 256 KiB, 1 MiB, 4 MiB, and 16 MiB.
- At each byte target, include different shapes:
  - shallow XY-oriented chunk shape;
  - moderate XYZ chunk shape;
  - near-isotropic XYZ chunk shape where physical sampling permits;
  - source-native chunk shape; and
  - one-plane chunk shape.
- Include edge chunks and non-divisible array dimensions.

### Pyramid candidates

Hold the base array, codec, and base-level chunk shape fixed while varying:

- a factor-of-two schedule with per-axis stopping of each finished axis;
- the current Acquire Zarr strategy, which stops its coupled in-plane axes
  together and treats spatial depth separately;
- an aspect-preserving schedule that stops when the first active axis reaches
  one chunk;
- an explicit application-required schedule independent of automatic stopping;
  and
- a coarse-level chunk-shape change when a fixed chunk shape would prevent the
  required coarsest level or violate a read limit.

Include strongly anisotropic shapes and cases where array dimensions are not
divisible by the downsampling factor. Use the same requested schedule across
builders wherever their APIs permit it, and record unsupported requests rather
than silently substituting a different schedule.

### Shard candidates

- Unsharded baseline.
- Stored shard byte targets: approximately 64 MiB, 256 MiB, 1 GiB, and 4 GiB.
- For each target, vary the chunks per shard rather than only total bytes.
- Include shard shapes that spread along XY, Z, and the axis along which source
  write order advances.
- Reject candidates that exceed format, store, process peak RSS, retry, or
  upload constraints before expensive benchmarks.

### Concurrency candidates

- Maximum concurrent storage read requests and Zarr writer worker counts: 1, 2,
  4, 8, 16, and 32 where the system supports them.
- Record observed concurrent storage operations and distinct active shards.
- Stop increasing concurrency once read or conversion throughput improves by
  less than `throughput_tolerance` or a limit on writer working memory, process
  peak RSS, or tail latency fails.

## 6. Metrics and accounting

### 6.1 Chunk and shard inventory

```text
raw_chunk_bytes = element_bytes * product(chunk_shape)
chunk_count = product(ceil(array_shape / chunk_shape))
shard_shape = chunk_shape * chunks_per_shard
chunk_count_per_shard = product(chunks_per_shard)
shard_count = product(ceil(array_shape / shard_shape))
```

Report by array and resolution level:

- cumulative per-axis downsampling factors;
- chunk shape and in-bounds edge extents;
- logical chunk-grid cells intersecting the array;
- stored chunks and omitted fill chunks;
- shards;
- metadata objects;
- shard-index bytes;
- median, p05, p95, and maximum encoded chunk payload bytes;
- median, p05, p95, and maximum stored shard bytes; and
- fraction of each edge chunk and edge shard that lies outside the logical
  array.

### 6.2 Byte accounting

Record these separately:

- source bytes read;
- raw logical array bytes;
- decoded chunk bytes;
- bytes at every codec-stage boundary under study;
- encoded chunk payload bytes;
- omitted fill-chunk count and logical bytes represented by those chunks;
- shard-index and checksum bytes;
- metadata bytes;
- final stored bytes, with encoded chunk payload, shard-index, checksum, and
  metadata subtotals;
- transferred storage bytes;
- payload bytes reread and rewritten during updates; and
- index bytes rewritten during updates.

Derived values:

```text
encoded_fraction = encoded_chunk_payload_bytes / decoded_chunk_bytes
estimated_useful_encoded_bytes = useful_logical_bytes * measured_encoded_fraction
transfer_amplification = transferred_storage_bytes / estimated_useful_encoded_bytes
decode_amplification = decoded_chunk_bytes / useful_logical_bytes
write_amplification = all_storage_bytes_written_for_update
                    / final_encoded_payload_bytes_for_changed_chunks
```

Never use `final_stored_bytes / raw_logical_bytes` alone to claim codec
effectiveness. That fraction also reflects omitted fill chunks, indexes, and
metadata.

### 6.3 Requests and concurrency

For each selection or batch:

- chunks intersected;
- shards intersected;
- shard-index reads;
- encoded chunk payload range reads;
- complete stored-value reads;
- coalesced reads;
- storage read requests issued;
- distinct shards touched;
- peak concurrent storage read requests per shard and across shards;
- cache hits and misses for the shard-index, encoded-payload, and decoded-chunk
  caches; and
- transferred storage bytes caused by gaps in coalesced ranges.

### 6.4 Timing

- end-to-end conversion time;
- sustained and instantaneous useful logical input and output bytes per second;
- tile/transpose stage, codec, shard-index, and delivery time;
- time blocked on queue capacity or writeback;
- per-selection p50, p95, and p99 latency;
- time to first displayed pixel;
- time until each resolution level becomes readable; and
- flush, commit, and finalize duration.

Report useful logical throughput, stored-byte throughput, and network transfer
throughput separately.

### 6.5 Memory and resource use

- process peak RSS;
- anonymous RSS versus file-backed/page-cache memory where the platform exposes them;
- allocator high-water mark if available;
- queued source bytes;
- resident downsampling, rechunking, and pyramid-intermediate bytes;
- resident decoded chunk-buffer bytes;
- resident encoded chunk-payload bytes;
- cache-pool or transaction bytes;
- active-shard count;
- per-shard index and transport state;
- open files/connections/uploads; and
- CPU and GPU memory when those paths are used.

Also record source rereads and intermediate bytes materialized; RSS alone does
not reveal whether a builder traded memory for extra I/O or temporary storage.

Sample memory frequently enough to capture flush and commit peaks. A single before/after RSS measurement is insufficient.

## 7. Experiment: writer working memory

### Hypotheses

**H1 — Acquire Zarr:** With a fixed chunk shape and pipeline configuration,
writer working memory is dominated by fixed queues plus the current chunk
layer/band and in-flight codec and multiscale buffers. It should not grow in
proportion to stored shard bytes when encoded chunks are delivered
incrementally.

**H2 — TensorStore:** For partial writes to indexed shards, writer working
memory and write amplification can grow with stored shard bytes and the number
of active shards, depending on cache pool, transaction boundaries, write
coverage, and arrival order.

**H3 — zarr-python:** Partial shard updates can incur read-modify-write work;
concurrent or poorly ordered updates may increase writer working memory and
bytes rewritten.

**H4 — iohub:** Process peak RSS includes source decoding and conversion state
plus the selected Zarr writer's working memory. Attribute the result to the
complete pipeline and the pinned writer version.

These are hypotheses. The experiment should be capable of disproving them.

### Controlled variables

- identical logical dataset and codec;
- identical final chunk and shard layout;
- same store and machine;
- same durability/flush requirement;
- same write order for each paired comparison; and
- explicit cache configuration, transaction scope, and concurrency settings.

### Independent variables

- Zarr writer and exact version;
- source order, shard-major, chunk-major, or random arrival;
- target stored shard bytes;
- chunks updated per shard before switching shards;
- active shard count;
- maximum concurrent write operations;
- complete versus partial shard coverage;
- TensorStore cache pool and transaction scope;
- zarr-python store and codec configuration; and
- iohub's Zarr writer and source reader.

### Required outputs

- process peak RSS, writer working memory, and their time series;
- incremental writer working memory per active shard;
- slope of writer working memory and process peak RSS versus stored shard bytes;
- slope of writer working memory and process peak RSS versus active-shard count;
- conversion throughput and stored-byte throughput;
- payload bytes reread and shard-index bytes read during writes;
- payload bytes rewritten and index bytes rewritten;
- commit and finalize latency; and
- correctness result.

### Key plots

1. Writer working memory and process peak RSS versus stored shard bytes, one
   line per Zarr writer and write order.
2. Writer working memory and process peak RSS versus active shards, one line
   per Zarr writer.
3. Write amplification versus fraction of each shard updated before switching.
4. Conversion throughput versus active shards, with writer working memory and
   process peak RSS limits overlaid.
5. Writer working memory and process peak RSS time series for one representative
   flush or commit.

## 8. Cold and cached read experiment

For every candidate layout, replay the same logical traces under each cache
state:

- cold: a new process with empty shard-index, encoded-payload, and decoded-chunk
  caches, plus a record of how OS, proxy, CDN, and storage-service caches were
  controlled;
- index-warm: populated shard-index cache, cold encoded-payload and
  decoded-chunk caches;
- payload-warm: populated shard-index and encoded-payload caches, cold
  decoded-chunk cache;
- decoded-warm: all three caches populated.

For each cache state, test every required store profile:

- object store with measured efficient range reads;
- local or network filesystem; and
- explicit no-range, complete stored-value control where possible.

Measure:

- useful logical bytes;
- transferred storage bytes;
- decoded chunk bytes;
- shard-index bytes;
- storage read requests;
- distinct shards touched;
- latency distribution; and
- CPU time.

Report results by selection class as well as a workload-weighted aggregate. Do not let a high-volume easy trace hide a poor single-plane or single-channel case.

## 9. Compression experiment

For each candidate chunk shape:

- encode identical content with a fixed codec configuration;
- randomize candidate execution order across repetitions;
- report raw chunk bytes, encoded chunk payload bytes, time, and encoding throughput;
- retain per-chunk distributions rather than only dataset totals;
- stratify by level, channel, and sparsity where appropriate; and
- repeat with omission of fill-valued chunks disabled or separately accounted
  where possible.

Use the measured encoded fractions to apply the policy's explicit `compression_tolerance` relative to the best candidate. Report the complete curve so the team can revise that tolerance; do not infer an unrecorded “compression knee.”

## 10. Downsampling and pyramid-layout experiment

Use the same base arrays, base-level chunks, codec, required coarsest level, and
downsampling method for paired comparisons. Cross these
layout policies:

1. stop finished axes with the same per-axis stopping rule for every
   scheduled axis;
2. stop a declared coupled group when the first member reaches one chunk,
   including the current Acquire Zarr in-plane strategy;
3. stop all active axes together to preserve their reduction aspect; and
4. change chunk shape on coarse levels to reach the required coarsest level.

Run each policy through every relevant builder that can express it. Treat an
unsupported schedule as a capability result, not as a failed performance run.

Measure:

- emitted level count, shapes, cumulative factors, and coarsest emitted level;
- per-level chunk shape, in-bounds edge extents, decoded chunk bytes, shard
  shape, chunks per shard, shard count, storage-object count, and stored bytes;
- pyramid-build throughput in useful logical output bytes per second, process
  peak RSS, resident pyramid-state bytes, source rereads,
  intermediate bytes, and time until each level is readable;
- cold time to first displayed pixel for the thumbnail or viewport at the selected level;
- viewer decode and transfer amplification at every emitted level; and
- numerical correctness for odd dimensions and edges using ramps, impulses,
  and label regions with known expected reductions.

Keep the reduction kernel constant when comparing layout and builder costs.
Test intensity and label reductions separately when both are in scope. The
layout conclusion should state whether a fixed chunk shape passed at every
required level, whether the producer used per-axis stopping or declared coupled
groups, and what change was necessary only if the required outcome did not
pass.

Key plots:

1. Level shape and chunk grid by cumulative downsampling factor for an anisotropic
   array.
2. Cold time to first displayed pixel versus coarsest emitted level.
3. Pyramid-build throughput and process peak RSS by builder and schedule.
4. Per-level shard count and stored bytes for fixed versus adapted chunks.

## 11. Shard parallelism and active-shard experiment

### Reader side

- Fix total useful bytes requested.
- Vary how requests map to one, a few, or many shards.
- Compare adjacent/coalescible and dispersed reads.
- Measure read throughput, tail latency, observed storage concurrency, and
  distinct shards touched per selection or batch.

### Zarr writer side

- Fix total output and layout.
- Vary active shards and ordering.
- Measure conversion throughput, blocking time, writer working memory, process
  peak RSS, open state, and finalize time.

The expected result is not “more is always better.” Identify the smallest
active-shard count beyond which conversion throughput improves by less than
`throughput_tolerance`, and the largest count within the limits for writer
working memory, process peak RSS, and tail latency.

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
| Chunk | four raw chunk byte targets × representative chunk shapes |
| Pyramid | per-axis stopping, coupled-axis stopping, required schedule, coarse-level chunk-shape change |
| Pyramid builder | current Acquire Zarr, next-generation Acquire Zarr, ngff-zarr, ome-zarr-py where viable |
| Shard | unsharded + four targets for stored shard bytes |
| Zarr writer | Acquire Zarr, TensorStore, zarr-python, and the Zarr writer under iohub |
| Write order | source order, shard-major, random |
| Active shards | 1, 4, 16, 32 or platform-safe subset |
| Store | local filesystem + one production-like object store |
| Cache state | cold, index-warm, payload-warm, decoded-warm |

### Confirmation

- Retain passing layouts on the measured Pareto frontier plus candidates needed
  to test policy-limit boundaries.
- Run full-size production-like datasets.
- Add network filesystem if it is a deployment target.
- Repeat interleaved A/B runs across multiple sessions.
- Confirm on the intended compute and storage environment.

## 14. Policy limits

Define numeric values with the team before final policy selection:

| Policy limit | Policy parameter |
|---|---|
| Sustained conversion throughput exceeds maximum source rate with safety margin | `minimum_conversion_throughput_bytes_per_second` |
| Writer working memory stays within its deployment budget | `maximum_writer_working_memory_bytes` |
| Process peak RSS stays within its deployment budget | `maximum_peak_rss_bytes` |
| Shard count for the stated dataset scope stays within its operational budget | `maximum_shard_count` |
| Average stored shard bytes reach the target store's throughput plateau | `minimum_efficient_stored_value_bytes` |
| Pyramid reaches the required coarsest level | `required_coarsest_level` |
| Every level passes structural and numerical checks | `require_valid_level_geometry`, `require_downsample_correctness` |
| p05 distinct shards touched by parallel batches meets the shard parallelism target | `shard_parallelism_target` |
| Zarr writer active shards remain bounded | `maximum_active_shards` |
| Interactive and training traces stay within amplification limits | `maximum_p95_transfer_amplification`, `maximum_p95_decode_amplification` |
| Storage read requests per selection or batch stay within the workload limit | `maximum_p95_storage_read_requests` |
| Shard retry and complete stored shard value read costs remain acceptable | `maximum_stored_shard_bytes` |
| Encoded fraction is within tolerance of the best candidate | `compression_tolerance` |
| Tail latency meets client needs | workload-specific `maximum_p95_latency_ms`, `maximum_p99_latency_ms` |

Rejecting a candidate should name the failed policy limit. Do not silently bury hard constraints inside a weighted score.

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
  chunk_shape:
  shard_shape:
  chunks_per_shard:
  codec: {}
pyramid:
  builder:
  required_coarsest_level:
    maximum_array_shape:
    minimum_cumulative_downsampling_factors:
    minimum_physical_sample_spacing:
  requested_cumulative_downsampling_factors: []
  stopping_rule:
  emitted_levels: []
  downsampling_method:
conversion_path:
  source_and_metadata_layer:
  zarr_writer:
  write_pattern:
  write_order:
  reader_request_concurrency:
  zarr_writer_concurrency:
  maximum_active_shards:
  writer_cache_configuration: {}
  transaction_scope:
workload:
  trace_id:
  cache_configuration: {}
metrics:
  raw_chunk_bytes:
  decoded_chunk_bytes:
  encoded_chunk_payload_bytes:
  omitted_fill_chunks:
  logical_bytes_represented_by_omitted_fill_chunks:
  shard_index_bytes:
  stored_bytes:
  transferred_storage_bytes:
  payload_bytes_reread:
  payload_bytes_rewritten:
  index_bytes_rewritten:
  useful_logical_bytes:
  storage_read_requests:
  distinct_shards_touched:
  writer_working_memory_bytes:
  peak_rss_bytes:
  source_bytes_reread:
  intermediate_stored_bytes:
  time_to_first_readable_level_ms: {}
  conversion_throughput_bytes_per_second:
  stored_byte_throughput_bytes_per_second:
  network_transfer_throughput_bytes_per_second:
  latency_ms: {p50: null, p95: null, p99: null}
implementation_counters:
  zero_skipped_bytes:
  zero_skipped_bytes_semantics:
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
- Writer working memory and process peak RSS scaling by stored shard bytes and
  active shards.
- Explicit single-pass streaming versus arbitrary-region write comparison.
- At least one strongly anisotropic pyramid comparison covering
  builder-selected stopping, per-axis stopping, and a coarse-level chunk-shape
  change.
- Per-level layout inventory, pyramid-build resource costs, cold time to
  first displayed pixel, and downsampling correctness.
- Whole-dataset storage-object count and at least one operational timing.
- Correctness validation.
- Pinned source revisions and library versions.
- A short limitations section naming untested environments and clients.

## Cross-references

- Narrative and policy: [outline.md](outline.md)
- Presentation sequence: [presentation-outline.md](presentation-outline.md)
- Figure specifications: [figure-outline.md](figure-outline.md)
- Executable planner design: [planner-design.md](../../code/planner-design.md)
- Canonical terms: [glossary.md](glossary.md)
