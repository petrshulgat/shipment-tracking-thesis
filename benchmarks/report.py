"""Turn insert_results.csv into a summary table and a chart (FR-13, D-32).

Run:  python -m benchmarks.report
Writes insert_summary.csv and insert_throughput.png to benchmarks/results/.
"""
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")  # write image files, no window needed
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

RESULTS_DIR = Path(__file__).parent / "results"

METHOD_ORDER = ["single", "batch_100", "batch_1000", "batch_5000", "bulk"]
METHOD_LABELS = {"single": "Single", "batch_100": "Batch 100", "batch_1000": "Batch 1,000",
                 "batch_5000": "Batch 5,000", "bulk": "Bulk"}
INDEX_ORDER = ["none", "minimal", "full"]
INDEX_COLORS = {"none": "#2a78d6", "minimal": "#eb6834", "full": "#1baf7a"}
INDEX_MARKERS = {"none": "o", "minimal": "s", "full": "^"}
NFR_01_TARGET = 5000  # events/s


def read_results(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def summarise(rows):
    """Median of the repeats for each (n_events, index_config, method)."""
    groups = defaultdict(list)
    for r in rows:
        groups[(int(r["n_events"]), r["index_config"], r["method"])].append(r)

    summary = []
    for (n_events, index_config, method), runs in groups.items():
        values = [int(r["events_per_s"]) for r in runs]
        summary.append({
            "n_events": n_events, "index_config": index_config, "method": method, "runs": len(runs),
            "median_events_per_s": round(median(values)),
            "min_events_per_s": min(values), "max_events_per_s": max(values),
            "median_insert_only_events_per_s": round(median(int(r["insert_only_events_per_s"]) for r in runs)),
            "median_status_s": round(median(float(r["status_s"]) for r in runs), 2),
            "median_db_seconds": round(median(float(r["db_seconds"]) for r in runs), 2),
        })
    summary.sort(key=lambda s: (s["n_events"], INDEX_ORDER.index(s["index_config"]),
                                METHOD_ORDER.index(s["method"])))
    return summary


def write_summary(summary, path):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)


def size_label(n_events):
    return f"{n_events / 1_000_000:g}M events" if n_events >= 1_000_000 else f"{n_events // 1000}k events"


def draw_chart(summary, path):
    """Dots with min-max lines: one panel per dataset size, one color and shape per index config.

    Dots rather than bars because the axis is logarithmic: a log axis has no zero,
    so bar lengths would mislead. Shapes keep the series apart without color.
    """
    sizes = sorted({s["n_events"] for s in summary})
    values = {(s["n_events"], s["index_config"], s["method"]): s for s in summary}

    fig, axes = plt.subplots(1, len(sizes), figsize=(5.2 * len(sizes), 4.2), sharey=True, squeeze=False)
    offset = 0.22
    for ax, n_events in zip(axes[0], sizes):
        methods = [m for m in METHOD_ORDER if (n_events, "none", m) in values]
        for i, index_config in enumerate(INDEX_ORDER):
            xs = [m_pos + (i - 1) * offset for m_pos in range(len(methods))]
            rows = [values[(n_events, index_config, m)] for m in methods]
            ax.vlines(xs, [r["min_events_per_s"] for r in rows], [r["max_events_per_s"] for r in rows],
                      color=INDEX_COLORS[index_config], linewidth=2, zorder=3)
            ax.scatter(xs, [r["median_events_per_s"] for r in rows], s=48, color=INDEX_COLORS[index_config],
                       marker=INDEX_MARKERS[index_config], edgecolors="white", linewidths=1,
                       label=index_config, zorder=4)
        ax.axhline(NFR_01_TARGET, color="#52514e", linewidth=1, linestyle="--", zorder=2)
        ax.text(0.99, NFR_01_TARGET * 1.08, "NFR-01 target (5,000)", ha="right", fontsize=8, color="#52514e",
                transform=ax.get_yaxis_transform())
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax.set_xticks(range(len(methods)), [METHOD_LABELS[m] for m in methods], fontsize=9)
        ax.set_title(size_label(n_events), fontsize=11, loc="left")
        ax.grid(axis="y", color="#e4e3df", linewidth=0.8, zorder=0)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="both", length=0)
    axes[0][0].set_ylabel("Events per second (log scale)", fontsize=9)
    axes[0][-1].legend(title="Index config", frameon=False, fontsize=9, title_fontsize=9, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=200)


if __name__ == "__main__":
    summary = summarise(read_results(RESULTS_DIR / "insert_results.csv"))
    write_summary(summary, RESULTS_DIR / "insert_summary.csv")
    draw_chart(summary, RESULTS_DIR / "insert_throughput.png")
    for s in summary:
        print(f"{s['n_events']:>8} {s['index_config']:<8} {s['method']:<11} {s['median_events_per_s']:>7} events/s")
