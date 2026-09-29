"""Analytical diagrams for the readable-Zarr article.

Coordinates inside each component are millimetre-like design coordinates. All
geometry is constructed from declared integer array/chunk shapes, not benchmark
images. Run with ``article/.venv/bin/python article/figures/diagrams.py``.
"""
from __future__ import annotations

import csv
from pathlib import Path

from style import COLORS, MM, ROOT, plt, save_figure, style_context
from matplotlib.patches import Rectangle


BLUE = COLORS["blue"]
ORANGE = COLORS["orange"]
PALE_BLUE = COLORS["pale_blue"]
PALE_ORANGE = COLORS["pale_orange"]
GRAY = COLORS["gray"]
WRITTEN = "#DDDDDD"


def _canvas(fig, spec, height):
    ax = fig.add_subplot(spec)
    ax.set(xlim=(0, 183), ylim=(0, height), aspect="equal")
    ax.set_axis_off()
    return ax


def _text(ax, x, y, value, **kwargs):
    options = dict(ha="left", va="center", fontsize=10, color="black")
    options.update(kwargs)
    return ax.text(x, y, value, **options)


def _label(ax, letter, title, y):
    _text(ax, 2, y, letter, fontsize=12, fontweight="bold")
    _text(ax, 9, y, title)


def _rect(ax, x, y, w, h, face="none", edge=GRAY, lw=1.0, **kwargs):
    patch = Rectangle((x, y), w, h, facecolor=face, edgecolor=edge,
                      linewidth=lw, **kwargs)
    ax.add_patch(patch)
    return patch


def _pixel_rect(ax, origin, size, rect, **kwargs):
    """Draw a (y,x,height,width) pixel rectangle in a 512-square array."""
    x, y = origin
    ry, rx, rh, rw = rect
    return _rect(ax, x + size * rx / 512,
                 y + size * (512 - ry - rh) / 512,
                 size * rw / 512, size * rh / 512, **kwargs)


def _grid(ax, origin, size, chunk, *, linewidth=0.8, color=GRAY):
    cy, cx = chunk
    x, y = origin
    for yy in range(0, 513, cy):
        yy = y + size * yy / 512
        ax.plot([x, x + size], [yy, yy], color=color, lw=linewidth)
    for xx in range(0, 513, cx):
        xx = x + size * xx / 512
        ax.plot([xx, xx], [y, y + size], color=color, lw=linewidth)


def _intersections(crop, chunk):
    y, x, h, w = crop
    cy, cx = chunk
    return [(yy, xx, cy, cx)
            for yy in range((y // cy) * cy, y + h, cy)
            for xx in range((x // cx) * cx, x + w, cx)]


def _crop_grid(ax, origin, size, chunk, crop):
    touched = _intersections(crop, chunk)
    for rect in touched:
        _pixel_rect(ax, origin, size, rect, face=PALE_ORANGE, edge="none")
    _pixel_rect(ax, origin, size, crop, face=PALE_BLUE, edge="none")
    _grid(ax, origin, size, chunk)
    _pixel_rect(ax, origin, size, crop, edge=BLUE, lw=1.5)
    return len(touched)


def draw_crop_geometry(fig, spec):
    """Figure 1a: translated crops, geometry, metrics and a shared legend."""
    ax = _canvas(fig, spec, 88)
    ax.set_ylim(17, 105)
    _label(ax, "a", "A translated 256 × 256 crop (one uint16 plane)", 101)
    crop = (64, 64, 256, 256)
    # The main diagrams share one column grid and identical vertical anchors.
    for center, shape, title in [
        (44, (128, 128), "32 KiB chunks"),
        (139, (256, 256), "128 KiB chunks"),
    ]:
        _text(ax, center, 92, title, ha="center", fontweight="bold")
        _text(ax, center, 85.5, f"{shape[0]} × {shape[1]} uint16 pixels", ha="center", fontsize=9)
        count = _crop_grid(ax, (center - 21, 39.5), 42, shape, crop)
        decoded_kib = count * shape[0] * shape[1] * 2 // 1024
        ratio = decoded_kib / 128
        _text(ax, center, 34, f"{count} chunks · {decoded_kib} KiB decoded", ha="center", fontsize=9)
        _text(ax, center, 28, f"{ratio:g}× decoded / useful", ha="center", fontweight="bold", fontsize=9)
    # Legend occupies a dedicated row, with no labels touching the diagrams.
    _rect(ax, 10, 19.5, 4, 4, face=PALE_BLUE, edge=BLUE, lw=1.2)
    _text(ax, 17, 21.5, "Requested pixels", fontsize=9)
    _rect(ax, 69, 19.5, 4, 4, face=PALE_ORANGE, edge=GRAY)
    _text(ax, 76, 21.5, "Decoded but unused", fontsize=9)
    ax.plot([137, 143], [21.5, 21.5], color=GRAY, lw=0.8)
    _text(ax, 146, 21.5, "Chunk edge", fontsize=9)
    return ax


def draw_shard_geometry(fig, spec):
    """Figure 2a: paired orthogonal views and a separate central legend."""
    ax = _canvas(fig, spec, 75)
    _label(ax, "a", "Chunks inside files; the active append layer", 71)
    left, right, size = (14, 20), (127, 20), 40
    _text(ax, 34, 64, "XY: active layer", ha="center")
    _text(ax, 147, 64, "XZ: append along Z", ha="center")
    _rect(ax, *left, size, size, face=PALE_BLUE, edge="none")
    # Exact, distinct line classes: fine chunks inside heavy shard/file borders.
    for spacing, width, color in [(size / 8, 0.8, GRAY), (size / 4, 1.5, "black")]:
        for i in range(round(size / spacing) + 1):
            d = i * spacing
            ax.plot([left[0] + d] * 2, [left[1], left[1] + size], color=color, lw=width)
            ax.plot([left[0], left[0] + size], [left[1] + d] * 2, color=color, lw=width)
    ax.annotate("", (left[0] + size, 15), (left[0], 15), arrowprops=dict(arrowstyle="->", lw=1.2))
    _text(ax, 34, 10, "X", ha="center", fontsize=9)
    ax.annotate("", (8, left[1] + size), (8, left[1]), arrowprops=dict(arrowstyle="->", lw=1.2))
    _text(ax, 3, 40, "Y", ha="center", fontsize=9)
    _text(ax, 91, 52, "16 active files\n4 × 4 XY grid", ha="center", fontsize=9, linespacing=1.6)
    ax.plot([65, 73], [38, 38], color="black", lw=1.5)
    _text(ax, 77, 38, "Shard / file", fontsize=9)
    ax.plot([65, 73], [29, 29], color=GRAY, lw=0.8)
    _text(ax, 77, 29, "Chunk", fontsize=9)
    _rect(ax, *right, size, 3 * size / 4, face="#F3F3F3", edge="none")
    _rect(ax, right[0], right[1] + 3 * size / 4, size, size / 4, face=PALE_BLUE, edge="none")
    for i in range(5):
        d = i * size / 4
        ax.plot([right[0] + d] * 2, [right[1], right[1] + size], color="black", lw=1.5)
        ax.plot([right[0], right[0] + size], [right[1] + d] * 2, color="black", lw=1.5)
    for i in range(4):
        d = (i + 0.5) * size / 4
        ax.plot([right[0] + d] * 2, [right[1], right[1] + size], color=GRAY, lw=0.8)
        ax.plot([right[0], right[0] + size], [right[1] + d] * 2, color=GRAY, lw=0.8)
    ax.annotate("", (174, right[1] + size), (174, right[1]), arrowprops=dict(arrowstyle="->", lw=1.2))
    _text(ax, 179, 40, "Z", ha="center", fontsize=9)
    _text(ax, 147, 13, "X →  (Y into page)", ha="center", fontsize=9)
    _text(ax, 91.5, 3, "Illustrative geometry; measured primary counts: 4, 9, 15, 30.", ha="center", fontsize=9)
    return ax


def conversion_steps():
    """Exact allocation accounting for the declared serial, no-prefetch model.

    Each source/destination chunk is 64 KiB. Source and destination allocations
    are independent; copying views do not allocate another input. We allocate a
    full destination chunk at first touch, even when only half is filled.
    """
    retained = {}  # (destination y,x) -> number of copied half-chunks
    rows = []
    for index in range(8):
        sy, sx = divmod(index, 2)
        keys = [(sy // 2, sx * 2), (sy // 2, sx * 2 + 1)]
        for key in keys:
            retained.setdefault(key, 0)
            retained[key] += 1
        before_flush = len(retained)
        raw_peak_kib = (1 + before_flush) * 64
        complete = [key for key in retained if retained[key] == 2]
        for key in complete:
            del retained[key]
        rows.append(dict(step=index + 1, source_y=sy * 128, source_x=sx * 256,
                         source_kib=64, destinations_before_flush=before_flush,
                         raw_arrays_during_copy_kib=raw_peak_kib,
                         destinations_written=len(complete),
                         destinations_retained=len(retained),
                         retained_destination_kib=64 * len(retained)))
    assert [row["retained_destination_kib"] for row in rows] == [128, 256, 128, 0] * 2
    assert max(row["raw_arrays_during_copy_kib"] for row in rows) == 320
    return rows


def _destination_state(ax, origin, size, step):
    """Output-grid state after release of input and synchronous complete writes."""
    # Only the upper source half is processed in states 1–4.
    written = range(0, 2) if step == 3 else range(0, 4) if step == 4 else []
    live = range(0, 2) if step == 1 else range(0, 4) if step == 2 else range(2, 4) if step == 3 else []
    for col in written:
        _pixel_rect(ax, origin, size, (0, col * 128, 256, 128), face=WRITTEN, edge="none")
    for col in live:
        _pixel_rect(ax, origin, size, (0, col * 128, 256, 128), face=PALE_ORANGE, edge="none")
        _pixel_rect(ax, origin, size, (0, col * 128, 128, 128), face=PALE_BLUE, edge="none")
    _grid(ax, origin, size, (256, 128))
    for col in live:
        _pixel_rect(ax, origin, size, (0, col * 128, 256, 128), edge=ORANGE, lw=1.5)


def draw_conversion_memory(fig, spec):
    """Figure 4: three aligned sections in a 183 × 205 mm canvas."""
    ax = _canvas(fig, spec, 205)
    _label(ax, "a", "Rechunking a 512 × 512 uint16 array", 201)
    source, destination, size = (23, 145), (118, 145), 42
    _text(ax, 44, 194, "Source chunks", ha="center")
    _text(ax, 139, 194, "Destination chunks", ha="center")
    _pixel_rect(ax, source, size, (0, 0, 128, 256), face=PALE_BLUE, edge="none")
    _grid(ax, source, size, (128, 256))
    for i in range(8):
        sy, sx = divmod(i, 2)
        _text(ax, source[0] + size * (sx + 0.5) / 2,
              source[1] + size * (3.5 - sy) / 4, str(i + 1), ha="center")
    _destination_state(ax, destination, size, 1)
    _text(ax, 44, 139, "[128, 256] uint16 · 64 KiB each", ha="center", fontsize=9)
    _text(ax, 139, 139, "[256, 128] uint16 · 64 KiB each", ha="center", fontsize=9)
    ax.annotate("", (108, 166), (75, 166), arrowprops=dict(arrowstyle="->", lw=1.2))
    _text(ax, 91.5, 173, "Copy source 1", ha="center", fontsize=9)
    # Each processing statement occupies its own fixed-width column.
    _text(ax, 9, 129, "Read one source.\nNo prefetch or cache.", fontsize=9, linespacing=1.5)
    _text(ax, 69, 129, "Copy to outputs.\nRelease source.", fontsize=9, linespacing=1.5)
    _text(ax, 125, 129, "Write complete outputs.\nRelease after writing.", fontsize=9, linespacing=1.5)

    _label(ax, "b", "Live output allocations after each step", 115)
    rows = conversion_steps()
    for step, center in enumerate([25, 69, 113, 157], 1):
        _text(ax, center, 107, f"After source {step}", ha="center", fontsize=9)
        _destination_state(ax, (center - 14, 73), 28, step)
        row = rows[step - 1]
        _text(ax, center, 67, f"{row['destinations_retained']} live buffers", ha="center", fontsize=9)
        _text(ax, center, 61, f"{row['retained_destination_kib']} KiB", ha="center", fontsize=9, fontweight="bold")
    # A separate legend band makes the three meanings readable without occlusion.
    _rect(ax, 10, 51, 4, 4, face=PALE_BLUE, edge=BLUE, lw=1.2)
    _text(ax, 17, 53, "Copied pixels", fontsize=9)
    _rect(ax, 65, 51, 4, 4, face=PALE_ORANGE, edge=ORANGE, lw=1.5)
    _text(ax, 72, 53, "Allocated, unfilled", fontsize=9)
    _rect(ax, 130, 51, 4, 4, face=WRITTEN, edge=GRAY)
    _text(ax, 137, 53, "Written / released", fontsize=9)

    _label(ax, "c", "Largest raw-array live set (analytical)", 43)
    _text(ax, 9, 35, "64 KiB input + 4 × 64 KiB output = 320 KiB", fontweight="bold")
    _text(ax, 9, 28, "Array allocations only; codec buffers and process overhead are additional.", fontsize=9)
    ax.plot([9, 176], [24, 24], color=GRAY, lw=1.0)
    _text(ax, 9, 20, "Read / decode", fontweight="bold", fontsize=9)
    _text(ax, 49, 20, "One source request: compressed input + workspace.", fontsize=9)
    _text(ax, 9, 12, "Encode / write", fontweight="bold", fontsize=9)
    _text(ax, 49, 12, "One workspace + one encoded output; synchronous.", fontsize=9)
    _text(ax, 9, 4, "TIFF streaming", fontweight="bold", fontsize=9)
    _text(ax, 49, 4, "Extra decoding + queued images; absent here.", fontsize=9)
    return ax


def main():
    data = ROOT / "article/figures/data/diagram-conversion-buffers.csv"
    data.parent.mkdir(parents=True, exist_ok=True)
    rows = conversion_steps()
    with data.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    with style_context():
        for name, draw, height in [
            ("crop", draw_crop_geometry, 88),
            ("shards", draw_shard_geometry, 75),
            ("conversion", draw_conversion_memory, 205),
        ]:
            fig = plt.figure(figsize=(183 * MM, height * MM))
            spec = fig.add_gridspec(1, 1, left=0, right=1, bottom=0, top=1)[0]
            draw(fig, spec)
            save_figure(fig, f"previews/diagram-{name}")
            plt.close(fig)


if __name__ == "__main__":
    main()
