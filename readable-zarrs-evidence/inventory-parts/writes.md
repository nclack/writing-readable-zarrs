# Chucky write evidence inventory

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
