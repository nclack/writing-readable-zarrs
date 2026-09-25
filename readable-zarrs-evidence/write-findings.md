# Streaming write findings

Exported 3,326 recorded observations from 20 distinct microscopy/replay study families, including references, failures, calibration and fixed-layout controls. Public/path-sanitized copies were matched to original study executions and are listed as aliases in `write-metadata.json`; they add no observations. The dedicated shard-count study is covered by the separate concurrency export. Later writer-adapter campaigns are inventoried separately.

**The archive does not establish a final stored-size optimum.** Its output counter is measured shard-write call bytes, not a final filesystem census. `strict_final_stored_size_winner` is null throughout. The separately labeled proxy follows the original analysis: sum measured shard-write bytes / sum logical input bytes, then choose greatest median logical GiB/s at no more than 1.10 times the smallest proxy value in a comparable group. The comparison uses exact integer fractions for the threshold and retains exact throughput ties.

The current report selects 238 configurations and 674 sample observations from these exports. Its 28 input/backend/sink conditions have 15 proxy winners in 16–64 KiB and 13 above 64 KiB. This does not support a universal 16–64 KiB write preference. CPU and GPU results are different resource budgets on different machines, and several GPU transfer inputs have only five selected settings. The main grids test 16, 64 and 256 KiB; DynaCell adds 128 KiB. They do not directly establish a 32 KiB write result.

| Input | Backend / workers | Chunk / block request KiB | Codec | Logical GiB/s median [min,max] | Proxy extra bytes | Repeats |
| --- | --- | --- | --- | --- | --- | --- |
| bbbc010-brightfield | cpu / 32 | 64 / 64 | blosc-zstd | 5.602 [5.109, 5.654] | 0.00% | 3 |
| bbbc010-brightfield | gpu / 4 | 64 / 64 | blosc-zstd | 6.412 [6.393, 6.431] | 0.00% | 2 |
| bbbc022-mito | cpu / 32 | 64 / 64 | blosc-zstd | 5.215 [4.460, 5.245] | 0.07% | 3 |
| bbbc022-mito | gpu / 4 | 256 / 64 | blosc-zstd | 4.214 [4.172, 4.225] | 2.30% | 3 |
| cosem-cos7-em | cpu / 32 | 256 / — | zstd | 4.925 [4.463, 5.178] | 0.23% | 3 |
| cosem-cos7-em | gpu / 4 | 256 / — | zstd | 4.358 [4.278, 4.366] | 0.27% | 3 |
| dynacell-a549-phase | cpu / 32 | 16 / 4 | blosc-lz4 | 4.738 [2.994, 5.345] | 1.64% | 3 |
| dynacell-a549-phase | gpu / 4 | 16 / 4 | blosc-lz4 | 5.150 [4.215, 6.752] | 4.94% | 3 |
| jump-scope-fluorescence | cpu / 32 | 16 / 4 | blosc-lz4 | 5.541 [4.751, 5.575] | 7.27% | 3 |
| jump-scope-fluorescence | gpu / 4 | 256 / 64 | blosc-zstd | 3.524 [3.503, 3.545] | 0.00% | 2 |
| opencell-dna | cpu / 32 | 16 / 16 | blosc-lz4 | 5.389 [4.865, 6.117] | 7.92% | 3 |
| opencell-dna | gpu / 4 | 256 / 64 | blosc-zstd | 3.463 [3.391, 3.535] | 0.00% | 2 |
| opencell-protein | cpu / 32 | 16 / 16 | blosc-lz4 | 5.615 [4.777, 6.045] | 8.07% | 3 |
| opencell-protein | gpu / 4 | 256 / 64 | blosc-zstd | 3.105 [3.017, 3.193] | 0.00% | 2 |

These are observed ranges, not confidence intervals. `write-winners.csv` identifies all eligible rivals with overlapping ranges and the best tested smaller/larger eligible alternative. Shape, codec, requested block, actual shard geometry and resources vary together in a whole-configuration choice; the winning chunk byte count is not a controlled chunk-only effect.

Comparison groups preserve study/session, source hash and logical XY extent, dtype, replay depth/order, machine/backend, CPU allocation/worker count, sink/mount, output/I/O buffers, timing/minimum-work profile and memory budget. Earlier screens and later confirmations are never pooled. Corrected 32-worker Turin measurements replace the report view, not the retained earlier four-worker measurements. Repeated-plane-within-chunk observations are kept with an explicit exclusion. OpenCell depth-four worker controls remain separate from depth-one transfer studies.

The normalization removes unequal replay volumes by reporting measured shard writes per logical GiB. These are repeated cyclic inputs, with a shared source hash within each group; raw file totals are never compared across different run lengths. XY padding and final chunk padding stay in the output cost. Per-row start plane, complete source cycles, tail planes, actual shape, submitted bytes and padded chunk bytes expose finite-cycle differences. This is a measured average cost over each replay, not an exact census for an identical finite array. The aggregate fold is a ratio of byte sums; it is neither the arithmetic mean nor median of per-run folds.

Normalization audit of the current view: 198 of 674 samples end with a partial source cycle. All include at least 1,024 complete cycles; the largest tail is 0.0752% of logical frames. These small fractions quantify the difference; they are not a bound on compressed-size error. No exact equal-finite-volume assumption is used for proxy eligibility. Current sample windows span 3.001–16.588 s including drain, with at least 32 GiB logical input.

Source raw packs are fully loaded and XY-padded before the measured window. TIFF decoding and source I/O are not timed. Warmup is drained and excluded; measured elapsed time includes append, final drain, writer close/metadata publication and the filesystem queue flush. The counter excludes separately published metadata and counts write requests rather than durable storage. Record-level preparation, warmup, append, drain and process wall time are retained; they must not be interchanged.

The native coverage rule requires pass/sufficient coverage, at least two warmup batches, four measured batches, two generation transitions, minimum timing and final drain no more than 10% of measured time. Per-study minimum logical work and timing are also checked. Reference drift is retained rather than used to discard points. The frontiers require complete studies and valid sample records; failed/partial studies and controls remain visible in `write-summary.csv`.

1 exported observation(s) report more than one internal native attempt. Earlier internal attempts are not separately retained by the native benchmark; their aggregate discarded duration is preserved, and no artificial per-attempt throughput is created. Warmup byte/time measurements stay on their owning observation because they are not separate measured samples.

Host peak RSS is the Linux process lifetime high-water mark (RUSAGE_SELF), not complete TIFF conversion memory. Device used bytes are a free-memory delta, not a measured device peak; pinned and total estimates are modeled allocations. Source camera requirements are absent from the Pareto studies. Their coverage-qualified finite unpaced replay does not prove indefinite acquisition at a required rate. Controlled-arrival output-pool/recovery observations remain a separate family.

The matched Blosc request comparisons are in `write-block-comparisons.csv`. GPU subdivision is modeled from the retained implementation as min(requested block, chunk); an encoded-header measurement is absent. CPU effective subdivision is unknown. Interpret the export as a requested-block intervention at fixed chunk/codec/shuffle/backend and geometry, not an automatically measured effective block size.

NFSv3 nconnect=16 is retained only where a contemporaneous storage record supplies it; early NFS records without options remain unknown. L40 and Turin sample throughput must not be pooled. Two/three-round min–max ranges and bracket references show only the observed session. Matched rounds help compare block requests but do not remove between-session filesystem drift.

Block counterexample: at the same 16 KiB chunk, BBBC022 GPU Blosc-LZ4 with bitshuffle changes from 16.846 to 7.137 logical GiB/s on discard when the requested block increases from 4 to 16 KiB; observed ranges do not overlap. On NFS the corresponding medians are 5.890 and 6.329, with overlapping ranges. Thus a small block effect is not general; CPU discard 16 KiB comparisons are much closer and the filesystem can obscure the difference.

Bracketing reference variation is exported in `write-reference-drift.csv`, using references separately from sample throughput. Current NFS first→last reference rates (logical GiB/s): dynacell-a549-phase gpu 5.719→6.377; bbbc010-brightfield gpu 3.861→3.202; opencell-dna gpu 3.535→4.062; jump-scope-fluorescence gpu 4.763→3.840; opencell-protein gpu 4.504→3.615; opencell-dna cpu 3.381→3.238; dynacell-a549-phase cpu 4.412→3.516; cosem-cos7-em cpu 5.053→5.202; bbbc010-brightfield cpu 2.620→2.706; cosem-cos7-em gpu 4.291→5.362; opencell-protein cpu 3.819→2.597; jump-scope-fluorescence cpu 2.802→3.118; bbbc022-mito gpu 2.633→3.759; bbbc022-mito cpu 3.730→2.994. These do not establish network load as the cause; they demonstrate within-session variation that limits narrow ranking claims.


Reproduce with `python3 write-analysis.py --worktree /path/to/archived/chucky --main /path/to/chucky --output .`. Portable regeneration from shipped observations requires no source checkout: `python3 write-analysis.py --from-rows write-runs.csv --metadata write-metadata.json --output regenerated`. No third-party packages, benchmarks or Slurm jobs are used.
