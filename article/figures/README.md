# Article figures

Draft figures for [Writing readable Zarrs](../draft.md). The article's
[figure plan](../../planning/article-outline.md) defines the argument;
[style guidance](../../planning/writing-guidelines.md#figure-style-and-delivery)
records the current Nature conventions used here.

| Figure | Content | Outputs |
|---|---|---|
| 1 | Crop geometry and local NVMe crop/scan tradeoffs | [PDF](figure-1.pdf), [SVG](figure-1.svg), [preview](figure-1.png) |
| 2 | Active shard layer and NFS streaming measurements | [PDF](figure-2.pdf), [SVG](figure-2.svg), [preview](figure-2.png) |
| 3 | BBBC022 image, complete CPU/GPU NFS comparisons and fixed-block Zstd comparison | [PDF](figure-3.pdf), [SVG](figure-3.svg), [preview](figure-3.png) |
| 4 | Analytical conversion-buffer example | [PDF](figure-4.pdf), [SVG](figure-4.svg), [preview](figure-4.png) |
| S1 | Before/after reference runs, kept separate by study | [PDF](figure-s1.pdf), [SVG](figure-s1.svg), [caption](supporting.md) |

The NFS write evidence remains central to the article. Local NVMe measurements
support the read conclusions; the less reliable NFS read measurements are
excluded from these comparisons. Reads use synthetic smooth4 input, whereas
writes use microscopy replay. These are separate studies.

## Reproduce

From the repository root, with Python 3.12:

```sh
python3 -m venv article/.venv
article/.venv/bin/python -m pip install -r article/requirements.txt
article/.venv/bin/python article/figures/build_figures.py
article/.venv/bin/python article/build_review.py
```

The listed direct dependency versions reproduce this drafting environment;
they are not a complete transitive lock. Arial must be installed. Figure source
and inputs are recorded with SHA-256 hashes in [manifest.json](manifest.json).
The build replaces generated figures, leaving the evidence inputs untouched.
PDF masters are 183 mm wide with embedded TrueType fonts. The article reading
profile uses 9–10 pt text, 12 pt panel letters, thicker strokes and heights
chosen to keep diagrams, data and annotations separate. This larger profile
implements the author's 2026-09-26 readability request; journal print dimensions
and typography would be a separate export. SVGs preserve text but depend on
font availability. PNGs are reading previews, not the vector masters.

Figure 3a embeds a native-resolution 696 × 520 image from the actual BBBC022
benchmark input, with vector labels and a calibrated 100 µm scale bar outside
the image. The stored [uint16 field](data/bbbc022-a14-s1-w5.npy) is unchanged;
the [provenance record](data/bbbc022-a14-s1-w5.json) identifies the source TIFF,
verified benchmark asset, CC0 attribution and display-only intensity mapping.
The first field matches the existing corpus thumbnail. Its whole-field linear
grayscale limits are the recorded 1st and 99.5th percentiles; no denoising,
filtering or crop was applied. PDF/SVG retain the native image raster and
editable vector annotations.

The original data came from [BBBC022v1][bbbc022] and its
[plate 20585/channel w5 archive][bbbc022-images]. To repeat the extraction from
the checksum-matching benchmark raw asset:

```sh
article/.venv/bin/python article/figures/prepare_bbbc022_sample.py /path/to/bbbc022-mito.raw
```

Regular figure builds use the included field and require no external corpus.

## Evidence and design

Figure 3b–c uses all 27 configurations in the retained BBBC022 CPU/GPU comparisons,
validated against all 81 contributing runs. [Comparison source](write_sweeps.py),
[summaries and observed ranges](data/write-sweep-summary.csv),
[runs](data/write-sweep-runs.csv) and [transformations](data/write-sweep-provenance.json)
retain the original comparison groups. Compression uses measured shard-write
bytes as a proxy, with a separate 10% threshold for each group. Figure 3d–e
retains the newer six-layout comparison with directly measured final sizes.
The assembled reading figure is 183 × 250 mm to preserve legibility.
Across b–e, color and shape identify the compressor; a filled symbol marks
the highest median that meets its comparison's 10% size allowance. Panels
d–e therefore use blue Blosc-Zstd squares, with only 64 KiB filled. Chunk
sizes and the proposed 128 KiB compromise are identified with text.

- [Measured panels](measured.py), [selected data](data/), and
  [measurement/caption notes](measured-notes.md).
- [Analytical diagrams](diagrams.py) and [assumptions/caption notes](diagram-notes.md).
- [Shared style](style.py) and [figure assembly](build_figures.py).

Report medians and observed ranges with run counts; ranges are not confidence
intervals. Figure 4 counts specified live raw-array allocations, not measured
process memory. Each caption states the relevant qualifications.

Figure preparation used the Scientific Visualization skill from K-Dense:
Kassis, T., Agarwal, V., He, Y., Patel, D., and Brueckner, A. M. (2026),
[Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents](https://doi.org/10.48550/arXiv.2609.00065).
The current arXiv record was verified on 2026-09-25. Nature guidance is linked
in the project style document; adopting it is not journal acceptance or an
accessibility certification.

[bbbc022]: https://bbbc.broadinstitute.org/BBBC022
[bbbc022-images]: https://data.broadinstitute.org/bbbc/BBBC022/BBBC022_v1_images_20585w5.zip
