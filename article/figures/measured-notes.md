# Measured figure panels

Drafted 2026-09-25 and revised for readability on 2026-09-26 using the Scientific Visualization skill and the project's
[Nature-style figure guidance](../../planning/writing-guidelines.md).
These are provisional article figures, not a journal-compliance certification.
The author's later readability request takes precedence over the earlier
5–7 pt text ceiling and compact print dimensions: reading figures use 9–10 pt
text, 12 pt panel letters and stronger strokes while retaining editable vectors.

Reproduce the selected data and component previews from the repository root:

```sh
article/.venv/bin/python article/figures/measured.py
```

The root assembler imports `draw_read_damacy`, `draw_read_tensorstore`,
`draw_shard_primary`, `draw_shard_followup`, `draw_write_sample` and `draw_write_tradeoff` from
`measured.py`. Each accepts `(fig, spec)` and adds its data axes and any
dedicated annotation rows. `draw_write_sample` adds the native source image;
`draw_write_tradeoff` adds a compression overview and a separate interval row for
each of the six candidates. The functions do not save or close the parent figure. Call
`export_data()` to regenerate the audit tables. Component previews use 183 mm
width, with respective heights 108, 135 and 140 mm. Root composition can use the
first two groups as the measured rows in Figures 1 and 2.
`write_sweeps.py` supplies `draw_write_sweeps` and `export_sweeps` for the
complete historical BBBC022 CPU/GPU comparisons in Figure 3b–c.
`draw_shard_reference(fig, spec)` supplies a separate supporting reference
plot; its component preview is 183 × 110 mm.

## Data transformations and validation

- Source CSVs remain unchanged. `data/measured-provenance.json` records source
  paths and SHA-256 checksums. Selected summaries and all contributing run rows
  are exported as CSVs, retaining original source locators and run identities.
- The code independently verifies every plotted throughput median, minimum,
  maximum and repetition count against the selected individual observations.
  Write rates are also checked as logical bytes / 2^30 / elapsed seconds, and
  elapsed seconds as append plus final drain/close seconds.
- Intervals are observed minima and maxima, never confidence intervals.
  There are no smoothed lines or interpolated response curves.
- The Figure 1 horizontal and vertical coordinates summarize **separate
  workload runs**; their whiskers do not describe a jointly observed 2D sample
  or joint confidence region. Vertical scales differ between readers and are
  explicitly labelled. Horizontal scales are shared.
- Figure 2 filled points are medians and open points are individual runs.
  The primary plot uses four categorical groups labelled with actual shard
  counts (4, 9, 15, 30). LZ4 and Zstd symbols are separated within the two shared
  groups so their rate intervals do not cover one another; these display
  offsets do not alter counts or rates. Thin gray lines
  in the later follow-up connect the three actual paired rounds; they are not
  an interpolation of unmeasured shard counts. Paired gain annotations use
  the median of the per-round rate ratios, not a ratio of group medians.
- Figure 3d–e shows compression fold: unpadded logical input bytes divided by
  median final file length, including metadata and shard indexes. All logical
  input sizes are equal. The 10% size allowance is a minimum compression fold
  of the best tested fold divided by 1.10: 1.8859857001 / 1.10 = 1.7145324546.
  The base-2 logarithmic axis spans 1.6–2.0×, with ticks in fold units. All
  values are positive; no records are excluded for the logarithmic display.
  The source records identical final sizes across the three runs
  of each candidate. Its overview shows medians without intervals; the adjacent
  candidate rows display every observed rate interval separately, avoiding the
  almost completely overlapping whiskers for 64 and 128 KiB at nearly identical
  compression folds. The row labels report compression fold to three decimals.
  The selected data retain the earlier final-size ratios as an audit column;
  the code verifies that both forms of the allowance select the same candidates.

## Figure 1b–c: read tradeoffs

**Caption contribution.** CPU read rates for Damacy (b) and TensorStore (c)
on local NVMe, with synthetic smooth4 uint16 input. Each point combines the
median translated-crop read rate (horizontal) and full-array read rate (vertical) for a
chunk layout; whiskers show the observed min–max from three runs per workload.
Shapes are Z × Y × X; chunk sizes are uncompressed uint16 capacities. Rates
use useful source bytes, not the twice-larger float32 host output. Both
readers use Blosc-Zstd with bitshuffle and fixed 16 KiB blocks. Damacy's
`chunks256-random` mode disables readahead for both workloads. The vertical
scales differ. The highlighted 128 KiB layout is a proposed compromise;
512 KiB has higher crop and scan medians for TensorStore. These are separate
from Figure 3's microscopy/NFS write measurements.

**Alt-text contribution.** Two scatter plots show the balance between two
read workloads. Each point represents one chunk layout, pairing its crop
read rate horizontally with its full-array read rate vertically. The
workloads are measured separately; the point is not a combined throughput.
Damacy trades reduced crop speed for faster scans as chunks grow from 32 to
128 to 512 KiB. The 128 KiB point retains 87% of the 32 KiB crop rate and nearly
doubles the full-array read rate. TensorStore's medians improve with larger chunks for
both workloads, with overlapping full-scan ranges at 128 and 512 KiB.

**Sources and exact scope.** `readable-zarrs-evidence/read-summary.csv`, selected
by `phase=cpu-chunk-blocks`, `storage_type=local block storage`, `codec=zstd`,
`block_bytes=16384`, reader TensorStore or Damacy `chunks256-random`, raw chunks
32/128/512 KiB, and workloads `random-1x256x256`/`full-scan`. The exported
`data/read-selected-summary.csv` contains all 12 selected rows; the 36
contributing run rows are in `data/read-selected-runs.csv`.

One `[512,4096,4096]` uint16 array contains 16 GiB logical input, stored in
sixteen `[512,1024,1024]` shards of 1 GiB raw capacity. Crops are 16,384
`[1,256,256]` selections per pass, in batches of 128; the sampler cycles through
shard start regions, then draws valid XY origins within each region and random
Z planes. It is not a globally uniform sampler. Selections can overlap and
cross shard boundaries. Scans cover the array with `[8,256,256]` tiles.
The measured 256-square crop is a nearby example for a hypothetical vision
transformer with 224-square inputs, not a measurement of a training pipeline.

Active time includes planning, file reads, decode, dtype conversion and output
assembly. Preparation and cache control are excluded. Client file pages start
at verified zero residency before each pass, indexes are warm, and within-pass
reuse is allowed. The data fit RAM. Both readers return contiguous float32
host arrays with 32 decode/copy participants and 16 file workers. Damacy uses
two 256-chunk input buffers. The machine is `cpu-turin-gp-l-244-025`;
Damacy revision `8d0931e7d131fd5d4c565458736ab586012c78c1`; TensorStore `0.1.85`.
The byte metric is `useful_active_gib_s`; the original summary's primary
float32-output rate is deliberately not plotted. NFS read rows are not used.

## Figure 2b–c: shard parallelism and separate follow-up

**Caption contribution.** Chucky GPU drain capacity for replayed BBBC022
MitoTracker uint16 microscopy data written to shared NFS (`nconnect=16`).
The rate is logical input divided by append plus final drain/close time;
source loading and writer initialization are excluded. Filled markers are
medians, whiskers are observed ranges and open markers show individual runs.
(b) The primary study uses a 32 GiB minimum and six rounds. LZ4 has 64 KiB
chunks with 16 KiB blocks; the Zstd control has 256 KiB chunks with 256 KiB
blocks, so gains are interpreted within each series. (c) A later, adaptively
selected 30-versus-54 comparison uses a separate job, a 96 GiB minimum and
three rounds; thin gray lines connect paired runs. It is not pooled with the
primary study. Reference rates varied: primary after/before ratios ranged
0.515–1.292, including a round-2 drop from 5.621 to 2.898 GiB/s. References
are reported separately and do not normalize the plotted rates. Counts describe
shards in the append layer, not observed I/O overlap or NFS socket assignment.

**Alt-text contribution.** In the primary LZ4 series, the median drain rate
increases from 3.24 GiB/s at four shards to 5.62 at fifteen and 6.12 at thirty,
with substantial run-to-run variation. The Zstd control remains near
2.7 GiB/s at four and fifteen shards. In the separate later comparison, each
54-shard run is slower than its paired 30-shard run; the median paired drop
is 13.4%.

**Sources and exact scope.** The primary summaries are
`bbbc022-evidence/shard-summary.csv` (six rows), with selected samples from
`bbbc022-evidence/write-runs.csv` (36 observations, GPU job `3836375`).
The paired summaries come from `bbbc022-evidence/shard-paired-summary.csv`.
The follow-up summaries and samples are
`bbbc022-evidence/shard-extension-summary.csv` and
`bbbc022-evidence/shard-extension-runs.csv` (six selected observations,
GPU job `3837212`), with `shard-extension-paired-summary.csv` for ratios.
All are exported under `data/shard-*` with the primary and follow-up kept
separate. Full primary and follow-up reference drift tables are also exported.

The primary protocol is `coverage-qualified-through-final-close-v2`, with
two seconds requested warmup, three seconds requested append, at least two
generation transitions and a 32 GiB minimum. Samples contain
34,360,684,800 logical bytes, slightly above that minimum. The follow-up
contains 103,082,054,400 bytes per sample, slightly above its 96 GiB minimum.
Dynamic coverage-qualified timing differs from the fixed-volume shared-layout
study in Figure 3. The input is preloaded and continuously available; the rate
is drain capacity, not a measured sustained acquisition limit or a durable
storage guarantee. Raw shard capacities remain near 1 GiB, but changing the
count also changes realizable grouping and append-axis extent.

The LZ4 chunk shape is `[4,64,128]`; the Zstd control is `[4,128,256]`.
Both use bitshuffle and level hint 3. The GPU is an NVIDIA L40 on
`cw-us-e4a2-l40-202-211`. Chucky base revision is
`e3cd3af6c669c99d2b15bbebf9e95a6132319f09`, with the recorded study patches
for zero integer fill metadata and benchmark metering capacity. The shard
study uses binary SHA-256
`9702c7bb6089c69449553fa4a42e9ff96af7c4a5461acbb86bccbf8a32288ed9`.
The earlier interrupted shard attempt is supplementary and excluded because
the metering wrapper's capacity required restarting the entire comparison.

The primary paired LZ4 15/4 gain is 76.1%, observed range 64.9–194.7%;
30/15 is 10.1%, range −14.1–22.4%. The Zstd 15/4 gain is 2.8%, range
−0.8–5.5%. The later 54/30 gain is −13.4%, range −15.3–−11.0%.
These are repeated measurements in a noisy shared environment, not population
confidence intervals, a stable ceiling or a causal test of `nconnect`.

**Supporting reference-plot caption.** All before/after LZ4 reference runs
at fifteen shards from the primary study (a) and later adaptive follow-up (b).
Each gray segment connects the two reference observations bracketing
one round of samples. The two roles are separated horizontally within each
round so nearly equal rates remain visible. Open circles are before-sample measurements; black
squares are after-sample measurements. There is no aggregation or uncertainty
interval in this panel. Primary references use a 32 GiB logical-input minimum;
later references use 96 GiB and belong to a separate GPU job. Both use 64 KiB
chunks, 16 KiB blocks, bitshuffle, and append-through-close logical drain rates
to shared NFS. No reference correction is applied to the main sample rates.

**Supporting alt text.** Six primary before/after pairs vary strongly, with the
largest drop in round 2, from 5.62 to 2.90 GiB/s. Three later reference pairs
range from 4.67 to 5.59 GiB/s and show smaller before/after differences.

## Figure 3: compression fold and writing capacity

**Caption.** BBBC022 microscopy writing to shared NFS. Panel a shows the
complete fixed first input field: U2OS cells labelled with MitoTracker Deep
Red, plate 20585, well A14, site 1, channel w5. Whole-field grayscale display
uses the recorded 1st–99.5th-percentile limits, 246–1018.405; benchmark pixels
are unchanged. The external 100 µm bar uses 0.656 µm/pixel calibration.
Panels b–c show every retained current-report BBBC022 configuration in the
CPU and GPU comparisons: 14 and 13 configurations, each with three sample runs.
Points show median drain capacity; ranges remain in the linked source table.
Compression fold is summed logical input / summed measured shard-write bytes,
a proxy for final size. CPU and GPU thresholds are respectively 1.7175067861×
and 1.7537721345×, each the best fold in that comparison group / 1.10. Ten
configurations in each group fail the allowance. Filled symbols select the
highest median eligible configuration. CPU and GPU use different machines
and resource budgets, kept in separate panels. Both have fifteen append-layer
shards. Codec, chunk shape and block request vary together.
Panels d–e retain the separate, fixed-volume GPU comparison: six raw chunk
sizes, fixed Blosc-Zstd with bitshuffle, 16 KiB blocks and four approximately
1 GiB raw shards. Compression divides unpadded logical input by measured
final file lengths including metadata/indexes. Panel d shows medians and the
1.7145324546× threshold; panel e gives each observed min–max rate interval its
own row, with compression fold below the chunk label. All six sizes are
within 2% of the smallest. Colors and marker shapes identify compressors consistently
across b–e. All d–e points use blue Blosc-Zstd squares, with only the 64 KiB
highest qualifying median filled. Panel d labels 64 and 128 KiB directly;
128 KiB is identified in the footer as the proposed compromise. The shared
legend defines both compressor symbols and the filled-symbol rule.
All compression axes use base-2 logarithmic scales;
values right of each dashed threshold qualify. Timing counts append plus
final drain/close, excluding input loading and preparatory writing. All three
studies remain separate from each other and Figure 1's local synthetic reads.

**Alt text.** A BBBC022 microscopy field with an external scale bar sits above
separate CPU and GPU comparison plots. Faster LZ4 configurations often fall below
the compression allowance; ten configurations fail in each panel. Filled
symbols select qualifying Zstd configurations. Below, all six fixed-block
Zstd layouts pass their final-size threshold. Separate rows show median rates
and observed ranges; 128 KiB remains the proposed read compromise and 64 KiB
has the highest median in that fixed-block study.

**Historical comparison sources and exact scope.** `write_sweeps.py` selects
`current_report_selected=true`, `proxy_frontier_eligible=true`, `sink=fs` and
`input_id=bbbc022-mito` from `readable-zarrs-evidence/write-summary.csv`.
There are no further per-configuration exclusions. The source groups are
CPU `reef-turin-microscopy-pareto-core-3710982` (40 allocated CPUs, 32 workers)
and GPU `reef-l40-final-confirmation-3704091` (8 allocated CPUs, NVIDIA L40,
4 workers). Both use 32 I/O workers, four output buffers, four replay planes
per chunk, approximately 1 GiB raw shards, fifteen actual append-layer shards,
`nconnect=16`, and a minimum 32 GiB logical input per sample. Their source
hash matches the image in panel a. Codec, chunk and block settings vary;
128 KiB is absent from these historical grids.

The generated `data/write-sweep-summary.csv` preserves all 27 configurations,
original groups, rates, observed ranges and byte counters.
`data/write-sweep-runs.csv` contains all 81 referenced sample records.
`data/write-sweep-provenance.json` states the exact selection and transforms.
The build verifies medians/minima/maxima and byte sums against each listed raw
row ID, and checks threshold eligibility using exact integer fractions.
Historical rate/time fields agree to better than 9e-8 relative precision;
the check permits 1e-6 for independently rounded exports. Proxy fold is a ratio
of sums, not a mean of individual folds. Dynamic replay volumes differ;
normalization does not assert identical finite arrays. Measured write calls
include padding and index writes but omit separately published metadata and
are not a final-file census. The thresholds and throughput comparisons are
computed within each original study, without pooling references or jobs.
No jitter is applied to near-coincident measurements. Hollow codec symbols
preserve their boundaries; filled marks identify the selected configurations.
The source table preserves the exact values and ranges of every setting.

**Fixed-layout sources and exact scope.** `bbbc022-evidence/shared-layout-summary.csv`
contains six rows; the 18 corresponding observations are in
`bbbc022-evidence/write-runs.csv`, job `3836189`. The selected summaries and
observations are exported in `data/write-selected-summary.csv` and
`data/write-selected-runs.csv`. All have logical shape `[32768,520,696]`,
23,718,789,120 logical bytes and shard shape `[2048,512,512]`. Chunk shapes are
16 KiB `[1,64,128]`, 32 KiB `[1,128,128]`, 64 KiB `[1,128,256]`,
128 KiB `[1,256,256]`, 256 KiB `[1,256,512]` and 512 KiB `[1,512,512]`.

**Microscopy source and display.** The sample in Figure 3a is native field zero
from the actual 16-field benchmark input, stored without cropping, filtering,
denoising or pixel rescaling in `data/bbbc022-a14-s1-w5.npy`. It matches the
field used by the existing corpus preview and was not newly selected for
brightness or appearance. The accompanying JSON supplies field identity,
calibration, display limits, license and citations. The entire raw input asset
was checksum-verified against `bbbc022-evidence/input-source.json` before this
field was extracted; the figure function verifies the saved NumPy file checksum
before loading it. The source TIFF checksum is a retained provenance record,
not a new download verification.

Source: [BBBC022, Broad Bioimage Benchmark Collection](https://bbbc.broadinstitute.org/BBBC022),
[Gustafsdottir and colleagues (2013)](https://doi.org/10.1371/journal.pone.0080999).
The on-figure “BBBC022 · Broad Institute” label links to the dataset page in
vector exports. The recorded data license is CC0-1.0; source credit is retained.

The complete image is 48 mm wide and 35.86 mm high, giving approximately
368 pixels/inch at its native 696 × 520 resolution. `imshow` uses
`interpolation="none"` and fixed global linear limits 246–1018.405. Values
outside these limits saturate only in the display: 3,344 pixels below the
lower limit and 1,810 above the upper limit, out of 361,920 pixels. The native
uint16 values remain unchanged. The 100 µm bar spans 152.439 native pixels,
or 10.51 mm in the figure; it and its label sit below the pixels. All right-side
metadata are 9 pt, start at a common 60 mm horizontal anchor, and use 6.8 mm
vertical spacing. Title and panel letter are inside the allocated row with
the same left-gutter alignment as the plots. The row requires at least
135 × 54 mm; the full Figure 3 uses the planned 183 × 250 mm layout with
a 56.7 mm source-image row. No label or bar covers the image.

The timing policy is `fixed-volume-after-discard-warmup-through-close-v1`.
Source preparation, initialization and the separate discarded warmup are
outside the plotted rate. Final size is the actual file-length census, not
metered shard-write traffic or filesystem allocation. The size audit is
`bbbc022-evidence/size-accounting.md`; metadata and indexes are counted once.
The smallest final length is 12,576,335,610 bytes (32 KiB chunks). No horizontal
range appears because each layout's three final file lengths are identical.

The GPU/node and Chucky base revision are as above. This shared-layout phase
uses the earlier binary SHA-256
`5f3c23b481f6d9279d547b828554873042cd92698defb7570dfe05cc2ae8d881`, including
the zero integer-fill metadata patch; it predates the benchmark-metering
capacity change and was retained unchanged. It is not a conversion-memory
benchmark and excludes TIFF decoding.

## Display choices and review

Labels and marker shapes redundantly identify the highlighted candidates.
Text is black; no gridlines, gradients, smoothing or decorative 3D are used.
Nonzero throughput limits in the read and compression-fold scatter plots make their
measured differences legible; axis limits are explicit and no bars encode a
length from a hidden baseline. The shard-rate plots share a zero baseline and
the same vertical scale. Figure 3b–c uses common axis limits for the separate
CPU/GPU comparisons and places thresholds and legends outside the data axes.
Figure 3d–e uses a compression/rate scatter overview and a separate
candidate-by-rate interval display so no uncertainty interval is
hidden behind another candidate's interval. Titles and panel letters use common
alignment anchors. Settings, legends and explanatory notes occupy dedicated
rows outside the data axes. No text box or opaque legend covers any data.

The component PNGs were rendered and visually inspected at their intended
physical sizes; labels and overlapping ranges were checked. The root assembly
must repeat the inspection after placing schematic panels above the measured
rows. `style.py` exports editable SVG text and Type 42 vector PDF, with Arial,
10 pt default labels, 9 pt annotations/ticks, 12 pt lowercase bold panel letters,
and 1.1–1.3 pt data strokes, following the author's readability revision.
Source code and data, not the PNG preview, are the editable masters.

Software used for rendering: Python 3.12.14 (project runtime), Matplotlib 3.11.2,
NumPy 2.5.3. The plotting code uses standard-library CSV/statistics and
Matplotlib; no seaborn, Plotly or network service is required.

The 2026-09-28 compact composition keeps all five panels at 183 × 250 mm.
From the bottom edge, the lower data axes occupy 22–72 mm, the single-row
codec legend 88–96 mm, the upper data axes 116–174 mm, and the sample-image
row 190–244 mm. Text offsets are physical point distances; fonts remain
9–12 pt. Repeated upper-panel explanations remain in the caption. The full
PDF and the 880 px article display were checked for overlap and clipping.
