# Article glossary

Use these terms for the [current article](article-outline.md). Give exact
benchmark field names when reporting source data. The
[extended glossary](archive/glossary.md) preserves the earlier guide's
multiscale vocabulary, tool inventory, policy terms, and planner schema mappings.

## Reads and layouts

- **Read workload:** the selections an application requests, their order or
  sampling distribution, concurrency, and cache configuration.
- **Selection:** a requested array region, described here by its origin and
  shape. A **batch** is a group of selections processed together.
- **Translated XY crop:** a fixed-shape crop requested at varying XY origins.
  State the other-axis extents and the position distribution.
- **Chunk-aligned crop:** a selection whose origin and extent follow chunk
  boundaries. An aligned origin alone does not imply whole-chunk coverage.
- **Chunk:** the independently encoded/decoded array block in this article's
  indexed-sharding model. **Chunk shape** is its extent in array elements.
- **Shard:** a stored value containing independently encoded chunks and an
  index locating their byte ranges. On the tested filesystems, it is a file.
  **Shard shape** is its extent in array elements; **chunks per shard** is
  the per-axis quotient of shard shape and chunk shape.
- **Range read:** reading a byte interval of a stored value. Reading individual
  chunks from a shard efficiently depends on both client and storage support.
- **Cache configuration:** which caches are used, their capacities and initial
  state, and the handling of OS and server caches. Distinguish shard-index,
  encoded-payload, and decoded-chunk caches. Say which layers are cold or warm.

## Bytes and performance

Use `KiB`, `MiB`, and `GiB` for binary layout quantities. Preserve benchmark
source units before converting decimal `GB/s`. State the array, selection,
batch, or complete-dataset scope of each count.

- **Raw chunk bytes:** dtype bytes per element times the product of the declared
  chunk shape. Edge padding can make this larger than the in-bounds content.
- **Raw shard capacity:** dtype bytes per element times the product of the
  declared shard shape. This is different from the compressed file size.
- **Useful logical bytes:** uncompressed, in-bounds values requested or
  processed by the application.
- **Decoded chunk bytes:** complete decoded chunk representations processed
  to serve the selections, including values outside them.
- **Encoded payload bytes:** encoded chunk data, excluding the shard index
  and metadata. **Shard-index bytes** locate chunks within the shard.
- **Transferred storage bytes:** bytes moved by storage requests, including
  index reads and any extra ranges fetched. State the measurement boundary.
- **Stored bytes:** final store contents for the declared scope, including
  payload, indexes, and metadata. Identify any exclusions.
- **Decode amplification:** decoded chunk bytes / useful logical bytes for
  the same selection or batch. Report storage traffic separately; compression,
  caching, fill omission, and coalescing can change transferred bytes.
- **Compression fold:** input bytes / output bytes, with both byte domains
  named. Distinguish logical input from padded input and payload from stored
  output. Preserve a source's alternative definition explicitly.
- **Throughput:** named bytes or samples divided by elapsed time. Identify
  input versus output bytes and whether source I/O, decoding, drain, final
  close, and device transfers are timed. Closing a file alone does not prove
  durable storage.
- **Pareto frontier:** tested configurations for which no eligible alternative
  is at least as good on every objective and strictly better on one. State
  the objectives, eligibility rules, and comparison group.
- **10% output-size tolerance:** the write analysis selects greatest throughput
  among comparable configurations with `S <= 1.10 * min(S)`. Compare the same
  logical input volume. This does not define the read analysis's selection
  rule or a throughput plateau. Report ties and uncertain rankings.

## Writing and memory

- **Streaming:** producing Zarr from images arriving during acquisition or
  while converting TIFFs. Acquisition emphasizes sustained throughput;
  TIFF conversion emphasizes memory use. State the input order and buffering.
- **Rechunking:** the Zarr-to-Zarr transformation considered here, including
  v2-to-v3 conversion. Record source and destination layouts, formats, codecs,
  and traversal. A format-version change need not change chunk shape.
- **Concurrent shards:** for streaming, the shards in the `D-1` dimensional
  layer currently receiving appended data. They are typically opened, written,
  and closed over the same interval. Report the actual count as well as any
  requested target.
- **Distinct shards touched:** different shards intersected by a read selection
  or batch. This and the streaming layer count describe available work;
  **observed concurrency** measures actual overlap in I/O. Neither count is
  interchangeable with worker count or NFS connection count.
- **Writer working memory:** queues, unfinished chunks, codec buffers, indexes,
  active-shard state, and other buffers attributable to the writer.
- **Process peak RSS:** the complete process's maximum resident memory. Source
  decoding and other components make this different from writer memory.
  Identify worker-process coverage and device/pinned memory separately where
  applicable. Distinguish measured peaks, allocation estimates, and budgets.

Attribute benchmarks to the measured tool and revision: Chucky for the
reported write experiments, Damacy and TensorStore for the reported read
experiments. Name conversion tools from their actual records. Random
subvolume writes are outside the article's scope.
