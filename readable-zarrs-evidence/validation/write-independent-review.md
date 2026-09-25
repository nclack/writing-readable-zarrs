# Independent write aggregation review

Reviewed `write-analysis.py`, the row/metadata schema, findings, summaries, winners and Blosc comparison export. The check used Python's CSV reader, integer fractions and `statistics.median`, without importing the aggregation code or running benchmarks. Counts refer to the complete export including the precursor runtime records: **3,326 observations, 20 study families, 1,293 summaries, 92 winners and 194 Blosc comparison pairs**.

One provenance issue was found and corrected. The frozen regenerated export was independently rechecked; no unresolved selection or numerical discrepancy was found.

## Issue identified

`reef-turin-microscopy-workers-3708156/execution-0017`, configuration `730d99687f468282`, source `#/records/16`, is the failed BBBC022 attempt. Its `input_id` is `bbbc022-mito`, but the initial export labeled `content` and `workload` as `synthetic_or_low_level_control` because the failed result lacked `image_replay`. Missing result details do not establish synthetic input. The attempt should retain its planned microscopy scope with explicit provenance, or be marked unknown.

The writer agent corrected the row to `content=microscopy`, `workload=raw_pack_cyclic_streaming_replay`, and `workload_scope_source=retained_case_configuration`. The unsupported `not_microscopy` exclusion was removed. I independently verified the regenerated row still has `status=error`, `study_status=failed` and `frontier_candidate_record=false`. It was already excluded for failure/incompleteness. The summary, winner and findings files remain byte-identical to the reviewed versions, and the block-comparison checks still pass.

## Numerical and grouping checks

All 1,293 summaries reproduce their exported attempt counts, valid-observation counts, median throughput and byte sums from their listed `write-runs.csv` rows. For each eligible comparison group, I independently calculated `size = sum(measured_sink_write_bytes) / sum(logical_input_bytes)`, tested eligibility with the exact integer comparison `10 × size <= 11 × smallest_size`, and selected the greatest median throughput while preserving exact ties. I also independently checked dominance: another point must be no larger and no slower, and strictly better in at least one quantity.

The result matches every exported eligibility, Pareto and winner flag: **92 eligible comparison groups, 293 frontier points, 288 points within the size threshold, and 92 winners**. The 28 current-report winners split into 15 at 16–64 KiB and 13 above 64 KiB, as stated in the findings. No fold-threshold substitution of `0.90 × best_fold` was used; the equivalent threshold is `best_fold / 1.10`.

I checked every comparison group for incompatible values of study/session, source hash, input identity/version, dtype, source-plane count, source bytes, logical source format, backend, host, CPU allocation, workers, I/O workers, output buffers, memory setting, sink/storage/mount options, timing policy, duration/minimum-work profile, binary/revision and target batch size. None of these fields varied inside a group. Per-summary configurations also retained fixed chunk/shard shape, codec, level, shuffle and block request. Study/session separation prevents pooling earlier screens with confirmations or different hardware. Different chunk shapes and codecs remain whole-configuration choices, as the findings explain.

## Direct current-report spot checks

Each row below was recalculated from the listed raw sample rows, checking all competing configurations in that comparison group. Rates are logical GiB/s; penalties use the shard-write-byte proxy.

| Input / backend / sink | Summary ID | Sample rows in study | Repeats | Median | Proxy penalty |
| --- | --- | --- | ---: | ---: | ---: |
| BBBC022 / CPU / NFS | `afbbe6ca18aa45e79689` | `reef-turin-microscopy-pareto-core-3710982`: `execution-0036`, `0059`, `0139` | 3 | 5.215286599 | 0.074657% |
| BBBC022 / GPU / NFS | `f881343f300fb40229fd` | `reef-l40-final-confirmation-3704091`: `execution-0068`, `0121`, `0190` | 3 | 4.214475580 | 2.297094% |
| COSEM / CPU / NFS | `dd201c35f97383efb19b` | `reef-turin-microscopy-pareto-core-3710982`: `execution-0044`, `0080`, `0120` | 3 | 4.924985207 | 0.232806% |
| OpenCell DNA / CPU / NFS | `223e9c650af62d69a060` | `reef-turin-microscopy-pareto-transfer-3710982`: `execution-0053`, `0137`, `0248` | 3 | 5.388890322 | 7.921892% |
| BBBC010 / GPU / NFS | `5037fcd42f2a780a5655` | `reef-l40-final-transfer-3702747`: `execution-0118`, `0168` | 2 | 6.412002563 | 0.000000% |

For an explicit rejection check, BBBC022 CPU group `1c3b0561cd4734fecc81` contains a faster 6.384152314 GiB/s configuration, summary `7a039dc4943892667a07`, but its 17.098742% proxy penalty correctly excludes it from the 10% selection. The winning summary's exact ratio is `213292736/402664275`, versus the group's minimum `213133616/402664275`.

## Retention, size meaning and replay caveats

The export retains 17 observations from failed study `reef-turin-microscopy-workers-3708156` and eight from the cancelled study `reef-turin-microscopy-pareto-3710801` whose checkpoint says `running`. All are excluded from frontier selection. It also retains 323 repeated-source-plane-within-chunk rows with explicit exclusions. No incomplete, failed, control or repeated-plane row enters an eligible configuration. The one native retry, `reef-l40-microscopy-sinks-3671242/execution-0110`, retains attempt 2/5 and 6.622587232 seconds of discarded work, explicitly stating that earlier native-attempt details were not retained. Warmup byte/time windows remain attached to observations instead of being invented as additional repetitions. All 3,326 row IDs are unique.

`final_stored_bytes` is empty for every row and `strict_final_stored_size_winner` is empty throughout the summaries. Findings clearly distinguish measured shard-write calls from exact final file size, metadata size and durable-storage completion. The proxy cannot establish a strict final-stored-size optimum.

The finite-cycle audit independently reproduces **674 current sample observations, 198 partial source-cycle tails, at least 1,024 complete cycles per sample, and a largest tail fraction of 0.0752445%**. The findings correctly call normalization an observed average byte cost across cyclic replay and do not equate it with an identical finite logical volume or use that tail fraction as a compression-error bound. The source hash, shape, start plane, tail and padding counters remain available for scrutiny.

## Blosc checks

All **194 pairs** (22 selected in the current report) have fixed comparison group, dataset/hash, chunk shape, shard shape/capacity, dtype, codec/level, shuffle, backend, resources and timing profile. The requested block size changes. Recorded effective CPU block size remains unknown, and the GPU block field is explicitly modeled. No duplicate round labels caused an overwrite in the paired calculations; paired counts and median ratios independently match.

The reported BBBC022 GPU counterexample is supported by fixed `[4,32,64]` chunks and matching shard geometry. Discard summaries `d9dc3abdd8a558345963` / `6d324dc82caaf331841e` compare 4 KiB / 16 KiB block requests: medians 16.845857509 / 7.136885390 GiB/s, three matched rounds, paired ratio 0.423658183, nonoverlapping observed ranges. NFS summaries `7b53c0b34f5e549f7743` / `c95c83a860feaeb0aa5f` use the same fixed configuration with the corresponding requests: 5.889656293 / 6.328569702 GiB/s, three matched rounds and overlapping ranges. These are request comparisons, not measured effective-block claims.

No write-agent files were edited during this review. Only this review document was created. The checks assess the retained export and its stated scope; they do not turn proxy bytes, short replay duration or observed min–max ranges into stronger measurements.

Final reviewed SHA-256 values:

| Artifact | SHA-256 |
| --- | --- |
| `write-analysis.py` | `710ad3c224e66ece7a21d139611e7e309accfadd1916cfd6ca1739ca2cf310d5` |
| `write-runs.csv` | `df6b9216ab927a10142662a7ff319da4b4ba308043d2897f36c50695ae6f60a2` |
| `write-summary.csv` | `3ff5af2be35d10c4eee79aec9389e1334eef37cde446589a0b533d66c62372c1` |
| `write-winners.csv` | `7325a5557e4a837b0b3e37b17877898ae2f2258ef1ad1b3e8621791f32079d6b` |
| `write-block-comparisons.csv` | `b3dbdc2f78d499eb6d31215efe56e34691285d243cf1dae0dfe2b6db15deecda` |
| `write-findings.md` | `56d6c66d9a1d57bada013bed79e23960f2e547453e1504fb67cdd26e203e5cb3` |
