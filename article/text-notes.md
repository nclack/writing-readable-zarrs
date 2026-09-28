# Draft review notes

`draft.md` is a complete first draft following the accepted audience, outline
and length. Current rendered-text word counts, excluding headings, image alt text
and reference definitions: 2,728 body; 867 figure captions; 859 methods.

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
