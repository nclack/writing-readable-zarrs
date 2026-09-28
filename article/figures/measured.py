"""Measured panels; every value is selected from the retained evidence CSVs.

Run ``article/.venv/bin/python article/figures/measured.py`` from the repository
root to regenerate selected data and component previews. Nothing is read from
the NFS read measurements. Original evidence files are never modified.
"""
from __future__ import annotations

import csv
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from statistics import median

from style import ROOT, COLORS, WRITE_CODECS, MM, style_context, save_figure
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FormatStrFormatter, NullLocator

DATA = Path(__file__).resolve().parent / "data"
READ_SOURCE = "readable-zarrs-evidence/read-summary.csv"
WRITE_SOURCE = "bbbc022-evidence/shared-layout-summary.csv"
SHARD_SOURCE = "bbbc022-evidence/shard-summary.csv"
FOLLOW_SOURCE = "bbbc022-evidence/shard-extension-summary.csv"


def rows(path):
    with (ROOT / path).open(newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(name, records):
    if not records:
        raise ValueError(f"No records for {name}")
    DATA.mkdir(parents=True, exist_ok=True)
    with (DATA / name).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def _assert_close(actual, expected):
    if abs(float(actual) - float(expected)) > max(1e-10, abs(float(expected)) * 1e-10):
        raise ValueError(f"Summary mismatch: {actual} != {expected}")


def _check_summary(summary, observations, prefix, value, count):
    if len(observations) != int(summary[count]):
        raise ValueError(f"Repetition count changed for {summary}")
    values = [float(row[value]) for row in observations]
    for suffix, stat in (("median", median), ("min", min), ("max", max)):
        _assert_close(summary[prefix + suffix], stat(values))


@lru_cache(maxsize=1)
def collect_data():
    """Select published comparison groups and verify against individual runs."""
    selected_reads = [r for r in rows(READ_SOURCE) if
        r["phase"] == "cpu-chunk-blocks"
        and r["storage_type"] == "local block storage"
        and r["codec"] == "zstd" and r["block_bytes"] == "16384"
        and (r["reader"] == "tensorstore" or
             (r["reader"] == "damacy" and r["implementation"] == "chunks256-random"))
        and r["workload"] in ("random-1x256x256", "full-scan")
        and int(r["raw_chunk_bytes"]) in (32768, 131072, 524288)]
    selected_reads.sort(key=lambda r: (r["reader"], int(r["raw_chunk_bytes"]), r["workload"]))
    assert len(selected_reads) == 12
    raw_reads = rows("readable-zarrs-evidence/read-runs.csv")
    read_observations = []
    for row in selected_reads:
        run_ids = set(json.loads(row["source_run_ids"]))
        observations = [r for r in raw_reads if r["run_id"] in run_ids]
        assert all(r["status"] == "ok" and r["storage_type"] == "local block storage"
                   for r in observations)
        _check_summary(row, observations, "useful_active_gib_s_", "useful_active_gib_s", "repetitions")
        read_observations.extend(observations)

    writes = sorted(rows(WRITE_SOURCE), key=lambda r: int(r["chunk_bytes"]))
    primary = sorted(rows(SHARD_SOURCE), key=lambda r: (r["codec"], int(r["actual_layer_shards"])))
    followup = sorted(rows(FOLLOW_SOURCE), key=lambda r: int(r["actual_layer_shards"]))
    raw_writes = rows("bbbc022-evidence/write-runs.csv")
    raw_followup = rows("bbbc022-evidence/shard-extension-runs.csv")
    write_observations, shard_observations, follow_observations = [], [], []
    for summaries, raw, dest in ((writes, raw_writes, write_observations),
                                 (primary, raw_writes, shard_observations),
                                 (followup, raw_followup, follow_observations)):
        for row in summaries:
            observations = [r for r in raw if r["job_id"] == row["job_id"]
                            and r["case_id"] == row["case_id"]
                            and r["role"] == "sample" and r["accepted"] == "true"]
            _check_summary(row, observations, "logical_gibs_", "logical_gibs", "n")
            if row["experiment"] == "shared-layouts":
                _check_summary(row, observations, "final_file_bytes_", "final_file_bytes", "n")
            for r in observations:
                _assert_close(r["logical_gibs"], float(r["logical_bytes"]) / 2**30 / float(r["elapsed_s"]))
                _assert_close(r["elapsed_s"], float(r["append_s"]) + float(r["drain_s"]))
            dest.extend(observations)

    smallest_size = min(float(row["final_file_bytes_median"]) for row in writes)
    assert len({row["logical_bytes_median"] for row in writes}) == 1
    logical_bytes = float(writes[0]["logical_bytes_median"])
    compression_limit = logical_bytes / smallest_size / 1.10
    for row in writes:
        assert row["codec"] == "blosc-zstd" and row["blosc_block_bytes"] == "16384"
        assert row["actual_layer_shards"] == "4" and row["n"] == "3"
        row["final_size_over_smallest"] = float(row["final_file_bytes_median"]) / smallest_size
        row["size_allowance_pass"] = row["final_size_over_smallest"] <= 1.10
        row["compression_fold"] = logical_bytes / float(row["final_file_bytes_median"])
        row["compression_fold_limit"] = compression_limit
        assert row["compression_fold"] > 0
        assert (row["compression_fold"] >= compression_limit) == row["size_allowance_pass"]
    assert len(writes) == 6 and all(r["size_allowance_pass"] for r in writes)
    assert max(r["final_size_over_smallest"] for r in writes) < 1.02
    paired = rows("bbbc022-evidence/shard-paired-summary.csv")
    paired_followup = rows("bbbc022-evidence/shard-extension-paired-summary.csv")
    return dict(reads=selected_reads, read_observations=read_observations,
                writes=writes, write_observations=write_observations,
                primary=primary, shard_observations=shard_observations,
                followup=followup, follow_observations=follow_observations,
                paired=paired, paired_followup=paired_followup)


def export_data():
    data = collect_data()
    for name, key in (("read-selected-summary.csv", "reads"),
                      ("read-selected-runs.csv", "read_observations"),
                      ("write-selected-summary.csv", "writes"),
                      ("write-selected-runs.csv", "write_observations"),
                      ("shard-primary-summary.csv", "primary"),
                      ("shard-primary-runs.csv", "shard_observations"),
                      ("shard-followup-summary.csv", "followup"),
                      ("shard-followup-runs.csv", "follow_observations"),
                      ("shard-primary-paired.csv", "paired"),
                      ("shard-followup-paired.csv", "paired_followup")):
        write_csv(name, data[key])
    for source, name in (("bbbc022-evidence/write-reference-drift.csv", "shard-primary-reference-drift.csv"),
                         ("bbbc022-evidence/shard-extension-reference-drift.csv", "shard-followup-reference-drift.csv")):
        write_csv(name, rows(source))
    inputs = [READ_SOURCE, WRITE_SOURCE, SHARD_SOURCE, FOLLOW_SOURCE,
              "readable-zarrs-evidence/read-runs.csv", "bbbc022-evidence/write-runs.csv",
              "bbbc022-evidence/shard-extension-runs.csv",
              "bbbc022-evidence/shard-paired-summary.csv",
              "bbbc022-evidence/shard-extension-paired-summary.csv",
              "bbbc022-evidence/write-reference-drift.csv",
              "bbbc022-evidence/shard-extension-reference-drift.csv"]
    manifest = {"inputs": [{"path": p, "sha256": hashlib.sha256((ROOT / p).read_bytes()).hexdigest()} for p in inputs],
                "transformations": [
                    "Read selection: cpu-chunk-blocks, local block storage, Zstd, 16384-byte blocks, 32/128/512 KiB chunks; Damacy chunks256-random or TensorStore; full-scan and random-1x256x256.",
                    "Read rates: useful_active_gib_s, using source uint16 bytes; no NFS read records selected.",
                    "Write rates: logical uint16 bytes / 2**30 / (append seconds + final drain/close seconds).",
                    "Final-size ratio: median final_file_bytes / smallest median final_file_bytes among six shared-layout candidates; logical volume equal for every candidate.",
                    "Compression fold: unpadded logical input bytes / median final_file_bytes, including metadata and shard indexes. The 10% size allowance is compression fold >= best observed fold / 1.10. All values are positive; none excluded from the base-2 logarithmic axis, with limits 1.6 to 2.0 and ticks in fold units.",
                    "Medians and observed minima/maxima independently verified against retained run records.",
                    "Paired gain annotations: 100 * (median of per-round numerator/denominator rates - 1); not ratios of pooled medians.",
                    "Primary and later adaptive follow-up remain separate; reference observations are not pooled with samples."],
                "uncertainty": "Observed min/max, never confidence intervals; read and write-layout n=3, primary shard n=6, follow-up n=3."}
    (DATA / "measured-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")


def _panel(ax, label, header_lines=1):
    baseline = 16 + (header_lines - 1) * 13.5
    ax.annotate(label, (0, 1), xycoords="axes fraction", xytext=(-36, baseline), textcoords="offset points",
                fontsize=12, fontweight="bold", va="baseline", ha="left",
                annotation_clip=False)


def _heading(ax, text, label):
    ax.annotate(text, (0, 1), xycoords="axes fraction", xytext=(0, 16), textcoords="offset points",
                fontsize=10, va="baseline", ha="left", annotation_clip=False,
                linespacing=1.35)
    _panel(ax, label, text.count("\n") + 1)


def _errors(row, prefix):
    center = float(row[prefix + "median"])
    return [[center - float(row[prefix + "min"])], [float(row[prefix + "max"]) - center]]


def _draw_read(fig, spec, reader, letter):
    ax = fig.add_subplot(spec)
    subset = [r for r in collect_data()["reads"] if r["reader"] == reader]
    symbols = {32: ("o", COLORS["gray"]), 128: ("D", COLORS["blue"]), 512: ("s", COLORS["orange"])}
    offsets = ({32: (-10, 12), 128: (10, -20), 512: (10, 12)} if reader == "damacy"
               else {32: (10, -12), 128: (-10, 21), 512: (10, 12)})
    for kib in (32, 128, 512):
        crop = next(r for r in subset if int(r["raw_chunk_bytes"]) == kib * 1024 and r["workload"].startswith("random"))
        scan = next(r for r in subset if int(r["raw_chunk_bytes"]) == kib * 1024 and r["workload"] == "full-scan")
        x, y = float(crop["useful_active_gib_s_median"]), float(scan["useful_active_gib_s_median"])
        marker, color = symbols[kib]
        ax.errorbar(x, y, xerr=_errors(crop, "useful_active_gib_s_"),
                    yerr=_errors(scan, "useful_active_gib_s_"), fmt=marker,
                    color=color, markersize=6.5, markeredgecolor="black", markeredgewidth=.9,
                    elinewidth=1.3, capsize=3, capthick=1.1, zorder=3)
        shape = " × ".join(map(str, json.loads(crop["chunk_shape"])))
        if reader == "tensorstore" and kib == 128:
            # Anchor above the whole observed range so narrower composite
            # panels cannot push the two-line label across the vertical axis.
            ax.text(x + .025, float(scan["useful_active_gib_s_max"]) + .10,
                    f"{kib} KiB\n{shape}", ha="left", va="bottom",
                    fontsize=9, fontweight="bold")
            continue
        dx, dy = offsets[kib]
        ax.annotate(f"{kib} KiB\n{shape}", (x, y), xytext=(dx, dy),
                    textcoords="offset points", ha="left" if dx > 0 else "right",
                    va="bottom" if dy > 0 else "top", fontsize=9,
                    fontweight="bold" if kib == 128 else "normal")
    ax.set(xlabel="Crop read rate (useful GiB/s)",
           ylabel="Full-array read rate (useful GiB/s)", xlim=(1.1, 2.4))
    ax.set_xticks([1.2, 1.6, 2.0])
    if reader == "damacy":
        ax.set_ylim(3.6, 14.8)
        ax.set_yticks([4, 6, 8, 10, 12, 14])
        title = "Damacy · local NVMe"
    else:
        ax.set_ylim(3.5, 6.5)
        ax.set_yticks([3.5, 4.0, 4.5, 5.0, 5.5, 6.0])
        title = "TensorStore · local NVMe"
    _heading(ax, title, letter)
    return ax


def draw_read_damacy(fig, spec):
    return _draw_read(fig, spec, "damacy", "b")


def draw_read_tensorstore(fig, spec):
    return _draw_read(fig, spec, "tensorstore", "c")


def _gain(data, codec, comparison):
    row = next(r for r in data if r["codec"] == codec and r["comparison"] == comparison)
    return 100 * (float(row["rate_ratio_median"]) - 1)


def draw_shard_primary(fig, spec):
    grid = spec.subgridspec(2, 1, height_ratios=[1, .30], hspace=.25)
    ax = fig.add_subplot(grid[0, 0])
    footer = fig.add_subplot(grid[1, 0])
    footer.set_axis_off()
    data = collect_data()
    for row in data["primary"]:
        lz4 = row["codec"] == "blosc-lz4"
        color, marker = (COLORS["blue"], "o") if lz4 else (COLORS["orange"], "s")
        count = int(row["actual_layer_shards"])
        # The four measured counts are categorical groups. Dodge codecs only
        # within shared groups so the long LZ4 range cannot cover Zstd data.
        x = {4: 0, 9: 1, 15: 2, 30: 3}[count]
        if count in (4, 15):
            x += -.11 if lz4 else .11
        raw = [r for r in data["shard_observations"] if r["case_id"] == row["case_id"]]
        ax.scatter([x] * len(raw), [float(r["logical_gibs"]) for r in raw],
                   s=18, facecolors="white", edgecolors=color, linewidths=.9, zorder=2)
        ax.errorbar(x, float(row["logical_gibs_median"]), yerr=_errors(row, "logical_gibs_"),
                    color=color, fmt=marker, markersize=6.5, markeredgecolor="black", markeredgewidth=.9,
                    capsize=3, capthick=1.1, elinewidth=1.3, zorder=3)
    g15 = _gain(data["paired"], "blosc-lz4", "15/4")
    g30 = _gain(data["paired"], "blosc-lz4", "30/15")
    gz = _gain(data["paired"], "blosc-zstd", "15/4")
    handles = [Line2D([], [], color=COLORS["blue"], marker="o", markersize=6.5, linestyle="none", markeredgecolor="black", markeredgewidth=.9,
                      label=f"LZ4: 64 KiB chunks; 16 KiB blocks\nPaired: 15/4 +{g15:.1f}%; 30/15 +{g30:.1f}%"),
               Line2D([], [], color=COLORS["orange"], marker="s", markersize=6.5, linestyle="none", markeredgecolor="black", markeredgewidth=.9,
                      label=f"Zstd: 256 KiB chunks and blocks\nPaired: 15/4 +{gz:.1f}%")]
    footer.legend(handles=handles, loc="upper left", fontsize=9, handletextpad=.5,
                  borderaxespad=0, labelspacing=1.0)
    ax.set(xlabel="Shards in append layer", ylabel="Drain capacity (logical GiB/s)",
           xlim=(-.5, 3.5), ylim=(0, 7.5), xticks=[0, 1, 2, 3],
           xticklabels=[4, 9, 15, 30], yticks=[0, 2, 4, 6])
    _heading(ax, "Primary study\n32 GiB minimum · 6 rounds", "b")
    return ax


def draw_shard_followup(fig, spec):
    grid = spec.subgridspec(2, 1, height_ratios=[1, .30], hspace=.25)
    ax = fig.add_subplot(grid[0, 0])
    footer = fig.add_subplot(grid[1, 0])
    footer.set_axis_off()
    data = collect_data()
    for round_id in ("1", "2", "3"):
        pair = sorted([r for r in data["follow_observations"] if r["round"] == round_id],
                      key=lambda r: int(r["actual_layer_shards"]))
        assert len(pair) == 2
        ax.plot([int(r["actual_layer_shards"]) for r in pair],
                [float(r["logical_gibs"]) for r in pair], color="#707070", lw=1.1,
                marker="o", markersize=4, markerfacecolor="white", zorder=1)
    for row in data["followup"]:
        ax.errorbar(int(row["actual_layer_shards"]), float(row["logical_gibs_median"]),
                    yerr=_errors(row, "logical_gibs_"), fmt="o", color=COLORS["blue"],
                    markeredgecolor="black", markeredgewidth=.9, markersize=6.5,
                    capsize=3, capthick=1.1, elinewidth=1.3, zorder=3)
    g = _gain(data["paired_followup"], "blosc-lz4", "54/30")
    footer.text(0, 1, f"LZ4: 64 KiB chunks\n16 KiB blocks\n54/30 paired: {g:.1f}%\nLines join paired rounds",
                transform=footer.transAxes, fontsize=9, va="top", linespacing=1.45)
    ax.set(xlabel="Shards in append layer", ylabel="Drain capacity (logical GiB/s)",
           xlim=(22, 62), ylim=(0, 7.5), xticks=[30, 54], yticks=[0, 2, 4, 6])
    _heading(ax, "Later follow-up\n96 GiB minimum · 3 rounds", "c")
    return ax


def _write_points(ax, candidates, winner):
    """Median-only compression overview; the companion panel shows every rate interval."""
    for row in candidates:
        kib = int(float(row["chunk_kib"]))
        _, color, marker = WRITE_CODECS[row["codec"]]
        x, y = row["compression_fold"], float(row["logical_gibs_median"])
        ax.plot(x, y, marker=marker, linestyle="none", color=color,
                markersize=6, markeredgewidth=1.1,
                fillstyle="full" if row is winner else "none", zorder=3)
        if kib == 128 or row is winner:
            ax.annotate(f"{kib} KiB", (x, y), xytext=(-10, 0),
                        textcoords="offset points", ha="right", va="center", fontsize=9)


def draw_write_sample(fig, spec):
    """Show the fixed first microscopy field without covering or resampling pixels.

    The surrounding row is 54 mm high in the assembled Figure 3. Image and
    annotation positions use physical units, so the 48 mm image width and
    calibrated external scale bar remain independent of the row's aspect ratio.
    """
    import numpy as np

    sample_path = DATA / "bbbc022-a14-s1-w5.npy"
    metadata = json.loads(sample_path.with_suffix(".json").read_text())
    if hashlib.sha256(sample_path.read_bytes()).hexdigest() != metadata["array_sha256"]:
        raise ValueError("BBBC022 figure sample checksum does not match its provenance")
    sample = np.load(sample_path, allow_pickle=False)
    if list(sample.shape) != metadata["shape_yx"] or str(sample.dtype) != metadata["dtype"]:
        raise ValueError("BBBC022 figure sample geometry or dtype changed")

    row = fig.add_subplot(spec)
    row.set_axis_off()
    position = spec.get_position(fig)
    width_mm = position.width * fig.get_figwidth() / MM
    height_mm = position.height * fig.get_figheight() / MM
    image_width_mm = 48.0
    image_height_mm = image_width_mm * sample.shape[0] / sample.shape[1]
    image_bottom_mm = 9.5
    image_top_mm = image_bottom_mm + image_height_mm
    if height_mm < image_top_mm + 8 or width_mm < 135:
        raise ValueError("The microscopy sample row needs at least 135 × 54 mm")

    header_y = (height_mm - 4.5) / height_mm
    row.text(0, header_y, "BBBC022 microscopy input", transform=row.transAxes,
             ha="left", va="baseline", fontsize=10)
    row.annotate("a", (0, header_y), xycoords="axes fraction",
                 xytext=(-36, 0), textcoords="offset points", ha="left",
                 va="baseline", fontsize=12, fontweight="bold", annotation_clip=False)

    image_ax = row.inset_axes([0, image_bottom_mm / height_mm,
                              image_width_mm / width_mm, image_height_mm / height_mm])
    low, high = metadata["display"]["intensity_limits"]
    image_ax.imshow(sample, cmap="gray", vmin=low, vmax=high,
                    interpolation="none", origin="upper", aspect="equal")
    image_ax.set_axis_off()

    # The bar is an editable vector outside the pixel rectangle. Its length
    # comes from the source pixel calibration rather than image magnification.
    scale_um = metadata["display"]["scale_bar_um"]
    pixel_um = metadata["pixel_size_um_yx"][1]
    bar_width_mm = (scale_um / pixel_um) * image_width_mm / sample.shape[1]
    center_mm = image_width_mm / 2
    row.plot([(center_mm - bar_width_mm / 2) / width_mm,
              (center_mm + bar_width_mm / 2) / width_mm],
             [6.2 / height_mm] * 2, transform=row.transAxes,
             color="black", lw=1.8, solid_capstyle="butt", clip_on=False)
    row.text(center_mm / width_mm, 4.4 / height_mm, f"{scale_um:g} µm",
             transform=row.transAxes, fontsize=9, ha="center", va="top")

    labels = ["U2OS cells", "MitoTracker Deep Red",
              f"Plate {metadata['plate']} · {metadata['well']} · site {metadata['site']}",
              "First of 16 input fields", "Full field · 520 × 696 uint16 pixels",
              "BBBC022 · Broad Institute"]
    for index, label in enumerate(labels):
        text = row.text(60 / width_mm, (image_top_mm - 6.8 * index) / height_mm,
                        label, transform=row.transAxes, fontsize=9,
                        ha="left", va="top")
        if index == len(labels) - 1:
            text.set_url(metadata["source_url"])
    return row, image_ax


def draw_write_tradeoff(fig, spec, labels=("b", "c")):
    """Absolute compression fold and one clear rate-interval lane per candidate."""
    grid = spec.subgridspec(1, 2, width_ratios=[1, 1.5], wspace=.5)
    overview = fig.add_subplot(grid[0, 0])
    detail = fig.add_subplot(grid[0, 1])
    candidates = collect_data()["writes"]
    winner = max((r for r in candidates if r["size_allowance_pass"]),
                 key=lambda r: float(r["logical_gibs_median"]))
    compression_limit = candidates[0]["compression_fold_limit"]
    overview.set_xscale("log", base=2)
    _write_points(overview, candidates, winner)
    overview.axvline(compression_limit, color="black", linestyle=(0, (3, 2)), lw=1.3)
    overview.annotate(f"10% size limit: ≥ {compression_limit:.3f}×",
                      (compression_limit, .07), xycoords=overview.get_xaxis_transform(),
                      xytext=(-7, 0), textcoords="offset points", fontsize=9,
                      ha="right", va="bottom", rotation=90)
    overview.set(xlim=(1.6, 2.0), xticks=[1.6, 1.8, 2.0],
                 ylabel="Drain capacity (logical GiB/s)", xlabel="Compression fold (log scale)",
                 ylim=(2.05, 2.90), yticks=[2.1, 2.3, 2.5, 2.7, 2.9])
    overview.xaxis.set_major_formatter(FormatStrFormatter("%.1f×"))
    overview.xaxis.set_minor_locator(NullLocator())
    ticklabels = []
    for index, row in enumerate(candidates):
        kib = int(float(row["chunk_kib"]))
        _, color, marker = WRITE_CODECS[row["codec"]]
        detail.errorbar(float(row["logical_gibs_median"]), index,
                        xerr=_errors(row, "logical_gibs_"), fmt=marker, color=color,
                        markersize=6, markeredgewidth=1.1,
                        fillstyle="full" if row is winner else "none",
                        elinewidth=1.3, capsize=3, capthick=1.1, zorder=3)
        ticklabels.append(f"{kib} KiB\n{row['compression_fold']:.3f}×")
    detail.set(xlim=(2.1, 2.8), xticks=[2.2, 2.4, 2.6, 2.8],
               ylim=(len(candidates) - .4, -.6), yticks=list(range(len(candidates))),
               yticklabels=ticklabels, xlabel="Drain capacity (logical GiB/s)")
    detail.spines["left"].set_visible(False)
    detail.tick_params(axis="y", length=0, pad=9)
    for tick, row in zip(detail.get_yticklabels(), candidates):
        if int(float(row["chunk_kib"])) in (64, 128):
            tick.set_fontweight("bold")
    _heading(overview, "Fixed-block Zstd comparison\nFinal stored bytes · GPU", labels[0])
    _heading(detail, "Capacity by chunk size\nCompression fold below each chunk", labels[1])
    overview.annotate("Final-size comparison: logical input / final bytes. Intervals: observed min–max, 3 runs.\n"
                "128 KiB: proposed compromise. 64 KiB: highest observed write median.",
                (0, 0), xycoords="axes fraction", xytext=(0, -40), textcoords="offset points",
                fontsize=9, va="top", linespacing=1.45, annotation_clip=False)
    return overview, detail


def draw_shard_reference(fig, spec):
    """Supporting plot: all before/after reference pairs in their original jobs."""
    grid = spec.subgridspec(2, 2, width_ratios=[1.4, 1], height_ratios=[1, .16], wspace=.2, hspace=.25)
    axes = []
    for index, source, title in (
        (0, "bbbc022-evidence/write-reference-drift.csv", "Primary references\n32 GiB minimum"),
        (1, "bbbc022-evidence/shard-extension-reference-drift.csv", "Later references\n96 GiB minimum")):
        ax = fig.add_subplot(grid[0, index])
        points = rows(source)
        for row in points:
            x = int(row["round"])
            before, after = float(row["before_logical_gibs"]), float(row["after_logical_gibs"])
            # Each tick is a round, not a timestamp. Separate the two roles
            # within that group so nearly equal observations remain visible.
            ax.plot([x - .13, x + .13], [before, after], color="#707070", lw=1.2, zorder=1)
            ax.plot(x - .13, before, marker="o", markersize=6.5, markeredgewidth=1.1, linestyle="none",
                    color=COLORS["blue"], markerfacecolor="white", zorder=3)
            ax.plot(x + .13, after, marker="s", markersize=6, linestyle="none",
                    color="black", zorder=3)
        ax.set(xlabel="Round", ylabel="Drain capacity (logical GiB/s)",
               xlim=(.5, len(points) + .5), ylim=(0, 7),
               xticks=list(range(1, len(points) + 1)), yticks=[0, 2, 4, 6])
        _heading(ax, title, "a" if index == 0 else "b")
        axes.append(ax)
    footer = fig.add_subplot(grid[1, :])
    footer.set_axis_off()
    handles = [Line2D([], [], color=COLORS["blue"], marker="o", markersize=6.5, markerfacecolor="white", linestyle="none", label="Before samples"),
               Line2D([], [], color="black", marker="s", markersize=6, linestyle="none", label="After samples")]
    footer.legend(handles=handles, loc="upper center", ncol=2, fontsize=9, borderaxespad=0)
    return axes


def main():
    export_data()
    with style_context():
        fig = plt.figure(figsize=(183 * MM, 108 * MM), layout="constrained")
        grid = fig.add_gridspec(1, 2)
        draw_read_damacy(fig, grid[0, 0])
        draw_read_tensorstore(fig, grid[0, 1])
        save_figure(fig, "previews/measured-read")
        plt.close(fig)
        fig = plt.figure(figsize=(183 * MM, 135 * MM), layout="constrained")
        grid = fig.add_gridspec(1, 2, width_ratios=[1.5, 1])
        draw_shard_primary(fig, grid[0, 0])
        draw_shard_followup(fig, grid[0, 1])
        save_figure(fig, "previews/measured-shards")
        plt.close(fig)
        fig = plt.figure(figsize=(183 * MM, 140 * MM), layout="constrained")
        draw_write_tradeoff(fig, fig.add_gridspec(1, 1)[0, 0])
        save_figure(fig, "previews/measured-write")
        plt.close(fig)
        fig = plt.figure(figsize=(183 * MM, 110 * MM), layout="constrained")
        draw_shard_reference(fig, fig.add_gridspec(1, 1)[0, 0])
        save_figure(fig, "previews/measured-reference")
        plt.close(fig)


if __name__ == "__main__":
    main()
