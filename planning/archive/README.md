# Archived guide planning

Archived 2026-09-25. These documents preserve the earlier broad guide and its
supporting plans. Their requirements and recommendations are superseded for
the [current article](../article-outline.md).

| File | Historical role |
|---|---|
| [outline.md](outline.md) | Guide covering layout policy, multiscale arrays, and conversion tools |
| [measurements.md](measurements.md) | Comprehensive proposed measurement program |
| [figure-outline.md](figure-outline.md) | Figure specifications and assignments for that guide |
| [presentation-outline.md](presentation-outline.md) | Slide sequence derived from that guide |
| [glossary.md](glossary.md) | Extended vocabulary, tool inventory, and planner schema mappings |
| [writing-guidelines.md](writing-guidelines.md) | Earlier writing rules and review checklist |

The current article retires these requirements:

- Streaming versus arbitrary-region writes as the main write comparison.
- Multiscale/downsampling policy, pyramid-builder and writer-selection trees,
  and mandatory layout decision records.
- A comprehensive viewer/cache/pyramid/operational experiment matrix before
  publishing scoped findings.
- Planner objectives preferring the largest passing chunks and smallest
  passing shards as article recommendations.
- A complete pass/fail policy and deterministic winner for every recommendation.
- Substituting Acquire Zarr for Chucky when naming measured implementations.

The [planner design](../../code/planner-design.md) remains a separate code
project. The [DCA review](../reference/dca-chunking-sharding-review-outline.md)
and [collaborator feedback](../reference/dca-feedback.md) are separate reference
material. Their links to these archived plans preserve historical context.

Retained text may contain old prescriptions, unverified implementation claims,
and planned experiments. Reuse mechanisms or source leads after checking them
against the current scope and evidence. No measurements or implementations are
established merely by appearing in an outline.
