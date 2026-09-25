BBBC022 measured evidence

See [findings](findings.md), [validation and completeness](validation.json), [joint layout table](joint-layouts.csv), [write summaries](write-summary.csv), [read summaries](read-summary.csv), and [paired shard ratios](shard-paired-summary.csv). Figures are PNG and editable SVG; every figure has a CSV of its plotted observations.

The input is sixteen mock-control fields from plate 20585, site 1, channel w5 of [BBBC022v1](https://bbbc.broadinstitute.org/BBBC022), Gustafsdottir and colleagues' U2OS Cell Painting experiment in the Broad Bioimage Benchmark Collection. The source images are CC0. [input-source.json](input-source.json) records the exact selection and TIFF hashes.

Raw writer observations and reader events are preserved under raw/ as deterministic gzip streams (mtime zero). raw/provenance.tar.gz contains only selected text metadata, configurations, traces, schedules, source identities, patches, scripts, helpers and logs. bundle.json lists every bundled artifact and checksum. Pixel stores, source image payloads and compiled binaries remain outside this bundle; their original paths and identities are retained.

Regenerate summaries and figures without cluster originals using Python 3.11+ and Matplotlib:

~~~bash
python3 export_evidence.py --from-bundle . --output regenerated
~~~

Use --no-plots for standard-library-only table regeneration. To collect the original run, use:

~~~bash
python3 export_evidence.py --root STUDY_ROOT --reads READER_OUTPUT --output EVIDENCE_OUTPUT
~~~

The exporter opens recorded text files only. It does not inspect pixel stores, execute native benchmarks, allocate cluster resources, or change the historical readable-zarrs-evidence archive. Collection, compression and plotting should run on a compute allocation. Unqualified and provisional observations remain in raw records; read-cases.csv records failed and missing cases. An incomplete export is labeled incomplete rather than padded with expected results.

The [post-primary shard follow-up](shard-extension-summary.csv) has separate [54/30 paired ratios](shard-extension-paired-ratios.csv), [references](shard-extension-references.csv), [protocol](shard-extension-protocol.json) and [validation](shard-extension-validation.json). It was selected after reviewing all six primary rounds and uses a separate job with a 96 GiB logical minimum. It does not alter the primary extension decision, counts or summaries. These extra outputs are enabled only by the archived shard-extension-complete.txt marker.

[Size accounting](size-accounting.md) explains the relation between metered writes, final file lengths, alignment and metadata for the retained stores.

[Allocation ledger](allocation-ledger.json) preserves the recorded Slurm jobs and resource use.

[Reader source](reader-source.md) identifies the base revision and single cumulative patch that reproduce all 310 frozen native source hashes.
