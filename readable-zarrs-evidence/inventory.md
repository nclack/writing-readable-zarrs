# Experiment inventory

Snapshot: 2026-09-25. This inventory follows the existing-evidence scope in `planning/cluster-data-prompts.md`. [README.md](README.md) maps the working claims to findings and exports. All original source records were preserved; no new measurement or allocation was run.

Families can overlap across sections: CHAMMI preparation, its subsequent read timings, and the shard-count analysis concern related records. Reports and copied archives are not additional measurements. Exact row-level locators and unknown fields remain in the companion CSV/JSON files.

## Read experiment inventory

Inspected retained records on 2026-09-25. Paths below are under `/mnt/main0/home/nclack` unless absolute. No data generation, benchmark execution, cache changes, mount changes or Slurm allocation was performed. Dataset trees were not traversed. `read-source-manifest.json` and the read aggregation script record the precise small files consumed.

| Family | Tool/revision and dates | Machine/backend/storage | Content and workload | Sweep/repetitions/status | Raw records and report |
|---|---|---|---|---|---|
| June microscopy survey | Damacy GPU; exact binary revision absent from most JSON; TensorStore CPU version often absent; June 12 onward | L40 nodes for Damacy, separate Turin CPU allocation for TensorStore; `/bio`/`/mnt/main0` NFS; historical mount options not embedded in individual runs | Real CHAMMI, Allen Cell static/dynamic and Jacobo MIP; random crops, heterogeneous arrays | Baseline/tuned pipeline; TensorStore 1–32 threads, usually one observation/thread. Retained raw runs; not a chunk-size Pareto study | `data/damacy/scenarios/survey-{baseline,tuned}/runs`, matching `scenarios/*.tensorstore.json`; `tmp/2026-06-12-survey/{run*.log,ts-sweep.log}` |
| June CHAMMI reformat/read controls | Damacy GPU, June 15; TensorStore used to prepare sharded copies, not the measured reader here | L40 / shared NFS; historical nconnect claim in notes, provenance limitations in run JSON | Real idr0017 and mixed CHAMMI; original coarse chunks vs 256-square chunks, sharded/unsharded; crops `[1,1,1,256,256]` | Initial 50-batch runs, sparse 120-batch confirmation, dense 1/2/4/8/16/32/64/128 shards per array; three repeats per confirmation phase. Preserve earlier phases | `src/damacy/bench/runs/chammi-*`; `tmp/2026-06-15-chammi-reformat/{gpu_job*.log,gpu_confirm.log,gpu_curve.log,curve_fit.py}`; scenarios under `data/damacy/scenarios/chammi` |
| June raw Dynacell/tuning and 128-square controls | Damacy GPU, June 6–15; measured revision usually unknown | H100/L40; slow RunAI NFS and fast shared NFS kept separate | Real heterogeneous 5D arrays, random crops; original 1 MiB chunks; source layout/reformatted controls | Coalescing, file readers, lookahead, metadata/cache settings; 128-square and reformatted controls have separate runs. Not evidence for a 32 KiB optimum | `src/damacy/bench/runs/dynacell-*`, `qd-*`, `rop-*`, etc.; `tmp/2026-06-15-bench128`, `tmp/2026-06-15-dynacell-reformat`; project memory provides discovery leads, not measured provenance |
| Original PR160 warm Pareto | Damacy CPU `5126f0958c0be3922a0a00c49d127ba62ddbc6a9` + frozen LZ4/benchmark patches; Sept 16 onward | 40 physical Turin cores, 32 decode/assembly participants, 8 readers, no GPU; node-local files warmed | Synthetic random12/zeros/random/XOR/smooth4/smooth8; four independent uint16 arrays `[512,1024,1024]`, one raw 1 GiB shard each; full scans and translated/aligned 128/256/512-square queries | 84 generated settings, 124 workloads, 516 timed repetitions across baseline/query/smooth phases; retained per-workload raw JSON. TensorStore full readback is validation, not a speed comparison | `tmp/2026-09-16-damacy-pr160-pareto/{job-3715528,amplification-job-3716180,smooth-job-3716593}`; combined `bandwidth-job-3716866/report` duplicates these observations |
| Original PR160 cold-storage phase | Same PR160 base and audited sources; multiple retained retry allocations | Accepted timings all `cpu-turin-gp-l-244-043`, local block storage, same 32+8 reader budget | Matched four-shard synthetic inputs; full scans, translated and aligned crops; chunks 16/64/256/1024 KiB and block sweep | 56 settings, 68 workloads, 204 accepted repetitions. Two cache-residency failures and canceled other-node allocation retained. Final results resume earlier accepted cases | `tmp/2026-09-16-damacy-pr160-pareto/storage-job-3717912/results`; provenance maps to 3717174/3717813/3717912; report and `storage-provenance.csv` |
| Sept 23 shard-grid and paired CPU scheduling control | PR160 vs PR164 `ec2a6ed0ee1468e41eb70ee19eee6101f9dbbeb2`; TensorStore 0.1.85 | 48-core Turin allocation, 32 decode/copy participants, 16 readers, local storage | Synthetic smooth4, 16 GiB uint16 volume, sixteen raw 1 GiB shards; fixed 64 KiB chunks/16 KiB blocks; crop/aligned/scan controls | Main paired rerun 84 timings + 28 preflight + 18 traces. Fixed-layout implementation control, not a chunk optimum. Separate shard-grid parent handled by concurrency analysis | `tmp/2026-09-23-damacy-pr164-before-after/job-3806589/{results,report}`; original report presentation retained. Earlier pilot `tmp/2026-09-23-damacy-pr160-shard-grid` |
| Sept 24 readahead and buffers | PR164 plus controls; TensorStore 0.1.85 | Same Turin 48-core allocation / 32 decode participants, 16 file readers, local storage | Same 16 GiB smooth4 volume and fixed 64/16 KiB encoding; crop/scan | Readahead/handle lifetime: 90 timings; buffer capacity: 84 timings. Separate preflight and traces. Distinct implementation phases, not extra repetitions of PR168 | `tmp/2026-09-24-damacy-cold-readahead/job-3808884` and `tmp/2026-09-24-damacy-cpu-read-buffers/job-3810330` |
| Sept 24 small-chunk Pareto | PR168 `8d0931e7d131fd5d4c565458736ab586012c78c1` + benchmark controls; TensorStore 0.1.85 | Turin local storage, 32 decode/copy participants and 16 readers; host float32 output | Synthetic smooth4 16 GiB; chunks 16/32/64/128 KiB, all depth one; fixed 16 KiB blocks; translated `[1,256,256]` crops and complete scan tiles `[8,256,256]` | 144 timings, 48 preflight conditions and 48 separate traces; three interleaved repeats. One setup failure; report corrections duplicate observations | `tmp/2026-09-24-damacy-cold-chunks/job-3811387/{results,report}`; `CORRECTIONS.md`, reports `report-original` and `report-first-review` |
| Sept 24–25 chunk/block Pareto | Same PR168 sources and controls; TensorStore 0.1.85 | `cpu-turin-gp-l-244-025`, local storage, same resource budget | Same synthetic volume; 32/128/512 KiB depth-one chunks; 4–512 KiB blocks, LZ4/Zstd, bitshuffle | 20 encodings, 360 timing repetitions +120 preflight +120 separate traces; three shuffled rounds. Complete; original/presented reports have identical CSVs | `tmp/2026-09-24-damacy-cold-blocks/job-3822266/results`; `report-presented/FINDINGS.md` |
| Sept 25 NFS/local spot check | Same PR168 sources/controls and TensorStore 0.1.85 | 48-core Turin allocation, 32 decode/copy participants, 16 readers; adjacent NFS/local conditions | Byte-identical smooth4 volume, sixteen raw 1 GiB shards; Zstd 32/32,128/128,512/512 and LZ4 512/512 KiB; crops/scans | 144 timing repetitions, 48 preflight; three shuffled rounds with alternating local/NFS order. Complete, limited four-encoding coverage | `tmp/2026-09-25-damacy-nfs-spot/job-3832563/{results,report}`; `FINDINGS.md`, runtime `nfs-filesystem.txt`, mountstats |
| Sept 25 L40 comparison | Frozen native sources, future GPU/CPU study | L40 measurement intended; preparation stage recorded | Reuses NFS spot input; no retained performance results at first inspection | Root STATE stale: job-3833138 started 2026-09-25T16:48:29Z and has build/configure records, but no finished/exit/results file. Treat as incomplete and inspect actual artifacts at export time | `tmp/2026-09-25-damacy-l40-nfs/job-3833138`; do not treat plan/schedule as measured rows |

The modern raw measurement JSONs are small metadata records (about 0.4–3 MB per original phase and roughly 25–44 MB per recent result tree excluding references). Large query reference JSONs and payloads are unnecessary for basic export; source hashes and recorded geometry are retained. Historical raw runs live alongside summaries, so report-selected subsets must not replace them.

### Definitions and claims to test

- Modern chunk KiB and 1 GiB shard sizes mean actual uncompressed uint16 capacities. Stored shard files include encoded chunks and indexes and vary by codec/block size. Initial 1 MiB chunks span eight Z planes; recent 512 KiB chunks span one. Equal bytes alone do not match geometry.
- Original PR160 warm full-scan Pareto maximizes compression and useful output; warm query frontiers minimize encoded bytes per useful byte while maximizing throughput. The cold query frontier minimizes measured storage bytes per useful byte and maximizes throughput. Sept 24 compression-axis revisions maximize raw uint16/stored-shard bytes and returned float32 throughput; retain earlier traffic-axis frontiers. No read-side 10% output-size winner rule was specified.
- Original cold-study primary rates include eviction/residency checks; recent studies primarily show active read timing, with controls outside. Both retain wall rates. Do not combine these rates without naming their interval.
- Modern local cold passes require zero client-file residency and independent page-union lower bounds, but allow reuse within a pass. NFS additionally leaves server caches uncontrolled; NFS payload/latency counters are shared-mount counters. Process read_bytes is not an NFS traffic counter. Contemporary mount records exist in the NFS spot job.
- June memory's `nconnect=16` explanation is a hypothesis, not measured causality. Several shard counts exist, but files touched, active file calls, and NFS connections have different meanings. The root concurrency analysis handles the shard-count evidence.
- The local small-chunk sweep is the direct source for a near-32 KiB crop preference, but uses synthetic content. The four-encoding NFS spot check favors larger chunks among tested candidates and is a counterexample to transferring the local optimum. Modern complete full-scan controls exist; alignment-only controls preserve crop size but Z extents can still cut chunks.
- June TensorStore JSONs can count native/source bytes while Damacy counts float32 output; the archival comparison block also reports pushed samples including warmup against steady-state time. RNG warmup consumption and output placement require source review before absolute comparisons. Preserve original quantities; do not use the old comparison headline as normalized evidence.
- No read result measures a training loop or interactive viewer. TensorStore data-generation/readback time is not conversion throughput or peak-memory evidence.

The remaining scope questions are empirical gaps: real-microscopy 16–64 KiB layout sweeps were not located on the read side; nconnect-matched causal controls are not established; and the L40 study was incomplete at inventory time. These gaps do not prevent the existing CPU/read exports. The completed read aggregation is described in `read-findings.md`: 3,182 retained rows, 719 summaries, explicit failures/exclusions, and portable summary reproduction from the shipped rows.

## Chucky write evidence inventory

Inventoried on 2026-09-25 from existing metadata and result files. No benchmark,
build, test suite, allocation, or microscopy payload scan was run.

The complete source checkout is
`~/tmp/2026-09-07-chucky-microscopy-pr/worktree` (HEAD
`e3cd3af6c669c99d2b15bbebf9e95a6132319f09`, clean when inspected), abbreviated
`W` below. The current `~/src/chucky` checkout is `d33ea36f95bca3d6cb56ab79322971380f925bc9`
with existing working changes; its microscopy index contains only the first two
studies. W's index contains eleven and selects portions of five for the current
report. Measurement/build revisions are retained inside each study and differ
from either current checkout revision.

| Experiment family | Date; machine/backend | Data and workload | Swept controls/repetitions; state | Original records / retained report |
| --- | --- | --- | --- | --- |
| First microscopy sweep | 2026-09-12; Reef L40 CPU/GPU | Six microscopy inputs, preloaded raw cyclic streaming replay | 60 configurations, three retained executions each; 256 KiB chunks; historical | `~/src/chucky/bench/results/reef-l40-432380c-20260912-microscopy-256k.json`; W/`build-microscopy-l40-256k` |
| Runtime calibration | 2026-09-13; L40 CPU/GPU | Microscopy replay and separate synthetic ORCA2 controls | 273 records; timing/minimum-work profiles and confirmation. Two earlier runtime series retain another 108 + 24 executions. Native retries may expose only their final result and aggregate discarded time | `~/tmp/2026-09-13-microscopy-calibration-3666599/calibration.json`; identical working archive under W/`build-microscopy-calibration-20260913`; precursor `~/tmp/2026-09-13-microscopy-runtime/{calibration,cpu-control-repeat}/executions.jsonl` |
| Pilot and discovery | 2026-09-13; L40 CPU/GPU; discard | COSEM first crop, BBBC022; raw-pack streaming replay | Pilot 48 executions; discovery 400. Chunks, codec, block request, backend; independent phases | W/`build-microscopy-study-20260913/{pilot-3667862,discovery-3667908}/study.json`; discovery retained as `reef-l40-20260913/study.json` |
| Initial sink comparison | 2026-09-13; L40 CPU/GPU; discard/shared NFS | COSEM first crop, BBBC022 replay | 416 executions, paired rounds and bracketing references; historical | W/`build-microscopy-next-experiment-20260913/run-3671242/study.json`; retained `reef-l40-sinks-20260913/study.json` |
| Output buffers and recovery | 2026-09-13–14; L40 CPU/GPU; shared NFS/discard | COSEM first crop and separate larger COSEM v2 source; fixed-layout replay with controlled arrivals and pauses | First study: 52 observations, 12 recovery observations, six low-level I/O references. Second: 56 observations, 12 recovery observations, four old-crop references | W/`build-microscopy-output-pool-20260913/run-3671630/study.json`; W/`build-microscopy-cosem-v2-20260914/run-3681071/study.json` |
| Four-versus-16 target shards | 2026-09-14; L40 CPU/GPU; shared NFS | COSEM v2 and BBBC022 replay | 256 observations, eight paired rounds; actual counts 4 versus 16/15; selected three settings per input | W/`build-microscopy-shards-20260914/run-3684715/study.json`; `analysis/comparisons.csv`, `analysis/summary.json`. Exported by the concurrency analysis |
| Filesystem screen | 2026-09-14–15; L40 CPU/GPU; NFS | COSEM v2, BBBC022 replay | 300 executions; chunks, blocks, codecs; earlier screen retained | W/`build-microscopy-fs-pareto-20260914/run-3689339/study.json`; retained `reef-l40-filesystem-screen-3689339/study.json` |
| Discard screen and five-input transfer | 2026-09-16; L40 CPU/GPU; discard and NFS | Core COSEM/BBBC022; DynaCell, OpenCell DNA/protein, BBBC010, JUMP | 200 and 240 executions respectively; two-round screens; transfer uses selected settings, not a complete grid | W/`build-microscopy-final-20260916/run-3702747/{discard,transfer}/study.json`; corresponding retained archives |
| Final core confirmation and DynaCell refinement | 2026-09-16; L40 CPU/GPU core, GPU refinement; discard and NFS | COSEM v2/BBBC022 and DynaCell replay | 268 and 52 executions, three rounds; 84+16 configurations, 252+48 samples, 16+4 references | W/`build-microscopy-confirmation-3rounds-20260916/run-3704091/{confirmation,refinement}/study.json`; current GPU report selection |
| CPU worker comparison and failed precursor | 2026-09-16; Turin CPU and L40 GPU; discard and NFS | Five inputs; depth-four replay | Complete Turin and L40 studies: 110 executions each. Failed Turin precursor: 17 records, including one recorded error. BBBC010 and DynaCell depth-four chunks repeat their sole source plane; their apparent compression advantage was withdrawn | W/`build-microscopy-cpu-scaling-20260916/{turin-3708156,turin-3708278,l40-3708541}/study.json`; two complete studies retained but omitted from current report |
| Cancelled full CPU attempt | 2026-09-16; Turin CPU | Pre-correction replay geometry | Eight references and no samples; checkpoint still says `running`, surrounding archive records cancellation | W/`build-microscopy-unified-20260916/turin-3710801/study.json` |
| Corrected CPU core and transfer | 2026-09-16; Turin CPU, 32 compression workers in 40-core allocation; discard/NFS | Seven inputs; core depth 4, transfer depth 1 | 158+272 executions; 134 configurations, 402 samples, 28 references; three rounds; current CPU selection | W/`build-microscopy-unified-corrected-20260916/turin-3710982/{core,transfer}/study.json`; retained `reef-turin-microscopy-pareto-{core,transfer}-3710982/study.json` |
| Separate synthetic Blosc Pareto | 2026-09-05–06; RTX 5070 laptop, RTX 5080, L40 GPU | Generated `orca2_single`, not microscopy | L40/5080 raw repetitions retained; 5070 summary only; chunks/blocks/codec/shuffle; discard sink | `docs/benchmarks/blosc-{rtx5070-20260905,rtx5080-20260905,l40-20260906}`; `pareto.html` |

The microscopy report is `microscopy.html`, and its source selection is
W/`bench/studies/microscopy/index.json#/report`: 238 configurations and 674 sample
observations are selected, not the complete archive. Source copies under
top-level `~/tmp` folders, original job directories, main/alternate checkouts,
and generated sites overlap. Path-sanitized public archives have different
file hashes despite preserving measured values. Deduplicate by study and
execution identity plus measurement content; keep all source locators and all
nonduplicate phases. Do not count report rows as additional measurements.

All main microscopy Pareto experiments are raw-plane replay, not TIFF-to-Zarr
conversion. `bench/bench_input.c` preloads a raw pack and zero-pads XY to the
chunk grid; `bench_source_slice` cycles through that buffer. The timed loop
starts after preload/context/stream initialization and drained warmup. The
measurement includes final writer flush, close/metadata publication, and
`bench_zarr_flush`; the record separates append, drain, warmup and preparation
times. Closing does not establish crash durability. Native validity requires
pass/sufficient coverage, at least two warmup batches, four measured batches,
two generation transitions, minimum timing, and drain at most 10% of the measured
window. Study validation also enforces the requested timing/minimum logical work,
layout, source hash and settings. Unstable reference rates flag confirmation;
they are not a license to remove inconvenient measurements.

Chunk bytes and full shard capacities are **uncompressed** geometry. Microscopy
protocols normally constrain full shard capacity to 512 MiB–1 GiB; actual shapes
and active counts vary. The 16-shard request is soft. Earlier experiments use
four, and actual counts can be fewer than the request. Keep requested and actual
values separately.

`measurement.output_bytes` is `physical_sink_writes`: the sum of shard write
call lengths after subtracting warmup writes. `bench/sink_metering.c` does not
count presizing, truncation or append-metadata bytes; `bench/sink_discard.c`
counts lengths without storing files. Thus this is not a final filesystem size
census, and neither sink result supplies a strict final-stored-size winner.
The original report's fold is summed logical input bytes divided by summed
measured shard-write bytes across repetitions, with median logical GiB/s
throughput. The separately requested 10% rule is fold ≥ maximum fold / 1.10,
not 90% of maximum fold. The follow-up exports will label it as the original
measured sink-write proxy and preserve the unavailable final-size criterion.

Later retained studies preserve contemporaneous NFSv3/TCP `nconnect=16`,
1 MiB rsize/wsize and shared-export identities in `storage`; original job
folders preserve unredacted destinations and mount output. Early calibration's
`filesystem.txt` establishes NFS but lacks mount options. Machine profiles and
today's mount are context, not proof of historical settings. L40 and Turin
resource budgets and dates must remain separate.

Raw records contain process host peak/baseline counters, device free-memory
deltas and modeled allocation estimates, with different meanings. They do not
measure TIFF decoding or complete rechunking memory. No camera source-rate
requirement accompanies the Pareto phases. Output-pool/recovery studies have
controlled arrival-rate diagnostics and must remain separate from unpaced
finite replay. Later writer-adapter campaigns under
`~/tmp/2026-09-16-writer-comparison` are covered by the conversion inventory as
preloaded-input acquisition evidence, not complete conversions or the chunk
frontier.

Best leads for the claims: use the full indexed microscopy phases for the
16–64 KiB tradeoff and block-size comparisons; use the dedicated paired shard
study for 4 versus 16/15; use contemporaneous mount records for NFS context.
The archive has no matched nconnect sweep proving a shard/socket relationship,
and no final stored-byte census establishing the exact stated storage objective.
Earlier single-plane COSEM, withdrawn repeated-plane cases, limited transfer
grids, different CPU budgets and busy-NFS drift are material comparison limits.

The completed write export is `write-runs.csv`: 3,326 unique observations across
20 study families, including 3,325 recorded passes and one recorded error.
`write-source-manifest.json` lists originals and verified duplicate aliases.
`write-metadata.json` retains the indexed report selection, original plans,
machine/build/storage records and source-derived layout bounds. Derived summaries,
frontiers, winners, block comparisons and reference drift are regenerated by
`write-analysis.py`, including a portable mode using only the shipped rows.

## Shard and file concurrency inventory

Inventory date: 2026-09-25. These records were discovered without running experiments or reading microscopy payloads. Paths below are relative to `/mnt/main0/home/nclack` unless absolute. Analysis follows this inventory; counts and hypotheses here do not select an optimum.

| Family | Tool / revision | Dates / machine / backend | Destination and historical storage | Dataset / workload | Variables / repetitions / status | Retained evidence and report |
| --- | --- | --- | --- | --- | --- | --- |
| Paired microscopy shard targets | Chucky `3facc0dac1061ebc2a56bdd27a9c317dbda2e6f4` plus retained patch `69d01e5f365f5b476031a04695f63666f9abed46547b1e85683a321ba9dcd54a` | 2026-09-14; `cw-us-e4a2-l40-234-003`; CPU four compression workers and L40 GPU | Shared-home NFSv3; run-time `study.json.storage` records `nconnect=16`; filesystem samples and discard references remain separate | COSEM corpus v2 u8 and BBBC022 MitoTracker u16, cyclic preloaded streaming replay | Requested 4/16, actual 4/16 COSEM and 4/15 BBBC022; 3 selected codec/layout settings per input; 8 paired rounds; 192 samples plus 64 bracket references, all passed | `tmp/2026-09-07-chucky-microscopy-pr/worktree/build-microscopy-shards-20260914/run-3684715/study.json`; raw execution records, commands, plan and source patch retained; `analysis/comparisons.csv` and `analysis/summary.json` are derived, overlapping exports |
| CHAMMI file-layout sweep | Damacy reader and TensorStore layout preparation; recover measured reader revision per result | 2026-06-15; distinct L40 nodes for sparse confirmation (`cw-us-e4a2-l40-202-047`) and dense sweep (`cw-us-e4a2-l40-202-063`) | Shared `~/data/damacy` destination; historical mount details require separate evidence; cache-drop messages are advisory eviction | CHAMMI idr0017 microscopy, 512 selected arrays; crop reads after rechunking | 1/2/4/8/16/32/64/128 indexed shards per array plus unsharded and original layout controls; sparse and dense phases have 3 rounds, earlier exploratory records also retained | `tmp/2026-06-15-chammi-reformat/gpu_{job,job2,confirm,curve}.log`; raw `src/damacy/bench/runs/chammi-*/*/results.json`; scenarios and generation script in `data/damacy/scenarios`; old analyses select latest or last three and must not replace the complete record |
| Sixteen-shard paired CPU reads | Damacy PR160 `5126f0958c0be3922a0a00c49d127ba62ddbc6a9` plus pinned patches; TensorStore 0.1.85 | 2026-09-23/24; accepted runs on `cpu-turin-gp-l-244-025`; CPU only | Node-local XFS, verified from the historical job filesystem record | Synthetic smooth4 uint16, 16 GiB array; translated, aligned and full-array reads | Fixed sixteen 1 GiB raw shards, fixed 64 KiB chunks / 16 KiB Blosc blocks; 72 accepted backend repetitions; four separate instrumented read-overlap diagnostics; earlier failed cache diagnostics retained | `tmp/2026-09-23-damacy-pr160-shard-grid/job-3804536/report/{repetitions.csv,concurrency.json,README.md}` and original records from job 3804241 / continuation 3804536; report-only axis correction is a duplicate, not additional measurements |
| Later CPU read-overlap controls | Damacy PR164 and PR168 revisions; TensorStore 0.1.85; exact source records in `concurrency-sources.json` | 2026-09-23–25; `cpu-turin-gp-l-244-025`; CPU only | Node-local XFS; historical per-job filesystem records | Same synthetic smooth4 uint16 volume and sixteen raw 1 GiB shards; crop and full-scan diagnostics | 224 separate traces across scheduling, readahead, buffers, chunk and block studies; active shard counts and overlapping file-read calls are distinct fields | `tmp/2026-09-23-damacy-pr164-before-after/job-3806589/report/concurrency.csv`, `tmp/2026-09-24-damacy-{cold-readahead/job-3808884,cpu-read-buffers/job-3810330,cold-chunks/job-3811387,cold-blocks/job-3822266}/report/concurrency.csv`; these traces are excluded from timed throughput summaries |
| Synthetic Orca shard/write-size split | Chucky experimental checkout and retained patch; pin in environment/source records | 2026-09-04; separate L40 nodes for screening, confirmation and larger-write confirmation | Destination and run-time mount recorded in each results environment | Synthetic Orca streaming, not microscopy | Append-shard minimum and output write cap vary; paired/interleaved blocks; pilot manifest has no completed measurements | `tmp/2026-09-04-orca-shard-split/{pilot-results,results,confirm-results,large-split-results}/`; `runs.tsv` locates raw JSON/log pairs; do not pool phases or equate a split target with actual active files |
| NFS file/request-depth and multi-stream controls | Existing filesystem microbenchmarks and Chucky | 2026-08-24; CPU Turin and L40 nodes kept separate | Historical NFS probe logs retained; one-byte-domain/rate convention per harness | Uncompressed synthetic writes and filesystem controls | Request depth, file counts, request sizes, local/NFS target, 1/2/4/8 whole streams | `tmp/2026-08-24-nfs/{probe-cpu.log,probe-l40.log,streams.log,streams.sh,section2.md}`; narrative is a summary, not raw repeated trials |

The microscopy shard size is decoded capacity: layout metadata records chunk shapes, chunks per shard and `full_shard_bytes`. Four/16 comparisons change shard grouping, append-axis extent and per-file write size while retaining each matched chunk/codec/input. They do not isolate file count alone or locate a plateau above sixteen.

The paired sixteen-shard read experiment is a fixed-count diagnostic, not a count sweep. A batch spans sixteen files; measured peak simultaneous shard reads are separate quantities. Its own larger planned chunk/block sweep did not run; later independent chunk/block studies did complete and their diagnostics are retained as a separate family. The CHAMMI sweep has much smaller shards than 1 GiB and cannot be pooled with it.

Working-claim map: the September paired write study directly tests whether a larger shard layer helps; the June CHAMMI sweep tests distributing reads across files; the September diagnostic tests whether sixteen available files actually overlap. None alone tests whether an optimum tracks `nconnect`, because no matched change in connection count is established. Synthetic Orca/NFS controls provide implementation and variability context, not microscopy write-frontier evidence.

## Conversion evidence inventory

The retained conversion jobs found here are **Zarr v3 to Zarr v3** preparation jobs. They establish that the requested arrays were written, but do not measure conversion peak memory or comparable conversion throughput. No complete TIFF-to-Zarr or v2-to-v3 performance experiment was found in the scoped search below. Absence is limited to that search, not a claim about all cluster activity.

| Experiment family | Tool / revision | Date / machine / backend | Source and destination / storage | Dataset and workload | Variables / repetitions / status | Retained raw records / reports |
| --- | --- | --- | --- | --- | --- | --- |
| CHAMMI layout preparation | `make_sharded_chammi.py`, TensorStore requested `>=0.1.84`; installed version and code revision unknown | 2026-06-15; conversion CPU hostname not recorded; later L40 read jobs are separate | Existing v3 level-0 arrays in `/bio/projects/katamari/data/CHAMMI-75/train` to v3 arrays in `~/data/damacy/chammi-sharded`; both shared `/mnt/main0` paths; no contemporaneous conversion mount record found | 512 arrays from mixed studies and 512 idr0017 arrays; each worker reads a complete source array then writes one complete destination array | Nine recorded dataset/layout executions: mixed studies with one shard per array; idr0017 with 1, 2, 4, 8, 16, 32, 64, 128 shards per array. Sixteen array workers; one logged attempt per configuration; all report 512 written, zero errors | `~/tmp/2026-06-15-chammi-reformat/cpu_job{,2,3}.{sh,log}`; script `~/data/damacy/scenarios/make_sharded_chammi.py`; scenarios `~/data/damacy/scenarios/chammi/*.json`. First explicitly indexed destination metadata path is absent for every configuration; completion logs and scenarios remain. Project memory `chammi-reformat-test.md` summarizes subsequent reads, not conversion throughput |
| DynaCell bounded-window preparation | `reformat_dynacell.py`, TensorStore requested `>=0.1.84`; installed version and code revision unknown | 2026-06-15, `cpu-turin-gp-l-243-191`, CPU, job 2476048 | Existing sharded v3 under `/mnt/main0/data-sync/runai-cluster/runai-dynamic-imaging-models/dynamic-imaging-models-120t` to v3 under `~/tmp/2026-06-15-dynacell-reformat/store/{reformat,current}`; no historical mount record in conversion job | Fifty origin windows, each `[16,1,8,512,512]` float32, rather than complete source arrays | Two layouts, one recorded write of each; 16 workers; requested chunks `[1,1,1,128,128]` and `[1,1,4,256,256]`, respective output shards `[2,1,2,512,512]` and `[2,1,8,512,512]`; 32 and 8 shards per array logged; all 50 written with zero errors | Job script `cpu_rechunk.sh`, raw `logs/rechunk.log`, script, input/output scenarios retained. Explicitly indexed destination metadata retained. A single 18:02:53–18:03:03 job interval includes dependency installation and both conversions. `results-{current,reformat}.json` / `report-*.txt` measure later Damacy reads |
| Existing idr0017 unsharded reference | Actual converter and revision unknown | Path includes 2026-05-28; execution date and machine unverified | `/bio/projects/katamari/ivirshup/2026-05-28_rechunked/CHAMMI-75/train`; sampled current metadata is v3, uint8, `[1,1,1,256,256]` unsharded chunks | Used as a read comparison, without retained conversion execution records located | No conversion repetitions, resource records or timer found | `~/data/damacy/scenarios/chammi/ivirshup-idr0017.json`; subsequent GPU logs. Retain as a near miss, not a manufactured conversion attempt |
| September writer comparison | Chucky, TensorStore and other writers, with frozen source manifests; TensorStore 0.1.85 in frame/transaction studies | 2026-09-16 onward; Turin CPU and later GPU studies kept separate | Preloaded raw corpus packs to v3 outputs, NFS; per-study `storage-preflight.json` explicitly records `nconnect=16` | Finite replay and camera-input simulations, **not complete TIFF conversion**; raw image loading/padding/preparation precede writer timing | Includes source-frame versus large layer buffers, transactional TensorStore, and a retained TensorStore framewise timeout. Measured process RSS/high-water marks and 250 ms sampled timelines, configured cache/queue limits, and independent allocation requests must stay separate | `~/tmp/2026-09-16-writer-comparison/{input-preparation-comparison,tensorstore-transactions,tensorstore-frame-input,...}`. Raw `results/study.json`, per-run records/timelines, summaries and source snapshots remain; many output arrays intentionally cleaned up |
| TIFF-origin corpus preparation | Chucky corpus scripts, `tifffile` / NumPy; importer snapshots and recorded hashes available | 2026-09-08 OpenCell and 2026-09-13 BBBC022 | TIFF pages to headerless `.raw` packs, then separate preloaded replay | Source decode/pixel checks create corpus assets; no timed collection-of-TIFFs-to-Zarr job or conversion memory record found | Earlier BBBC022 576-field corpus and later 16-field subset are distinct preparations | `~/tmp/2026-09-08-opencell/{extract,store}.{sh,log}`; `~/tmp/2026-09-13-bbbc022-pilot.qFGPCw/{import.sh,slurm-3671605.log}`; `~/data/chucky-benchmarks-data/scripts/import_bbbc022.py` |
| COSEM corpus versions | `import_cosem.py`, NumPy and source Zarr reader; retained script hash | 2026-09-13; preparation job | Remote Zarr v2 source region to 32-plane uint8 `.raw` pack | “COSEM v2”, “corpus v3”, and binary format v2 are corpus/pack versions, **not Zarr v2-to-v3 conversion** | One cropped/downsampled-by-selection raw-pack preparation; source pixel equality and hashes recorded | `~/tmp/2026-09-13-cosem-stack.ruflut1h/{import_cosem.py,import.log,source/plan.json}` and `~/tmp/2026-09-13-microscopy-v3-rc1.gbqip5w3/notes.md` |
| Corpus geometry / recompression surveys | TensorStore reads plus NumPy / numcodecs; geometry analysis | 2026-06-15, CPU jobs | Metadata and sampled decompressed blocks; no complete destination Zarr generation | Read-amplification models, sampled compression, modeled whole-corpus stored-size impact | Configured per-array read caps are not measured memory; encoded sample sizes do not measure temporary disk peaks or complete conversion traffic | `~/tmp/2026-06-15-{corpus128,compression-survey,size-impact}` scripts, results JSON, reports and logs |

All shapes use the stored axis order. Conversion scripts use TCZYX; dtype byte sizes refer to uncompressed elements. Indexed current source metadata shows all selected CHAMMI arrays are uint8. Its 256² target chunks have 64 KiB capacity; edge clipping for small arrays in the mixed set produces capacities down to 11,648 bytes. DynaCell's new 128² float32 chunks have 64 KiB capacity; the comparison uses 1 MiB chunks. These conversion copies do not target 1 GiB output shards. DynaCell's respective destination shard capacities are 4 MiB and 16 MiB. Rounded `du -sh` observations (1010M / 1.9G / 5.3G) measure allocated disk use, not exact encoded payload or exact final stored bytes.

The conversion scripts read/decode source pixels and wait for destination write futures. They do not establish a durable-write policy, timed close/fsync boundary, measured source rereads, or actual simultaneous input/output file counts. Each Python worker materializes one complete source array (CHAMMI) or one bounded window (DynaCell) before the destination write. This is implementation evidence, not a measured process peak; TensorStore allocations, compression, caches and overlapping workers add unknown amounts. `max_gpu_memory_mb=8192` in copied Damacy scenarios controls later readers, not these CPU conversion processes.

The best concurrency lead is CHAMMI's later `gpu_curve.{sh,log}`, `gpu_confirm.{sh,log}`, `sweep.py`, `curve_fit.py` and matched scenarios. Its files-per-array counts must not be renamed acquisition append-layer counts or simultaneously active file counts. The memory note's claimed causal link to `nconnect=16` is an interpretation; the conversion records supply no changed-nconnect control. September writer preflights contain direct historical mount evidence, for example `tensorstore-transactions/storage-preflight.json` records node `cpu-turin-gp-l-243-211`, job 3715115 and `nconnect=16`.

The bounded discovery search examined job-root text files and one directory level below under `~/tmp`, with `.py`, `.sh`, `.md`, `.txt`, `.log` extensions and files at most 1 MB. It skipped builds, environments, stores, payload assets and source snapshots; the saved search manifest records 6,056 files / 33,757,706 bytes. Targeted follow-up read known scripts, logs, scenarios, current indexed metadata and project memory under the Damacy, Chucky, acquire-zarr and evolutionaryscale projects. No image or chunk payload was read. The companion conversion manifests record exact retained-source hashes, searched paths, scope and exclusions. This does not search every arbitrary directory or remote history.

Remaining questions are narrow: no complete TIFF-to-Zarr memory/throughput record; no v2-to-v3 run; no measured conversion host/device/pinned-memory peaks; no per-layout conversion timer; no conversion concurrency/memory-budget/processing-block sweep; no measured rereads, rewritten output bytes or temporary-disk peaks. Prompt 5 exports retain these nulls and list replay and preparation near misses separately.

## Recorded write-study provenance

This table expands the write families into their retained study records. Revisions here identify the runner; the compiled revision is separately recorded when known. Missing revisions or dates remain unknown. Status comes from the archived checkpoint; the canceled 3710801 study still says running there, as explained in its family entry. [The machine-readable index](inventory-write-studies.csv) includes full revisions, actual recorded destinations, original source paths, input IDs, workloads and status values. Each row points into `write-metadata.json`; observations resolve through `write-runs.csv`.

| Study | Date interval | Runner revision | Machine / backend | Storage | Observations / study status |
| --- | --- | --- | --- | --- | --- |
| reef-l40-microscopy-pilot-3667862 | 2026-09-13 → 2026-09-13 | d26258b96b77 | cw-us-e4a2-l40-234-199 / cpu, gpu | discard | 48 / complete |
| reef-l40-microscopy-discovery-3667908 | 2026-09-13 → 2026-09-13 | b1ebae5b62f1 | cw-us-e4a2-l40-202-047 / cpu, gpu | discard | 400 / complete |
| reef-l40-microscopy-sinks-3671242 | 2026-09-13 → 2026-09-13 | 9670f41b70e6 | cw-us-e4a2-l40-202-211 / cpu, gpu | discard, nfs | 416 / complete |
| reef-l40-filesystem-screen-3689339 | 2026-09-14 → 2026-09-15 | ed084d68cf1a | cw-us-e4a2-l40-202-211 / cpu, gpu | nfs | 300 / complete |
| reef-l40-final-discard-3702747 | 2026-09-16 → 2026-09-16 | a5adb2ebfea1 | cw-us-e4a2-l40-234-163 / cpu, gpu | discard | 200 / complete |
| reef-l40-final-transfer-3702747 | 2026-09-16 → 2026-09-16 | a5adb2ebfea1 | cw-us-e4a2-l40-234-163 / cpu, gpu | discard, nfs | 240 / complete |
| reef-l40-final-confirmation-3704091 | 2026-09-16 → 2026-09-16 | 06fc280b2810 | cw-us-e4a2-l40-202-189 / cpu, gpu | discard, nfs | 268 / complete |
| reef-l40-final-refinement-3704091 | 2026-09-16 → 2026-09-16 | 06fc280b2810 | cw-us-e4a2-l40-202-189 / gpu | discard, nfs | 52 / complete |
| reef-turin-microscopy-workers-3708156 | 2026-09-16 → unknown | ee1b50a2eb19 | cpu-turin-gp-l-243-211 / cpu | discard, nfs | 17 / failed |
| reef-turin-microscopy-workers-3708278 | 2026-09-16 → 2026-09-16 | 3f7425978806 | cpu-turin-gp-l-243-179 / cpu | discard, nfs | 110 / complete |
| reef-l40-microscopy-workers-3708541 | 2026-09-16 → 2026-09-16 | 3f7425978806 | cw-us-e4a2-l40-234-083 / gpu | discard, nfs | 110 / complete |
| reef-turin-microscopy-pareto-3710801 | 2026-09-16 → unknown | 99622b1e9bc6 | cpu-turin-gp-l-243-179 / cpu | discard, nfs | 8 / running |
| reef-turin-microscopy-pareto-core-3710982 | 2026-09-16 → 2026-09-16 | f30f20802ed7 | cpu-turin-gp-l-243-179 / cpu | discard, nfs | 158 / complete |
| reef-turin-microscopy-pareto-transfer-3710982 | 2026-09-16 → 2026-09-16 | f30f20802ed7 | cpu-turin-gp-l-243-179 / cpu | discard, nfs | 272 / complete |
| microscopy-calibration-3666599 | 2026-09-13 → unknown | 42e3e1878afd | cw-us-e4a2-l40-202-153 / cpu, gpu | discard, nfs | 273 / complete |
| microscopy-runtime-calibration-3666600 | 2026-09-13 → 2026-09-13 | 71edf9ecfe9f | cw-us-e4a2-l40-202-153 / cpu, gpu | discard | 108 / complete |
| microscopy-runtime-cpu-control-repeat-3667399 | 2026-09-13 → 2026-09-13 | 71edf9ecfe9f | cw-us-e4a2-l40-202-009 / cpu | discard | 24 / complete |
| reef-l40-432380c-20260912-microscopy-256k | 2026-09-12 → unknown | 432380c41403 | cw-us-e4a2-l40-202-193 / cpu, gpu | discard | 180 / complete |
| microscopy-output-pool | 2026-09-13 → 2026-09-13 | a8bf68e58388 | cw-us-e4a2-l40-234-199 / cpu, gpu | discard, nfs | 70 / complete |
| cosem-v2-output-buffers-20260914 | 2026-09-14 → 2026-09-14 | a8bf68e58388 | cw-us-e4a2-l40-234-079 / cpu, gpu | discard, nfs | 72 / complete |
