"""The dashboard command: one self-contained HTML page of outcomes and stats.

Writes <data>/reports/dashboard.html. It opens in any browser, needs no
server or internet, and loads nothing from outside the file. Every number on
it comes from the CSVs that code produced (stats.csv, results.csv,
compare.csv, sample_size_note.txt). The page lives in data/, so it is
gitignored like the rest of your calls.
"""

from __future__ import annotations

import json
import math
import webbrowser
from datetime import date
from html import escape
from pathlib import Path
from typing import Any

from coach import archive, compare, report
from coach.config import Paths
from coach.friendly import CoachError, ok
from coach.scorecards import parse_rubric, read_csv_rows, validate_all

GROUP_ORDER = ["won", "lost", "stalled", "open", ""]
GROUP_LABEL = {"won": "Won", "lost": "Lost", "stalled": "Stalled", "open": "Open", "": "No outcome yet"}

# (column, label, unit, decimals)
STRIPS = [
    ("rep_talk_pct", "Rep talk share", "%", 1),
    ("rep_questions", "Questions the rep asked", "", 0),
    ("longest_rep_monologue_sec", "Longest rep monologue", "s", 1),
    ("price_silence_sec", "Silence after stating price", "s", 1),
    ("rubric_avg", "Rubric average", " / 5", 2),
]
STAT_COLS = [("rep_talk_pct", "Talk %", 1), ("rep_questions", "Qs", 0),
             ("longest_rep_monologue_sec", "Monologue s", 1), ("price_silence_sec", "Price gap s", 1)]


def _f(v: Any, decimals: int = 1) -> str:
    if v is None or v == "":
        return "-"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return escape(str(v))
    return f"{x:.{decimals}f}" if decimals else f"{x:.0f}"


def _num(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    t = math.floor(lo / step) * step
    ticks = [round(t, 6)]
    while ticks[-1] < hi - step * 1e-6:  # the last tick always reaches past the largest value
        t += step
        ticks.append(round(t, 6))
    return ticks


def trust_level(note: list[str]) -> tuple[str, str]:
    text = " ".join(note)
    if "impossible" in text:
        return "critical", "Comparison not possible yet"
    if "not meaningful" in text:
        return "serious", "Too few calls to compare"
    if "directional" in text:
        return "warning", "Directional hints only"
    return "neutral", "Correlation, not cause"


def strip_svg(metric: str, rows: list[dict], means: dict[str, float | None], unit: str, decimals: int) -> str:
    """Dots for every won and lost call on one axis, with each group's average marked."""
    pts = {g: [(r["call_id"], r[metric]) for r in rows if r["outcome"] == g and r.get(metric) is not None]
           for g in ("won", "lost")}
    values = [v for g in pts.values() for _, v in g]
    if not values:
        return '<p class="empty">No won or lost calls have this number yet.</p>'
    ticks = _nice_ticks(min(0.0, min(values)), max(values))
    lo, hi = ticks[0], ticks[-1]
    W, L, R = 600, 72, 24

    def x(v: float) -> float:
        return L + (v - lo) / (hi - lo) * (W - L - R)

    parts = [f'<svg viewBox="0 0 {W} 92" role="img" aria-label="{escape(metric)} by outcome">']
    for t in ticks:
        parts.append(f'<line class="grid" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="6" y2="68"/>'
                     f'<text class="tick" x="{x(t):.1f}" y="84" text-anchor="middle">{_f(t, 0 if t == int(t) else 1)}</text>')
    for row_y, g in ((22, "won"), (52, "lost")):
        parts.append(f'<text class="rowlab" x="0" y="{row_y + 4}">{GROUP_LABEL[g]}</text>')
        seen: dict[float, int] = {}
        for cid, v in pts[g]:
            k = round(v, 1)
            seen[k] = seen.get(k, 0) + 1
            dy = [0, -6, 6, -11, 11][(seen[k] - 1) % 5]
            tip = f"{cid}: {_f(v, decimals)}{unit}"
            parts.append(f'<circle class="dot {g}" cx="{x(v):.1f}" cy="{row_y + dy}" r="5" tabindex="0" '
                         f'data-tip="{escape(tip)}"><title>{escape(tip)}</title></circle>')
        m = means.get(g)
        if m is not None:
            parts.append(f'<line class="mean {g}" x1="{x(m):.1f}" x2="{x(m):.1f}" y1="{row_y - 13}" y2="{row_y + 13}"/>')
    parts.append("</svg>")
    return "".join(parts)


def gap_rows(items: list[tuple[str, str, float | None, float | None, float | None]]) -> str:
    """Diverging bars: won average minus lost average for each rubric behavior."""
    diffs = [d for *_, d in items if d is not None]
    span = max([abs(d) for d in diffs] + [1.0])
    # Zero sits in the middle only when some gaps are negative. Otherwise bars use the full width.
    zero = 50.0 if any(d < 0 for d in diffs) else 0.0
    room = 50.0 if zero else 100.0
    out = []
    for rid, name, won, lost, diff in items:
        if diff is None:
            bar = '<span class="gap-none">no data</span>'
        else:
            pct = abs(diff) / span * room
            side = "won" if diff >= 0 else "lost"
            left = zero if diff >= 0 else zero - pct
            bar = (f'<span class="gap-bar {side}" style="left:{left:.2f}%;width:{max(pct, 0.6):.2f}%" '
                   f'data-tip="{escape(name)}: won {_f(won, 2)}, lost {_f(lost, 2)}"></span>')
        out.append(
            f'<div class="gap-row"><div class="gap-name">{escape(name)}<code>{escape(rid)}</code></div>'
            f'<div class="gap-track"><span class="gap-zero" style="left:{zero:.0f}%"></span>{bar}</div>'
            f'<div class="gap-val num">{"+" if diff and diff > 0 else ""}{_f(diff, 2)}'
            f'<small>{_f(won, 2)} vs {_f(lost, 2)}</small></div></div>')
    return "".join(out)


DEFAULT_TITLE = "AI Sales Coach Dashboard"


def build(paths: Paths, title: str = DEFAULT_TITLE, fragment: bool = False) -> str:
    if not paths.data.is_dir():
        raise CoachError(f"The {paths.show(paths.data)}/ folder does not exist yet.", "Run: python coach.py init")
    stats = {r["call_id"]: r for r in read_csv_rows(paths.stats_csv)}
    results = {r["call_id"]: r for r in read_csv_rows(paths.results_csv)}
    table = {r["metric"]: r for r in read_csv_rows(paths.reports / "compare.csv")}
    note_path = paths.reports / compare.NOTE_FILE
    note = note_path.read_text(encoding="utf-8").splitlines() if note_path.exists() else []
    _, rows = compare.combined_rows(paths)
    try:
        rubric = parse_rubric(paths.rubric)
    except CoachError:
        rubric = []
    rubric_ids = [i.id for i in rubric]
    if not rubric_ids and results:
        # No rubric file here: the behavior columns sit between rubric_avg and rapport_score.
        cols = list(next(iter(results.values())))
        if "rubric_avg" in cols and "rapport_score" in cols:
            rubric_ids = cols[cols.index("rubric_avg") + 1:cols.index("rapport_score")]
    names = {i.id: i.name for i in rubric}
    coaching = {}
    for p in sorted(paths.scorecards.glob("*.json")) if paths.scorecards.is_dir() else []:
        try:
            coaching[p.stem] = str(json.loads(p.read_text(encoding="utf-8")).get("one_thing_to_change") or "")
        except (OSError, json.JSONDecodeError):
            pass

    counts = {g: sum(1 for r in rows if r["outcome"] == g) for g in GROUP_ORDER}
    level, level_text = trust_level(note)

    # Outcome split bar
    seg = "".join(
        f'<span class="seg {g or "none"}" style="flex:{counts[g]}" data-tip="{GROUP_LABEL[g]}: {counts[g]}"></span>'
        for g in GROUP_ORDER if counts[g])
    legend = "".join(f'<span class="key"><i class="sw {g or "none"}"></i>{GROUP_LABEL[g]} <b class="num">{counts[g]}</b></span>'
                     for g in GROUP_ORDER if counts[g])

    # Won vs lost strips
    strips = []
    for metric, label, unit, dec in STRIPS:
        row = table.get(metric, {})
        means = {"won": _num(row.get("won_mean")), "lost": _num(row.get("lost_mean"))}
        mdec = max(dec, 1)  # averages keep a decimal even when single calls are whole numbers
        summary = (f'<span class="won-t">Won avg <b class="num">{_f(means["won"], mdec)}{unit}</b> '
                   f'<small>n={escape(row.get("won_n") or "0")}</small></span>'
                   f'<span class="lost-t">Lost avg <b class="num">{_f(means["lost"], mdec)}{unit}</b> '
                   f'<small>n={escape(row.get("lost_n") or "0")}</small></span>')
        strips.append(f'<div class="strip"><div class="strip-head"><h3>{escape(label)}</h3>'
                      f'<div class="strip-sum">{summary}</div></div>{strip_svg(metric, rows, means, unit, dec)}</div>')

    # Rubric gaps, biggest first
    gap_items = []
    for rid in rubric_ids:
        r = table.get(rid, {})
        gap_items.append((rid, names.get(rid, rid), _num(r.get("won_mean")), _num(r.get("lost_mean")),
                          _num(r.get("diff_won_minus_lost"))))
    gap_items.sort(key=lambda i: -(i[4] if i[4] is not None else -99))

    # Heatmap table
    head = "".join(f'<th class="rot" title="{escape(names.get(rid, rid))}"><span>{escape(names.get(rid, rid))}</span></th>'
                   for rid in rubric_ids)
    head += "".join(f'<th class="num">{escape(lab)}</th>' for _, lab, _ in STAT_COLS)
    body = []
    by_id = {r["call_id"]: r for r in rows}
    for g in GROUP_ORDER:
        ids = sorted(cid for cid, r in by_id.items() if r["outcome"] == g)
        if not ids:
            continue
        body.append(f'<tr class="grp"><th colspan="{3 + len(rubric_ids) + len(STAT_COLS)}">'
                    f'<i class="sw {g or "none"}"></i>{GROUP_LABEL[g]} <span class="num">{len(ids)}</span></th></tr>')
        for cid in ids:
            res, st = results.get(cid, {}), stats.get(cid, {})
            cells = []
            for rid in rubric_ids:
                s = _num(res.get(rid))
                if s is None:
                    cells.append('<td class="hm empty">-</td>')
                else:
                    cells.append(f'<td class="hm s{int(s)}" title="{escape(names.get(rid, rid))}: {int(s)}">{int(s)}</td>')
            cells += [f'<td class="num">{_f(st.get(col), dec)}</td>' for col, _, dec in STAT_COLS]
            tip = coaching.get(cid, "")
            body.append(f'<tr><th class="cid"><a href="#call-{escape(cid)}"><code>{escape(cid)}</code></a>'
                        f'<span class="avg num">avg {_f(res.get("rubric_avg"), 2)}</span></th>'
                        f'{"".join(cells)}<td class="coach">{escape(tip) or "<span class=muted>Not scored yet</span>"}</td></tr>')

    # Everything else about each call: scorecard, quotes, email, transcript
    try:
        reports = {r.call_id: r for r in validate_all(paths, quiet=True)}
    except CoachError:
        reports = {}
    calls = report.load_calls(paths, reports)
    order = GROUP_ORDER
    filters = "".join(
        f'<button type="button" data-filter="{g or "none"}" aria-pressed="false">{GROUP_LABEL[g]}</button>'
        for g in order if any(c["outcome"] == g for c in calls))

    note_html = "".join(f"<li>{escape(line)}</li>" for line in note)
    today = date.today().isoformat()
    first, last = archive.date_range([c["id"] for c in calls])
    span_text = f" dated {first} to {last}" if first else ""
    banner = ""
    if archive.is_archive(paths):
        if title == DEFAULT_TITLE:
            title = f"Archived calls: {paths.data.name}"
        banner = ('<div class="archived-banner">Archived period. These calls are not in your current numbers. '
                  '<a href="../../../reports/dashboard.html">Go to your current dashboard</a></div>')
    style = CSS + report.EXTRA_CSS
    has_stats = bool(rows)
    charts = f"""
  <section class="panel" id="outcomes">
    <h2>Outcomes</h2>
    <div class="split" role="img" aria-label="Calls by outcome">{seg}</div>
    <div class="keys">{legend}</div>
  </section>

  <section class="panel" id="charts">
    <div class="sec-head"><h2>Won vs. lost</h2><p>Each dot is one call. The tall line is the group average. Hover a dot for the call id.</p></div>
    <div class="strips">{"".join(strips)}</div>
  </section>

  <section class="panel">
    <div class="sec-head"><h2>Where wins and losses differ</h2>
    <p>Rubric average on won calls minus lost calls. Bars to the right: won calls scored higher.</p></div>
    <div class="gaps">{gap_rows(gap_items) if gap_items else '<p class="empty">No rubric found.</p>'}</div>
  </section>

  <section class="panel" id="scores">
    <div class="sec-head"><h2>Every score at a glance</h2>
    <div class="scale"><span>Score</span>{"".join(f'<i class="hm s{n}">{n}</i>' for n in range(1, 6))}</div></div>
    <p class="hint">Click a call to jump to its details below.</p>
    <div class="table-scroll"><table class="calls">
      <thead><tr><th>Call</th>{head}<th>One thing to change</th></tr></thead>
      <tbody>{"".join(body)}</tbody>
    </table></div>
  </section>""" if has_stats else """
  <section class="panel" id="charts"><h2>Charts</h2>
    <p class="empty">Charts appear here after your calls are transcribed and you run <code>python coach.py analyze</code>.</p></section>"""
    trust = (f'<div class="trust {level}"><span class="icon" aria-hidden="true"></span><div><b>{escape(level_text)}</b>'
             f'<span>{escape(note[1] if len(note) > 1 else (note[0] if note else ""))}</span></div></div>') if note else ""
    content = f"""
{banner}<nav class="nav" aria-label="Sections"><div>
  <a href="#start">Start here</a><a href="#periods">Which calls</a><a href="#findings">Findings</a><a href="#charts">Charts</a>
  <a href="#calls">Calls</a><a href="#guide">How to read this</a></div></nav>
<main class="wrap">
  <header class="top">
    <div>
      <p class="eyebrow">AI Sales Coach</p>
      <h1>{escape(title)}</h1>
      <p class="sub">{len(calls)} calls{span_text}, from <code>{escape(paths.show(paths.data))}/</code>. Built {today}. This page stays on your computer.</p>
    </div>
    {trust}
  </header>

  <section class="panel" id="start">
    <h2>Start here</h2>
    {report.status_html(paths, calls)}
  </section>

  <section class="panel" id="periods">
    <h2>Which calls are on this page</h2>
    {report.periods_html(paths, calls)}
  </section>

  <section class="panel" id="findings">
    <div class="sec-head"><h2>Your findings</h2><p>Written by Claude from the numbers below. Every number in it comes from a file the code produced.</p></div>
    {report.findings_html(paths)}
  </section>
{charts}

  <section class="panel" id="calls">
    <div class="sec-head"><h2>Every call</h2>
      <div class="filters" role="group" aria-label="Show calls">
        <button type="button" data-filter="all" aria-pressed="true">All</button>{filters}
        <button type="button" data-expand="open">Open all</button><button type="button" data-expand="close">Close all</button>
      </div></div>
    <p class="hint">Click a call to see its scores with the exact words behind them, the email history, and the transcript.</p>
    <div class="cards">{report.call_cards(calls, names, GROUP_LABEL, order)}</div>
  </section>

  <section class="panel" id="guide">
    <h2>How to read this</h2>
    {report.GUIDE}
  </section>

  <footer class="notes">
    <h2>How far to trust this</h2>
    <ul>{note_html or "<li>Nothing to compare yet.</li>"}</ul>
    <p>Scores are AI judgment, each backed by a quote the validator found in the transcript. Statistics come from timestamps.</p>
  </footer>
</main>
<div id="tip" role="tooltip" hidden></div>
<script>{JS}{report.EXTRA_JS}</script>"""
    if fragment:
        return f"<title>{escape(title)}</title>\n<style>{style}</style>\n{content}"
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{escape(title)}</title><style>{style}</style></head><body>{content}</body></html>\n")


def run_dashboard(paths: Paths, open_it: bool = False, quiet: bool = False) -> Path:
    out = paths.reports / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(paths), encoding="utf-8")
    if not quiet:
        ok(f"Saved {paths.show(out)}. Open it in your browser. It works offline and stays on your computer.")
    if open_it:
        webbrowser.open(out.resolve().as_uri())
    return out


CSS = """
:root{color-scheme:light;
 --page:#f7f6f2;--surface:#fcfcfb;--ink:#0b0b0b;--ink-2:#52514e;--muted:#6f6d67;--grid:#e1e0d9;--axis:#c3c2b7;
 --ring:rgba(11,11,11,.10);--won:#2a78d6;--lost:#eb6834;--stalled:#9a988f;--open:#c9c7bd;
 --s1:#cde2fb;--s2:#9ec5f4;--s3:#6da7ec;--s4:#2a78d6;--s5:#184f95;--s-ink:#0b0b0b;--s-ink-dark:#ffffff;
 --warn:#fab219;--serious:#ec835a;--critical:#d03b3b;--neutral:#898781;--good:#0a7f0a;--hl:rgba(42,120,214,.10);
 --tip-bg:#0b0b0b;--tip-ink:#ffffff}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
 --page:#0f0f0e;--surface:#1a1a19;--ink:#ffffff;--ink-2:#c3c2b7;--muted:#9c9a92;--grid:#2c2c2a;--axis:#383835;
 --ring:rgba(255,255,255,.10);--won:#3987e5;--lost:#d95926;--stalled:#7d7b74;--open:#4a4945;
 --hl:rgba(57,135,229,.20);--tip-bg:#ffffff;--tip-ink:#0b0b0b}}
:root[data-theme="dark"]{color-scheme:dark;
 --page:#0f0f0e;--surface:#1a1a19;--ink:#ffffff;--ink-2:#c3c2b7;--muted:#9c9a92;--grid:#2c2c2a;--axis:#383835;
 --ring:rgba(255,255,255,.10);--won:#3987e5;--lost:#d95926;--stalled:#7d7b74;--open:#4a4945;
 --hl:rgba(57,135,229,.20);--tip-bg:#ffffff;--tip-ink:#0b0b0b}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
code{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:.86em}
.num{font-variant-numeric:tabular-nums}
.wrap{max-width:1120px;margin:0 auto;padding-inline:20px;padding-block:28px 48px;display:flex;flex-direction:column;gap:20px}
h1,h2,h3{margin:0;text-wrap:balance}
h1{font-size:1.75rem;line-height:1.2;letter-spacing:-.01em}
h2{font-size:1.05rem}
h3{font-size:.92rem;font-weight:600}
.eyebrow{margin:0 0 4px;font-size:.72rem;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);font-weight:600}
.sub{margin:6px 0 0;color:var(--ink-2)}
.top{display:flex;flex-wrap:wrap;gap:16px;justify-content:space-between;align-items:flex-end}
.trust{display:flex;gap:10px;align-items:flex-start;max-width:420px;padding:10px 14px;border-radius:10px;
 background:var(--surface);box-shadow:inset 0 0 0 1px var(--ring)}
.trust div{display:flex;flex-direction:column;gap:2px}.trust span{color:var(--ink-2);font-size:.86rem}
.trust .icon{flex:none;width:12px;height:12px;margin-top:5px;border-radius:50%;background:var(--neutral)}
.trust.warning .icon{background:var(--warn);border-radius:2px;transform:rotate(45deg)}
.trust.serious .icon{background:var(--serious);border-radius:2px;transform:rotate(45deg)}
.trust.critical .icon{background:var(--critical);border-radius:2px}
.panel{background:var(--surface);border-radius:12px;box-shadow:inset 0 0 0 1px var(--ring);padding:18px 20px;display:flex;flex-direction:column;gap:14px}
.sec-head{display:flex;flex-wrap:wrap;gap:6px 16px;align-items:baseline;justify-content:space-between}
.sec-head p{margin:0;color:var(--ink-2);font-size:.88rem;max-width:62ch}
.split{display:flex;gap:2px;height:14px;border-radius:7px;overflow:hidden}
.seg.won{background:var(--won)}.seg.lost{background:var(--lost)}.seg.stalled{background:var(--stalled)}
.seg.open,.seg.none{background:var(--open)}
.keys{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:.9rem;color:var(--ink-2)}
.key b{color:var(--ink);margin-left:2px}
.sw{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:-1px}
.sw.won{background:var(--won)}.sw.lost{background:var(--lost)}.sw.stalled{background:var(--stalled)}
.sw.open,.sw.none{background:var(--open)}
.strips{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:18px 28px}
.strip{display:flex;flex-direction:column;gap:4px}
.strip-head{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 12px;align-items:baseline}
.strip-sum{display:flex;gap:14px;font-size:.84rem;color:var(--ink-2)}
.strip-sum b{color:var(--ink)}.strip-sum small{color:var(--muted)}
.won-t::before,.lost-t::before{content:"";display:inline-block;width:3px;height:11px;margin-right:6px;vertical-align:-1px;border-radius:1px}
.won-t::before{background:var(--won)}.lost-t::before{background:var(--lost)}
svg{width:100%;height:auto;display:block;overflow:visible}
svg .grid{stroke:var(--grid);stroke-width:1}
svg .tick{fill:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
svg .rowlab{fill:var(--ink-2);font-size:12px;font-weight:600}
svg .dot{stroke:var(--surface);stroke-width:2;cursor:default}
svg .dot.won{fill:var(--won)}svg .dot.lost{fill:var(--lost)}
svg .dot:focus{outline:none;stroke:var(--ink)}
svg .mean{stroke-width:3;stroke-linecap:round}
svg .mean.won{stroke:var(--won)}svg .mean.lost{stroke:var(--lost)}
.gaps{display:flex;flex-direction:column;gap:6px}
.gap-row{display:grid;grid-template-columns:minmax(0,15rem) minmax(0,1fr) 7.5rem;gap:12px;align-items:center}
.gap-name{font-size:.9rem;display:flex;flex-direction:column;line-height:1.25}
.gap-name code{color:var(--muted);font-size:.74rem}
.gap-track{position:relative;height:18px}
.gap-zero{position:absolute;top:-3px;bottom:-3px;width:1px;background:var(--axis)}
.gap-bar{position:absolute;top:3px;height:12px;border-radius:3px}
.gap-bar.won{background:var(--won)}.gap-bar.lost{background:var(--lost)}
.gap-none{position:absolute;left:52%;font-size:.8rem;color:var(--muted)}
.gap-val{text-align:right;font-weight:600;display:flex;flex-direction:column;line-height:1.2}
.gap-val small{font-weight:400;color:var(--muted);font-size:.76rem}
.scale{display:flex;gap:3px;align-items:center;font-size:.8rem;color:var(--muted)}
.scale span{margin-right:6px}
.scale i{font-style:normal;width:24px;text-align:center;border-radius:4px;font-weight:600;font-size:.78rem}
.table-scroll{overflow-x:auto}
table.calls{border-collapse:separate;border-spacing:2px;font-size:.86rem;min-width:100%}
.calls th,.calls td{padding:5px 8px;text-align:left;vertical-align:middle}
.calls thead th{font-weight:600;color:var(--ink-2);vertical-align:bottom;font-size:.78rem}
.calls th.rot{height:9.5rem;padding:0;width:34px}
.calls th.rot span{display:block;writing-mode:vertical-rl;transform:rotate(180deg);white-space:nowrap;margin:0 auto;padding:4px 0}
.calls th.num,.calls td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.calls tr.grp th{padding-top:14px;font-size:.82rem;color:var(--ink);border-bottom:1px solid var(--grid)}
.calls tr.grp .num{color:var(--muted);font-weight:400;margin-left:4px}
.cid{white-space:nowrap;font-weight:400}.cid code{display:block}
.cid .avg{display:block;font-size:.74rem;color:var(--muted)}
td.hm,.scale .hm{text-align:center;font-weight:600;font-variant-numeric:tabular-nums;border-radius:4px;min-width:30px}
.hm.s1{background:var(--s1);color:var(--s-ink)}.hm.s2{background:var(--s2);color:var(--s-ink)}
.hm.s3{background:var(--s3);color:var(--s-ink)}.hm.s4{background:var(--s4);color:var(--s-ink-dark)}
.hm.s5{background:var(--s5);color:var(--s-ink-dark)}.hm.empty{color:var(--muted)}
td.coach{min-width:16rem;max-width:30rem;color:var(--ink-2);font-size:.82rem;line-height:1.35}
.muted{color:var(--muted)}
.empty{color:var(--muted);margin:0}
.hint{margin:-6px 0 0;color:var(--muted);font-size:.84rem}
.cid a{color:inherit;text-decoration:none}.cid a:hover code,.cid a:focus-visible code{text-decoration:underline}
.notes{padding-inline:4px;color:var(--ink-2);font-size:.88rem;display:flex;flex-direction:column;gap:6px}
.notes h2{color:var(--ink);font-size:.95rem}.notes ul{margin:0;padding-left:1.1rem}.notes p{margin:0;max-width:75ch}
#tip{position:fixed;z-index:10;pointer-events:none;background:var(--tip-bg);color:var(--tip-ink);padding:4px 8px;border-radius:6px;font-size:.8rem;white-space:nowrap}
@media (max-width:640px){.gap-row{grid-template-columns:minmax(0,1fr) 5.5rem}.gap-track{grid-column:1 / -1;grid-row:2}
 h1{font-size:1.4rem}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

JS = """
(function(){var t=document.getElementById('tip');if(!t)return;
function show(e){var el=e.target.closest('[data-tip]');if(!el){t.hidden=true;return}
 t.textContent=el.getAttribute('data-tip');t.hidden=false;var r=el.getBoundingClientRect();
 var x=Math.min(window.innerWidth-t.offsetWidth-8,Math.max(8,r.left+r.width/2-t.offsetWidth/2));
 t.style.left=x+'px';t.style.top=Math.max(8,r.top-t.offsetHeight-8)+'px'}
document.addEventListener('mouseover',show);document.addEventListener('focusin',show);
document.addEventListener('mouseout',function(e){if(e.target.closest('[data-tip]'))t.hidden=true});
document.addEventListener('focusout',function(){t.hidden=true});})();
"""
