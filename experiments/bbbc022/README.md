# BBBC022 read/write and shard-count experiments

The frozen plan is [plan.json](plan.json). Cluster runs and retained arrays live
under `/mnt/main0/home/nclack/tmp/2026-09-25-bbbc022-read-write`.

Only BBBC022 MitoTracker is used: 16 independent 520 × 696 uint16 planes,
replayed cyclically from plane zero. The source SHA-256 is
`1eff677d3f7d6785bdc8e65079613d6ba2c801a19f33503517a12b8df54affc7`.
The larger arrays contain repeated fields, not additional independent images.

The source sample contains one mock-control well from each plate row A–P,
plate 20585, site 1, channel w5. [input-source.json](input-source.json) preserves
the selection rule, TIFF names and hashes from the original import manifest.
The images come from [BBBC022v1](https://bbbc.broadinstitute.org/BBBC022),
Gustafsdottir and colleagues' U2OS Cell Painting experiment, distributed through
the Broad Bioimage Benchmark Collection under CC0.

## Shared layouts

Six depth-one chunk shapes span 16–512 KiB, with fixed `[2048,512,512]` shards
and four files per append layer. GPU Blosc-Zstd uses bitshuffle, a 16 KiB block
setting and level hint 3. The level is a hint for this GPU backend.

Every retained array has shape `[32768,520,696]`: 22.08984375 GiB of logical
pixels. Submitted data include zero padding to the chunk grid: 27, 30, 30,
36, 48 and 64 GiB across increasing chunk sizes. Padding is part of the layout
cost for this image extent.

[writer.patch](writer.patch) adds explicit shard geometry and an exact-volume
mode to the frozen Chucky benchmark. A separate discard stream warms the same
process, then a new filesystem stream starts at source plane zero. Timing runs
from the first append through flush, close, metadata publication and final
filesystem drain. Source loading, context initialization, stream initialization
and separate warmup are recorded outside that interval. The measured stream
must contain exactly the requested frames; it cannot extend or retry.
The interval includes filesystem I/O completion; it does not establish
crash-durable storage.

The fixed-volume timing policy is distinct from the earlier replay studies.
It requires four complete batches, two generation transitions, at least 0.25 s
of appending and a final drain fraction no greater than 10%. A rejected run is
retained as a failure. Discard warmup may retry under the existing benchmark
rules; its complete cost is included in `separate_warmup_s` and its stderr log.
Process peak host memory includes that warmup.

Before measurement, six 17-frame stores must match the source pixel for pixel,
including frame 16 repeating source plane zero. These short native runs are
expected to return `insufficient_coverage` after closing the output; they are
correctness checks, not performance observations. Larger retained stores are
checked with complete planes covering all source phases, the tail, midpoint
and both sides of every shard-generation boundary.

The CPU read protocol uses Damacy and TensorStore with 32 decode/copy workers,
16 I/O workers, contiguous float32 host output and no decoded-data cache.
It saves identical query traces across layouts and readers, including translated
256 × 256 crops, aligned and translated 512 × 512 crops with matching frame
lists, and exact full-frame scans of the logical array. Each observation runs
in a fresh process. Shard indexes are warmed outside timing; file-specific
client cache eviction is verified before each pass. Server cache state is
uncontrolled. Three interleaved repetitions require 10 s active time and 1 GiB
of useful uint16 source bytes; returned float32 bytes are twice that amount.

## Shard counts

The Blosc-LZ4 series fixes `[4,64,128]` chunks, 16 KiB blocks, bitshuffle and
level hint 3. Requested targets 4, 12, 16 and 48 yield 4, 9, 15 and 30 actual
files per layer. Target 32 duplicates target 16 and is not a distinct case.
The maximum is 54. It is added for the last three rounds only if the median
paired 30/15 rate ratio exceeds 1.05 after three rounds and at least 1,200 s
remain. This conditional extension has fewer repetitions and must be labeled.

The limited Blosc-Zstd control keeps `[4,128,256]` chunks, 256 KiB blocks,
bitshuffle and level hint 3, comparing four and fifteen files per layer.
Fifteen is the maximum for that fixed chunk grid.

All cases use a 65,536-frame geometry reference so even the 54-file layout can
retain approximately 1 GiB raw shard capacity. The original coverage timing
policy remains in force: 2 s requested warmup, at least 3 s append time,
32 GiB minimum logical input, four batches, two generation transitions and
final drain at most 10% of elapsed time. Actual measured volume can exceed the
minimum, especially at the upper shard counts. Six shuffled rounds include
fifteen-file reference observations before and after each round.

The writer uses four output buffers, 32 filesystem workers, four CPU workers,
64 MiB target batches and a four-write limit per file. Mount settings are
recorded and held unchanged. The result concerns achievable layouts, including
their changed grouping and append-axis extent; it does not isolate file count
or establish an optimum tied to `nconnect`.

The completed primary series did not trigger its conditional extension:
the first three paired 30/15 ratios had median 0.995528. Across all six rounds,
the median was 1.101446, with individual ratios from 0.858860 to 1.224117.
The fifteen-shard references also varied substantially, including a 48.5%
before-to-after drop in round two. This is not a stable throughput ceiling.

That later result motivated a separate follow-up using
[extend_shards.py](extend_shards.py) and
[run_gpu_extension.sh](run_gpu_extension.sh). Three paired rounds compare
30 and 54 shards, with fifteen-shard references before and after each pair.
All twelve observations use a common 96 GiB minimum logical input, enough
for two complete generations of the 54-shard layout. The original binary,
codec, chunks, resource limits and timing policy are retained. The schedule
and the reason for this later decision are saved before measurement.

This follow-up runs after the CPU reads finish. Its records, summaries and
completion marker are separate from the primary 32 GiB series. It does not
rewrite the original stopping decision or add observations to its six rounds.

## Execution and evidence

The user authorized execution with an initial cumulative allocation budget of
two hours on CPU nodes and two hours on one L40. Build, setup, failed attempts
and measurements count against those caps. Jobs run on Slurm compute nodes;
scripts, logs and surviving artifacts stay on shared storage. No benchmark is
run on the login node.

[run_cpu_build.sh](run_cpu_build.sh) builds the frozen CPU reader and L40 writer.
[reader-source.md](reader-source.md) identifies the reader's base revision and
single cumulative [source patch](reader.patch). Static reconstruction matches
all 310 frozen native source hashes; overlapping older patches are not applied
again.
[run_gpu.sh](run_gpu.sh) runs writer tests, pixel checks and measurements using
[write_benchmark.py](write_benchmark.py). [read_benchmark.py](read_benchmark.py)
preserves each scheduled read case, its checks, counters, timings and terminal
status. A result is accepted only after a successful process exit.

[run_cpu_reads.sh](run_cpu_reads.sh) checks both readers on all six retained
layouts before the 144 read observations. [account_stores.py](account_stores.py)
uses recorded counters and file metadata to verify final-size accounting.
[size-accounting.md](size-accounting.md) explains the write-path identity and
the measured correction, which is below 0.0012% of final file length.
[export_evidence.py](export_evidence.py) packages the recorded results, source
identities, query traces and plots. Its `--from-bundle` mode regenerates the
analysis without the original cluster directories.

[run_cpu_export.sh](run_cpu_export.sh) exports the complete evidence on a
four-CPU allocation, verifies that portable regeneration reproduces every
CSV, findings and validation file, and creates a checked archive. Its Slurm
ledger includes failed attempts and uses the final export job's full time
limit as a conservative bound while that job is still running.

The older `readable-zarrs-evidence` archive remains a separate snapshot. New
observations and any interoperability fixes must retain their own source,
binary, configuration and timing-policy identities.

## Integer fill-value compatibility

The first pixel check exposed a writer metadata issue: Chucky serialized the
uint16 array's zero fill as `0.0`. TensorStore read it successfully, while
Damacy rejected the metadata with a generic decode error. Integer fill values
must omit fractional and exponent parts under the
[Zarr specification](https://zarr-specs.readthedocs.io/en/latest/v3/data-types/index.html#permitted-fill-values).

[diagnose_reads.py](diagnose_reads.py) preserves the original array and checks
the first encoded chunk directly with the reader's Blosc library. It then
tests a separate metadata view with integer zero and unchanged shard files.
[writer-fill-value.patch](writer-fill-value.patch) makes the isolated writer
emit integer zero for integer dtypes, so subsequent arrays can be read directly.
The experiment uses zero fill only; handling nonzero integer fills is outside
this patch. No reader decoding or pixel encoding code is changed.

## Metering capacity and the shard restart

The first shard sweep reached the conditional 54-shard layout, then failed
before producing a timing observation. The benchmark's metering wrapper had
only 32 file slots. [writer-metering.patch](writer-metering.patch) raises that
bookkeeping capacity to 64; [metering-failure.md](metering-failure.md) traces
the failure and records the source hashes.

[run_cpu_meter_fix.sh](run_cpu_meter_fix.sh) rebuilds the benchmark and its
check binaries. The next GPU preflight adds a 17-frame LZ4 store with 54 shards
and checks every pixel. The complete shard experiment then restarts with the
patched binary, so its comparisons share the same implementation.

The 18 completed shared-layout observations and their retained arrays come
from the earlier binary. They are carried forward unchanged, with their
original job and binary identities. The interrupted shard observations remain
in a separate supplementary table. The restart follows the bookkeeping
failure and does not select observations by rate.
