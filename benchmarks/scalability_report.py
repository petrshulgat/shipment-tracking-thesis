"""How the system scales from 100k to 10M events (FR-13, NFR-04, NFR-05, D-37).

Run:  python -m benchmarks.scalability_report
Reads every insert_results*.csv, query_results*.csv and etl_results*.csv in
benchmarks/results/, uses the `full` index config (D-36), and writes:
  scalability_summary.csv, scalability_queries.png, scalability_etl.png, scalability_inserts.png
"""
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")  # write image files, no window needed
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, LogLocator

from benchmarks.report import INDEX_COLORS, size_label

RESULTS_DIR = Path(__file__).parent / "results"

QUERY_NAMES = {"AP-05": "AP-05 status", "AP-06": "AP-06 history", "AP-07": "AP-07 by facility",
               "AP-10": "AP-10 metrics", "AP-11": "AP-11 by courier"}
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]  # fixed order, never cycled
INSERT_METHODS = {"batch_1000": "Direct, batch 1,000", "bulk": "Bulk"}
REFERENCE_GRAY = "#52514e"


def read_all(pattern):
    rows = []
    for path in sorted(RESULTS_DIR.glob(pattern)):
        with open(path, newline="") as f:
            rows.extend(csv.DictReader(f))
    return rows


def medians(rows, series_key, value_key):
    """{series: {n_events: median value}} over the repeats or rounds."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r[series_key], int(r["n_events"]))].append(float(r[value_key]))
    result = defaultdict(dict)
    for (series, n_events), values in groups.items():
        result[series][n_events] = median(values)
    return result


def query_series(rows):
    """p95 per query, database level, `full` indexes."""
    return medians([r for r in rows if r["level"] == "database" and r["index_config"] == "full"],
                   "query", "p95_ms")


def etl_series(rows):
    return medians(rows, "index_config", "seconds_per_day")


def insert_series(rows):
    return medians([r for r in rows if r["index_config"] == "full" and r["method"] in INSERT_METHODS],
                   "method", "events_per_s")


def linear_reference(points):
    """What the values would be if they grew in proportion to the data, from the smallest size."""
    first = min(points)
    return {n: points[first] * n / first for n in points}


def line_chart(series, labels, colors, ylabel, path, reference=None):
    """One line per series over dataset size, on log-log axes, labelled at the line end."""
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    if reference:
        xs = sorted(reference)
        ax.plot(xs, [reference[x] for x in xs], color=REFERENCE_GRAY, linewidth=1, linestyle="--", zorder=2)
        ax.text(xs[-1], reference[xs[-1]] * 1.15, "linear growth", ha="right", fontsize=8, color=REFERENCE_GRAY)
    for name, color in zip(labels, colors):
        if name not in series:
            continue
        xs = sorted(series[name])
        ys = [series[name][x] for x in xs]
        ax.plot(xs, ys, color=color, linewidth=2, marker="o", markersize=7,
                markeredgecolor="white", zorder=3)
        ax.annotate(labels[name], (xs[-1], ys[-1]), xytext=(8, 0), textcoords="offset points",
                    va="center", fontsize=8, color="#0b0b0b")
    sizes = sorted({x for points in series.values() for x in points})
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks(sizes, [size_label(n).replace(" events", "") for n in sizes])
    ax.minorticks_off()
    ax.set_xlim(sizes[0] / 1.6, sizes[-1] * 4)  # room for the end labels
    ax.yaxis.set_major_locator(LogLocator(subs=(1, 2, 5)))  # 1, 2, 5, 10, 20, 50 ... so short ranges still get numbers
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}" if v >= 1 else f"{v:g}"))
    ax.set_xlabel("Events in the database", fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(axis="y", color="#e4e3df", linewidth=0.8, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(axis="both", length=0, labelsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def summary_rows(queries, etl, inserts):
    rows = []
    for experiment, unit, data in (("query_p95", "ms", queries), ("etl_per_day", "s", etl),
                                   ("insert", "events/s", inserts)):
        for series, points in data.items():
            for n_events in sorted(points):
                rows.append({"experiment": experiment, "series": series, "n_events": n_events,
                             "median": round(points[n_events], 3), "unit": unit})
    return rows


if __name__ == "__main__":
    queries = query_series(read_all("query_results*.csv"))
    etl = etl_series(read_all("etl_results*.csv"))
    inserts = insert_series(read_all("insert_results*.csv"))

    with open(RESULTS_DIR / "scalability_summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["experiment", "series", "n_events", "median", "unit"])
        writer.writeheader()
        writer.writerows(summary_rows(queries, etl, inserts))

    line_chart(queries, QUERY_NAMES, SERIES_COLORS, "p95 latency in ms (log scale)",
               RESULTS_DIR / "scalability_queries.png")
    line_chart(etl, {"minimal": "minimal indexes", "full": "full indexes"},
               [INDEX_COLORS["minimal"], INDEX_COLORS["full"]], "ETL seconds per day (log scale)",
               RESULTS_DIR / "scalability_etl.png", reference=linear_reference(etl["full"]) if "full" in etl else None)
    line_chart(inserts, INSERT_METHODS, SERIES_COLORS[:2], "Events per second (log scale)",
               RESULTS_DIR / "scalability_inserts.png")
    for row in summary_rows(queries, etl, inserts):
        print(f"{row['experiment']:<12} {row['series']:<11} {row['n_events']:>9} {row['median']:>12} {row['unit']}")
