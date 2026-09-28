# Review of the BBBC022 evidence

Scope update, 2026-09-25: the author subsequently excluded NFS read speeds
from article recommendations in favor of local NVMe reads. The suspected
NFS IOPS limitation and its engineering are deferred. The review below retains
its historical calculations and interpretation; its NFS read-based drafting
recommendations are superseded by the
[local-read/write compromise](local-read-write-compromise.md). The writer
and size-accounting findings remain applicable.

Reviewed 2026-09-25 against commit `4fccbfe`. No numerical discrepancy was
found in the checks below. The new evidence closes the earlier matched
microscopy/NFS read gap and supports the revised read-first outline. It also
changes the initial small-chunk story substantially.

This supplements the [original collection review](evidence-review-2026-09-25.md),
which describes commit `80bde95`. The current
[outline](../article-outline.md) and [results and scope](../follow-up-experiments.md)
already incorporate the main qualifications. No additional experiment is
needed to make their scoped claims.

## What changes the article

### Read amplification does not determine throughput by itself

For translated 256 × 256 crops, 256–512 KiB chunks outperform 32 KiB in both
CPU readers on this NFS setup. Damacy's medians are 0.587–0.599 versus
0.249 useful source GiB/s; TensorStore's are 0.510–0.543 versus 0.235.
The ranges for 256 and 512 KiB overlap, so keep them as a favorable pair
rather than claiming a stable winner between them.

Damacy's measured decoded-byte amplification rises from 2.235 at 32 KiB
to 5.688 at 256 KiB and 5.879 at 512 KiB, while useful throughput increases.
That is a useful teaching example: reducing unused decoded pixels helps one
cost without necessarily improving the whole read path. These observations
do not isolate the contribution of request overhead, reader buffering,
readahead, decoding or NFS behavior. TensorStore has no decoded-byte counter
in this study. See the [read summaries](../../bbbc022-evidence/read-summary.csv).

Full scans also resist a general chunk-size rule. Damacy's highest median
is 32 KiB at 2.930 GiB/s; TensorStore's is 128 KiB at 2.454 GiB/s. Reading
every logical value still decodes padded array edges: Damacy's full-scan
amplification spans 1.222–2.897 across these layouts. Padding is not a complete
explanation, since 32 and 64 KiB have identical padded volume but different
rates. Keep the older local synthetic results as a separate comparison,
without attributing the reversal to storage alone.

### The common write study leaves room to choose for reads

All six final sizes are within 2% of the smallest. Every candidate therefore
passes the author's 10% output-size tolerance. Applying that rule to median
write rates picks 64 KiB, but its observed range overlaps every other layout's
range. The [joint table](../../bbbc022-evidence/joint-layouts.csv) is the strongest
bridge from reading to writing: read requirements distinguish candidates
whose measured output sizes and write rates are close.

The per-file audit resolves the metered-versus-final-size question for the
six retained stores. The correction is below 0.0012% of final length and
cannot affect the 10% cutoff here. Keep historical and dynamic-run size
metrics under their original labels; this equality does not automatically
transfer to those paths. See [size accounting](../../bbbc022-evidence/size-accounting.md).

### File parallelism has substantial but conditional benefits

The primary LZ4 paired comparisons give a median 76.1% gain from four to
fifteen append-layer shards. Fifteen to thirty gives a smaller 10.1% median
gain, with paired changes from −14.1% to +22.4%. The Zstd control gains only
2.8% from four to fifteen; its chunk and block settings differ from LZ4's.
Compare gains within each series. See the
[primary paired summaries](../../bbbc022-evidence/shard-paired-summary.csv).

In the separate follow-up, 54 shards are slower than 30 in all three paired
rounds: median 13.4% lower, range 11.0–15.3% lower. Preserve its later job,
adaptive selection and 96 GiB minimum separately from the primary 32 GiB
series. The exporter does this correctly, including retaining the original
decision not to extend the primary study. See the
[follow-up summary](../../bbbc022-evidence/shard-extension-paired-summary.csv).

These results support diminishing benefits and a measured regression beyond
thirty under the follow-up conditions. They do not establish a portable
sixteen- or thirty-shard optimum or a causal match to `nconnect=16`.
The primary reference runs' largest before/after drop is 48.5%; report this
variation rather than treating the smaller incremental gain as stable.

## Keep these distinctions visible in the draft

- The source is sixteen microscopy fields replayed cyclically. The resulting
  22.09 GiB arrays do not represent additional biological diversity.
- Shared read/write layouts have depth-one chunks and four files per append
  layer. The shard-count study uses different chunk shapes and, for LZ4, a
  different codec. Its gains cannot be assigned to the joint-table layouts.
- Read rates count useful uint16 source bytes. Earlier read reports often
  count returned float32 bytes, twice that amount in this study.
- Both readers have warm indexes and verified client file-cache eviction.
  Server cache is uncontrolled. The benchmark excludes source loading,
  validation, selection preparation and cache-control time.
- The aligned and translated 512-pixel controls change XY coverage, reuse
  and shard crossings as well as chunk alignment. They measure two useful
  workloads without isolating an alignment-only speedup.
- Writer rates measure drain capacity through final drain and close with
  preloaded input. Conversion memory remains an analytical section with
  explicit buffering assumptions, not a claim of measured conversion peaks.

For article figures, identify BBBC022, NFS, codec, repetition count and
median/min–max semantics in each caption. Include chunk shapes near the
capacity axis and keep the 30/54 follow-up visibly separate. The existing
figures are useful supporting artifacts; no plotting discrepancy was found.

## Verification

- Verified all 51 output checksums, the outer archive checksum and all 55
  archive file members against the extracted bundle. The portable exporter
  verified 1,382 provenance members; both raw streams also matched their
  uncompressed lengths and hashes.
- Regenerated into a temporary directory. Forty-one files were byte-identical.
  The only other regenerated common-file differences were the expected
  `plots_generated: false` metadata field and the output checksum inventory
  from using `--no-plots`.
- Independently checked all 144 raw read results against 952 pass events,
  successful terminal records, cache-eviction records, byte sums and timing
  denominators. Every result met the ten-second and one-GiB minima. Full
  scans accounted for every logical value once per pass.
- Independently checked all 66 primary-bundle writer observations and all
  12 separate follow-up observations against native timing, logical/submitted
  bytes, spatial padding and coverage requirements.
- Recomputed median/min/max and metric counts for 12 write groups, 48 read
  groups and two follow-up write groups. Independently checked all 24 primary
  shard ratios and three follow-up ratios, with their five summary groups.
- Recomputed both accounting identities from the six per-file inventories:
  `W = sum(ceil(L/A) * A)` and `S = W - P + M`. Every residual was zero.
- Inspected the read harness, reader helpers, exporter and all four figures.

This verifies the retained records and calculations. It does not rerun the
cluster benchmarks or independently read the external pixel stores. The
evidence bundles and experiment sources were left unchanged.
