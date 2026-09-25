# Planning documents

The article is for **engineers choosing Zarr layouts for microscopy acquisition,
training, and visualization**. It moves from read workloads to layout choices,
then streaming and rechunking. Acquisition emphasizes throughput; TIFF
conversion and Zarr-to-Zarr rechunking emphasize memory use alongside throughput.

Writing process: **audience → outline → target length → draft → edit**.

## Active files

| File | Role |
|---|---|
| [article-outline.md](article-outline.md) | Audience, argument, section outline, proposed length, and evidence needs |
| [cluster-data-prompts.md](cluster-data-prompts.md) | Collect existing read, streaming, concurrency, and conversion-memory evidence |
| [glossary.md](glossary.md) | Terms needed for the article |
| [writing-guidelines.md](writing-guidelines.md) | Writing process and editing criteria |

This README and those four documents are the active writing plan.

Collected measurements, findings, figures, source provenance, and reproduction
scripts are in the [evidence guide](../readable-zarrs-evidence/README.md). The
[evidence archive](../readable-zarrs-evidence.tar.gz) contains the same collection.

## Status: 2026-09-25

- Audience and outline are established; the proposed length is 2,500 words.
  Article prose has not been drafted; the evidence bundle includes overview figures.
- Existing cluster measurements have been collated and checked, including
  observed variation and counterexamples to the working claims. The located
  conversion records do not measure peak memory or per-layout throughput.
- The exports distinguish raw capacities, returned bytes, and storage counters.
  Write-size rankings use measured shard-write bytes as a proxy for final size.
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
