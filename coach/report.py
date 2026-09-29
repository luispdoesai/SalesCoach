"""The parts of the dashboard that bring every file into one readable page.

- status_items: what is done and what to do next, in plain words.
- render_markdown: shows Findings.md inside the page.
- call_cards: one expandable card per call with its scorecard, quotes,
  email history, tone hints, and the transcript.

Everything is read from files on disk. Counts here are made by code.
"""

from __future__ import annotations

import json
import re
from html import escape

from typing import Any

from coach import callfile
from coach.callfile import EMAIL_PLACEHOLDER, fmt_ts
from coach.config import OUTCOME_VALUES, STARTER_RUBRIC_MARKER, Paths
from coach.scorecards import Report, find_quote_all, read_csv_rows

AUDIO = {".m4a", ".mp3", ".wav", ".aac", ".ogg", ".opus", ".flac", ".webm", ".aif", ".aiff", ".mp4", ".mov"}


# Loading everything about the calls

def load_calls(paths: Paths, reports: dict[str, Report]) -> list[dict[str, Any]]:
    stats = {r["call_id"]: r for r in read_csv_rows(paths.stats_csv)}
    results = {r["call_id"]: r for r in read_csv_rows(paths.results_csv)}
    outcomes = {r["call_id"]: r for r in read_csv_rows(paths.outcomes_csv)}
    contacts = {r["call_id"]: r for r in read_csv_rows(paths.contacts_csv)}
    calls = []
    for path in sorted(paths.calls.glob("*.md")) if paths.calls.is_dir() else []:
        cid = path.stem
        try:
            cf = callfile.read(path)
        except (OSError, UnicodeDecodeError):
            continue
        card = None
        card_path = paths.scorecards / f"{cid}.json"
        if card_path.exists():
            try:
                card = json.loads(card_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                card = None
        outcome = (outcomes.get(cid, {}).get("outcome") or "").lower()
        calls.append({
            "id": cid, "cf": cf, "card": card, "report": reports.get(cid),
            "stats": stats.get(cid, {}), "result": results.get(cid, {}),
            "outcome": outcome if outcome in OUTCOME_VALUES else "",
            "outcome_row": outcomes.get(cid, {}), "contact": contacts.get(cid, {}),
            "has_card": card_path.exists(),
        })
    return calls


# What to do next

def status_items(paths: Paths, calls: list[dict]) -> list[tuple[str, str, str]]:
    """(level, what, how to fix) in plain words. level is todo, warn, or done."""
    items: list[tuple[str, str, str]] = []

    def ids(xs: list[str]) -> str:
        return ", ".join(xs[:4]) + (f", and {len(xs) - 4} more" if len(xs) > 4 else "")

    waiting = [p.name for p in paths.inbox.iterdir() if p.suffix.lower() in AUDIO] if paths.inbox.is_dir() else []
    if waiting:
        items.append(("todo", f"{len(waiting)} recording{'s' if len(waiting) != 1 else ''} waiting to be transcribed.",
                      "Run: python coach.py transcribe"))
    if paths.rubric.exists() and paths.rubric.read_text(encoding="utf-8").lstrip().startswith(STARTER_RUBRIC_MARKER):
        items.append(("warn", "You are still using the starter rubric, not one built for how you sell.",
                      "In Claude Code, run /coach-rubric"))
    review = [c["id"] for c in calls if c["cf"].meta.get("needs_review") is True]
    if review:
        items.append(("warn", f"Check who is who on {ids(review)}. The tool was not sure which speaker is you.",
                      "Open the call below and read the first lines. If REP and PROSPECT are swapped, run: "
                      "python coach.py transcribe --file CALL_ID --rep-speaker spk_1"))
    unscored = [c["id"] for c in calls if not c["has_card"]]
    if unscored:
        items.append(("todo", f"{len(unscored)} call{'s' if len(unscored) != 1 else ''} not scored yet: {ids(unscored)}.",
                      "In Claude Code, run /coach-score"))
    failed = [c["id"] for c in calls if c["report"] is not None and not c["report"].ok]
    if failed:
        items.append(("warn", f"{len(failed)} scorecard{'s' if len(failed) != 1 else ''} failed the quote check and "
                              f"{'are' if len(failed) != 1 else 'is'} left out of the numbers: {ids(failed)}.",
                      "In Claude Code, ask it to re-score those calls using exact words from the transcript"))
    no_outcome = [c["id"] for c in calls if not c["outcome"]]
    if no_outcome:
        items.append(("todo", f"{len(no_outcome)} call{'s' if len(no_outcome) != 1 else ''} with no outcome: {ids(no_outcome)}.",
                      f"Open {paths.show(paths.outcomes_csv)} and add won, lost, stalled, or open for each"))
    no_email = [c["id"] for c in calls if c["cf"].email_block.strip() == EMAIL_PLACEHOLDER]
    if no_email:
        items.append(("optional", f"Email history not pulled for {len(no_email)} call{'s' if len(no_email) != 1 else ''}.",
                      "Optional. In Claude Code, run /coach-emails"))
    findings = paths.reports / "Findings.md"
    if calls and not findings.exists():
        items.append(("todo", "Your findings are not written yet.", "In Claude Code, run /coach-findings"))
    elif findings.exists() and paths.results_csv.exists() and findings.stat().st_mtime < paths.results_csv.stat().st_mtime:
        items.append(("warn", "Your findings are older than your latest scores.", "In Claude Code, run /coach-findings again"))
    if not calls and not waiting:
        items.append(("todo", "No calls yet.", f"Drop recordings into {paths.show(paths.inbox)}/ named like "
                                               "2026-09-28_JD_Discovery.m4a, then run: python coach.py transcribe"))
    from coach.archive import suggestions
    from coach.config import suggest_after_days

    reports = [c["report"] for c in calls if c["report"] is not None]
    for why, what in suggestions(paths, reports, suggest_after_days()):
        items.append(("suggest", why, what))
    if not items:
        items.append(("done", "Everything is up to date.", "Record your next calls and drop them in the inbox."))
    from coach.archive import is_archive

    if is_archive(paths):
        # Claude Code needs to know this is an archived folder, not the current one.
        where = f" and say: use {paths.show(paths.data)}"
        items = [(lvl, what, fix + where if "In Claude Code" in fix or "Optional. In Claude Code" in fix else fix)
                 for lvl, what, fix in items]
    return items


def status_html(paths: Paths, calls: list[dict]) -> str:
    scored = sum(1 for c in calls if c["report"] is not None and c["report"].ok)
    with_outcome = sum(1 for c in calls if c["outcome"])
    counts = (f'<div class="counts"><span><b class="num">{len(calls)}</b> transcribed</span>'
              f'<span><b class="num">{scored}</b> scored</span>'
              f'<span><b class="num">{with_outcome}</b> with an outcome</span></div>')
    label = {"todo": "To do", "warn": "Check", "optional": "Optional", "done": "Done", "suggest": "Suggested"}
    rows = "".join(
        f'<li class="st {lvl}"><span class="st-tag">{label[lvl]}</span><div><b>{escape(what)}</b>'
        f'<span>{escape(fix)}</span></div></li>' for lvl, what, fix in status_items(paths, calls))
    return f'{counts}<ul class="status">{rows}</ul>'


# Findings.md inside the page

def _inline(text: str) -> str:
    out = escape(text)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?<![\w*])\*([^*\s][^*]*)\*(?!\w)", r"<i>\1</i>", out)
    return out


def render_markdown(md: str) -> str:
    """A small, safe Markdown renderer for the shapes Findings.md uses."""
    lines = md.splitlines()
    html: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue
        if s.startswith("```"):
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            html.append(f"<pre>{escape(chr(10).join(block))}</pre>")
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            level = min(len(m.group(1)) + 1, 5)  # the page already has an h1 and h2s
            html.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    rows.append(cells)
                i += 1
            if rows:
                head = "".join(f"<th>{_inline(c)}</th>" for c in rows[0])
                body = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
                html.append(f'<div class="table-scroll"><table class="md"><thead><tr>{head}</tr></thead>'
                            f"<tbody>{body}</tbody></table></div>")
            continue
        if re.match(r"^([-*]|\d+\.)\s+", s):
            ordered = bool(re.match(r"^\d+\.", s))
            items = []
            while i < len(lines) and re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                items.append(re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i]))
                i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip() \
                        and not re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                    items[-1] += " " + lines[i].strip()
                    i += 1
            tag = "ol" if ordered else "ul"
            html.append(f"<{tag}>" + "".join(f"<li>{_inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        if s.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            html.append(f"<blockquote>{_inline(' '.join(quote))}</blockquote>")
            continue
        para = [s]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||```|>|[-*]\s|\d+\.\s)", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        html.append(f"<p>{_inline(' '.join(para))}</p>")
    return "\n".join(html)


def findings_html(paths: Paths) -> str:
    path = paths.reports / "Findings.md"
    if not path.exists():
        return ('<p class="empty">Not written yet. Once your calls are scored and have outcomes, '
                'open Claude Code in this folder and run <code>/coach-findings</code>. '
                "Your findings will then appear here.</p>")
    stale = ""
    if paths.results_csv.exists() and path.stat().st_mtime < paths.results_csv.stat().st_mtime:
        stale = ('<p class="stale"><b>Out of date.</b> These findings were written before your latest changes, '
                 "so they may describe calls that are no longer on this page. "
                 "Run <code>/coach-findings</code> in Claude Code to update them.</p>")
    return f'{stale}<div class="md-body">{render_markdown(path.read_text(encoding="utf-8"))}</div>'


# One card per call

def _price_sentences(card: dict | None, stats: dict) -> str:
    if not card:
        return "Not scored yet."
    p = card.get("price_handling") or {}
    if not p.get("price_stated"):
        return "Price was not stated on this call."
    parts = ["Price was stated."]
    if p.get("prospect_objected"):
        parts.append("The prospect pushed back.")
        parts.append("You held the price." if p.get("held_price") else "You did not hold the price.")
    else:
        parts.append("The prospect did not push back.")
    if p.get("conceded_or_discounted"):
        parts.append("You offered a discount or concession.")
    gap, who = stats.get("price_silence_sec"), stats.get("price_next_speaker")
    if gap not in (None, ""):
        if float(gap) == 0:
            parts.append("You kept talking right after the price.")
        else:
            parts.append(f"Silence after the price: {gap} seconds, then the "
                         f"{'prospect' if who == 'PROSPECT' else 'rep'} spoke.")
    return " ".join(parts)


def _chip(score: Any) -> str:
    try:
        s = int(score)
    except (TypeError, ValueError):
        return '<span class="chip hm empty">-</span>'
    return f'<span class="chip hm s{s}">{s}</span>'


def _quote(q: Any, ts: Any) -> str:
    if not q:
        return '<span class="muted">No quote. This did not happen on the call.</span>'
    stamp = f'<code class="ts">[{escape(str(ts))}]</code> ' if ts else ""
    return f'{stamp}<q>{escape(str(q))}</q>'


def _card_html(c: dict, names: dict[str, str], group_label: dict[str, str]) -> str:
    cf, card, st, cid = c["cf"], c["card"], c["stats"], c["id"]
    meta = cf.meta
    contact = c["contact"]
    who = " at ".join(x for x in (contact.get("prospect_name"), contact.get("company")) if x)
    pill = f'<span class="pill {c["outcome"] or "none"}">{group_label[c["outcome"]]}</span>'
    flags = []
    if meta.get("needs_review") is True:
        flags.append('<span class="flag warn">Check speakers</span>')
    if not c["has_card"]:
        flags.append('<span class="flag todo">Not scored</span>')
    elif c["report"] is not None and not c["report"].ok:
        flags.append('<span class="flag warn">Failed quote check</span>')
    avg = c["result"].get("rubric_avg")
    summary = (f'<summary>{pill}<span class="call-title"><code>{escape(cid)}</code>'
               f'<span class="who">{escape(who or str(meta.get("stage") or ""))}</span></span>'
               f'<span class="call-meta">{escape(str(meta.get("stage") or ""))} · {fmt_ts(float(meta.get("duration_sec") or 0))}'
               f'{" · avg " + escape(avg) if avg else ""}</span>{"".join(flags)}</summary>')

    blocks = []
    if card:
        rw = card.get("rewrite") or {}
        misses = "".join(f"<li>{escape(str(m))}</li>" for m in card.get("top_misses") or [])
        blocks.append(
            '<div class="call-grid">'
            f'<div class="focus"><h4>One thing to change</h4><p class="big">{escape(str(card.get("one_thing_to_change") or ""))}</p>'
            f'<h4>Biggest misses</h4><ol>{misses}</ol></div>'
            f'<div class="rewrite"><h4>Your weakest moment, rewritten</h4>'
            f'<p><span class="lab">Instead of</span>{_quote(rw.get("original_quote"), rw.get("timestamp"))}</p>'
            f'<p><span class="lab">Try</span><q>{escape(str(rw.get("better_version") or ""))}</q></p></div>'
            '</div>')
    stat_list = [("Your share of talk time", st.get("rep_talk_pct"), "%"),
                 ("Questions you asked", st.get("rep_questions"), ""),
                 ("Your longest stretch without a pause", st.get("longest_rep_monologue_sec"), " seconds")]
    stat_html = "".join(f'<div><dt>{escape(lab)}</dt><dd class="num">{escape(str(v)) + unit if v not in (None, "") else "-"}</dd></div>'
                        for lab, v, unit in stat_list)
    blocks.append(f'<div class="call-grid"><div><h4>Measured from the recording</h4><dl class="facts">{stat_html}</dl></div>'
                  f'<div><h4>Price</h4><p>{escape(_price_sentences(card, st))}</p></div></div>')

    if card:
        rows = []
        for s in card.get("rubric_scores") or []:
            rows.append(f'<li>{_chip(s.get("score"))}<div><b>{escape(names.get(s.get("id"), str(s.get("id"))))}</b>'
                        f'<p>{_quote(s.get("evidence_quote"), s.get("timestamp"))}</p>'
                        f'<p class="why">{escape(str(s.get("why") or ""))}</p></div></li>')
        for key, label in (("rapport", "Rapport"), ("tone_match", "Tone match")):
            s = card.get(key) or {}
            rows.append(f'<li>{_chip(s.get("score"))}<div><b>{label}</b>'
                        f'<p>{_quote(s.get("evidence_quote"), s.get("timestamp"))}</p>'
                        f'<p class="why">{escape(str(s.get("why") or ""))}</p></div></li>')
        blocks.append(f'<h4>Scores, with the words that earned them</h4><ul class="scores">{"".join(rows)}</ul>')
        objs = card.get("objections") or []
        if objs:
            obj_rows = "".join(
                f'<li><span class="flag {"ok" if o.get("handled") else "warn"}">'
                f'{"Handled" if o.get("handled") else "Not handled"}</span><div><b>{escape(str(o.get("type") or "").replace("_", " "))}</b>'
                f'<p>{_quote(o.get("evidence_quote"), o.get("timestamp"))}</p><p class="why">{escape(str(o.get("why") or ""))}</p></div></li>'
                for o in objs)
            blocks.append(f'<h4>Objections</h4><ul class="scores">{obj_rows}</ul>')
    if c["report"] is not None and not c["report"].ok:
        errs = "".join(f"<li>{escape(e)}</li>" for e in c["report"].errors[:8])
        blocks.append(f'<div class="failed"><h4>Why this scorecard is left out of the numbers</h4><ul>{errs}</ul></div>')

    email = cf.email_block.strip()
    blocks.append('<h4>Email history</h4>' + (
        f'<pre class="email">{escape(email)}</pre>' if email != EMAIL_PLACEHOLDER
        else '<p class="muted">Not pulled yet. Optional: run <code>/coach-emails</code> in Claude Code.</p>'))
    tone_lines = [ln[2:] for ln in cf.tone_text.splitlines() if ln.startswith("- ")]
    if tone_lines:
        blocks.append('<h4>Tone hints <small>from the audio. Verify before trusting.</small></h4><ul class="tone">'
                      + "".join(f"<li>{escape(t)}</li>" for t in tone_lines) + "</ul>")

    # Transcript, with the lines the scorecard quotes marked
    marks: dict[int, list[str]] = {}
    if card:
        quoted = [(names.get(s.get("id"), s.get("id")), s.get("evidence_quote")) for s in card.get("rubric_scores") or []]
        quoted += [("Objection", o.get("evidence_quote")) for o in card.get("objections") or []]
        quoted += [("Rewrite", (card.get("rewrite") or {}).get("original_quote"))]
        for label, q in quoted:
            if q:
                for idx in find_quote_all(q, cf.lines)[:1]:
                    marks.setdefault(idx, []).append(str(label))
    lines_html = "".join(
        f'<li class="{ln.role.lower()}{" quoted" if i in marks else ""}"><code class="ts">{fmt_ts(ln.start)}</code>'
        f'<span class="spk">{"You" if ln.role == "REP" else "Prospect" if ln.role == "PROSPECT" else escape(ln.role)}</span>'
        f'<span class="said">{escape(ln.text)}'
        + (f'<small class="used">Quoted for: {escape(", ".join(marks[i]))}</small>' if i in marks else "")
        + "</span></li>" for i, ln in enumerate(cf.lines))
    blocks.append(f'<details class="transcript"><summary>Read the transcript ({len(cf.lines)} lines)</summary>'
                  f'<ol class="lines">{lines_html}</ol></details>')
    return (f'<details class="call" id="call-{escape(cid)}" data-outcome="{c["outcome"] or "none"}">{summary}'
            f'<div class="call-body">{"".join(blocks)}</div></details>')


def call_cards(calls: list[dict], names: dict[str, str], group_label: dict[str, str], order: list[str]) -> str:
    if not calls:
        return '<p class="empty">No transcribed calls yet.</p>'
    ranked = sorted(calls, key=lambda c: (order.index(c["outcome"]), c["id"]))
    return "".join(_card_html(c, names, group_label) for c in ranked)


def periods_html(paths: Paths, calls: list[dict]) -> str:
    """Which calls this page covers, and links to archived periods."""
    from coach.archive import date_range, is_archive, list_archives

    ids = [c["id"] for c in calls]
    first, last = date_range(ids)
    span = f"from <b>{escape(first)}</b> to <b>{escape(last)}</b>" if first else ""
    if is_archive(paths):
        return (f'<p>This page shows an <b>archived period</b>: {len(ids)} calls {span}. '
                "These calls are not part of your current numbers.</p>"
                '<p><a class="btn" href="../../../reports/dashboard.html">Back to your current dashboard</a></p>'
                f'<p class="hint">To put these calls back with your current ones, run '
                f'<code>python coach.py restore {escape(paths.data.name)}</code>.</p>')
    archives = list_archives(paths)
    rows = "".join(
        f'<li><a href="../archive/{escape(a["name"])}/reports/dashboard.html">{escape(a["name"])}</a>'
        f'<span>{a["count"]} calls{", " + escape(a["first"]) + " to " + escape(a["last"]) if a["first"] else ""}</span></li>'
        for a in archives)
    archived = (f'<h3>Archived periods</h3><ul class="periods">{rows}</ul>' if archives else
                '<p class="hint">No archived periods yet.</p>')
    return (f"<p>This page covers <b>{len(ids)} current calls</b> {span}. Older calls you archive are kept "
            "separately, each period with its own page, so they never mix into these numbers.</p>"
            f"{archived}"
            '<p class="hint">To set older calls aside, ask Claude Code, or run '
            "<code>python coach.py archive --before 2026-09-01</code> with your own date. "
            "It shows the calls first and asks before moving anything.</p>")


GUIDE = """
<dl class="guide">
<div><dt>Scores from 1 to 5</dt><dd>How well you did each behavior in your rubric. 5 means done fully and well. 1 means it did not happen or went badly. Every score of 2 or more comes with the exact words from the call that earned it.</dd></div>
<div><dt>Your share of talk time</dt><dd>How much of the talking you did. Measured from the recording, not guessed.</dd></div>
<div><dt>Questions you asked</dt><dd>Question marks in your lines. Close, but not exact.</dd></div>
<div><dt>Longest stretch without a pause</dt><dd>The longest time you talked before the prospect said anything.</dd></div>
<div><dt>Silence after the price</dt><dd>How long you stayed quiet after saying the price, and who spoke next. Zero means you kept talking.</dd></div>
<div><dt>Won vs. lost</dt><dd>What your won calls had in common compared with your lost ones. It shows what goes together, not what caused a win. With few calls, treat it as a hint.</dd></div>
<div><dt>Tone hints</dt><dd>An AI's read of how each side sounded, minute by minute. Useful, but check it against the recording.</dd></div>
<div><dt>Where the files live</dt><dd>Everything on this page comes from the data folder next to it. This page never leaves your computer and is never uploaded.</dd></div>
</dl>
"""

EXTRA_CSS = """
ul.periods{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}
ul.periods li{display:flex;flex-wrap:wrap;gap:4px 14px;align-items:baseline}
ul.periods a{font-weight:600;color:var(--won)}ul.periods span{color:var(--ink-2);font-size:.88rem}
#periods h3{font-size:.92rem;margin-top:4px}#periods p{margin:0;max-width:75ch}
a.btn{display:inline-block;padding:6px 14px;border-radius:999px;background:var(--ink);color:var(--surface);text-decoration:none;font-weight:600;font-size:.88rem}
.stale{margin:0;padding:10px 14px;border-radius:8px;background:var(--warn);color:#0b0b0b;max-width:75ch}
.stale code{color:#0b0b0b}
.archived-banner{background:var(--warn);color:#0b0b0b;text-align:center;padding:8px 16px;font-weight:600;font-size:.9rem}
.archived-banner a{color:#0b0b0b}
.nav{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--page);border-bottom:1px solid var(--grid)}
.nav div{max-width:1120px;margin:0 auto;padding-inline:20px;display:flex;gap:4px 18px;flex-wrap:wrap;padding-block:8px}
.nav a{color:var(--ink-2);text-decoration:none;font-size:.88rem;font-weight:500;padding:4px 0}
.nav a:hover,.nav a:focus-visible{color:var(--ink);text-decoration:underline}
.counts{display:flex;flex-wrap:wrap;gap:6px 22px;color:var(--ink-2)}.counts b{color:var(--ink);font-size:1.3rem;margin-right:4px}
.status{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
.st{display:flex;gap:12px;align-items:flex-start}
.st div{display:flex;flex-direction:column;gap:1px}.st div span{color:var(--ink-2);font-size:.86rem}
.st-tag{flex:none;width:5.2rem;text-align:center;font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;
 padding:3px 0;border-radius:5px;background:var(--grid);color:var(--ink)}
.st.todo .st-tag{background:var(--won);color:#fff}.st.warn .st-tag{background:var(--warn);color:#0b0b0b}
.st.done .st-tag{background:var(--good);color:#fff}.st.suggest .st-tag{background:var(--ink);color:var(--surface)}.st.optional .st-tag{background:var(--grid);color:var(--ink-2)}
.md-body{max-width:75ch;display:flex;flex-direction:column;gap:10px}
.md-body h2,.md-body h3{font-size:1.05rem;margin-top:10px}.md-body h4,.md-body h5{font-size:.95rem}
.md-body p,.md-body ul,.md-body ol{margin:0}.md-body li{margin:3px 0}
.md-body blockquote{margin:0;padding-left:12px;border-left:3px solid var(--axis);color:var(--ink-2)}
.md-body pre,pre.email{white-space:pre-wrap;background:var(--page);padding:10px 12px;border-radius:8px;margin:0;font-size:.84rem}
table.md{border-collapse:collapse;font-size:.86rem}
table.md th,table.md td{border-bottom:1px solid var(--grid);padding:5px 10px;text-align:left}
.filters{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.filters button{font:inherit;font-size:.84rem;padding:4px 12px;border-radius:999px;border:1px solid var(--axis);
 background:var(--surface);color:var(--ink);cursor:pointer}
.filters button[aria-pressed="true"]{background:var(--ink);color:var(--surface);border-color:var(--ink)}
.filters button:focus-visible{outline:2px solid var(--won);outline-offset:2px}
.cards{display:flex;flex-direction:column;gap:8px}
details.call{border-radius:10px;box-shadow:inset 0 0 0 1px var(--ring);background:var(--surface)}
details.call>summary{list-style:none;cursor:pointer;display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;padding:12px 14px}
details.call>summary::-webkit-details-marker{display:none}
details.call>summary::before{content:"";width:8px;height:8px;border-right:2px solid var(--muted);border-bottom:2px solid var(--muted);
 transform:rotate(-45deg);margin-right:2px;transition:transform .15s}
details.call[open]>summary::before{transform:rotate(45deg)}
details.call>summary:focus-visible{outline:2px solid var(--won);outline-offset:-2px;border-radius:10px}
.call-title{display:flex;flex-direction:column;line-height:1.25}.who{font-size:.84rem;color:var(--ink-2)}
.call-meta{color:var(--muted);font-size:.84rem;margin-left:auto}
.pill{font-size:.74rem;font-weight:700;padding:2px 9px;border-radius:999px;color:#fff;background:var(--open)}
.pill.won{background:var(--won)}.pill.lost{background:var(--lost)}.pill.stalled{background:var(--stalled)}
.pill.open,.pill.none{background:var(--open);color:var(--ink)}
.flag{font-size:.72rem;font-weight:600;padding:2px 8px;border-radius:5px;background:var(--grid);color:var(--ink);white-space:nowrap}
.flag.warn{background:var(--warn);color:#0b0b0b}.flag.todo{background:var(--grid)}.flag.ok{background:var(--good);color:#fff}
.call-body{padding:4px 18px 18px;display:flex;flex-direction:column;gap:12px;border-top:1px solid var(--grid)}
.call-body h4{margin:6px 0 0;font-size:.92rem}.call-body h4 small{font-weight:400;color:var(--muted)}
.call-body p{margin:4px 0}
.call-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:12px 28px}
.focus .big{font-size:1.02rem;font-weight:600}.focus ol{margin:4px 0 0;padding-left:1.2rem}
.rewrite .lab{display:block;font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:700}
q{quotes:"\\201C" "\\201D"}
.ts{color:var(--muted);font-size:.78rem}
dl.facts{margin:4px 0 0;display:grid;gap:4px}dl.facts div{display:flex;justify-content:space-between;gap:12px;border-bottom:1px dashed var(--grid);padding-block:3px}
dl.facts dt{color:var(--ink-2)}dl.facts dd{margin:0;font-weight:600}
ul.scores{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px}
ul.scores li{display:flex;gap:12px;align-items:flex-start}
.chip{flex:none;display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:6px;font-weight:700}
ul.scores li>.flag{flex:none;margin-top:3px}
.why{color:var(--ink-2);font-size:.88rem}
ul.tone{margin:0;padding-left:1.1rem;color:var(--ink-2);font-size:.86rem}
.failed{background:var(--page);border-radius:8px;padding:8px 12px}.failed ul{margin:4px 0;font-size:.85rem}
details.transcript>summary{cursor:pointer;font-weight:600;font-size:.92rem;padding:4px 0}
ol.lines{list-style:none;margin:6px 0 0;padding:0;display:flex;flex-direction:column;gap:2px;max-height:34rem;overflow-y:auto}
ol.lines li{display:grid;grid-template-columns:3.4rem 5rem minmax(0,1fr);gap:8px;padding:4px 8px;border-radius:6px;font-size:.88rem}
ol.lines li.rep .spk{color:var(--won);font-weight:600}ol.lines li.prospect .spk{color:var(--lost);font-weight:600}
ol.lines li.quoted{background:var(--hl)}
.used{display:block;color:var(--muted);font-size:.76rem}
dl.guide{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:12px 28px;margin:0}
dl.guide dt{font-weight:600}dl.guide dd{margin:2px 0 0;color:var(--ink-2);font-size:.9rem}
@media (max-width:640px){ol.lines li{grid-template-columns:3rem minmax(0,1fr)}ol.lines li .said{grid-column:1 / -1}
 .call-meta{margin-left:0}}
"""

EXTRA_JS = """
(function(){var bar=document.querySelector('.filters');if(!bar)return;
var cards=[].slice.call(document.querySelectorAll('details.call'));
bar.addEventListener('click',function(e){var b=e.target.closest('button');if(!b)return;
 if(b.dataset.filter){[].forEach.call(bar.querySelectorAll('[data-filter]'),function(x){x.setAttribute('aria-pressed',x===b?'true':'false')});
  cards.forEach(function(c){c.hidden=!(b.dataset.filter==='all'||c.dataset.outcome===b.dataset.filter)})}
 if(b.dataset.expand){var open=b.dataset.expand==='open';cards.forEach(function(c){if(!c.hidden)c.open=open})}});
function openHash(){var id=location.hash.slice(1);var el=id&&document.getElementById(id);if(el&&el.tagName==='DETAILS')el.open=true}
window.addEventListener('hashchange',openHash);openHash();})();
"""
