# Draft review notes

`draft.md` has completed an argument and relevance review against the author's
revision at `da81c5e`. Current rendered-text word counts, excluding headings,
image alt text and reference definitions: 3,025 body; 606 figure
captions; 814 methods.

Checks completed:

- Verified the selected fixed-16-KiB-block local read rates against
  `readable-zarrs-evidence/read-summary.csv` and writer rates/final sizes
  against `bbbc022-evidence/shared-layout-summary.csv`.
- Verified shard ratios and LZ4/Zstd chunk/block settings against the primary
  and extension CSVs. The separate follow-up remains explicitly separate.
- Resolved local-read hardware, worker settings, TensorStore version and
  Damacy source identity from read metadata. Writer identities remain linked
  to the phase-specific source manifest.
- Coordinated Figure 4's exact analytical example with the figure author:
  512-square uint16, `[128,256]` to `[256,128]`, serial row-major traversal,
  320 KiB raw-array allocation bound with explicit exclusions.
- All relative Markdown targets currently resolve. Figure captions assume
  final panel lettering 1a–c and 2a–c. Figure 1 explicitly notes differing
  reader scan-axis scales.
- Included the Scientific Agent Skills citation verified by the parent agent
  and pinned Doc Coauthoring link in the methods acknowledgment.

Useful fresh-reader checks:

1. What layout should an engineer try first, and what changes would justify
   smaller or larger chunks?
2. Does the article imply the actual 224-square model workload was measured?
3. Can a reader distinguish useful source bytes, float32 output bytes,
   decoded bytes, padded submission bytes and final stored size?
4. Does the reader understand why local reads and NFS writes are separate
   evidence, while NFS writing remains valid?
5. Can a reader distinguish sixteen illustrative shards, actual tested shard
   counts, worker counts, socket counts and observed I/O overlap?
6. Does the acquisition discussion imply an indefinitely sustainable rate,
   a universal headroom percentage or crash durability?
7. Can a reader explain why the 320 KiB conversion estimate is neither a
   whole-shard buffer requirement nor measured process RSS?

Fresh-reader review answered the seven practical questions correctly. Added
the six write chunk shapes and their axis meanings, explicitly matched the
128 KiB read/write chunk geometry, and attributed confidence in the NFS read
measurements to the author. The reader confirmed those fixes. Final captions
were reconciled with the assembled panels; read-label collisions were fixed.

Editorial handoff: captions are deliberately self-contained. The first draft retains
evidence links useful for review; publication can replace repository-local
links with public artifact URLs. No new evidence claims require experiments
before reviewing this draft.

Readability revision, 2026-09-27:

- The introduction establishes the applications and two main read patterns,
  defines Pareto analysis, and states the proposed layout after the approach.
- The 224-square vision transformer is hypothetical; model tokens and storage
  chunks are distinguished. Technical terms are introduced within the narrative.
- Section headings are descriptive noun phrases. Chunk-aligned reads are a
  control, and the 128 KiB choice is not claimed to be TensorStore's frontier.
- All five figures have larger type and thicker lines, aligned panel labels and
  dedicated notes/legend rows. Figure 3 separates each rate interval into its own
  row. Captions describe these displays and preserve the evidence boundaries.
- Final PDFs were inspected at the article's display width. Embedded fonts,
  editable SVG text, numerical summaries and relative links were checked.

Article links use reference-style Markdown, with URL definitions at the end
and ordinary inline links in HTML. Named software uses collapsed references
such as `[Damacy][]`; other labels can reuse explicit reference identifiers. Damacy, TensorStore, Chucky and acquire-zarr link at introduction.
Chucky is introduced as a next-generation backend for acquire-zarr, as specified
by the author; backend is defined as the component that performs the writes.

BBBC022 source revision: the first introduction links to the original Broad
collection; Methods link the exact source ZIP and both recommended papers.
Figure 3a shows the checksum-verified first input field at native resolution,
with a calibrated scale bar outside the pixels and documented display contrast.
The fixed-layout panels retain the earlier write measurements (now d/e). Other figure files are
byte-for-byte unchanged after rebuilding.

Compression-fold revision, 2026-09-28: Figure 3 uses logical input / final
stored bytes on a base-2 logarithmic axis. The 10% size allowance is marked
at the best tested fold / 1.10 (1.715×). The caption and preceding definition
explain the direction of the allowance; selected data retain both metrics.
All six candidates and their raw rate ranges are unchanged. The PDF render
was checked for label overlap, data occlusion and embedded fonts.
The restored article preview was also inspected at 738 px figure width.

Expanded write evidence, 2026-09-28: Figure 3b–c now includes the complete
retained BBBC022 CPU/GPU NFS sweeps: 14 + 13 settings, 81 runs, and 10 settings
below each study's own 10% threshold. The selected eligible settings are
filled. Source tables preserve observed ranges; the plots show medians.
The article defines the historical write-byte proxy and distinguishes it from
direct final-file measurements in the retained six-layout panels d–e.
The image stays in panel a. Figure height is 345 mm at the unchanged 183 mm
width, with threshold labels and shared legends outside the scatter axes.
The expanded PDF and refreshed HTML preview were inspected; the displayed
figure is 738 px wide. All 35 reference definitions resolve, local targets
exist, and other figure exports remain byte-identical.

Compact layout revision, 2026-09-28: Figure 3 is now 183 × 250 mm, 27.5%
shorter than the preceding version, with all five panels and the same 9–12 pt
fonts. A single-row codec legend, fixed physical spacing and removal of
repeated figure notes reduce whitespace. Visible article prose, captions,
alt text and panel titles use measurements/comparisons in place of sweep.
The final PDF and browser preview (880 px wide) were visually checked.

Symbol consistency revision, 2026-09-28: Figure 3b–e shares one compressor
color/shape key. All fixed-block points are blue Blosc-Zstd squares; only
64 KiB, the highest qualifying median, is filled. The shared legend defines
this rule, d directly labels 64 and 128 KiB, and the footer identifies
128 KiB as the proposed compromise. Caption and alt text agree. PDF and
refreshed HTML were visually checked at unchanged figure dimensions and
font sizes; data tables and other figures remain byte-identical.

Read-axis wording, 2026-09-28: Figure 1 uses Full-array read rate and
Crop read rate, both in useful GiB/s. Caption, alt text and measured-panel
notes use the same wording. The longer labels fit without changes to
font sizes or figure dimensions; PDF rendering was checked.
Panels b–c now share the heading Balance between two read workloads.
The caption and alt text explain each point as one layout with separate
crop and full-array read measurements. Refreshed browser preview checked.

Read/write compromise revision, 2026-09-28: Removed aligned/full-array
controls from Figure 1a and shortened the figure to 183 × 210 mm. All
chunk dimensions in Figures 1 and 4 explicitly include uint16. The article
now treats the TensorStore full-array 128/512 KiB difference as unresolved
by these three repeats, while retaining the 512 KiB crop advantage. The
128 KiB recommendation combines read priorities with the separate NFS
microscopy write results. A linked audit distinguishes TensorStore data
cache configuration, within-pass file caching, measured traffic and modeled
chunk/decode counts. PDFs and refreshed browser preview were inspected;
source hashes, exported data and unrelated figure exports are unchanged.


Argument and relevance review, 2026-09-28 (baseline `da81c5e`):

- Independent reader, evidence and editorial reviews identified and resolved
  the main consistency problems. Reader-specific chunk advice again depends
  on crop priority; full scans are exhaustive selections without an assumption
  that every selection covers whole chunks; the write-size allowance uses
  stored bytes per logical input byte, with the historical write-byte proxy
  identified at its introduction.
- Removed the Figure 2 claim of a 9 GiB/s storage maximum. Its source is a
  separate 1.68-second microbenchmark, not a ceiling measured for these
  writer runs. Clarified that changing shard count also changes shard geometry.
- Kept the read-derived candidate, then developed the writing evidence before
  synthesizing the compromise. Moved Figure 1 next to its introduction.
  Kept both shard-design goals and the write-based origin of the read layout.
- Cut repeated recommendation previews, lengthy cache diagnostics, duplicate
  caption interpretations, exact display-intensity bounds, and benchmark
  restart history. Detailed data and provenance remain in linked evidence.
- The final independent reader confirmed the argument order and resolution
  of the substantive issues. Its final table-scope ambiguity was fixed by
  explicitly assigning the six chunk shapes to Figure 3d–e.
- Rebuilt the local preview and standalone publication output. Checked local
  targets and reference rendering. Figure assets and measurements are unchanged.

Synthetic input clarification, 2026-09-29: The author supplied the smooth4
generator description: blend two smooth random 3D fields at different spatial
scales, round to 12-bit intensities stored as uint16, then replace the lowest
four bits with independent random values from 0–15. Methods and the read
findings now explain the four-noise-bit name and distinguish the generator
from the later studies' 16 GiB volume. This is an author-supplied description;
the original generator source and its exact parameters remain outside the
portable evidence bundle. The read measurements remain explicitly synthetic.


Chunk geometry and storage applicability, 2026-09-29:

- Explained low-dimensional chunks as extent one along independently selected
  plane, time and channel axes, while retaining dimensions jointly consumed by
  the workload. The point is to avoid decoding values outside the requested
  selection, not to prescribe one-dimensional strips for XY crops.
- Added operation-rate limits to the chunk-size tradeoff: fewer requests can
  justify larger chunks even when they increase unused bytes. The author
  confirmed that 10,000–100,000 IOPS is a general storage capability range,
  not a measured device rating for these benchmark machines. The text uses
  it to explain applicability and links primary documentation on I/O size
  and throughput. NFS read timings remain excluded from recommendations.
- Mirrored both qualifications in the final layout recommendations and rebuilt
  the article preview. No figure assets or numerical observations changed.

Paragraph tightening, 2026-09-29: Shortened the geometry and IOPS guidance.
Moved geometry next to the decode-amplification definition; kept storage
applicability after the TensorStore read-cost discussion, where it qualifies
the chunk-size tradeoff. Removed the forward reference to writing results.
Strengthened the geometry guidance with the multiplicative penalty: eight
planes and four channels give 32-fold decode amplification for a crop reading
one of each, before XY boundary waste.

Accuracy qualifications, 2026-09-29: Scoped the 32-fold example to whole-chunk
decoding for one crop and explained sharing decoded chunks across requests.
Marked the TensorStore lookup/scheduling explanation as a hypothesis; the
measurements do not isolate its cause. The IOPS range is explicitly illustrative,
with no benchmark-derived threshold claimed. Rebuilt the article and standalone
site; measurements and figure assets are unchanged.
