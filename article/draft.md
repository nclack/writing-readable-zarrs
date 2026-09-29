# Writing readable Zarrs
Nathan Clack, 2026 September

Microscopy data need to support visualization, model training, and processing
with arrays. A viewer or training pipeline often needs a small region at an
arbitrary position; an analysis may need every value. The way we arrange data
on disk can make one of these tasks fast and the other slow. Usually we want to
keep one stored representation that serves both, while remaining practical to
write during acquisition or conversion.

Zarr divides an array into **chunks**: rectangular blocks stored and usually
compressed together. **Decoding** reconstructs their array values during a read.
We can describe the main reads as **random, unaligned crops**, small regions
whose positions are not constrained to the chunk grid, and **full-array scans**,
which collectively read every value. Choosing chunk dimensions means balancing
these two patterns.

The approach used here is to measure read and write **throughput**, useful
array bytes processed per second, and analyze **Pareto frontiers**. A frontier
retains tested choices for which no
alternative is at least as good on every objective and better on at least
one. For example, improving crop throughput may mean sacrificing full-array
throughput; writing faster may mean accepting larger stored files.
We compare these tradeoffs, favor cropped reads for visualization and training,
then check whether the resulting layout can be written fast enough and converted
within a memory budget.

The measurements below support testing **128 KiB of uncompressed values per
chunk** as a starting compromise (1 KiB = 1,024 bytes). The case combines crop
and full-array read performance with writing capacity and stored size. It
does not require one layout to be fastest for every reader or workload.

## Read workloads

Consider a vision transformer accepting 224 × 224-pixel images. It divides
each input into 16 × 16 patches, represented as **tokens**, the model's input
units. Storage still needs to supply the whole image crop, potentially from
any position. Random crops approximate these training requests and some
visualization reads; their sizes will vary across applications.

For either workload, performance also depends on which requests are processed
together and whether a **cache** retains previously loaded data in memory.
Sharing work between requests can change performance even when crop dimensions
stay the same.

Here, the measured crops are 256 × 256 pixels in one image plane, placed
without regard to chunk boundaries. The full-array workload instead covers
every value using a fixed grid of selections. Individual selections need not
cover whole chunks, so sharing decoded chunks between requests can matter
even when the workload eventually uses every pixel.

## Chunk size

Reading part of a compressed chunk generally requires decoding the whole
chunk. We use uint16 pixels—unsigned 16-bit integers occupying two bytes each.
Shapes are written as `[Z,Y,X]`: numbers of planes, rows and columns. Thus
`[1,128,128]` uint16 chunks occupy 32 KiB before compression, while
`[1,256,256]` uint16 chunks occupy 128 KiB.

A translated 256 × 256 crop, meaning the same-sized selection moved to another
position, can intersect nine 128 × 128 uint16 chunks or four 256 × 256
uint16 chunks in one plane (Figure 1a). These cases require decoding 2.25 or
4 times the requested pixels.
**Decode amplification** is decoded chunk bytes divided by useful requested
bytes.

Keep chunks as low-dimensional as possible. For XY crops from one plane, time
point and channel, keep those chunk dimensions at one unless the workload
requires grouping them. The penalties multiply across axes: decoding a whole
chunk spanning eight planes and four channels for one such crop causes 32×
decode amplification, even before XY boundary waste.

Sharing decoded chunks across requests can reduce that work. Compression,
combined storage requests and file caching also change how much data must be
transferred. Smaller chunks
reduce boundary waste but create more chunks to locate, schedule and decode.
Throughput measurements capture the combined effect of these costs.

The Zarr readers [Damacy][] and [TensorStore][] were tested on a local
solid-state drive using NVMe, a storage interface designed for these drives.
Damacy is a reader I developed, optimized for loading data for model training.
TensorStore is a popular library for reading and writing large arrays. Here, both
readers decode synthetic image data on the computer's main processor (CPU)
and return float32 values, 32-bit floating-point numbers occupying four bytes
each. I report useful uint16 input bytes per second; rates counting the larger
output values would be twice as high.

A **codec** converts values into their stored representation (**encoding**)
and reconstructs them (**decoding**). These tests use Blosc with the
Zstandard compressor, abbreviated Zstd, or LZ4. Blosc can divide a chunk
into smaller compression **blocks**, a separate choice from storage chunk
dimensions. Figure 1b–c holds that block setting at 16 KiB. [Read data and
definitions][read-methods].

Figure 1b–c compares the two read workloads for three chunk layouts, keeping
the reader, compressor and compression block size fixed. Each point pairs a
layout's crop rate with its full-array read rate. The points show medians—the
middle values of three repeated measurements—and the bars show their observed
ranges. These panels help assess a balance between workloads; the broader
[read frontiers][read-frontiers] also account for compression or read traffic.

![A random-position crop intersects extra chunks; two local NVMe plots show the balance between crop and full-array reads for Damacy and TensorStore. Each point pairs rates for one chunk layout: crop reads horizontally and full-array reads vertically.][figure-1]

**Figure 1. Chunk geometry and read performance.** **a,** A 256 × 256 crop
at row 64, column 64 intersects nine 128 × 128 uint16 chunks or four
256 × 256 uint16 chunks (32 or 128 KiB per chunk). This chosen position
illustrates unused decoded pixels, not average amplification. **b–c,**
Damacy and TensorStore read a 16 GiB synthetic uint16 array from local NVMe
with CPU decoding, Blosc-Zstd and 16 KiB blocks. Each point pairs a layout's
median crop and full-array read rates from separate workloads; bars show
observed minima and maxima from three repetitions. Right means faster crops;
up means faster full-array reads. Vertical scales differ. Chunk dimensions
are Z × Y × X in uint16 pixels. Tables locating chunks are already loaded;
file data start outside the operating system's memory cache, with reuse
allowed during a pass. Rates count useful uint16 bytes over planning,
reading, decoding, conversion and output assembly. [Read summaries][read-summary].

For Damacy, 128 KiB captures much of the benefit of larger chunks for full-array
reads while retaining most of the small-chunk crop performance. Relative to
32 KiB, its crop rate falls from 2.007 to 1.749 GiB/s, a 13% loss, while its
full-array rate rises from 5.690 to 11.246 GiB/s, nearly doubling. Moving on to
512 KiB (`[1,512,512]` uint16) loses another 27% of crop throughput for a 14%
full-array gain. That makes 128 KiB a useful candidate when cropped reads
matter more, but full-array processing still needs to be practical.

TensorStore provides a different check. Its full-array rates at 128 and
512 KiB are not clearly separated by these repeats: the observed ranges are
4.54–5.63 and 4.46–5.36 GiB/s, respectively. The 512 KiB median is higher,
but these measurements do not establish a reliable full-array advantage.
Its crop result is clearer: 512 KiB reaches 1.614 GiB/s versus 1.394 at
128 KiB, a 16% gain, with non-overlapping observed ranges. This is evidence
for testing larger chunks when TensorStore crop performance is the priority,
not a reason to select them from full-array medians alone.

In these TensorStore runs, moving from 128 to 512 KiB nearly halves the
estimated number of chunks processed while more than doubling the measured
file bytes read. Fewer chunk lookups and scheduling operations may explain
the speedup, but the measurements do not isolate its cause. A larger dataset
or less overlap could change the balance.
[Read-cost audit][tensorstore-chunk-costs].

The best chunk size also depends on storage. These local NVMe results are most
relevant to systems that sustain many small reads. An illustrative capability
range is 10,000–100,000 read **IOPS** (input/output operations per second) at the
relevant request sizes; these benchmarks do not establish an IOPS threshold.
When that operation rate limits throughput, larger chunks can help: fewer
requests can outweigh the extra bytes read and decoded.
[I/O size and throughput][storage-iops].

## Shards

Small chunks need not mean millions of small files. A **shard** groups
encoded chunks with an **index**, a table locating each chunk's bytes. On the
filesystems discussed here, each shard is a file. A **range read** fetches a
specified interval of file bytes, allowing selected chunks to be read without
loading the whole shard.

Chunk shape controls the unit of decoding; shard shape controls file
grouping (Figure 2a). Two considerations guide shard size and shape. The
first is **filesystem concurrency**: spreading work across enough files for
the filesystem to operate on them in parallel. For streaming writes, the
layout should distribute incoming data evenly across those files.

The second is the total number of files in the Zarr dataset. Larger shards
group more chunks into each file, reducing the number of files to list, copy
or move. Choose a target file count that makes the complete dataset practical
to manage while retaining enough files to keep the writer busy.

Storage also imposes practical limits. Filesystems may limit the number of
**inodes**, the records describing individual files and directories, so a
dataset can exhaust the available file count before filling the disk
([inode allocation][inode-allocation]). In Amazon S3, each shard is an
**object**, a separately named stored item. Large objects can use **multipart
upload**, which sends an object in parts before assembling it. Object size,
part size and the number of parts must fit the [service's limits][s3-upload-limits].
Those size limits apply to stored bytes, after compression.

Here, the read comparisons keep sixteen shards fixed, based on what looked
like a good write configuration. Each has 1 GiB of **raw capacity**, its size
before compression. Chunk size varies within this fixed shard layout.

## Write workloads

Two writing workloads are considered here. **Streaming** accepts images arriving
during acquisition or perhaps from a sequence of decoded TIFF image files.
Alternatively, **rechunking** covers Zarr-to-Zarr conversion, including changing
the chunk layout.

| Write workload | Source | Main constraint here |
|---|---|---|
| Streaming | Instrument images or decoded TIFF files | Acquisition rate and buffering; conversion memory |
| Rechunking | An existing Zarr | Source/destination overlap and memory use |

Acquisition imposes an arrival order and rate. A conversion can often revisit
its source and choose its processing order, or **traversal**, to suit both
layouts. Throughput matters in both workloads, but the freedom to control
that order changes the memory problem. Random subvolume updates are outside
this discussion.

## Acquisition

[Chucky][] is a next-generation **backend**—the component that performs the
writes—for [acquire-zarr][], a library for streaming arrays as Zarr.
Streaming measurements were performed using Chucky to repeatedly write a
preloaded sequence of example microscopy images from public data sets.
Writes go to a shared cluster filesystem mounted over **NFS**, the Network
File System protocol. Its `nconnect=16` setting requests sixteen network
connections. These measurements characterize the writer and storage together.

**Logical input bytes** count their original pixels before compression,
excluding **padding**, extra values added to fill chunk boundaries. After
the last image is submitted, a **final drain** completes the pending work and
closes the files. **Drain capacity** is logical input divided by the time spent
submitting images plus final drain. Counting submission time alone would hide
unfinished work.

These rates exclude loading and decoding images but include compression on
the CPU or a graphics processor (GPU), plus filesystem output.
Acquisition needs **headroom**, spare writer capacity above its incoming rate,
and **buffers**, allocated memory holding
data awaiting processing. Buffering absorbs temporary slowdowns, not an indefinite
overload. The margin needed depends on variation in the incoming and writing
rates.

For streaming, **concurrent shards** are the shard files in the active layer
perpendicular to the direction in which data are appended. They are typically
opened, written and closed over the same interval. Append a Z/Y/X array along Z
with a 4 × 4 shard grid across Y/X, for example, and the layer contains sixteen
shards. This is the illustrative geometry in Figure 2a; the primary measured
counts are four, nine, fifteen and thirty.

The shard-count tests replay [BBBC022][] microscopy images with GPU compression.
This public collection of cultured human cells comes from the Broad Bioimage
Benchmark Collection; Figure 3a shows one of the sixteen fields used here. One
series uses LZ4, another lossless compressor. Rates are **paired** within each
test round: divide one configuration's rate by the other's before summarizing
the changes across rounds. Changing the layer count also changes shard shape
and work per file, so these compare complete layouts. Moving from four to
fifteen actual shards improves LZ4 drain capacity by a median paired 76.1%.
Moving from fifteen to thirty
adds a median 10.1%, but individual paired changes range from −14.1% to +22.4%.
The Zstd control gains only 2.8% from four to fifteen; its chunk and block
settings differ, so the useful comparison is within each series. [Paired primary
results][shard-paired-summary].

A later comparison finds all three 54-shard samples slower than their paired
30-shard samples, by a median 13.4%. That follow-up used a separate job and
a 96 GiB minimum input, versus 32 GiB in the primary series. **Reference
measurements**, repeated runs of a fixed configuration, show substantial
changes in performance during the tests. These results support spreading
writes across several files, with diminishing gains that depend on the codec
and workload; they do not identify one optimal shard count.
[Follow-up][shard-extension-paired-summary].

![An illustrative sixteen-shard append layer sits beside separate primary and follow-up measurements of write drain capacity versus actual shard count.][figure-2]

**Figure 2. File parallelism for streaming.** **a,** An illustrative Z/Y/X
array appended along Z, with sixteen shard files in its 4 × 4 active layer.
**b,** Chucky writes BBBC022 microscopy data to shared NFS with GPU compression
and `nconnect=16`. Shards hold approximately 1 GiB before compression. LZ4
uses 64 KiB `[4,64,128]` uint16 chunks and 16 KiB blocks; Zstd uses 256 KiB
`[4,128,256]` uint16 chunks and 256 KiB blocks. Points are medians from six
repetitions; bars show observed ranges. Rates count logical input bytes over
submission plus final drain and close, excluding source loading and decoding.
Each run processes at least 32 GiB of logical input. Reference runs show variation
([Figure S1][figure-s1]). **c,** A separate LZ4 follow-up compares thirty and
54 shards in three paired rounds, each processing at least 96 GiB of logical
input. Sources:
[primary results][shard-summary] and [follow-up][shard-extension-summary].

The next choice is how much writing speed to trade for compression. I choose
the highest median drain capacity within 10% of the smallest comparable output.
Because the benchmarks can process different input volumes, size is measured
as **stored bytes per logical input byte**. For this ratio `S` and median
drain capacity `T`, the rule is to maximize `T` subject to `S ≤ 1.10 × min(S)`.

Figure 3 expresses stored size as **compression fold**: logical input bytes
divided by stored bytes. A value of 2× means the stored output is half the input
size. The 10% size allowance requires a compression fold at least as large as
the best tested fold divided by 1.10, calculated within each comparable group.

The earlier BBBC022 comparisons in Figure 3b–c use bytes submitted to shard
writes as a proxy for final stored bytes. They show why the allowance matters.
Ten of fourteen CPU settings and ten of thirteen GPU settings fall below their
group's compression threshold. The fastest GPU setting, Blosc-LZ4 with 16 KiB
chunks and blocks, reaches 6.33 GiB/s but only 1.438× compression, below the
1.754× cutoff. The fastest qualifying setting, Blosc-Zstd with 256 KiB chunks
and 64 KiB blocks, reaches 4.21 GiB/s at 1.886×. Codec, chunk shape and block
request vary together in these comparisons; they did not test 128 KiB. The CPU
and GPU studies use different machines and resource budgets. [Measurements and
observed ranges][write-comparison-summary].

To check the read-derived choice, the newer BBBC022 comparison in Figure
3d–e measures final file lengths directly and varies chunk shape while keeping
the other writer settings fixed.

The six layouts all finish within 2% of the smallest file size, so every one
meets this comparison's 1.715× compression threshold (Figure 3d–e). At 128 KiB,
using the same `[1,256,256]` uint16 chunk shape as the read candidate, final
size is only 0.81% above the 32 KiB minimum. Its median drain capacity is 2.267
GiB/s, with an observed range of 2.196–2.735. The 64 KiB layout has the highest
median, 2.639 GiB/s, with a range of 2.286–2.725. Those overlapping ranges
do not establish either a stable ordering or equivalent performance. [Write
summaries][write-summary].

The writing evidence leaves room for the read-derived 128 KiB choice: its
stored size is near the minimum, and the observed writing rates overlap those
of the fastest median configuration. Together, the results support 128 KiB as
a starting compromise to check against the application's read mix and incoming
data rate. The read tests use synthetic data on local NVMe; the write tests
use microscopy images on NFS. This combines evidence from separate studies,
rather than establishing a single optimum. [Read/write comparison][local-read-write-compromise].

![A BBBC022 microscopy field with a 100 micrometre scale bar appears above
separate CPU and GPU comparison plots. Ten settings in each comparison fall
below its dashed compression threshold, including faster LZ4 choices. Colors and
shapes identify compressors throughout. Filled symbols select the highest median
rates within the allowance. Below, all six fixed-block Blosc-Zstd layouts use
blue squares, with only 64 KiB filled, and exceed their final-size compression
threshold; separate rows show their rate medians and ranges.][figure-3]

**Figure 3. Microscopy input and writing capacity.** **a,** A [BBBC022][bbbc022]
field of human U2OS cells, MitoTracker Deep Red channel. Scale bar, 100 µm
at 0.656 µm/pixel. Display contrast spans the 1st–99.5th intensity percentiles;
benchmark pixels are unchanged. Image: Gustafsdottir and colleagues, Broad
Bioimage Benchmark Collection, CC0. **b–c,** Fourteen CPU and thirteen GPU
configurations, each measured three times on shared NFS with fifteen shards
per append layer. Compression fold uses summed logical input divided by
summed shard-write bytes, a proxy for final size. CPU and GPU results use
different machines and resource budgets. **d–e,** A separate GPU comparison
holds Blosc-Zstd, bitshuffle (rearranging bits before compression), 16 KiB
blocks and four approximately 1 GiB raw shards per layer fixed. Each layout
processes 22.09 GiB of logical input per run, with three repetitions. Final size includes shard
indexes and **metadata**, the information describing the array.
Panel e shows rate medians and observed ranges. Throughout, colors and symbols
identify compressors; filled symbols select the highest median within the
10% size allowance. Compression axes are logarithmic; values right of each
dashed threshold qualify. Rates count logical input over submission plus final
drain and close, excluding input loading and preparatory writing. Sources:
[earlier comparisons][write-comparison-summary], [fixed-layout results][write-summary]
and [image provenance][bbbc022-thumbnail].

## Memory

When streaming, writer memory is only part of the process. Raw images may wait
in a queue while the writer retains unfinished chunks, indexes and pending
output. A codec also needs a **workspace**, temporary memory for compression or
decompression. Budget the buffers that coexist, counting shared buffers only
once.

Rechunking adds a geometric problem: source and destination chunks may overlap
without matching. Processing order determines how long decoded source data and
incomplete destinations must remain live. A source-oriented traversal can avoid
source rereads while retaining several partial destinations. Completing one
destination at a time can reduce that retention, at the cost of rereading or
caching source chunks shared with later outputs.

Figure 4 works through a small example. A 512 × 512 uint16 array changes from
`[128,256]` uint16 source chunks to `[256,128]` uint16 destination chunks. Each
chunk is 64 KiB. Read source chunks one at a time, left to right and then top
to bottom. Do not read ahead or cache earlier source chunks. Allocate a full
destination buffer on first touch and copy into it. Finish encoding and writing
completed outputs, then release their buffers before reading the next source.

After the first two source chunks, four destinations are half-filled: 256 KiB
of retained output. Decoding the next 64 KiB source while those buffers remain
live gives a 320 KiB raw-array allocation bound. Completing outputs reduces the
retained set; after four source chunks it is empty. The pattern repeats for the
lower half of the array.

That 320 KiB counts only raw-array buffers for this schedule. Encoded data,
codec workspaces, metadata and runtime allocations add to the total.
Overlapping reads and writes keeps additional
buffers allocated; a different processing order can also change the bound.

![Different source and destination grids lead to partial output buffers whose lifetimes depend on traversal; the stated serial example has a 320 KiB raw-array allocation bound.][figure-4]

**Figure 4. Conversion memory.** A 512 × 512 uint16 array changes from
`[128,256]` to `[256,128]` uint16 chunks, both 64 KiB. Read source chunks
left to right, top to bottom, without reading ahead or caching. Allocate each
destination in full on first touch; finish writing completed outputs before
reading the next source. The peak raw-array allocation is one 64 KiB source
plus four incomplete destinations: 320 KiB. Only one codec/write operation
runs at a time. Encoded input/output, codec workspaces, indexes, metadata and
runtime allocations are excluded. This is an analytical bound for the stated
schedule, not a measured process peak or a whole-shard buffering requirement.

For a real conversion, choose the processing order, bound queues and caches,
and sum the buffers that can coexist. Keep main-memory and GPU-memory budgets
separate. Check memory savings against any extra reading or writing they
require.

Sharding does not by itself require a whole output shard in memory. That depends
on the writer's delivery strategy. The example explains how to budget memory;
the available records do not measure complete conversion memory or throughput.
[Conversion evidence and limits][conversion-findings].

## Layout recommendations

Start with actual crops, full-array reads and the required writing rate. Try
128 KiB `[1,256,256]` uint16 chunks as a balance across those demands. Test
32 KiB `[1,128,128]` uint16 chunks when Damacy crop throughput dominates;
test 512 KiB `[1,512,512]` uint16 chunks when TensorStore crop throughput
dominates. Keep chunk extents at one along axes read one element at a time.
On storage limited by its rate of read operations, also test larger chunks.
Confirm the balance using the application's crops, storage system and
representative microscopy data, then check writer capacity and stored size.

Choose shard size and shape to balance filesystem concurrency with a manageable
total file count, within the storage system's limits. The tested LZ4 writer
benefits from exploring roughly fifteen to thirty concurrent shards; the
tested Zstd setup gains little from four to fifteen. Keep actual counts and
raw capacities in the configuration.

Then check how data arrive. Acquisition requires a drain rate above the incoming
rate to make room for variable service. Conversions require a memory budget
based on the buffers their processing order keeps allocated.

---

## Methods

**Local read comparison.** Figure 1 selects `phase=cpu-chunk-blocks`,
`storage_type=local block storage`, `codec=zstd`, `block_bytes=16384`,
Damacy `implementation=chunks256-random` or TensorStore, and workloads
`random-1x256x256` and `full-scan` from [read-summary.csv][read-summary].
Each point/workload has three repetitions.

The synthetic input, smooth4, blends two smooth random 3D fields at different
spatial scales, rounds the result to 12-bit intensities stored as uint16, and
replaces the lowest four bits with independent random values from 0–15. The
“4” denotes four noise bits per value, combining spatial structure with noise
for compression tests. Figure 1 uses a `[512,4096,4096]` uint16 array (16 GiB
uncompressed), partitioned into sixteen `[512,1024,1024]` shards.

Each crop pass requests 16,384 selections in
**batches**, groups of 128 processed together: the sampler cycles through shard
start regions, draws valid XY origins
within each region and random Z, and permits overlap and shard crossings. It is
not a globally uniform sampler. Matched encodings and readers reuse the saved
query list. Full scans tile with `[8,256,256]` selections and cover all logical
values.

The reading computer uses an AMD EPYC 9655P processor; the job allocates 48
physical cores and 64 GiB of main memory. Both readers use 32 workers for
decoding/copying and sixteen for file reads, producing float32 output in
one continuous region of main memory. Damacy keeps file handles open between
requests, disables readahead and uses two 256-chunk input buffers. Indexes
are already in memory. Before each pass, checks confirm that the operating
system's cache contains none of the input files' data pages, the fixed-size
units it manages. Reuse during the pass is allowed; the dataset fits in memory.
Active timing includes planning, reads, decoding, data-type conversion and
assembly, excluding preparation, correctness checks and cache checks. Rates use
`useful_active_gib_s_*`, not output-byte rates. Damacy's recorded base revision
is `8d0931e7d131fd5d4c565458736ab586012c78c1`, with benchmark changes and
native/source hashes retained in [read metadata][read-metadata]; TensorStore is
0.1.85. [Detailed read methods][read-methods].

**Microscopy writes.** Chucky replays sixteen 520 × 696 uint16 mock-control
fields from [BBBC022v1][bbbc022], obtained from the [plate 20585, channel
w5 image archive][bbbc022-images], using site 1. The dataset is described by
[Gustafsdottir et al. (2013)][bbbc022-study] and distributed through the Broad
Bioimage Benchmark Collection ([Ljosa et al., 2012][bbbc-reference]). The
fixed-volume comparison repeats the ordered source for 32,768 frames, totaling
22.08984375 GiB of logical input. The append axis is replay, not additional
spatial content. Shard shape is `[2048,512,512]`, with four files per layer.
Blosc-Zstd uses requested compression level 3, bitshuffle and a 16 KiB block
setting. Spatial padding varies by chunk shape; useful input, submitted padded
bytes, metered output and final file lengths remain distinct. Three runs per
layout use append-through-final-close timing, excluding initialization, input
loading and preparatory runs whose output is discarded. Source images carry the
CC0 public-domain dedication; selection, original authorship and TIFF hashes are
in [input provenance][input-source].

**Historical write comparisons.** Figure 3b–c includes every current-report,
frontier-eligible BBBC022 filesystem configuration in the archived summaries:
CPU study `reef-turin-microscopy-pareto-core-3710982` and GPU study
`reef-l40-final-confirmation-3704091`. These use the same source-image hash
as panel a, fifteen actual append-layer shards, four replay planes per chunk,
approximately 1 GiB raw shard capacities and NFS with `nconnect=16`. The CPU
study allocates forty CPUs and uses 32 writer workers; the NVIDIA L40 GPU study
allocates eight CPUs and uses four writer workers. Both use 32 I/O workers, four
output buffers and the coverage-qualified append-through-close timing policy.
Measured logical input is at least 32 GiB per run; replay volumes can differ.
Compression fold is the ratio of summed logical bytes to summed shard-write
bytes, including padding and measured index writes but excluding separately
published metadata. Final file lengths were not measured. Thresholds are
computed within each original comparison group using exact integer byte ratios.
All 81 sample runs and their observed rate ranges are retained; no references,
failed runs or superseded studies are pooled into these panels. [Contributing
runs][write-comparison-runs] and [measurement definitions][write-findings].

The six-layout fixed-volume comparison in Figure 3d–e uses the following
`[replay,Y,X]` chunk shapes; replay indexes repeated input frames. All values
are uint16.

| Raw chunk (KiB) | Chunk shape (uint16 pixels) |
|---:|---|
| 16 | `[1,64,128]` |
| 32 | `[1,128,128]` |
| 64 | `[1,128,256]` |
| 128 | `[1,256,256]` |
| 256 | `[1,256,512]` |
| 512 | `[1,512,512]` |

**Shard-count comparison.** Figure 2's primary series uses six rounds,
a 32 GiB logical minimum, two seconds of requested preparatory writing,
three seconds of requested image submission, at least two transitions between
shard layers and timing through final close. Rate ratios are paired within
rounds. Before/after reference rates have a median ratio of 0.975 and an
observed range of 0.515–1.292; the rates are not adjusted for this variation.
The later 30/54 comparison uses three rounds and a 96 GiB minimum in a separate
job, selected after the primary results. Chucky's revision and patched
binaries are recorded in the [phase identities][source-phases]. See the
[findings][bbbc022-findings] and [follow-up protocol][shard-extension-protocol].

All plotted intervals show observed minima and maxima, not confidence
intervals. Read and write studies use different inputs, hardware and shard
geometry; their measurements are not pooled.

[damacy]: https://github.com/nclack/damacy
[tensorstore]: https://google.github.io/tensorstore/
[read-methods]: ../readable-zarrs-evidence/read-findings.md
[read-frontiers]: ../readable-zarrs-evidence/read-frontiers.csv
[local-read-write-compromise]: ../planning/reference/local-read-write-compromise.md
[read-summary]: ../readable-zarrs-evidence/read-summary.csv
[chucky]: https://github.com/acquire-project/chucky
[acquire-zarr]: https://github.com/acquire-project/acquire-zarr
[inode-allocation]: https://man7.org/linux/man-pages/man8/mke2fs.8.html
[s3-upload-limits]: https://docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html
[shard-paired-summary]: ../bbbc022-evidence/shard-paired-summary.csv
[shard-extension-paired-summary]: ../bbbc022-evidence/shard-extension-paired-summary.csv
[figure-s1]: figures/supporting.md
[shard-summary]: ../bbbc022-evidence/shard-summary.csv
[shard-extension-summary]: ../bbbc022-evidence/shard-extension-summary.csv
[write-findings]: ../readable-zarrs-evidence/write-findings.md
[write-summary]: ../bbbc022-evidence/shared-layout-summary.csv
[size-accounting]: ../bbbc022-evidence/size-accounting.md
[conversion-findings]: ../readable-zarrs-evidence/conversion-findings.md
[read-metadata]: ../readable-zarrs-evidence/read-metadata.json
[input-source]: ../bbbc022-evidence/input-source.json
[source-phases]: ../bbbc022-evidence/source-phases.json
[bbbc022-findings]: ../bbbc022-evidence/findings.md
[shard-extension-protocol]: ../bbbc022-evidence/shard-extension-protocol.json
[figure-1]: figures/figure-1.png
[figure-2]: figures/figure-2.png
[figure-3]: figures/figure-3.png
[figure-4]: figures/figure-4.png
[bbbc022]: https://bbbc.broadinstitute.org/BBBC022
[bbbc022-images]: https://data.broadinstitute.org/bbbc/BBBC022/BBBC022_v1_images_20585w5.zip
[bbbc022-study]: https://doi.org/10.1371/journal.pone.0080999
[bbbc-reference]: https://doi.org/10.1038/nmeth.2083

[write-comparison-summary]: figures/data/write-sweep-summary.csv
[write-comparison-runs]: figures/data/write-sweep-runs.csv

[tensorstore-chunk-costs]: ../planning/reference/tensorstore-chunk-costs-2026-09-28.md
[storage-iops]: https://docs.aws.amazon.com/ebs/latest/userguide/ebs-io-characteristics.html

[bbbc022-thumbnail]: figures/data/bbbc022-a14-s1-w5.json
