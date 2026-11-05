"""Turn query_results.csv into a summary table, target checks and a chart (FR-13, D-34).

Run:  python -m benchmarks.query_report
Writes query_summary.csv and query_latency.png to benchmarks/results/.
"""
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")  # write image files, no window needed
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from benchmarks.report import INDEX_COLORS, INDEX_MARKERS, INDEX_ORDER, read_results, size_label

RESULTS_DIR = Path(__file__).parent / "results"

QUERY_ORDER = ["AP-05", "AP-06", "AP-07", "AP-11"]
QUERY_LABELS = {"AP-05": "AP-05\nstatus", "AP-06": "AP-06\nhistory",
                "AP-07": "AP-07\nby facility", "AP-11": "AP-11\nby courier"}
TARGETS_MS = {"AP-05": ("NFR-03", 20), "AP-06": ("NFR-02", 50)}
TARGET_EVENTS = 1_000_000  # the NFR targets are defined at 1M events


def summarise(rows):
    """Median of the rounds for each (level, n_events, index_config, query)."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r["level"], int(r["n_events"]), r["index_config"], r["query"])].append(r)

    def med(runs, column):
        return round(median(float(r[column]) for r in runs), 2)

    summary = []
    for (level, n_events, index_config, query), runs in groups.items():
        summary.append({
            "level": level, "n_events": n_events, "index_config": index_config, "query": query,
            "rounds": len(runs), "calls_per_round": int(runs[0]["calls"]),
            "p50_ms": med(runs, "p50_ms"), "p95_ms": med(runs, "p95_ms"), "p99_ms": med(runs, "p99_ms"),
            "lowest_round_p95_ms": min(float(r["p95_ms"]) for r in runs),
            "highest_round_p95_ms": max(float(r["p95_ms"]) for r in runs),
        })
    summary.sort(key=lambda s: (s["level"], s["n_events"], INDEX_ORDER.index(s["index_config"]),
                                QUERY_ORDER.index(s["query"])))
    return summary


def write_summary(summary, path):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)


def target_checks(summary):
    """One line per measurement that has a target: p95 at 1M events against NFR-02 / NFR-03."""
    lines = []
    for s in summary:
        if s["query"] in TARGETS_MS and s["n_events"] == TARGET_EVENTS:
            name, limit = TARGETS_MS[s["query"]]
            verdict = "pass" if s["p95_ms"] < limit else "FAIL"
            lines.append(f"{name} {s['query']} {s['level']:<8} {s['index_config']:<8} "
                         f"p95 {s['p95_ms']:>8} ms (target < {limit} ms): {verdict}")
    return lines


def draw_chart(summary, path):
    """Database-level p95: one panel per dataset size, one color and shape per index config.

    Dots on a log axis, as in the insert chart: scans are hundreds of times slower.
    """
    rows = [s for s in summary if s["level"] == "database"]
    sizes = sorted({s["n_events"] for s in rows})
    values = {(s["n_events"], s["index_config"], s["query"]): s for s in rows}

    fig, axes = plt.subplots(1, len(sizes), figsize=(5.2 * len(sizes), 4.2), sharey=True, squeeze=False)
    offset = 0.22
    for ax, n_events in zip(axes[0], sizes):
        for i, index_config in enumerate(INDEX_ORDER):
            xs = [q_pos + (i - 1) * offset for q_pos in range(len(QUERY_ORDER))]
            points = [values[(n_events, index_config, q)] for q in QUERY_ORDER]
            ax.vlines(xs, [p["lowest_round_p95_ms"] for p in points], [p["highest_round_p95_ms"] for p in points],
                      color=INDEX_COLORS[index_config], linewidth=2, zorder=3)
            ax.scatter(xs, [p["p95_ms"] for p in points], s=48, color=INDEX_COLORS[index_config],
                       marker=INDEX_MARKERS[index_config], edgecolors="white", linewidths=1,
                       label=index_config, zorder=4)
        if n_events == TARGET_EVENTS:
            for q_pos, query in enumerate(QUERY_ORDER):
                if query in TARGETS_MS:
                    name, limit = TARGETS_MS[query]
                    ax.hlines(limit, q_pos - 0.38, q_pos + 0.38, color="#52514e", linewidth=1,
                              linestyle="--", zorder=2)
                    ax.text(q_pos, limit * 1.12, f"{name} < {limit} ms", ha="center", fontsize=8, color="#52514e")
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        ax.set_xticks(range(len(QUERY_ORDER)), [QUERY_LABELS[q] for q in QUERY_ORDER], fontsize=9)
        ax.set_title(size_label(n_events), fontsize=11, loc="left")
        ax.grid(axis="y", color="#e4e3df", linewidth=0.8, zorder=0)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="both", length=0)
    axes[0][0].set_ylabel("p95 latency in ms (log scale)", fontsize=9)
    axes[0][0].legend(title="Index config", frameon=False, fontsize=9, title_fontsize=9, loc="upper left")
    fig.tight_layout()
    fig.savefig(path, dpi=200)


if __name__ == "__main__":
    summary = summarise(read_results(RESULTS_DIR / "query_results.csv"))
    write_summary(summary, RESULTS_DIR / "query_summary.csv")
    draw_chart(summary, RESULTS_DIR / "query_latency.png")
    for line in target_checks(summary):
        print(line)
