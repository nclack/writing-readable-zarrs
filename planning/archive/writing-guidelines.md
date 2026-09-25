# Writing and review criteria

Archived snapshot, 2026-09-25. Retained for the earlier guide and planner.
The current article uses [the shorter writing guidelines](../writing-guidelines.md);
this snapshot imposes no requirements on that article.

Use these criteria for the document, presentation, figures, and measurement report in this project.

## Writing process

1. Identify the audience and what the reader should be able to do.
2. Build the outline around that reader's questions and the available evidence.
3. Determine the target length from the outline and allocate space.
4. Draft.
5. Edit for argument, evidence, clarity, and length.

The current plan is [article-outline.md](../article-outline.md). The earlier
guide's broader scope does not set the current article's requirements.

## Goal

Teach enough mechanism that the reader can predict the recommendation before it is stated.

## Organize by dependency

1. Start with a concrete task or question the reader recognizes.
2. Introduce the minimum concepts needed to explain what happens.
3. Show the causal mechanism.
4. Present observations or measurements.
5. State the recommendation and its limits.

Define a term before its first substantive use. A title or clearly labeled claim may preview a conclusion, but actionable guidance should follow its prerequisites.

## Minimize vocabulary

- Introduce a term only when it affects a decision or will be reused.
- Use one preferred term for one concept within a given context.
- Prefer concrete quantities over umbrella terms.
- Replace an implementation-specific term with plain language unless the implementation detail matters.
- Move formulas, internal names, and specialized scheduling language to an appendix when they are not needed for the main argument.

For this project, use the canonical terms in [glossary.md](glossary.md). It
distinguishes standards-aligned vocabulary, project-defined metrics, and exact
implementation identifiers. Add a term only when it affects a decision, will be
reused, or prevents a likely ambiguity.

## Make recommendations reproducible

A recommendation should identify:

- the decision being made;
- the inputs used;
- a rejection threshold or required condition;
- a tie-break rule when several choices pass;
- the workload and environment for which it applies; and
- the evidence that supports it.

Two informed readers applying the recommendation to the same inputs should reach the same result. Replace words such as “small,” “large,” “enough,” “useful,” “material,” “reasonable,” and “modest” with a measured limit or an explicit comparison.

Do not invent a universal numeric threshold when evidence is missing. Name the policy parameter, describe how to measure it, and mark its value as unresolved.

## Separate kinds of statements

Use this progression for each major decision:

1. **Mechanism:** what the format, client, store, or Zarr writer does.
2. **Observation:** what source inspection or measurement shows for our workloads.
3. **Rule:** the policy adopted from that evidence.
4. **Exception:** the condition under which the rule must be reconsidered.

Label modeled estimates, measurements, implementation facts, hypotheses, and policy choices distinctly. Do not present an implementation-dependent behavior as a property of the Zarr format.

## Keep causal claims conditional

Name every component that controls the result. For example:

- Shard range-read cost depends on both client and storage support.
- Writer working memory depends on write order, stored shard bytes,
  active-shard count, and Zarr writer.
- The number of emitted resolution levels depends on the required coarsest
  level, downsampling schedule, chunk shapes, and builder stopping behavior.
- Exposing work on several shards permits parallelism but does not guarantee
  observed storage concurrency.
- Stored bytes for a dataset scope are affected by compression, omitted fill
  chunks, metadata, and indexes.

Avoid “always,” “without cost,” and “does not sacrifice” unless the claim is guaranteed by a stated contract.

## Support recommendations where they appear

- Place the most relevant source or measurement beside the claim it supports.
- Distinguish evidence imported from Idetik, Neuroglancer, Damacy, Acquire Zarr, or library documentation from measurements made for this project.
- Report raw input bytes, named codec-stage bytes, encoded chunk payload bytes,
  omitted fill chunks, shard-index bytes, metadata bytes, and stored bytes
  separately.
- State tool versions, storage environment, cache configuration, and workload
  beside benchmark results.

## Use examples deliberately

- Introduce one running example near the beginning.
- Reuse the same example to derive chunk shape, shard shape, and Zarr writer choice.
- Add alternative examples only when they change a decision.
- Include misaligned and boundary selections; do not teach only with perfectly aligned reads.

## Review checklist

### Concepts

- Is every necessary term defined before use?
- Can any two terms be combined?
- Can any term be replaced by a concrete quantity?
- Are product and implementation names kept out of the conceptual explanation until their roles are clear?

### Argument

- Does each recommendation follow from a mechanism and observation?
- Could the reader anticipate the recommendation?
- Are causal dependencies and exceptions stated?
- Is the required coarsest level separated from the levels a particular
  builder happens to emit?
- Does the running example carry the argument rather than merely illustrate it afterward?

### Recommendations

- Is the action specific?
- Are inputs and limits named?
- Is the tie-break rule explicit?
- Is the scope clear?
- Would two readers make the same choice?

### Evidence

- Is support adjacent to the claim?
- Are facts, measurements, hypotheses, and policy values distinguishable?
- Are byte and concurrency quantities accounted for without conflation?
- Are unmeasured thresholds visibly unresolved?

### Editing

- Does each section introduce only one new idea?
- Can a paragraph, list, formula, or product name be removed without weakening the argument?
- Are repeated recommendations consolidated in one canonical location?
- Are implementation details and source inventories moved to appendices?
