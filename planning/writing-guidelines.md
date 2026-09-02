# Writing and review criteria

Use these criteria for the document, presentation, figures, and measurement report in this project.

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
- Use one term for one concept throughout.
- Prefer concrete quantities over umbrella terms.
- Replace an implementation-specific term with plain language unless the implementation detail matters.
- Move formulas, internal names, and specialized scheduling language to an appendix when they are not needed for the main argument.

For this project, prefer:

| Preferred term | Meaning | Avoid as an interchangeable synonym |
|---|---|---|
| **selection** | The array region a reader requests | important read, logical selection, requested unit |
| **required workload** | A representative set of selections or writes that the layout must support | access geometry, consumer trace |
| **chunk shape** | The independently decoded extent along each array axis | chunk geometry |
| **resolution level** | One array in a multiscale pyramid | scale, LOD, pyramid image when used inconsistently |
| **downsampling schedule** | The cumulative per-axis reduction at every resolution level | automatic levels, pyramid policy |
| **nominal chunk shape** | The configured chunk shape before edge truncation or padding | actual edge-chunk extent |
| **shard shape in chunks** | The number of chunks grouped along each axis | shard packing vector |
| **storage object** | One file or one object-store object | file/object when the distinction is irrelevant |
| **requests per workload sample** | Physical reads required for one replayed selection or batch | request amplification, requests per selection when batches are included |
| **write engine** | The library that creates and updates Zarr storage | backend, implementation, writer when used inconsistently |
| **memory held while writing** | Queues, unfinished chunks, caches, and pending-write state | working set or resident state before they are defined |

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

1. **Mechanism:** what the format, client, store, or write engine does.
2. **Observation:** what source inspection or measurement shows for our workloads.
3. **Rule:** the policy adopted from that evidence.
4. **Exception:** the condition under which the rule must be reconsidered.

Label modeled estimates, measurements, implementation facts, hypotheses, and policy choices distinctly. Do not present an implementation-dependent behavior as a property of the Zarr format.

## Keep causal claims conditional

Name every component that controls the result. For example:

- Shard range-read cost depends on both client and storage support.
- Writer memory depends on write order, shard size, concurrency, and implementation.
- Pyramid depth depends on the required coarsest resolution, per-axis schedule,
  nominal chunks, and builder stopping behavior.
- Exposing work on several shards permits parallelism but does not guarantee physical concurrency.
- Stored dataset size is affected by compression, fill-value elision, metadata, and indexes.

Avoid “always,” “without cost,” and “does not sacrifice” unless the claim is guaranteed by a stated contract.

## Support recommendations where they appear

- Place the most relevant source or measurement beside the claim it supports.
- Distinguish evidence imported from Idetik, Neuroglancer, Damacy, Acquire Zarr, or library documentation from measurements made for this project.
- Report raw input bytes, codec input/output, skipped fill-value chunks, index/metadata bytes, and stored bytes separately.
- State tool versions, storage environment, cache state, and workload beside benchmark results.

## Use examples deliberately

- Introduce one running example near the beginning.
- Reuse the same example to derive chunk shape, shard shape, and write-engine choice.
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
- Is the required coarsest resolution separated from the levels a particular
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
