"""Statistics from timestamps. Pure code. No AI touches these numbers.

For each call in data/raw/:
- rep_talk_pct: rep speaking time / (rep + prospect speaking time), as a percent.
  Speaking time is the sum of utterance lengths (start to end).
- prospect_talk_pct: the same for the prospect. The two add up to 100.
- rep_questions: question marks in the rep's lines. An approximation: it
  depends on the transcriber's punctuation, and one line can hold two questions.
- longest_rep_monologue_sec: the longest stretch of consecutive rep utterances,
  from the first one's start to the last one's end.
- price_silence_sec: seconds from price_stated_end_sec (in the scorecard) to the
  next word spoken by anyone. price_next_speaker says who spoke. Blank if no
  price was stated or the call has no valid scorecard yet. 0 means the rep kept
  talking straight after the price.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from coach.config import Paths
from coach.friendly import CoachError, heading, note
from coach.scorecards import Report, write_csv

COLUMNS = ["call_id", "duration_sec", "rep_talk_pct", "prospect_talk_pct", "rep_questions",
           "longest_rep_monologue_sec", "price_silence_sec", "price_next_speaker"]


def talk_split(utterances: list[dict]) -> tuple[float | None, float | None]:
    rep = sum(max(0.0, u["end"] - u["start"]) for u in utterances if u.get("role") == "REP")
    prospect = sum(max(0.0, u["end"] - u["start"]) for u in utterances if u.get("role") == "PROSPECT")
    if rep + prospect == 0:
        return None, None
    rep_pct = round(100 * rep / (rep + prospect), 1)
    return rep_pct, round(100 - rep_pct, 1)


def rep_questions(utterances: list[dict]) -> int:
    return sum(u["text"].count("?") for u in utterances if u.get("role") == "REP")


def longest_rep_monologue(utterances: list[dict]) -> float:
    best, run_start, run_end = 0.0, None, None
    for u in sorted(utterances, key=lambda x: x["start"]):
        if u.get("role") == "REP":
            run_start = u["start"] if run_start is None else run_start
            run_end = u["end"] if run_end is None else max(run_end, u["end"])
            best = max(best, run_end - run_start)
        else:
            run_start = run_end = None
    return round(best, 1)


def price_silence(raw: dict, price_end: float | None) -> tuple[float | None, str]:
    """Gap after the price, and who broke it. Uses words when available."""
    if price_end is None:
        return None, ""
    roles = raw.get("speaker_mapping") or {}
    words = raw.get("words") or []
    if words:
        after = [w for w in words if w["start"] >= price_end - 0.05]
        if not after:
            return None, ""
        nxt = min(after, key=lambda w: w["start"])
        return round(max(0.0, nxt["start"] - price_end), 1), roles.get(nxt["speaker"], "")
    for u in sorted(raw["utterances"], key=lambda x: x["start"]):
        # Within 0.3 s of a line's end counts as the end of that line. Utterance
        # timing is coarse when there are no word timestamps.
        if u["start"] < price_end < u["end"] - 0.3:
            return 0.0, u.get("role", "")  # the same person kept talking
        if u["start"] >= price_end - 0.05:
            return round(max(0.0, u["start"] - price_end), 1), u.get("role", "")
    return None, ""


def load_raw(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["utterances"]  # noqa: B018  required field
        return raw
    except (OSError, json.JSONDecodeError, KeyError):
        raise CoachError(f"{path.name} in data/raw is damaged or incomplete.",
                         f"Transcribe that call again: python coach.py transcribe --file {path.stem} --force") from None


def call_stats(raw: dict, price_end: float | None) -> dict[str, Any]:
    utts = raw["utterances"]
    rep_pct, prospect_pct = talk_split(utts)
    silence, speaker = price_silence(raw, price_end)
    return {
        "call_id": raw["call_id"],
        "duration_sec": round(float(raw.get("duration_sec") or 0), 1),
        "rep_talk_pct": rep_pct,
        "prospect_talk_pct": prospect_pct,
        "rep_questions": rep_questions(utts),
        "longest_rep_monologue_sec": longest_rep_monologue(utts),
        "price_silence_sec": silence,
        "price_next_speaker": speaker,
    }


def print_stats(rows: list[dict[str, Any]]) -> None:
    def f(v: Any, unit: str = "") -> str:
        return "-" if v in (None, "") else f"{v:.1f}{unit}" if isinstance(v, float) else f"{v}{unit}"

    width = max(len(r["call_id"]) for r in rows)
    print(f"\n  {'call_id':<{width}}  {'talk%':>6} {'?s':>4} {'monolog':>8} {'price gap':>10}  next")
    for r in rows:
        print(f"  {r['call_id']:<{width}}  {f(r['rep_talk_pct']):>6} {f(r['rep_questions']):>4} "
              f"{f(r['longest_rep_monologue_sec'], 's'):>8} {f(r['price_silence_sec'], 's'):>10}  "
              f"{r['price_next_speaker'] or '-'}")
    print("  talk% = rep share of talk time. ?s = question marks in rep lines (approximate).")
    print("  price gap = silence after the price. Blank until a valid scorecard says when the price was stated.")


def build_stats(paths: Paths, reports: list[Report]) -> list[dict[str, Any]]:
    price_ends: dict[str, float | None] = {}
    for r in reports:
        if r.ok and r.data:
            ph = r.data.get("price_handling") or {}
            price_ends[r.call_id] = ph.get("price_stated_end_sec") if ph.get("price_stated") else None
    rows = []
    review = []
    for path in sorted(paths.raw.glob("*.json")) if paths.raw.is_dir() else []:
        raw = load_raw(path)
        raw.setdefault("call_id", path.stem)
        if raw.get("mapping_confidence") == "low":
            review.append(path.stem)
        rows.append(call_stats(raw, price_ends.get(path.stem)))
    write_csv(paths.stats_csv, COLUMNS, rows)
    heading(f"Statistics for {len(rows)} call(s), computed from timestamps")
    print(f"  Saved {paths.show(paths.stats_csv)}")
    if review:
        note(f"Speaker labels are unconfirmed for {', '.join(review)}. Talk stats depend on them. "
             "Check the first lines of those call files.")
    return rows
