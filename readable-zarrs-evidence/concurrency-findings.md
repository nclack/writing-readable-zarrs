# Shard and file concurrency findings

The paired microscopy experiment supports a larger streaming shard layer on its measured L40/NFS setup, especially for fast GPU codecs. It does not establish sixteen as an optimum or test whether the best count tracks NFS connections. The broader read sweep also benefits from distributing data across files, but its medians do not peak at sixteen.

Export: 729 rows, 158 summary points, and 96 matched write pairs. Every row retains a source locator. Reference observations, failed preflight, diagnostics and incomplete pilot are visible. Missing values are empty CSV cells / JSON null, never measured zeros.

## Paired microscopy streaming

Chucky on cw-us-e4a2-l40-234-003, 2026-09-14; historical study storage records establish NFSv3 with nconnect=16. Four output buffers, 32 I/O workers, four CPU compression workers and a four-write per-file cap are fixed. Three selected settings per input were tested for eight randomized paired rounds. Rates are logical input GiB/s; output accounting is metered shard writes, not a final stored-file census.

| Input | Backend | Codec | Actual layer count | Four-shard median GiB/s | Larger-layer median GiB/s | Median paired gain |
| --- | --- | --- | --- | ---: | ---: | ---: |
| bbbc022-mito | cpu | blosc-lz4 | 4 → 15 | 1.567 | 1.571 | +0.2% |
| bbbc022-mito | cpu | blosc-zstd | 4 → 15 | 0.518 | 0.531 | +2.6% |
| bbbc022-mito | cpu | none | 4 → 15 | 1.697 | 1.905 | +13.3% |
| bbbc022-mito | gpu | blosc-lz4 | 4 → 15 | 3.341 | 5.213 | +51.8% |
| bbbc022-mito | gpu | blosc-zstd | 4 → 15 | 2.691 | 2.743 | +1.9% |
| bbbc022-mito | gpu | none | 4 → 15 | 1.767 | 3.591 | +93.5% |
| cosem-cos7-em | cpu | blosc-lz4 | 4 → 16 | 1.274 | 1.280 | +0.3% |
| cosem-cos7-em | cpu | zstd | 4 → 16 | 1.091 | 1.112 | +2.1% |
| cosem-cos7-em | cpu | none | 4 → 16 | 1.637 | 1.667 | +2.4% |
| cosem-cos7-em | gpu | blosc-lz4 | 4 → 16 | 3.055 | 4.725 | +52.1% |
| cosem-cos7-em | gpu | zstd | 4 → 16 | 3.298 | 4.217 | +24.3% |
| cosem-cos7-em | gpu | none | 4 → 16 | 2.604 | 4.665 | +73.9% |

Accepted sample durations span 5.21–62.05 seconds. Final drain is included and reaches 3.04% of the measured interval. The two-second requested warmup is recorded separately. Raw packs are preloaded; source reading/decoding is outside timing. No recorded source-rate requirement, arrival trace or long-duration acquisition test establishes sustained acquisition at a specified rate.

The targets change shard grouping and append-axis extent while each paired chunk/codec/source stays fixed. Full shard capacity is recorded in uncompressed bytes and is at most about 1 GiB in this study. BBBC022 has fifteen, not sixteen, shards in the larger layer. Available files do not measure simultaneous writes. The four versus larger comparison has no observations above sixteen, so it cannot locate a throughput plateau.

`concurrency-paired.csv` preserves all 96 per-round ratios. The summary's minimum/maximum ranges are observed variation. Most compressed CPU pairs gain only a few percent; GPU Blosc-Zstd on BBBC022 also changes little. These are counterexamples to a universal large shard-count benefit. Interleaved uncompressed NFS/discard references and paired ordering reduce drift concerns, but do not measure cluster-wide network load. Larger filesystem variation than discard variation is evidence of a storage-path difference, not a complete causal attribution.

## CHAMMI read count sweep

All retained idr0017 phases are exported: exploratory, sparse confirmation and the dense three-round sweep. The dense phase ran on cw-us-e4a2-l40-202-063. Original whole-plane, unsharded rechunk and indexed-shard series have separate groups. Rates below are returned float32 decimal GB/s, not uint8 source bytes. Same seed alone is insufficient; the grouping also hashes the ordered URI list, sampling and pipeline settings.

| Indexed shards per array | Median GB/s | Observed GB/s range | Repetitions |
| ---: | ---: | ---: | ---: |
| 1 | 1.040 | 0.971–1.073 | 3 |
| 2 | 1.319 | 1.269–1.538 | 3 |
| 4 | 1.314 | 1.185–1.335 | 3 |
| 8 | 1.442 | 1.293–1.840 | 3 |
| 16 | 1.891 | 1.745–2.052 | 3 |
| 32 | 2.196 | 2.126–2.224 | 3 |
| 64 | 1.976 | 1.891–2.005 | 3 |
| 128 | 1.825 | 1.667–1.956 | 3 |

These are 64 KiB raw inner chunks in representative uint8 arrays, with shards shrinking from 8 MiB to 64 KiB; this is not the 1 GiB-shard experiment. Thirty-two has the largest dense-sweep median. Rates subsequently fall, so the medians do not show a flat sixteen-and-above plateau. Historical max-run interpretations near sixteen are not used to discard lower repetitions. A before-layout count of one in the old analysis is also misleading: the retained uint8 [1,2,1,2048,2048] metadata has two whole-plane files per representative array.

No retained per-job mount record establishes nconnect for these June runs. Their paths and archive context indicate shared storage, but the export leaves recorded_nconnect null. File-count histograms and generation scripts establish layouts; the generated sharded arrays themselves are no longer retained. Geometry reconstructed from those scripts is labeled modeled. distinct_shards counters are not simultaneously active files and can include warmup. Advisory client page-cache eviction does not control server caches; warmup follows eviction.

## Measured read overlap and filesystem controls

The September 23 fixed-count CPU pilot uses local XFS, not NFS: sixteen available 1 GiB raw shards, 64 KiB chunks, 16 KiB Blosc blocks, 32 decode/copy participants and 16 file readers. Separate instrumented diagnostics show peak overlapping shard reads of 9/10 for Damacy LZ4/Zstd and 14 for TensorStore. Time-weighted means are about 5.0 versus 6.8–6.9. Each diagnostic touches all sixteen shards and verifies 3,033 required ranges. These instrumented observations are excluded from throughput summaries and do not supply a shard-count optimum.

Later scheduling, readahead, buffer, chunk and block studies retain another 224 diagnostic table rows in concurrency-read-overlap.csv. They change this early picture: sixteen-way overlap is reached in later traces. For the 512/512 KiB Zstd scan diagnostic, Damacy's mean simultaneous shard reads are 10.95 with readahead disabled and 5.05 with default advice, versus TensorStore's 4.40. Both earlier and later phases remain visible. Distinct active files and active read calls have separate columns; these are application calls, not device queue depths. The fixed count does not identify an optimum or an NFS connection relationship.

Synthetic Orca append-axis and write-cap experiments are exported separately. Total output-file count and append-axis shard count are distinguished from the non-append layer geometry. Changing the total file count does not automatically change the number of active layer files. The three completed phases used different L40 nodes and are not pooled. The empty pilot manifest remains visible.

The August filesystem microbenchmarks include one/eight/64 available files, request depth, request size, local/NFS and sync controls. They record actual achieved request depth, not simultaneous file counts. Two-repeat NFS depth points show appreciable variation, including different rankings across repeats; the script's nconnect=16 description is not a recorded run-time mount, so that field remains null. Source logs retain network counters for a separate wire check, not load attribution for every run. No matched nconnect sweep was found in these records.

## Reproduction

From this directory, run `python3 scripts/aggregate_concurrency.py --from-rows` to recreate CSV summaries and these findings from concurrency-records.jsonl. Omit `--from-rows` to reread the retained sources on the cluster; use `--source-home` when that archive root moves. The script reads metadata only and never invokes an archived benchmark script. Source paths and SHA256 values are in concurrency-sources.json.

## Focused follow-ups, proposed only

1. Vary the streaming layer count above and below sixteen while fixing real input, chunk/codec, raw shard capacity, workers and timing; interleave repetitions. This would test the plateau rather than only the 4/16 contrast.
2. Vary nconnect in a matched storage experiment while fixing file counts, geometry, reader/writer budgets and workload; measure actual file/request overlap. This would test whether the useful file count tracks connections.
3. At fixed read layout and trace, vary request scheduling while retaining source/output hashes and byte counters. This would test why sixteen available shard files produce fewer overlapping reads.
