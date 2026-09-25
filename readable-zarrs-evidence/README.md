# Evidence for writing readable Zarrs

Collated on 2026-09-25 from retained measurement records, principally under `/mnt/main0/home/nclack/tmp`, following `planning/cluster-data-prompts.md`. Start with [the experiment inventory](inventory.md), then the findings below. Original records were preserved. This collection ran no new benchmarks, builds, test suites or Slurm jobs, changed no system settings, and read no microscopy pixel/chunk payloads.

| Collection | Exported scope | Findings and main tables |
| --- | --- | --- |
| Reads | 3,182 rows: 1,927 accepted timing observations, 551 duplicate exports, 474 preflight observations, 228 traces, two superseded pilot observations; 719 configuration summaries | [Findings](read-findings.md), [runs](read-runs.csv), [summaries](read-summary.csv), [frontiers](read-frontiers.csv), [workload comparisons](read-workload-comparisons.csv) |
| Streaming writes | 3,326 observations from 20 families, including references, controls and one recorded error; 1,293 summaries and 92 phase-specific proxy winners | [Findings](write-findings.md), [runs](write-runs.csv), [summaries](write-summary.csv), [winners and rivals](write-winners.csv), [block comparisons](write-block-comparisons.csv) |
| Shard/file concurrency | 729 rows across six families, including controls, references and incomplete attempts; 158 summary points and 96 paired write comparisons | [Findings](concurrency-findings.md), [runs](concurrency-runs.csv), [summaries](concurrency-summary.csv), [paired comparisons](concurrency-paired.csv), [read overlap](concurrency-read-overlap.csv) |
| Conversion | 11 logged Zarr v3-to-v3 preparation executions; 4,708 source/destination array-layout records; measured conversion throughput and memory peaks unavailable | [Findings](conversion-findings.md), [runs](conversion-runs.csv), [layouts](conversion-array-layouts.csv), [coverage and near misses](conversion-coverage.csv) |

Counts across collections overlap. In particular, CHAMMI timings and read-overlap traces also appear in the concurrency collection. They must not be added as independent measurements. The current microscopy write report selects only 238 configurations / 674 sample observations from the write archive; earlier phases remain available.

## What the records support

| Working claim | Assessment and best evidence |
| --- | --- |
| Roughly 32 KiB chunks favor translated XY crops | Supported for the measured **Damacy CPU, synthetic smooth4, local-storage crop** conditions with readahead disabled. TensorStore's fixed-block frontier includes 32 KiB, but its faster candidates use larger chunks; its extended chunk/block frontier favors 512 KiB. The four-encoding NFS spot check favors 512 KiB among tested candidates for both readers. A matched real-microscopy read sweep around 16–64 KiB was not located. See the small-chunk, extended-block and NFS sections of [read findings](read-findings.md). |
| Larger chunks help full-array or aligned reads | Complete tiled-scan controls support larger chunks in several measured settings. Aligned origins can still leave extents cutting chunks, and layout-specific alignment changes the requested samples. The export retains these distinctions and does not assign a universal aligned-read optimum. See [workload comparisons](read-workload-comparisons.csv). |
| Microscopy writes favor 16–64 KiB within 10% of minimum size | In the current report, **15 of 28** input/backend/sink conditions have proxy winners in that range; **13 favor larger chunks**. The measured cost is shard-write call bytes per logical input byte, including relevant padding/index writes. Exact final stored-file size was not measured, so the strict stored-size winner remains unknown. See [write findings](write-findings.md) for the 14 NFS winners, observed ranges and counterexamples. |
| About 16 concurrent shards is useful | The paired Chucky NFS study supports moving from four to **15 or 16 actual append-layer shards**, especially for GPU LZ4 (about 52% median paired gains). It has no points above sixteen. The separate dense CHAMMI read sweep peaks at 32 indexed shards per array and uses much smaller shards. No matched change in `nconnect` establishes causality. See [concurrency findings](concurrency-findings.md). |
| Blosc block size matters little for small chunks | Effects depend on backend, codec and storage. At a fixed 16 KiB chunk, one GPU BBBC022 LZ4 discard comparison changes from 16.846 to 7.137 logical GiB/s for a 4→16 KiB block request. Its NFS ranges overlap. Effective block sizes are modeled or unknown, rather than measured from encoded headers. See [block comparisons](write-block-comparisons.csv). |
| Conversion throughput and peak memory can be compared | The located conversion logs establish completion and layout, but supply **no per-layout conversion throughput or measured memory peaks**. No complete TIFF-to-Zarr or Zarr v2-to-v3 performance experiment was found in the documented search. Preloaded replay memory measurements and raw-pack preparation are retained as near misses, with their actual scope. See [conversion findings](conversion-findings.md). |

## Figures and interpretation

[Read workloads](figures/read-workloads.png) compares selected local crop, NFS crop and local scan conditions. [Write tradeoffs](figures/write-tradeoffs.png) shows all 119 current-report NFS candidate configurations, with the 10% proxy-cost band and selected winners. Both include observed minimum–maximum ranges. [SVG versions](figures/) and [the 141 source summary rows](figures/figure-data.csv) are included for editing and plotting. Machine/backend budgets and experiment phases remain separate in the underlying tables; the figures illustrate layout trends, not a normalized CPU/GPU competition.

Chunk KiB and shard capacities generally refer to uncompressed geometry; each table retains its byte definitions. Read counters distinguish useful source bytes, returned output bytes, decoded bytes, encoded bytes and storage traffic. In particular, returned float32 bytes can differ from source uint8/uint16 bytes. `GB/s` is decimal and `GiB/s` is binary. Historical unknown dtype/counter conversions remain unknown.

Write replay loads raw pixels before timing, excludes drained warmup, and includes final writer drain/close and filesystem queue flush. It does not establish complete conversion performance, crash durability, or indefinite acquisition at a source rate. Source hashes, finite replay tails, padding, run durations and reference drift remain available for assessing comparisons.

Blank CSV cells and JSON nulls mean unknown/unavailable. Ranges are observed variation, not confidence intervals. Invalid, superseded and duplicate records are explicit; read failures and allocation history are also preserved in [exclusions](read-exclusions.csv) and [attempts](read-attempts.csv). The L40 read study was incomplete at the inventory snapshot; its plan supplies no timing result.

## Provenance and verification

Run rows retain source paths and record/configuration locators. The read/write metadata and source manifests, [concurrency source manifest](concurrency-sources.json), and [conversion source manifest](conversion-source-manifest.csv) retain hashes and interpretation details. Source paths name the original cluster records. Cached export rows allow summary regeneration after those paths become unavailable; the archive does not contain the microscopy datasets or promise experiment reruns.

[Bundle validation](validation/bundle-validation.json) independently checks run-to-summary calculations, the exact write threshold, concurrency units/paired ratios, figure source values, and byte-identical portable regeneration. Additional checks compared 1,698 read rates and 810 write configuration summaries with archived results. The [independent write review](validation/write-independent-review.md) checked all 1,293 summaries, 92 winners and 194 block pairs. Collection-specific validation files preserve details.

## Reproduce the exports

Run these commands from this directory. Summary regeneration and validation use only the Python standard library and exported metadata; no benchmark packages or cluster allocation are needed.

```bash
python3 scripts/aggregate_reads.py --from-rows read-runs.csv --output .
python3 write-analysis.py --from-rows write-runs.csv --metadata write-metadata.json --output .
python3 scripts/aggregate_concurrency.py --from-rows
python3 scripts/conversion-analysis.py --summarize-only --output .
python3 scripts/build_inventory.py
python3 scripts/validate_evidence.py
```

To recreate the figures, run `python3 scripts/plot_evidence.py` with Matplotlib installed (rendered here with version 3.11.2). Each findings file documents the corresponding command for extracting original cluster records; conversion extraction can also use `scripts/conversion-analysis.py --from-cache conversion-source-records.json --output reproduced-conversions`.

`SHA256SUMS` records the packaged file contents. The sibling `readable-zarrs-evidence.tar.gz` contains this directory; its adjacent `.sha256` file checks the archive. Regenerating validation updates its timestamp, so verify package checksums before reproducing outputs. `python3 scripts/package_evidence.py` rebuilds and verifies the archive after intentional updates.
