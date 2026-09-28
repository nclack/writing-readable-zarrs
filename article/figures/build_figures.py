"""Build the four article figures from recorded data and analytical examples."""
from pathlib import Path
import hashlib
import json
import platform
import csv

from style import FIGURES, ROOT, MM, plt, style_context, save_figure
import matplotlib
import numpy
from matplotlib import font_manager
from diagrams import draw_crop_geometry, draw_shard_geometry, draw_conversion_memory, conversion_steps
from measured import (
    draw_read_damacy, draw_read_tensorstore, draw_shard_primary,
    draw_shard_followup, draw_write_sample, draw_write_tradeoff, draw_shard_reference, export_data,
)
from write_sweeps import draw_write_sweeps, export_sweeps


def build():
    export_data()
    export_sweeps()
    steps = conversion_steps()
    with (FIGURES / "data/diagram-conversion-buffers.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=steps[0].keys())
        writer.writeheader()
        writer.writerows(steps)
    outputs = []
    with style_context():
        fig = plt.figure(figsize=(183 * MM, 230 * MM))
        top = fig.add_gridspec(1, 1, left=.025, right=.98, bottom=.52, top=.985)
        bottom = fig.add_gridspec(1, 2, left=.105, right=.98, bottom=.075,
                                  top=.435, wspace=.38)
        draw_crop_geometry(fig, top[0])
        fig.text(.105, .495, "Balance between two read workloads",
                 fontsize=10, fontweight="bold", ha="left", va="baseline")
        draw_read_damacy(fig, bottom[0])
        draw_read_tensorstore(fig, bottom[1])
        outputs += save_figure(fig, "figure-1")
        plt.close(fig)

        fig = plt.figure(figsize=(183 * MM, 245 * MM))
        top = fig.add_gridspec(1, 1, left=.025, right=.98, bottom=.64, top=.97)
        bottom = fig.add_gridspec(1, 2, left=.105, right=.98, bottom=.08,
                                  top=.57, width_ratios=[1.5, 1], wspace=.4)
        draw_shard_geometry(fig, top[0])
        draw_shard_primary(fig, bottom[0])
        draw_shard_followup(fig, bottom[1])
        outputs += save_figure(fig, "figure-2")
        plt.close(fig)

        # Fixed physical bands: image 190–244 mm, upper plots 116–174 mm,
        # compact notes/legend 85–104 mm, lower plots 22–72 mm.
        fig = plt.figure(figsize=(183 * MM, 250 * MM))
        top = fig.add_gridspec(1, 1, left=.105, right=.975, bottom=190/250, top=244/250)
        draw_write_sample(fig, top[0])
        sweeps = fig.add_gridspec(1, 1, left=.105, right=.975, bottom=116/250, top=174/250)
        draw_write_sweeps(fig, sweeps[0])
        grid = fig.add_gridspec(1, 1, left=.105, right=.975, bottom=22/250, top=72/250)
        draw_write_tradeoff(fig, grid[0], labels=("d", "e"))
        outputs += save_figure(fig, "figure-3")
        plt.close(fig)

        fig = plt.figure(figsize=(183 * MM, 215 * MM))
        grid = fig.add_gridspec(1, 1, left=.025, right=.98, bottom=.025, top=.98)
        draw_conversion_memory(fig, grid[0])
        outputs += save_figure(fig, "figure-4")
        plt.close(fig)

        fig = plt.figure(figsize=(183 * MM, 110 * MM))
        grid = fig.add_gridspec(1, 1, left=.105, right=.98, bottom=.08, top=.86)
        draw_shard_reference(fig, grid[0])
        outputs += save_figure(fig, "figure-s1")
        plt.close(fig)

    source_paths = list(FIGURES.glob("*.py")) + list((FIGURES / "data").glob("*.csv"))
    source_paths += [ROOT / "readable-zarrs-evidence/read-summary.csv"]
    source_paths += [ROOT / "readable-zarrs-evidence/write-summary.csv", ROOT / "readable-zarrs-evidence/write-runs.csv"]
    source_paths += list((ROOT / "bbbc022-evidence").glob("*summary.csv"))
    source_paths += [
        ROOT / "bbbc022-evidence/input-source.json",
        FIGURES / "data/bbbc022-a14-s1-w5.npy",
        FIGURES / "data/bbbc022-a14-s1-w5.json",
    ]
    manifest = {
        "status": "Draft figures; analytical diagrams are not process-memory measurements.",
        "python": platform.python_version(), "matplotlib": matplotlib.__version__,
        "numpy": numpy.__version__, "font": font_manager.findfont("Arial"),
        "nature_guidance_checked": "2026-09-25",
        "display_profile": "Article reading: larger type and strokes requested 2026-09-26; 183 mm width with content-driven heights.",
        "reproduction": "python article/figures/build_figures.py",
        "read_scope": "Local NVMe, synthetic smooth4, fixed 16 KiB Zstd blocks.",
        "write_scope": "Separate BBBC022 microscopy replays over NFS: historical CPU/GPU sweeps use measured write-byte proxies; the newer fixed-volume comparison uses final file sizes. Primary shard and follow-up studies remain separate.",
        "microscopy_image": "Figure 3a retains native pixels from the first benchmark field; calibration and display-only contrast are recorded in data/bbbc022-a14-s1-w5.json.",
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(source_paths))
        },
        "outputs": [str(p.relative_to(ROOT)) for p in outputs],
    }
    (FIGURES / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Built four main figures and supporting Figure S1 as PDF, SVG and PNG.")


if __name__ == "__main__":
    build()
