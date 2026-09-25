This export contains 18 qualified shared-layout write samples, 36 qualified shard samples, 12 separate writer references, and 144 of 144 expected measurement read results. Writer coverage is complete; reader coverage is complete. Missing, rejected and duplicate conditions are listed in validation.json and read-cases.csv.

Medians and observed minimum–maximum ranges describe retained repetitions; ranges are not confidence intervals. Correctness observations and before/after references are excluded from primary summaries. A reader result is admitted only with one matching successful case_finished event and process return code zero.

The source contains sixteen 520 × 696 uint16 microscopy fields. The shared arrays repeat this ordered source from plane zero for 32,768 frames: 23,718,789,120 logical bytes (22.08984375 GiB), 2,048 complete source cycles and sixteen append-axis shard generations. The append axis represents replay, not newly measured spatial content. Shards are [2048,512,512], with four files per append layer. The six chunk layouts submit respectively 27, 30, 30, 36, 48 and 64 GiB after spatial padding.

The shared-layout observations remain from their completed original job and binary. The entire shard-count experiment was restarted after the benchmark sink wrapper's 32-writer limit prevented the first 54-shard observation from starting; the codec itself was not the limiting component. The wrapper limit was increased to 64 in a separately identified binary. The primary shard summaries use only the restarted series, with no old/new shard-job pooling. The 28 interrupted shard records (27 qualified measurements or references; 1 failed) remain in [supplementary-interrupted-shards.csv](supplementary-interrupted-shards.csv), with original status, available rates, job identities and source locations. Their exclusion was fixed by the capacity repair and full restart, without selection by measured rate. The recorded restart reason is: The benchmark metering wrapper had 32 slots and rejected the 54-shard startup. Raise its capacity to 64 and restart the entire shard experiment with one binary, preserving the completed shared-layout experiment. The failed startup has no measured rate and is not assigned zero throughput. [source-phases.json](source-phases.json) records the phase-specific jobs, binary hashes and patches.

The following qualified fixed-volume write summaries use logical input GiB/s and final file bytes per logical byte.

| Chunk KiB | n | Write median [min, max] GiB/s | Final-size ratio median [min, max] |
|---:|---:|---:|---:|
| 16 | 3 | 2.510 [2.343, 2.615] | 0.531919 [0.531919, 0.531919] |
| 32 | 3 | 2.365 [2.351, 2.429] | 0.530227 [0.530227, 0.530227] |
| 64 | 3 | 2.639 [2.286, 2.725] | 0.534476 [0.534476, 0.534476] |
| 128 | 3 | 2.267 [2.196, 2.735] | 0.534536 [0.534536, 0.534536] |
| 256 | 3 | 2.420 [2.347, 2.424] | 0.539218 [0.539218, 0.539218] |
| 512 | 3 | 2.496 [2.375, 2.517] | 0.540313 [0.540313, 0.540313] |

Fixed-volume write timing starts with appending to the newly initialized writer and includes final drain and close. Source loading, initialization and the separate discard warmup are excluded from this rate and retained separately. Dynamic shard measurements use the distinct coverage-qualified policy with two seconds requested warmup, three seconds requested append, a 32 GiB logical minimum and at least two generation transitions. Actual dynamic volumes can differ. The 54-shard geometry has 44.1796875 logical GiB per generation, so the coverage requirement can extend the measured input substantially.

These writer rates characterize drain capacity with preloaded, continuously available input. Sustained acquisition rates will be lower and need headroom for network and storage variation. These measurements do not establish a universal headroom percentage or include TIFF decoding and source loading. The interval includes filesystem I/O completion and close; it does not establish crash-durable storage.

Metered shard-write bytes, final file lengths and allocated bytes are recorded separately. Fixed-volume size ratios use the same logical uint16 input bytes as denominator. Final file lengths include the store's metadata and shard files; allocated bytes use st_blocks × 512. Only shared-layout observations have a final-file census here. No final-size ratio is inferred for dynamic shard runs, and no 10% size threshold or single scalar read winner is imposed.

The supplied retained-store-accounting.json preserves the additional per-file length and page-alignment audit, including its recorded checks of W = sum(ceil(L/A) × A). Consult that audit's explicit equality results; the exporter does not replace metered writes with final lengths.

The paired blosc-lz4 15/4 shard rate ratio has median 1.761 (median rate change 76.06%), observed range 1.649–2.947, n=6. Policy coverage-qualified-through-final-close-v2; job 3836375.

The paired blosc-zstd 15/4 shard rate ratio has median 1.028 (median rate change 2.82%), observed range 0.992–1.055, n=6. Policy coverage-qualified-through-final-close-v2; job 3836375.

The paired blosc-lz4 30/15 shard rate ratio has median 1.101 (median rate change 10.14%), observed range 0.859–1.224, n=6. Policy coverage-qualified-through-final-close-v2; job 3836375.

The paired blosc-lz4 9/4 shard rate ratio has median 1.535 (median rate change 53.45%), observed range 1.307–2.804, n=6. Policy coverage-qualified-through-final-close-v2; job 3836375.

Across 6 before/after reference pairs, the after/before 15-shard rate ratio has median 0.975 and range 0.515–1.292. Reference drift is reported separately and is not divided out of the sample measurements.

The largest reference drop was in round 2, job 3836375: after/before = 0.5155 (5.621 to 2.898 logical GiB/s). This observed variation limits conclusions about a stable throughput ceiling.

The full-series median paired blosc-lz4 30/15 gain is 10.14% across 6 pairs. It describes these observations and should not be interpreted as a stable ceiling.

The recorded 54-shard extension decision is False; the first-three-round median 30/15 ratio was 0.996, with 2703.5 seconds remaining on the measurement deadline. When enabled, the 54-shard condition has rounds 4–6 only; compare it with the paired 30-shard observations from those same rounds. This adaptive selection is not six independent repetitions at 54 shards.

A separate post-primary 30-versus-54 follow-up was chosen after reviewing the complete six-round primary 30/15 comparison. This later adaptive decision leaves the original first-three-round decision (False) unchanged. It uses a separate GPU job and a common 96 GiB logical-input minimum for samples and references, rather than the primary shard series' 32 GiB minimum. Its observations are never pooled with the primary job or used to change primary sample counts. [shard-extension-protocol.json](shard-extension-protocol.json) preserves the primary rates and decisions, the later rationale, binary identity, settings and saved schedule.

The completed primary blosc-lz4 30/15 comparison used 6 paired rounds and has median 1.101446, with observed range 0.858860–1.224117. This complete-series result motivated the later follow-up; it was not the original extension gate.

The separate follow-up export contains 12 of 12 expected records: 6 of 6 qualified 30/54 samples and 6 of 6 qualified 15-shard before/after references. Its coverage is complete. [shard-extension-runs.csv](shard-extension-runs.csv) retains every follow-up record, including any failure; [shard-extension-validation.json](shard-extension-validation.json) records missing or duplicate slots. The matched 54/30 rate ratios and 15-shard reference drift are separate from all primary summaries.

In the post-primary follow-up, the paired 54/30 logical-rate ratio has median 0.866081, observed range 0.847080–0.889689, n=3, GPU job 3837212. These are observed repetitions of the later selected comparison, not an independently prespecified extension of the six-round primary study.

Changing shard count changes realizable grouping, append-axis extent and work per file. These comparisons do not isolate an abstract file-count effect, establish a universal optimum, or establish a causal relationship with NFS nconnect. Worker, output-buffer and per-file limits, the recorded machine and the recorded mount belong to the result.

Read summaries below use useful uint16 source GiB/s, not float32 output bandwidth. The complete read-summary.csv also retains policy, trace and machine identities.

| Layout | Backend | Workload | n | Useful GiB/s median [min, max] |
|---|---|---|---:|---:|
| c16 | damacy | aligned-512 | 3 | 1.035 [1.030, 1.180] |
| c32 | damacy | aligned-512 | 3 | 2.127 [1.869, 2.277] |
| c64 | damacy | aligned-512 | 3 | 3.132 [2.207, 3.195] |
| c128 | damacy | aligned-512 | 3 | 3.353 [3.258, 3.494] |
| c256 | damacy | aligned-512 | 3 | 3.400 [2.953, 3.497] |
| c512 | damacy | aligned-512 | 3 | 3.451 [3.437, 3.686] |
| c16 | tensorstore | aligned-512 | 3 | 1.782 [1.751, 1.874] |
| c32 | tensorstore | aligned-512 | 3 | 2.079 [1.665, 2.152] |
| c64 | tensorstore | aligned-512 | 3 | 2.085 [1.686, 2.192] |
| c128 | tensorstore | aligned-512 | 3 | 2.129 [1.926, 2.186] |
| c256 | tensorstore | aligned-512 | 3 | 2.136 [1.926, 2.332] |
| c512 | tensorstore | aligned-512 | 3 | 2.326 [2.158, 2.333] |
| c16 | damacy | full-scan | 3 | 2.620 [2.560, 2.650] |
| c32 | damacy | full-scan | 3 | 2.930 [2.853, 2.968] |
| c64 | damacy | full-scan | 3 | 1.904 [1.753, 2.161] |
| c128 | damacy | full-scan | 3 | 1.588 [1.431, 1.873] |
| c256 | damacy | full-scan | 3 | 1.054 [1.037, 1.172] |
| c512 | damacy | full-scan | 3 | 1.881 [1.844, 2.057] |
| c16 | tensorstore | full-scan | 3 | 1.533 [1.474, 1.566] |
| c32 | tensorstore | full-scan | 3 | 2.148 [2.051, 2.198] |
| c64 | tensorstore | full-scan | 3 | 2.291 [2.248, 2.343] |
| c128 | tensorstore | full-scan | 3 | 2.454 [2.424, 2.498] |
| c256 | tensorstore | full-scan | 3 | 1.836 [1.773, 2.175] |
| c512 | tensorstore | full-scan | 3 | 2.017 [1.962, 2.122] |
| c16 | damacy | translated-256 | 3 | 0.164 [0.131, 0.185] |
| c32 | damacy | translated-256 | 3 | 0.249 [0.233, 0.284] |
| c64 | damacy | translated-256 | 3 | 0.399 [0.294, 0.414] |
| c128 | damacy | translated-256 | 3 | 0.407 [0.392, 0.443] |
| c256 | damacy | translated-256 | 3 | 0.587 [0.481, 0.592] |
| c512 | damacy | translated-256 | 3 | 0.599 [0.345, 0.638] |
| c16 | tensorstore | translated-256 | 3 | 0.135 [0.131, 0.161] |
| c32 | tensorstore | translated-256 | 3 | 0.235 [0.216, 0.248] |
| c64 | tensorstore | translated-256 | 3 | 0.345 [0.267, 0.396] |
| c128 | tensorstore | translated-256 | 3 | 0.367 [0.362, 0.368] |
| c256 | tensorstore | translated-256 | 3 | 0.510 [0.495, 0.537] |
| c512 | tensorstore | translated-256 | 3 | 0.543 [0.390, 0.555] |
| c16 | damacy | translated-512 | 3 | 0.488 [0.323, 0.590] |
| c32 | damacy | translated-512 | 3 | 0.633 [0.434, 0.672] |
| c64 | damacy | translated-512 | 3 | 1.166 [0.678, 1.280] |
| c128 | damacy | translated-512 | 3 | 1.232 [0.818, 1.283] |
| c256 | damacy | translated-512 | 3 | 1.274 [0.717, 1.337] |
| c512 | damacy | translated-512 | 3 | 1.196 [0.975, 1.440] |
| c16 | tensorstore | translated-512 | 3 | 0.495 [0.267, 0.509] |
| c32 | tensorstore | translated-512 | 3 | 0.664 [0.480, 0.722] |
| c64 | tensorstore | translated-512 | 3 | 1.122 [0.747, 1.151] |
| c128 | tensorstore | translated-512 | 3 | 1.217 [0.905, 1.223] |
| c256 | tensorstore | translated-512 | 3 | 1.167 [1.040, 1.232] |
| c512 | tensorstore | translated-512 | 3 | 1.088 [0.781, 1.279] |

Readers assemble contiguous host float32 output, whose bytes are exactly twice the useful uint16 selection bytes. Active read/assembly time excludes source loading, validation, Python selection preparation, index warming and client eviction. File-scoped client eviction is checked before each pass; metadata and shard indexes are warm and server cache state is uncontrolled. Shared mount counters can include other processes and are not server disk bytes. Decoded-byte and decoded-amplification counters are available for Damacy only; TensorStore entries remain blank. Process peak RSS is not a measured-interval peak. Aligned and translated 512-pixel traces have separate identities and coverage; their paired comparison remains separate.

The initial native writer emitted uint16 fill_value as 0.0. Damacy rejected that metadata before codec decoding. The retained metadata-only diagnosis restored reads by changing the spelling to integer zero; direct Blosc samples matched. The isolated writer-fill-value.patch changes metadata spelling without changing encoded pixels or the codec. Native writer source/binary identities were recorded after rebuilding; no additional reader patch was needed for this repair. The reader retains the pre-existing CPU codec and benchmark instrumentation changes in [reader.patch](reader.patch), documented in [reader-source.md](reader-source.md). The [official Zarr data-type specification](https://zarr-specs.readthedocs.io/en/latest/v3/data-types/index.html#permitted-fill-values) requires integer fill values without a fraction or exponent. Original failures, diagnosis records and the narrow repair are retained in the provenance archive.

Plots show medians with observed ranges and expose their numerical inputs in the corresponding figure-data CSVs. The joint table connects the writer and both readers for translated-256 and full-scan workloads; a blank joint value means missing or multiple incomparable reader groups, not zero throughput.
