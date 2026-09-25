# Writing guidelines

These guidelines apply to the [current article](article-outline.md). The
[earlier guide's rules](archive/writing-guidelines.md) are archived reference.

## Process

1. Identify the audience and what the reader should be able to do.
2. Outline the argument around that reader's questions and available evidence.
3. Determine the target length and allocate space.
4. Draft.
5. Edit for argument, evidence, clarity, and length.

## Argument

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

Check that every recommendation follows from the evidence shown, its limits
are clear, and each section advances the argument. Remove repeated rules,
unused terminology, and details that belong in methods or reference material.
