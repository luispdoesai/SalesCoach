"""Won vs. lost comparison: data/reports/compare.csv, a sample-size note, and charts.

Every number is computed here, from results.csv, stats.csv, and outcomes.csv.
This shows what won and lost calls had in common. It does not show cause.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coach.config import Paths
from coach.friendly import heading, ok
from coach.scorecards import read_csv_rows, read_outcomes, write_csv

GROUPS = ("won", "lost", "stalled")
COLUMNS = ["metric", "won_mean", "won_n", "lost_mean", "lost_n", "stalled_mean", "stalled_n", "diff_won_minus_lost"]
SKIP = {"call_id", "date", "prospect_initials", "stage", "outcome", "price_next_speaker"}
NOTE_FILE = "sample_size_note.txt"

# (metric, chart title, unit label, file name)
CHARTS = [
    ("rep_talk_pct", "Rep talk share", "% of talk time", "talk_pct.png"),
    ("rep_questions", "Questions the rep asked", "question marks per call", "questions.png"),
    ("longest_rep_monologue_sec", "Longest rep monologue", "seconds", "longest_monologue.png"),
    ("price_silence_sec", "Silence after stating price", "seconds", "price_silence.png"),
]

LABELS = {
    "rep_talk_pct": "Rep talk %", "prospect_talk_pct": "Prospect talk %", "rep_questions": "Rep questions",
    "longest_rep_monologue_sec": "Longest rep monologue (s)", "price_silence_sec": "Silence after price (s)",
    "duration_sec": "Call length (s)", "rubric_avg": "Rubric average",
}


def _num(value: str) -> float | None:
    try:
        return float(value) if value not in ("", None) else None
    except ValueError:
        return None


def combined_rows(paths: Paths) -> tuple[list[str], list[dict[str, Any]]]:
    """One row per call: stats + results, outcome from outcomes.csv."""
    outcomes = read_outcomes(paths, warn_bad=False)
    stats = {r["call_id"]: r for r in read_csv_rows(paths.stats_csv)}
    results = {r["call_id"]: r for r in read_csv_rows(paths.results_csv)}
    metrics: list[str] = []
    for source in (list(stats.values())[:1], list(results.values())[:1]):
        for row in source:
            metrics += [k for k in row if k not in SKIP and k not in metrics]
    rows = []
    for cid in sorted(set(stats) | set(results)):
        row: dict[str, Any] = {"call_id": cid, "outcome": outcomes.get(cid, "")}
        for src in (stats.get(cid, {}), results.get(cid, {})):
            for k in metrics:
                if k in src and row.get(k) is None:
                    row[k] = _num(src[k])
        rows.append(row)
    return metrics, rows


def compare_table(metrics: list[str], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    table = []
    for m in metrics:
        entry: dict[str, Any] = {"metric": m}
        for g in GROUPS:
            values = [r[m] for r in rows if r["outcome"] == g and r.get(m) is not None]
            entry[f"{g}_n"] = len(values)
            entry[f"{g}_mean"] = round(sum(values) / len(values), 2) if values else None
        if entry["won_mean"] is not None and entry["lost_mean"] is not None:
            entry["diff_won_minus_lost"] = round(entry["won_mean"] - entry["lost_mean"], 2)
        else:
            entry["diff_won_minus_lost"] = None
        table.append(entry)
    return table


def sample_note(rows: list[dict[str, Any]]) -> list[str]:
    counts = {g: sum(1 for r in rows if r["outcome"] == g) for g in (*GROUPS, "open")}
    total = len(rows)
    with_outcome = sum(counts.values())
    lines = [f"Sample: {total} call{'' if total == 1 else 's'}. {counts['won']} won, {counts['lost']} lost, "
             f"{counts['stalled']} stalled, {counts['open']} open, {total - with_outcome} with no outcome yet."]
    if counts["won"] == 0 or counts["lost"] == 0:
        missing = "won" if counts["won"] == 0 else "lost"
        lines.append(f"No {missing} calls yet, so a won vs. lost comparison is impossible.")
    elif counts["won"] < 5 or counts["lost"] < 5:
        lines.append("Fewer than 5 won or fewer than 5 lost calls: the comparison is not meaningful yet.")
    if total < 30:
        lines.append("Fewer than 30 calls in total: treat any pattern as a directional hint, not proof.")
    lines.append("This shows correlation, not cause. It shows what wins and losses had in common, not why they happened.")
    return lines


def _fmt(v: Any) -> str:
    if v is None:
        return "-"
    return f"{v:g}" if isinstance(v, float) else str(v)


def print_table(table: list[dict[str, Any]], only: list[str] | None = None) -> None:
    rows = [t for t in table if not only or t["metric"] in only]
    width = max([len(LABELS.get(t["metric"], t["metric"])) for t in rows] + [6])
    print(f"  {'Metric':<{width}}  {'Won':>7} {'(n)':>4}  {'Lost':>7} {'(n)':>4}  {'Won-Lost':>9}")
    print(f"  {'-' * width}  {'-' * 12}  {'-' * 12}  {'-' * 9}")
    for t in rows:
        print(f"  {LABELS.get(t['metric'], t['metric']):<{width}}  {_fmt(t['won_mean']):>7} {t['won_n']:>4}  "
              f"{_fmt(t['lost_mean']):>7} {t['lost_n']:>4}  {_fmt(t['diff_won_minus_lost']):>9}")


def draw_charts(rows: list[dict[str, Any]], charts_dir: Path) -> list[Path]:
    """Monochrome bar charts, won vs. lost, each call shown as a dot."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted, grid = "#1a1a1a", "#6b6b6b", "#e4e4e4"
    fills = {"won": "#3a3a3a", "lost": "#b5b5b5"}
    charts_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for metric, title, unit, fname in CHARTS:
        values = {g: [r[metric] for r in rows if r["outcome"] == g and r.get(metric) is not None]
                  for g in ("won", "lost")}
        fig, ax = plt.subplots(figsize=(5.2, 3.8), dpi=150)
        for i, g in enumerate(("won", "lost")):
            vals = values[g]
            if vals:
                mean = sum(vals) / len(vals)
                ax.bar(i, mean, width=0.55, color=fills[g], edgecolor="white", linewidth=2, zorder=2)
                ax.text(i, mean, f"{mean:.1f}", ha="center", va="bottom", fontsize=10, color=ink,
                        fontweight="bold", zorder=4)
                spread = [(-0.12 + 0.24 * k / max(len(vals) - 1, 1)) if len(vals) > 1 else 0 for k in range(len(vals))]
                ax.scatter([i + s for s in spread], vals, s=18, color="white", edgecolor=ink, linewidth=1, zorder=3)
            else:
                ax.text(i, 0, "no data", ha="center", va="bottom", fontsize=9, color=muted)
        ax.set_xticks([0, 1])
        ax.set_xticklabels([f"Won (n={len(values['won'])})", f"Lost (n={len(values['lost'])})"], color=ink)
        ax.set_ylabel(unit, color=muted, fontsize=9)
        ax.set_title(f"{title}\nn = {len(values['won'])} won, {len(values['lost'])} lost. Bars are averages. Dots are calls.",
                     fontsize=10, color=ink, loc="left")
        ax.grid(axis="y", color=grid, linewidth=0.8, zorder=0)
        ax.set_axisbelow(True)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(muted)
        ax.tick_params(axis="y", colors=muted, labelsize=8, length=0)
        top = max(values["won"] + values["lost"] + [0])
        ax.set_ylim(0, top * 1.18 if top > 0 else 1)
        ax.set_xlim(-0.6, 1.6)
        fig.tight_layout()
        out = charts_dir / fname
        fig.savefig(out, facecolor="white")
        plt.close(fig)
        saved.append(out)
    return saved


def run_compare(paths: Paths, charts: bool = True) -> dict[str, Any]:
    metrics, rows = combined_rows(paths)
    table = compare_table(metrics, rows)
    paths.reports.mkdir(parents=True, exist_ok=True)
    compare_csv = paths.reports / "compare.csv"
    write_csv(compare_csv, COLUMNS, table)
    note_lines = sample_note(rows)
    (paths.reports / NOTE_FILE).write_text("\n".join(note_lines) + "\n", encoding="utf-8")

    heading("Won vs. lost")
    print_table(table, only=[m for m, *_ in CHARTS] + ["rubric_avg"])
    print("\n  Sample-size note:")
    for line in note_lines:
        print(f"  - {line}")
    saved = draw_charts(rows, paths.charts) if charts and rows else []
    print()
    ok(f"Saved {paths.show(compare_csv)} ({len(table)} metrics) and {paths.show(paths.reports / NOTE_FILE)}")
    if saved:
        ok(f"Saved {len(saved)} charts to {paths.show(paths.charts)}/")
    return {"table": table, "rows": rows, "note": note_lines, "charts": saved}
