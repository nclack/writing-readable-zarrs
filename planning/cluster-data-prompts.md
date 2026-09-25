# Prompts for the cluster agent

These collect evidence for [the current article](article-outline.md). Send the
shared context once, then prompt 1. Use its inventory to direct prompts 2–5;
each analysis should also report missing evidence and contradictory results.

## Shared context

```text
We are preparing an article for engineers choosing Zarr layouts for microscopy
acquisition, training, and visualization. Aggregate existing benchmark results;
do not launch new benchmarks or change mounts, cache settings, or system tuning.
Write derived summaries and exports in a new readable-zarrs-evidence directory,
preserving the source records.

The article starts with read workloads, then proceeds to writing. The two
write workloads are streaming (acquisition or TIFF-to-Zarr conversion) and
rechunking (Zarr-to-Zarr transformation, including v2-to-v3 conversion).
Acquisition prioritizes sustained throughput. Memory use is important for both
TIFF conversion and rechunking, alongside their throughput. Random subvolume
writes are outside scope. Do not treat a streaming replay benchmark as evidence
of complete conversion performance or memory use.

The author's working findings are:
- About 16 concurrent shards was useful for streaming. Concurrent shards means
  the shards in the D-1 dimensional layer currently receiving appended data,
  typically opened, written, and closed over the same interval.
- Most tests used a busy cluster filesystem over NFS with nconnect=16; there
  are also measurements on other machines/storage. Shards were near 1 GiB.
- Chucky write measurements on actual microscopy data favored 16-64 KiB chunks
  when selecting the fastest configuration within 10% of the smallest output.
- Damacy and TensorStore favored about 32 KiB for randomly translated XY crops.
  Larger chunks appeared better for full-array or chunk-aligned reads.
- Blosc block size may have little effect at the small chunk sizes.

These are claims to evaluate, not conclusions the export must reproduce.
Keep machines, dates, storage destinations, workloads, and reader/writer
implementations separate. Do not pool raw throughput across systems.
Preserve actual chunk/shard shapes, byte definitions, and run-level variation.
Unknown fields should be null/unknown, never inferred as zero. Missing metadata
or hashes should not prevent useful exports; explain the resulting limits.
Use logical input/workload compatibility to decide whether runs can be compared.

Every derived row should identify its source file and run/configuration ID
(or row/record location), and every summary should be reproducible from those
rows. Retain failures, exclusions, and warmups with explicit status. Do not
silently choose best runs or replace missing measurements with estimates.
Return concise findings plus the generated files in a downloadable archive
or a named path I can copy back. Include the analysis script/command used.
```

## 1. Find the evidence and map the experiments

```text
Locate the existing Chucky write-side, Damacy read-side, and TensorStore
read-side Pareto experiments and shard/file-concurrency sweeps. Also locate
existing TIFF-to-Zarr and Zarr-to-Zarr conversion experiments, including memory
measurements. Start with known benchmark output and job directories; avoid
scanning microscopy payloads.

Useful source leads from the local checkouts (verify on the cluster):
- acquire-project/chucky: bench/studies/microscopy/index.json and its study.json
  files, bench/machines.toml, bench/workloads.toml, docs/benchmarks/, and
  scripts/sweep/report.py. The microscopy report is microscopy.html; the
  separate pareto.html page covers retained Blosc GPU experiments. Check
  actual input content rather than treating every Pareto page as microscopy.
- Damacy: bench/scenarios/, bench/runs/, bench/tensorstore_bench.py,
  bench/report.py, and any separate cluster experiment/job archives.

Produce inventory.md with one row per experiment family: tool/revision,
date range, machine, CPU/GPU backend, output destination and storage type,
dataset, workload, swept variables, repetitions, status, raw-data location,
and any existing report link. Classify writes as acquisition/streaming replay,
TIFF streaming conversion, or Zarr-to-Zarr rechunking; mark unknown scope.
For conversions, record source/destination formats and layouts and whether
source reading/decoding and peak memory were measured. Identify the actual
tools used rather than assuming a conversion tool from the experiment name.
Distinguish summaries from retained raw runs.
Identify duplicate exports, overlapping phases, and report-selected subsets;
do not discard earlier phases solely because a report displays a newer one.

Resolve, where the records allow:
1. Do chunk KiB and the approximately 1 GiB shards mean uncompressed capacity,
   encoded payload bytes, or final stored bytes? Were they targets or actuals?
2. What does each throughput numerator and timing interval include: input,
   padding, warmup, drain/final close, synchronization, or device transfers?
   Do not equate closing a file with durable storage without evidence.
3. Which runs actually used NFS and nconnect=16? Use run-time mount/provenance
   records; today's mount is context, not proof of a historical configuration.
4. Which controls exist: several shard counts, other nconnect values,
   full-array reads, chunk-aligned crops, cache states, and Blosc block sizes?
5. For conversions, what source/destination layout pairs, processing-block sizes,
   concurrency and memory limits were tested? Are reported memory values measured
   process/device peaks, configured budgets, or allocation estimates? If no
   conversion experiments exist, say so and continue with the available evidence.

Return a short map from each working claim to its best source records and
the smallest set of remaining questions. Do not rerun missing experiments.
```

## 2. Recover the read frontier and workload controls

```text
Aggregate existing Damacy and TensorStore layout experiments. Test the reported
preference near 32 KiB for randomly translated XY crops and the advantage for
larger chunks on full-array or chunk-aligned reads.

First recover the actual Pareto objectives, constraints, and winner-selection
rule in each read analysis. Do not assume it used the write-side 10% size rule.
If no rule was recorded, export the frontier and leave the winner undefined.

Export read-runs.csv with source/run/config IDs, tool/revision, date/order,
machine/backend, storage and recorded mount options, array/dtype/content,
chunk/shard shapes and byte definitions, codec settings, selection shape and
axes, XY origin distribution and alignment, seed/trace, sample/batch counts,
worker and request concurrency, read coalescing, shard counts, cache settings,
warmup, output dtype/device, timing interval, throughput/latency, and status.
Record byte counters separately: useful logical bytes, decoded chunk bytes,
encoded payload, index bytes, and transferred storage bytes, where available.
Do not infer absent counters from generic field names without checking their
implementation at the measured revision.

Analyze these workloads separately, using matched data/settings where possible:
1. Randomly translated XY crops: specify other-axis extents, crop sizes,
   sampling distribution, and any repeated/overlapping selections.
2. Chunk-aligned crops: report both origins and extents. If aligning for each
   layout changes the requested samples, say so; do not call that an identical
   trace. Origin alignment alone does not ensure the crop spans whole chunks.
3. Full-array reads: include final edge/padding behavior and whether timing
   covers the complete logical array.

For each reader and comparison group, produce throughput versus raw chunk
bytes and the recorded frontier. Preserve chunk shape as well as byte count.
Report repetitions, median, observed range, exclusions, and coverage gaps.
Where supported, calculate decoded/useful byte amplification and separately
report actual storage traffic. Label geometry-derived values as modeled;
index caching, fill omission, coalescing, and repeated reads can change traffic.

Use layout trends within each reader as the main comparison. Before any
absolute Damacy/TensorStore comparison, check that logical content, timed
sample positions (including warmup RNG consumption), crop shape, output dtype,
and scope match. State CPU/GPU output placement and whether transfers and
synchronization are included. Distinguish disabled client caches, best-effort
page-cache eviction, and uncontrolled server caches; do not label all as cold.

Produce read-summary.csv, plot-ready workload comparison data, and
read-findings.md. Identify which datasets/readers support 32 KiB, which do not,
and whether full/aligned controls exist. Missing controls are a gap, not a
license to infer their measured speed. Keep real microscopy and synthetic
results separate. Do not infer training-loop or viewer performance from crop
throughput alone.
```

## 3. Recover the streaming write frontier

```text
Using the inventory, aggregate the real-microscopy Chucky streaming write
experiments. Evaluate whether 16-64 KiB chunks provide the highest throughput
within 10% of the smallest measured output. Report counterexamples as well as
support. Keep acquisition traces, streaming replay, and complete TIFF conversion
separate. Rechunking belongs in the conversion analysis, not this frontier.

The acquisition question is whether a layout sustains the source rate. Recover
the source-rate requirement if recorded, plus run length, queue growth or stalls,
shard turnover, and final drain. Do not call a finite replay proof of sustained
acquisition at a specified rate without that evidence. Identify which read-side
candidate layouts also appear in these write experiments.

Export write-runs.csv with one row per recorded attempt. Include, when available:
source locator, study/config/run IDs, date/time and execution order, tool/build,
machine, CPU/GPU backend and workers, destination (filesystem/discard/other),
storage/mount context, dataset and replay extent, dtype, array/chunk/shard shapes,
raw chunk bytes, shard target and actual byte quantities, concurrent-shard
target and actual count, codec/level/shuffle, requested/effective Blosc block
bytes, logical input bytes, padded bytes, output payload/index/metadata or
stored bytes, elapsed time and timing policy, throughput, warmup, and status.
Record the write workload, source format, input staging/preload, and whether
source I/O and decoding are timed; record available memory measurements with
their scope. Report missing source-rate or memory evidence without inventing it.
Use a companion metadata file for repeated settings if that is clearer.

Define comparison groups using the same logical data, replay semantics,
machine, backend, resource budget, storage, timing policy, and measurement
phase. State what is swept within each group. Preserve codec and shape
differences; distinguish a whole-configuration choice from a controlled
chunk-only effect. Keep discard-sink measurements separate from filesystem
results, and local storage separate from NFS even on the same machine.

Within each comparable group:
- Recover the original size metric and throughput summary. Report repetition
  count, median throughput, observed range, and failures; label min-max as
  observed variation, not a confidence interval. If there are only summaries,
  preserve their meaning rather than manufacturing run-level samples.
- Compute the nondominated size/throughput frontier over valid configurations.
  Use the original experiment's validity rules, document exclusions, and keep
  failed/partial configurations visible with their limitations.
- For identical logical volumes, let S be the comparable final output size.
  If timed runs processed different amounts of identical content, normalize
  output bytes to a common logical input volume with matching padding/fill
  semantics. Explain the normalization; do not compare raw file totals from
  different input volumes or silently substitute payload size for stored size.
- Select the greatest median throughput among S <= 1.10 * min(S). The minimum
  is within that comparison group. Preserve exact ties and show close rivals
  whose observed variation makes their ordering uncertain.
- If only compression fold is available and its numerator is identical across
  candidates, the equivalent threshold is fold >= best_fold / 1.10, not
  0.90 * best_fold. State the fold's exact input-byte convention.
- Report winners' chunk shapes/bytes, size penalty, and throughput, alongside
  the best smaller/larger chunk alternatives. Mark sparse or missing coverage;
  the result is best among tested candidates, not a continuous optimum.

For Blosc, compare block sizes only with chunk shape, codec, level, shuffle,
backend, and workload held fixed. Recover effective block sizes where possible;
different requested values may produce the same actual subdivision. If block
size and chunk size changed together, label the effect unresolved.

Produce write-summary.csv, plot-ready frontier data, and write-findings.md.
In the findings, separate repeated patterns across datasets/systems from
exceptions and unstable rankings on the busy filesystem. Use existing paired
or interleaved runs to assess drift where available; otherwise state the limit.
Include sufficient run duration and finalization context to assess whether
each quoted throughput represents sustained writing.
```

## 4. Check shard concurrency, NFS context, and variability

```text
Find existing write and read experiments varying the number of files/shards
with active work. Evaluate the working target near 16 and the proposed link
to nconnect=16 without assuming that one file maps to one connection.

For streaming writes, use concurrent shards to mean the shards in the D-1
dimensional append layer. Recover actual geometry/counts, not only the requested
target. For reads, separately report distinct files touched per selection/batch
and any measured simultaneously active files; do not reuse the writer's
layer-count definition for those quantities. If rechunking runs are present,
record active input and output files separately and identify the processing
schedule; it need not have an acquisition-style append layer. Keep these
workloads separate and retain any memory-versus-concurrency measurements.

Export concurrency-runs.csv and a summary grouped by tool, machine, storage,
workload, chunk configuration, shard byte target, codec, cache settings,
workers/request depth, and recorded nconnect. Record full shard geometry at
each point; it may change as part of the sweep. Identify which dimensions
changed with shard count, including append-axis extent needed to retain
approximately 1 GiB per shard.
State whether 1 GiB is raw capacity, payload, or stored bytes. Retain run order,
time, duration, repetitions, throughput, failures, and available work-per-file
or observed I/O concurrency counters. File counts alone do not prove balanced
work or overlapping I/O.

Show throughput versus actual shard/file count, median and observed range,
and incremental gains. Identify an apparent plateau only where the sweep and
variation support it. Do not import the write selection's 10% output-size
tolerance as a throughput-plateau definition.

Separate these conclusions:
- The evidence for approximately 16 being useful on the measured setup.
- The broader observation that distributing work over several files helped.
- Whether the best count tracks NFS connection count. If nconnect was always
  16, this last relationship remains untested. If it varied, show matched
  comparisons and remaining confounders.

Use contemporaneous mount, job, network, and load records where available.
Do not infer historical mounts from today's state or attribute all variation
to network load without supporting counters. Report the evidence for storage
noise, codec/resource limits, and ordering effects separately.

Produce concurrency-findings.md and plot-ready data. End with at most three
focused follow-up experiments for claims the archive cannot resolve, listing
the changed variable, fixed controls, and the conclusion each would test.
Propose those experiments only; do not run them as part of this aggregation.
```

## 5. Recover conversion memory and throughput

```text
Aggregate existing conversion experiments for these two cases:
1. A collection of TIFFs streamed into a Zarr output.
2. An existing Zarr transformed into another Zarr (rechunking), including
   v2-to-v3 conversion where available. Version changes need not change chunk
   shape; record the actual source/destination layouts and transformations.

The main question is whether the desired output layout can be produced within
available memory, and what throughput that requires. Random subvolume writes
are outside scope. If there are no suitable experiments, return a precise
coverage gap; do not substitute acquisition replay or invent memory results.

Export conversion-runs.csv with source/run/config IDs, tool/revision, machine,
workload, source/destination storage, data content and logical extent, format
versions, dtypes, codecs, array/chunk/shard shapes, and requested output layout.
Record traversal, processing-block shape, workers/in-flight tasks, queue/cache
limits, configured memory budgets, temporary/intermediate storage, repetitions,
timing scope, elapsed time, throughput, and completion/validation status.
Distinguish format/layout changes from dtype/value transformations if present.

Recover memory measurements with their collection method and scope:
- Complete-process or job peak host memory, including source reading/decoding
  and all worker processes where measured. Do not sum independent per-worker
  peaks as though they occurred simultaneously.
- Device and pinned-host memory separately where applicable.
- Component measurements or estimates for input buffers, unfinished output
  chunks, codec buffers, indexes, and queues where actually available.
- Label configured limits, sampled peaks, allocator measurements, and modeled
  allocations distinctly. A GPU free-memory delta is not a measured peak.

For TIFF streaming, determine whether the measurement includes TIFF decoding
and source I/O, or starts from preloaded pixels. For rechunking, explain how
source/destination overlap and traversal affect retained buffers, source rereads,
and partial output assembly. Separate implementation evidence and memory models
from measured behavior; do not assume the entire output shard is buffered.
Report temporary-disk peaks, source bytes read, and output bytes rewritten only
if available, with clear measurement domains.

Within matched workload/data/layout/hardware groups, summarize repetitions,
peak memory, throughput, and variation as concurrency, processing-block size,
or a memory budget varies. Evaluate layouts relevant to the required output
reads. Do not pool TIFF and rechunking results or treat the fastest write
configuration within 10% of minimum output size as the conversion-memory winner.
If input scale was swept, show whether peak memory changes with dataset size;
otherwise do not claim dataset-size-independent memory use.

Produce conversion-summary.csv, plot-ready memory/throughput data, and
conversion-findings.md. State which settings meet any recorded memory budget,
what throughput they achieve, and whether lower memory increases rereads or
intermediate I/O. Report missing evidence without blocking other exports.
End with the smallest focused follow-up needed for an unresolved memory claim;
propose it only, do not run it during this aggregation.
```

## Local source leads checked while preparing these prompts

On 2026-09-24, the local Chucky checkout at `78e7f7d` contained the microscopy
study index and retained-study documentation named above. Its
`docs/bench-layout-policy.md` defines `min_shard_bytes` as an uncompressed
capacity floor and the concurrent-shard target as soft. The cluster records
must establish which settings and actual geometry each run used.

The local Damacy checkout at `dee3e66` contained `bench/tensorstore_bench.py`,
which describes matched sample generation and reports useful-output `GB/s`
using decimal bytes. Preserve source units before converting plot axes.
These are discovery leads, not evidence that the cluster ran these revisions.
