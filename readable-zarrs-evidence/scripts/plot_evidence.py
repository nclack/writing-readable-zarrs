import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter


COLORS = {"damacy": "#1768a5", "tensorstore": "#be6414", "cpu": "#1768a5", "gpu": "#9a3886"}


def read_csv(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def save_figure(figure, output, name):
    figure.savefig(output / (name + ".png"), dpi=170)
    figure.savefig(output / (name + ".svg"), metadata={"Date": None})
    plt.close(figure)


def read_figure(root, output, exported):
    rows = read_csv(root / "read-summary.csv")
    figure, axes = plt.subplots(1, 3, figsize=(13.2, 5.2))
    settings = (
        ("Local XFS: translated crops", "cpu-small-chunks", "local block storage", "random-1x256x256", "chunks256-random", [16, 32, 64, 128]),
        ("NFS: translated crops", "cpu-nfs-local-spot", "NFS", "random-1x256x256", "chunks256-random", [32, 128, 512]),
        ("Local XFS: full-array scan", "cpu-small-chunks", "local block storage", "full-scan", "chunks256-default", [16, 32, 64, 128]),
    )
    for panel, (axis, (title, phase, storage, workload, advice, ticks)) in enumerate(zip(axes, settings), 1):
        for reader in ("damacy", "tensorstore"):
            implementation = advice if reader == "damacy" else "tensorstore"
            selected = sorted((item for item in rows if item["phase"] == phase and item["reader"] == reader
                               and item["implementation"] == implementation and item["storage_type"] == storage
                               and item["workload"] == workload and item["codec"] == "zstd"),
                              key=lambda item: int(item["raw_chunk_bytes"]))
            if len(selected) != len(ticks):
                raise ValueError(f"Unexpected plot coverage: {phase}, {reader}, {len(selected)}")
            x = [int(item["raw_chunk_bytes"]) / 1024 for item in selected]
            y = [float(item["primary_gib_s_median"]) for item in selected]
            error = [[middle - float(item["primary_gib_s_min"]) for middle, item in zip(y, selected)],
                     [float(item["primary_gib_s_max"]) - middle for middle, item in zip(y, selected)]]
            label = "TensorStore" if reader == "tensorstore" else "Damacy, readahead " + ("off" if advice.endswith("random") else "default")
            axis.errorbar(x, y, yerr=error, marker="o", markersize=5, color=COLORS[reader],
                          capsize=3, linewidth=1.6, label=label)
            for item in selected:
                exported.append({**item, "figure": "read-workloads", "panel": panel, "source_file": "read-summary.csv",
                                 "source_record": "summary_id=" + item["summary_id"]})
        axis.set_title(title, fontsize=11)
        axis.set_xscale("log", base=2)
        axis.set_xticks(ticks)
        axis.xaxis.set_major_formatter(ScalarFormatter())
        axis.set_xlabel("Raw chunk capacity (KiB)")
        axis.set_ylabel("Returned float32 GiB/s")
        axis.grid(axis="y", alpha=0.2)
        axis.set_ylim(bottom=0)
        if panel < 3:
            axis.set_ylim(0, 4.5)
        axis.legend(fontsize=8, loc="lower left" if panel == 1 else "upper left")
    figure.suptitle("CPU read results depend on reader, workload and storage", fontsize=15, y=0.98)
    figure.subplots_adjust(top=0.85, bottom=0.28, left=0.06, right=0.99, wspace=0.32)
    figure.text(0.06, 0.13,
                "Synthetic smooth4 uint16, 16 GiB, sixteen 1 GiB raw shards; Blosc-Zstd, level 3, bitshuffle.\n"
                "Left/right: fixed 16 KiB blocks. Middle: separate NFS spot check with block = chunk; three encodings shown.\n"
                "Three repetitions per point; bars show observed min–max. Divide rates by two for useful uint16 GiB/s.\n"
                "Crops: (1,256,256); complete scans: batched (8,256,256) tiles. Host output; 32 decode/copy participants, 16 readers.",
                fontsize=8.5, va="center")
    save_figure(figure, output, "read-workloads")


def write_figure(root, output, exported):
    rows = [item for item in read_csv(root / "write-summary.csv")
            if item["current_report_selected"] == "true" and item["sink"] == "fs"
            and item["proxy_frontier_eligible"] == "true"]
    datasets = sorted({item["input_id"] for item in rows})
    if len(datasets) != 7:
        raise ValueError(f"Expected seven report inputs, got {datasets}")
    figure, axes = plt.subplots(4, 2, figsize=(11.6, 13.6))
    for panel, (axis, dataset) in enumerate(zip(axes.flat, datasets), 1):
        axis.axvspan(0, 10, color="#dcebd9", alpha=0.65)
        for backend in ("cpu", "gpu"):
            selected = [item for item in rows if item["input_id"] == dataset and item["backend"] == backend]
            if len({item["comparison_group"] for item in selected}) != 1:
                raise ValueError(f"Multiple comparison groups in {dataset}/{backend}")
            for item in selected:
                x = float(item["proxy_size_penalty_percent"])
                y = float(item["median_logical_gibs"])
                low, high = float(item["min_logical_gibs"]), float(item["max_logical_gibs"])
                winner = item["proxy_10pct_winner"] == "true"
                axis.errorbar(x, y, yerr=[[y - low], [high - y]], color=COLORS[backend],
                              fmt="*" if winner else "o" if backend == "cpu" else "s",
                              markersize=12 if winner else 4.2, capsize=2.3, alpha=1 if winner else 0.7,
                              markeredgecolor="black" if winner else COLORS[backend], markeredgewidth=0.6)
                if winner:
                    axis.annotate(f"{int(item['raw_chunk_bytes'])//1024} KiB", (x, y),
                                  xytext=(5, 7 if backend == "cpu" else -13), textcoords="offset points",
                                  fontsize=8, color=COLORS[backend])
                exported.append({**item, "figure": "write-tradeoffs", "panel": panel, "raw_source_file": item["source_file"],
                                 "source_file": "write-summary.csv", "source_record": "summary_id=" + item["summary_id"]})
        axis.set_title(dataset, fontsize=11)
        axis.set_xlabel("Extra measured shard-write bytes (%)")
        axis.set_ylabel("Logical input GiB/s")
        axis.grid(axis="y", alpha=0.2)
        axis.set_ylim(bottom=0)
        largest_penalty = max(float(item["proxy_size_penalty_percent"]) for item in rows if item["input_id"] == dataset)
        axis.set_xlim(left=-max(1, largest_penalty * 0.04))
    last = axes.flat[-1]
    last.axis("off")
    last.text(0.05, 0.88,
              "Current report selection, filesystem sink\n\n"
              "Blue circles: CPU, Turin, 32 workers\n"
              "Purple squares: GPU, L40, 4 host workers\n"
              "Stars: fastest median inside the 10% byte allowance\n"
              "Bars: observed min–max, 2 or 3 repetitions\n\n"
              "Each backend has its own input/session group\n"
              "and minimum-byte baseline. Source records\n"
              "include the earlier phases and excluded cases.",
              fontsize=10, va="top", linespacing=1.45)
    figure.suptitle("Microscopy streaming: throughput and measured shard-write bytes", fontsize=15, y=0.982)
    figure.subplots_adjust(top=0.94, bottom=0.1, left=0.08, right=0.97, hspace=0.53, wspace=0.27)
    figure.text(0.08, 0.038,
                "Preloaded cyclic replay; source I/O/decoding excluded, final drain included. Shard-write bytes are a measured proxy,\n"
                "not a final stored-file census. Stars select whole configurations (chunk shape, codec and block); labels give raw chunk KiB.\n"
                "CPU/GPU are separate machines and resource budgets. All source summary IDs are retained in figure-data.csv.",
                fontsize=9, va="center")
    save_figure(figure, output, "write-tradeoffs")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    output = args.evidence / "figures"
    output.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False,
                         "axes.spines.right": False, "svg.fonttype": "none"})
    records = []
    read_figure(args.evidence, output, records)
    write_figure(args.evidence, output, records)
    keys = list(dict.fromkeys(key for item in records for key in item))
    with (output / "figure-data.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(records)
    print(f"Saved two figures as PNG/SVG, with {len(records)} source summary rows.")


if __name__ == "__main__":
    main()
