"""Shared article-reading defaults and editable vector figure exports."""
from contextlib import contextmanager
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]
FIGURES = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "article" / ".cache" / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(ROOT / "article" / ".cache"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

COLORS = {
    "blue": "#0072B2", "orange": "#D55E00", "green": "#009E73",
    "purple": "#CC79A7", "gray": "#606060", "pale_blue": "#DDECF4",
    "pale_orange": "#F6E5D8", "black": "#000000",
}
# Figure 3 uses one compressor key across historical and fixed-block comparisons.
WRITE_CODECS = {
    "blosc-lz4": ("Blosc-LZ4", COLORS["orange"], "o"),
    "blosc-zstd": ("Blosc-Zstd", COLORS["blue"], "s"),
    "lz4": ("LZ4", "#666666", "^"),
    "zstd": ("Zstd", "#6F4696", "D"),
    "none": ("Uncompressed", "black", "x"),
}
MM = 1 / 25.4


@contextmanager
def style_context():
    # Fail explicitly if the requested typeface cannot be reproduced.
    font_manager.findfont("Arial", fallback_to_default=False)
    with plt.rc_context({
        "font.family": "Arial", "font.size": 10,
        "axes.labelsize": 10, "axes.titlesize": 10,
        "xtick.labelsize": 9, "ytick.labelsize": 9,
        "legend.fontsize": 9, "legend.frameon": False,
        "axes.linewidth": 1.0, "axes.spines.top": False,
        "axes.spines.right": False, "axes.grid": False,
        "lines.linewidth": 1.2, "lines.markersize": 6,
        "patch.linewidth": 1.0, "xtick.major.width": 1.0,
        "ytick.major.width": 1.0, "xtick.major.size": 3.5,
        "ytick.major.size": 3.5, "text.color": "black",
        "axes.labelcolor": "black", "figure.facecolor": "white",
        "axes.facecolor": "white", "savefig.facecolor": "white",
        "pdf.fonttype": 42, "ps.fonttype": 42,
        "svg.fonttype": "none", "svg.hashsalt": "readable-zarrs-draft",
    }):
        yield


def save_figure(fig, stem):
    """Write PDF/SVG masters and a 200 dpi PNG preview without changing page size."""
    stem = Path(stem)
    if not stem.is_absolute():
        stem = FIGURES / stem
    stem.parent.mkdir(parents=True, exist_ok=True)
    paths = []
    for suffix in ("pdf", "svg", "png"):
        path = stem.with_suffix("." + suffix)
        metadata = {"Creator": "Writing readable Zarrs figure source"}
        if suffix == "pdf":
            metadata.update(CreationDate=None, ModDate=None)
        elif suffix == "svg":
            metadata.update(Date=None)
        fig.savefig(path, dpi=200, bbox_inches=None, metadata=metadata)
        paths.append(path)
    return paths
