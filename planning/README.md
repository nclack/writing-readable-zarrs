# Planning documents

The article is for **engineers choosing Zarr layouts for microscopy acquisition,
training, and visualization**. It moves from read workloads to layout choices,
then streaming and rechunking. Compare writer layouts using drain capacity;
explain conversion memory from processing order, layout and buffer lifetimes.

Writing process: **audience → outline → target length → draft → edit**.

## Active files

| File | Role |
|---|---|
| [article-outline.md](article-outline.md) | Audience, argument, section outline, proposed length, and evidence needs |
| [cluster-data-prompts.md](cluster-data-prompts.md) | Collect existing read, streaming, concurrency, and conversion-memory evidence |
| [follow-up-experiments.md](follow-up-experiments.md) | Completed BBBC022 experiments, their limits, and analytical treatment of memory/output size |
| [glossary.md](glossary.md) | Terms needed for the article |
| [writing-guidelines.md](writing-guidelines.md) | Writing process and editing criteria |

This README and those five documents are the active writing plan.

Collected measurements, findings, figures, source provenance, and reproduction
scripts are in the [evidence guide](../readable-zarrs-evidence/README.md). The
[evidence archive](../readable-zarrs-evidence.tar.gz) contains the same collection.
The new [BBBC022 evidence](../bbbc022-evidence/README.md) and
[experiment protocol](../experiments/bbbc022/README.md) are separate from that
original snapshot. The [BBBC022 archive](../bbbc022-evidence.tar.gz) and its
[checksum](../bbbc022-evidence.sha256) contain the verified portable export.

## Status: 2026-09-25

- Audience and outline are established; the proposed length is 2,500 words.
  Article prose has not been drafted; the evidence bundle includes overview figures.
- Existing cluster measurements have been collated and checked, including
  observed variation and counterexamples to the working claims. The located
  conversion records do not measure peak memory or per-layout throughput.
- Conversion memory and final-size accounting will be explained through
  reasoning; neither requires a new experiment for this article.
- Use maximum drain rate to compare writer layouts. Sustained acquisition
  rates will be lower; the data do not supply a universal headroom factor.
  A separate sustained-rate study is not required for the layout comparisons.
- The BBBC022 primary experiments are complete: 18 writes across six shared
  layouts, all 144 scheduled CPU read observations, and 36 shard-count samples
  with 12 separate references. The arrays cyclically replay 16 microscopy
  fields; they do not add independent biological images.
- For translated 256 × 256 crops, both readers favor the 256–512 KiB candidates
  in this NFS series. Full scans favor different candidates: 32 KiB for Damacy
  and 128 KiB for TensorStore. The earlier 32 KiB crop preference is not general.
- Shared-layout write medians span 2.27–2.64 logical GiB/s with overlapping
  observed ranges. All final file sizes are within 2% of the smallest, so the
  10% size tolerance admits all six layouts. Read requirements remain decisive.
- The LZ4 primary series gains substantially from four to fifteen shards.
  Thirty versus fifteen gives a median paired gain of 10.1%, with individual
  gains from −14.1% to +22.4%; the Zstd control gains only about 2.8% from four
  to fifteen. In the separate 96 GiB follow-up, all three 54-shard samples are
  slower than their paired 30-shard samples: median 13.4% lower, range
  11.0–15.3% lower. These results do not establish a universal shard-count
  optimum; see the [results and scope](follow-up-experiments.md#experiment-2-extend-the-streaming-shard-count-sweep).
- The exports distinguish raw capacities, returned bytes, metered writes and
  final file lengths. A [source and file-metadata audit](../experiments/bbbc022/size-accounting.md)
  resolves the metered-write correction for the six retained layouts: below
  0.0012% of final file length. Other series retain their stated cost metric.
  Approximately 1 GiB shards are a test setting, not an established optimum.
- No matched connection-count sweep establishes the proposed relationship to
  `nconnect=16`. Blosc block-size effects depend on backend, codec, and storage.
- Multiscale policy, general tool selection, and random subvolume writes are
  outside scope. The archived experiment program is not a prerequisite.

## Archive and separate projects

- [Archived guide](archive/README.md): earlier outline, measurement program,
  figure and slide plans, extended glossary, and writing rules. This index
  records which requirements have been retired from the article.
- [Planner design](../code/planner-design.md): separate design beside the
  planner and explorer code; its objectives do not govern the article.
- [DCA review outline](reference/dca-chunking-sharding-review-outline.md):
  separate, deferred standards review.
- [DCA collaborator feedback](reference/dca-feedback.md): preserved source
  material for that review.
- [Development log](../devlog.md): historical notes on the planner/explorer.
