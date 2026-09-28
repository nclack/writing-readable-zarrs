"""Complete comparable BBBC022 NFS sweeps, using measured write-byte cost."""
import hashlib
import json
from fractions import Fraction
from functools import lru_cache
from statistics import median

from matplotlib.lines import Line2D
from matplotlib.ticker import FormatStrFormatter, NullLocator
from measured import rows, write_csv, _assert_close, _heading
from style import WRITE_CODECS as CODECS, ROOT, FIGURES, MM

SUMMARY = "readable-zarrs-evidence/write-summary.csv"
RUNS = "readable-zarrs-evidence/write-runs.csv"


@lru_cache(maxsize=1)
def collect_sweeps():
    selected = [r for r in rows(SUMMARY) if r["current_report_selected"] == "true"
                and r["sink"] == "fs" and r["input_id"] == "bbbc022-mito"
                and r["proxy_frontier_eligible"] == "true"]
    raw = {r["row_id"]: r for r in rows(RUNS)}
    observations = []
    for backend, count in (("cpu", 14), ("gpu", 13)):
        group = [r for r in selected if r["backend"] == backend]
        assert len(group) == count and len({r["comparison_group"] for r in group}) == 1
        costs = [Fraction(int(r["sink_write_byte_sum"]), int(r["logical_byte_sum"])) for r in group]
        best_cost = min(costs)
        for r, cost in zip(group, costs):
            assert r["storage_type"] == "nfs" and r["nconnect"] == "16"
            assert r["actual_layer_shards_geometry"] == "15"
            assert r["input_sha256"] == "1eff677d3f7d6785bdc8e65079613d6ba2c801a19f33503517a12b8df54affc7"
            runs = [raw[rid] for rid in json.loads(r["run_ids"])]
            assert len(runs) == int(r["valid_observations"]) == 3
            assert all(v["frontier_candidate_record"] == "true" and v["role"] == "sample" for v in runs)
            assert all(v["study_id"] == r["study_id"] and v["comparison_group"] == r["comparison_group"] for v in runs)
            for name, stat in (("median", median), ("min", min), ("max", max)):
                _assert_close(r[name + "_logical_gibs"], stat(float(v["throughput_logical_gibs"]) for v in runs))
            assert sum(int(v["logical_input_bytes"]) for v in runs) == int(r["logical_byte_sum"])
            assert sum(int(v["measured_sink_write_bytes"]) for v in runs) == int(r["sink_write_byte_sum"])
            for v in runs:
                # Historical rate and elapsed-time exports have independently
                # rounded precision; summaries above must still match exactly.
                rate = int(v["logical_input_bytes"]) / 2**30 / float(v["measurement_s"])
                assert abs(float(v["throughput_logical_gibs"]) / rate - 1) < 1e-6
            _assert_close(r["summed_logical_fold"], 1 / cost)
            qualifies = cost <= best_cost * Fraction(11, 10)
            assert qualifies == (r["proxy_within_10pct"] == "true")
            r["compression_fold"] = float(1 / cost)
            r["compression_fold_limit"] = float(1 / best_cost / Fraction(11, 10))
            r["size_allowance_pass"] = qualifies
            observations.extend(runs)
        assert sum(not r["size_allowance_pass"] for r in group) == 10
        winner = max((r for r in group if r["size_allowance_pass"]), key=lambda r: float(r["median_logical_gibs"]))
        assert winner["proxy_10pct_winner"] == "true"
    assert len({r["row_id"] for r in observations}) == 81
    return sorted(selected, key=lambda r: (r["backend"], r["codec"], int(r["raw_chunk_bytes"]), int(r["blosc_block_requested_bytes"] or 0))), observations


def export_sweeps():
    selected, observations = collect_sweeps()
    write_csv("write-sweep-summary.csv", selected)
    write_csv("write-sweep-runs.csv", observations)
    manifest = {
        "inputs": [{"path": p, "sha256": hashlib.sha256((ROOT / p).read_bytes()).hexdigest()} for p in (SUMMARY, RUNS)],
        "selection": "All current-report, frontier-eligible BBBC022-mito NFS sample configurations: CPU 14 and GPU 13, with 3 runs each. No further point selection.",
        "compression_fold": "Sum of unpadded logical input bytes / sum of measured shard-write bytes across the three runs. This is a write-byte proxy, not a final-file census or a mean of run folds.",
        "threshold": "Within each original comparison group: fold >= best fold / 1.10. Eligibility verified using exact integer fractions; 10 configurations fall below each group's threshold.",
        "plot": "Base-2 logarithmic x axes with common 0.75–2.08 limits; common linear throughput axes 2.4–7.2 logical GiB/s. All values are positive. Points are medians; observed min/max ranges and all 81 contributing runs are in the exported tables. Hollow symbols distinguish other settings from the filled highest-median eligible setting. No jitter, interpolation or cross-study pooling.",
        "validation": "Recomputed summary medians/minima/maxima and byte sums from the referenced raw row IDs. Rate/time arithmetic agrees within 1e-6 relative tolerance for independently rounded historical fields (observed maximum <9e-8).",
    }
    (FIGURES / "data/write-sweep-provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")


def draw_write_sweeps(fig, spec):
    grid = spec.subgridspec(1, 2, wspace=.40)
    selected, _ = collect_sweeps()
    axes = []
    for col, backend in enumerate(("cpu", "gpu")):
        ax = fig.add_subplot(grid[0, col])
        group = [r for r in selected if r["backend"] == backend]
        limit = group[0]["compression_fold_limit"]
        ax.set_xscale("log", base=2)
        ax.set(xlim=(.75, 2.08), xticks=[.8, 1, 1.5, 2], ylim=(2.4, 7.2),
               yticks=[3, 4, 5, 6, 7], xlabel="Compression fold (write-byte proxy)",
               ylabel="Drain capacity (logical GiB/s)" if col == 0 else "")
        ax.xaxis.set_major_formatter(FormatStrFormatter("%g×"))
        ax.xaxis.set_minor_locator(NullLocator())
        ax.axvline(limit, color="black", linestyle=(0, (3, 2)), lw=1.3)
        ax.annotate(f"10% limit\n≥ {limit:.3f}×", (1, 1), xycoords="axes fraction",
                    xytext=(0, 16), textcoords="offset points", ha="right",
                    va="baseline", fontsize=9, linespacing=1.35)
        for r in group:
            _, color, marker = CODECS[r["codec"]]
            ax.plot(r["compression_fold"], float(r["median_logical_gibs"]),
                    linestyle="none", marker=marker, color=color, markersize=6,
                    markeredgewidth=1.1, fillstyle="full" if r["proxy_10pct_winner"] == "true" else "none", zorder=3)
        _heading(ax, "CPU measurements\n32 workers" if backend == "cpu" else "GPU measurements\n4 workers", "b" if col == 0 else "c")
        chunk = "64" if backend == "cpu" else "256"
        ax.annotate(f"{len(group)} settings · 10 below the limit\nSelected: Blosc-Zstd, {chunk}/64 KiB",
                    (0, 0), xycoords="axes fraction", xytext=(0, -34), textcoords="offset points",
                    fontsize=9, va="top", linespacing=1.45, annotation_clip=False)
        axes.append(ax)
    position = spec.get_position(fig)
    key = fig.add_axes([position.x0, position.y0 - 31 * MM / fig.get_figheight(),
                        position.width, 11 * MM / fig.get_figheight()])
    key.set_axis_off()
    handles = [Line2D([], [], color=color, marker=marker, linestyle="none", markerfacecolor="none",
                      markeredgewidth=1.1, markersize=6, label=label)
               for label, color, marker in CODECS.values()]
    key.legend(handles=handles, ncol=5, loc="upper left", borderaxespad=0,
               handletextpad=.5, columnspacing=1.2)
    key.text(0, .2, "Filled symbols: highest median within 10% size allowance (per comparison).",
             transform=key.transAxes, fontsize=9, va="baseline")
    return axes
