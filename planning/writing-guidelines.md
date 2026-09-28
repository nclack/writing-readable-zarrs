# Writing guidelines

These guidelines apply to the [current article](article-outline.md). The
[earlier guide's rules](archive/writing-guidelines.md) are archived reference.

## Process

1. Identify the audience and what the reader should be able to do.
2. Outline the argument around that reader's questions and available evidence.
3. Determine the target length and allocate space.
4. Draft.
5. Edit for argument, evidence, clarity, and length.

## Drafting and figure tools

Two skills were installed in `~/.codex/skills` on 2026-09-25:

- [Scientific Visualization](https://github.com/K-Dense-AI/scientific-agent-skills/blob/49c6e97775eaa18ba791bebe23162a70ae601c18/skills/scientific-visualization/SKILL.md)
  for figure design, reproducible plotting, accessibility and export review.
- [Doc Coauthoring](https://github.com/anthropics/skills/blob/33375500bcea98d610eb30ce10ac4e59b89c390d/skills/doc-coauthoring/SKILL.md)
  for section drafting, refinement and testing whether a reader can understand
  the article without our conversation. Retain the process above and reuse the
  established audience, outline and length.

Use Python or Typst for figures: Python/Matplotlib is a natural fit for measured
plots; Typst can produce schematics and compose panels. Keep source data,
transformations and figure source under version control, with a reproduction
command and tool versions. Use shared typography and colours across both tools.

## Figure style and delivery

Follow the official **Nature research figure guide**, checked 2026-09-25:
[specifications](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/)
and [panel construction and export](https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/).
Use its principles for clear scientific presentation. The author requested
larger fonts, thicker strokes and more deliberate alignment on 2026-09-26;
the article's reading figures use the profile below. A journal submission can
have a separate print export checked against that journal's requirements.

- Design the reading figures at 183 mm width, with enough height for distinct
  diagram, plot and annotation rows. Align panel boundaries, titles, labels
  and legends to shared anchors; choose spacing consistently.
- Use Arial or Helvetica consistently. Default to 10 pt labels, at least
  9 pt for other text, and 12 pt lowercase bold upright panel letters. Keep
  text black on a clear background. Inspect at the article's 880-pixel width.
- Include axis lines, ticks and units in parentheses. Omit background gridlines,
  decorative effects and patterns. Use approximately 1–1.5 pt strokes; semantic
  chunk grids may use 0.8 pt lines to distinguish them from shard boundaries.
  Keep annotations outside data areas when possible. Text must not overlap
  other elements, and legends or notes must not obscure observations or ranges.
- Use an accessible palette, such as Okabe–Ito, with marker shapes or direct
  labels as additional cues. Avoid red/green contrasts and rainbow scales.
  Inspect contrast, colour-vision accessibility and grayscale legibility.
- Export editable vector PDF masters with embedded fonts. Keep text and lines
  as editable objects; inspect exports from either tool. For Matplotlib, set
  `pdf.fonttype = 42`; use `svg.fonttype = "none"` when exporting editable SVG.
  SVG/web and PNG previews can accompany the PDF. Use RGB; any microscopy
  raster panels need at least 300 dpi at final size, preferably 450 dpi when
  supported by the source, with editable scale bars and labels.

For this article, captions must identify the dataset, reader/writer settings,
storage, byte numerator, timing scope, number of runs and meaning of intervals.
Show the planned medians and observed ranges; do not label ranges as confidence
intervals. Keep analytical diagrams visibly distinct from measurements.
Retain the local-NVMe-read and separate microscopy-write scope in every comparison.

Render and inspect each delivered figure at its intended size for clipping,
legibility, font embedding and scientific meaning. Supply a caption, alt text
and the underlying data. A style preset alone does not establish compliance.

## Argument

Introduce the reader's problem, then the method, before stating the proposed
solution. Organize reads around two main patterns: random crops whose positions
are not constrained to chunks, and full-array scans. Introduce Pareto frontiers
as the method for characterizing tradeoffs and choosing a compromise. State the
objectives and reader for each comparison; 128 KiB is not a frontier optimum
for every reader. Whole-chunk alignment is a control within this discussion.

Start with read workloads, explain how chunk and shard choices affect them,
then examine how to produce the layout through streaming or rechunking.
Acquisition emphasizes throughput; TIFF conversion and rechunking emphasize
memory use alongside throughput.

Introduce the mechanism needed to understand each result, then state what the
measurements support and where the recommendation applies. Reuse a concrete
example where it helps; include translated crops and contrasting aligned or
full-array reads. Keep multiscale policy, tool-selection trees, and random
subvolume writes outside this article.

## Evidence

- Base read recommendations on local NVMe measurements, which the author judges
  more reliable for read-performance conclusions. Keep NFS read results as
  diagnostics outside the article's performance comparisons; the suspected
  IOPS limitation remains a deferred engineering hypothesis. NFS writing has
  been extensively tested in Chucky and remains supporting evidence. Local
  synthetic reads and microscopy writes are separate studies, not one matched
  read/write frontier.
- Name the workload, data, implementation, hardware/storage, and measurement
  scope beside each result. Put detailed reproduction instructions in methods.
- Distinguish observations, models, explanations, and hypotheses. Exposing
  several files does not establish observed concurrency or socket assignment.
- Define byte quantities, timing boundaries, and memory scope. Attribute
  measurements to the actual tool and revision, including Chucky by name.
- Preserve repetitions, exclusions, and variation. Report a supported range
  or several candidates when the evidence does not distinguish one winner.
- Make the stated selection rule reproducible, including the write analysis's
  10% output-size tolerance. The article need not define a complete policy
  optimizer or impose deterministic tie-breaks on uncertain rankings.
- Missing evidence should qualify the claim or motivate a focused follow-up.
  The archived experiment matrix is not a publication prerequisite.

## Language and editing

Use the [article glossary](glossary.md). Define necessary terms before using
them, use concrete quantities, and explain implementation details only when
they affect the reader's decision.

Use short noun phrases for section titles, such as "Read workloads" or
"Conversion memory"; avoid statements, questions and instructions. Introduce
jargon explicitly at first use in the narrative, or replace it with plain
language. Use a hypothetical vision transformer with 224 × 224 inputs and
16 × 16 token patches; do not name the internal model in the article or figures.

Use reference-style Markdown links throughout the article, with URL definitions
at the end of the source. Prefer the collapsed form, such as `[Damacy][]` with
`[damacy]: URL`; use `[link text][reference]` when the label differs or a source
is reused. Render ordinary inline links in HTML, without numbered footnotes or
a visible reference list. Link named software at its introduction.

Check that every recommendation follows from the evidence shown, its limits
are clear, and each section advances the argument. Remove repeated rules,
unused terminology, and details that belong in methods or reference material.
