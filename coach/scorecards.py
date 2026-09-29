"""Scorecards: rubric parsing, validation, quote verification, and merge.

Claude Code writes data/scorecards/<call_id>.json. This module checks them.
It never edits a scorecard. A failed scorecard is reported with the exact
field and the reason, then left out of results.csv until it is fixed.

The core rule: no quote, no score. Every score of 2 to 5 needs a quote
that really appears in the call file transcript.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from coach import callfile
from coach.callfile import CallFile, fmt_ts, parse_ts
from coach.config import OUTCOME_VALUES, Paths
from coach.friendly import CoachError, heading, note, ok

REQUIRED_KEYS = [
    "call_id", "scored_at", "rubric_scores", "rapport", "tone_match", "price_handling",
    "objections", "first_pain_question_sec", "top_misses", "rewrite", "one_thing_to_change",
]
PRICE_DETAIL_KEYS = ["price_stated_end_sec", "held_price", "conceded_or_discounted", "prospect_objected"]
HEADING_RE = re.compile(r"^###\s+(.+?)\s*:\s*(.+?)\s*$")
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
TIMESTAMP_SLACK_SEC = 90


# Rubric

@dataclass
class RubricItem:
    id: str
    name: str
    levels: dict[str, str] = field(default_factory=dict)


def parse_rubric(path: Path) -> list[RubricItem]:
    if not path.exists():
        raise CoachError(f"{path.name} does not exist yet, so scorecards cannot be checked.",
                         "Run /coach-rubric in Claude Code, or run: python coach.py init for a starter.")
    items: list[RubricItem] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        m = HEADING_RE.match(stripped)
        if m:
            rid = m.group(1).strip()
            if not ID_RE.match(rid):
                raise CoachError(
                    f"Rubric line {n} has the id '{rid}'. Ids must be lowercase letters, numbers, and underscores.",
                    f"Change it to something like: ### {re.sub(r'[^a-z0-9]+', '_', rid.lower()).strip('_') or 'my_behavior'}: {m.group(2)}")
            if any(i.id == rid for i in items):
                raise CoachError(f"The rubric has the id '{rid}' twice (line {n}).",
                                 "Give each behavior its own id.")
            items.append(RubricItem(rid, m.group(2).strip()))
        elif items and re.match(r"^[135]\s*:", stripped):
            items[-1].levels[stripped[0]] = stripped[2:].strip()
    if not items:
        raise CoachError(f"{path.name} has no behaviors.",
                         "Each behavior needs a heading like: ### price_handling: Price Handling")
    return items


# Quotes

ELLIPSIS_RE = re.compile(r"\s*(?:\.\.\.|…)\s*")
LEADING_LABEL_RE = re.compile(r"^\s*(?:\[[\d:]+\]\s*)?(?:REP|PROSPECT)\s*:\s*", re.IGNORECASE)
QUOTE_CHARS = {"‘": "'", "’": "'", "“": '"', "”": '"', " ": " "}


def normalize(text: str) -> str:
    """Lowercase, straight quotes, one space, and the same spacing around punctuation."""
    text = unicodedata.normalize("NFKC", str(text))
    for fancy, plain in QUOTE_CHARS.items():
        text = text.replace(fancy, plain)
    text = text.lower()
    text = re.sub(r"\s*([,.!?;:])\s*", r"\1 ", text)
    return " ".join(text.split()).strip(" \"'")


def find_quote_all(quote: str, lines: list[callfile.TranscriptLine]) -> list[int]:
    """Indexes of every transcript line that contains the quote.

    A quote must come from one line. An ellipsis (...) may join pieces of the
    same line, in order.
    """
    q = LEADING_LABEL_RE.sub("", str(quote or "")).strip().strip("\"'")
    pieces = [normalize(p) for p in ELLIPSIS_RE.split(q) if normalize(p)]
    if not pieces:
        return []
    hits = []
    for i, line in enumerate(lines):
        hay = normalize(line.text)
        pos = 0
        for piece in pieces:
            found = hay.find(piece.rstrip(".,!?;:"), pos)
            if found == -1:
                break
            pos = found + len(piece.rstrip(".,!?;:"))
        else:
            hits.append(i)
    return hits


def find_quote(quote: str, lines: list[callfile.TranscriptLine]) -> int | None:
    """Index of the first transcript line that contains the quote, or None."""
    hits = find_quote_all(quote, lines)
    return hits[0] if hits else None


# Validation

@dataclass
class Report:
    call_id: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    data: dict | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


class _Checker:
    def __init__(self, report: Report, cf: CallFile, duration: float):
        self.r = report
        self.cf = cf
        self.duration = duration

    def err(self, where: str, why: str) -> None:
        self.r.errors.append(f"{where}: {why}")

    def warn(self, where: str, why: str) -> None:
        self.r.warnings.append(f"{where}: {why}")

    def text(self, obj: dict, key: str, where: str) -> bool:
        value = obj.get(key)
        if not isinstance(value, str) or not value.strip():
            self.err(f"{where}.{key}", "must be a non-empty sentence")
            return False
        return True

    def seconds(self, value: Any, where: str, allow_null: bool = False) -> float | None:
        if value is None:
            if not allow_null:
                self.err(where, "is missing")
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self.err(where, f"must be a number of seconds, got {value!r}")
            return None
        if not 0 <= value <= self.duration + 1:
            self.err(where, f"{value} is outside the call (0 to {int(self.duration)} seconds)")
            return None
        return float(value)

    def timestamp(self, value: Any, where: str, allow_null: bool = False) -> float | None:
        if value is None or value == "":
            if not allow_null:
                self.err(where, "is missing. Use MM:SS, like 12:31")
            return None
        try:
            sec = parse_ts(value)
        except ValueError:
            self.err(where, f"'{value}' is not a timestamp. Use MM:SS, like 12:31")
            return None
        if sec > self.duration + 1:
            self.err(where, f"{value} is after the call ends ({fmt_ts(self.duration)})")
            return None
        return sec

    def quote(self, value: Any, where: str, required: bool, ts: float | None = None,
              speaker: str | None = None, speaker_required: bool = False) -> None:
        """Check a quote is in the transcript. speaker (REP or PROSPECT) says who should have said it."""
        if value is None or (isinstance(value, str) and not value.strip()):
            if required:
                self.err(where, "is empty. Scores of 2 to 5 need a word-for-word quote from the transcript")
            return
        if not isinstance(value, str):
            self.err(where, "must be text copied from the transcript")
            return
        hits = find_quote_all(value, self.cf.lines)
        if not hits:
            short = value if len(value) <= 80 else value[:77] + "..."
            self.err(where, f"quote not found in the transcript: \"{short}\". Copy it exactly from one line")
            return
        if speaker:
            right = [i for i in hits if self.cf.lines[i].role == speaker]
            if right:
                hits = right
            elif speaker_required:
                self.err(where, f"must be {speaker} words, but this quote is from a "
                                f"{self.cf.lines[hits[0]].role} line")
                return
            else:
                self.warn(where, f"usually quotes the {speaker}, but this is a {self.cf.lines[hits[0]].role} line")
        idx = hits[0]
        if ts is not None:
            line_start = self.cf.lines[idx].start
            nxt = self.cf.lines[idx + 1].start if idx + 1 < len(self.cf.lines) else self.duration
            if not (line_start - TIMESTAMP_SLACK_SEC <= ts <= nxt + TIMESTAMP_SLACK_SEC):
                self.warn(where, f"the quote is at [{fmt_ts(line_start)}] but the timestamp says {fmt_ts(ts)}")

    def scored(self, obj: Any, where: str, speaker: str | None = None) -> int | None:
        """A score block: score, timestamp, evidence_quote, why."""
        if not isinstance(obj, dict):
            self.err(where, "must be an object with score, timestamp, evidence_quote, and why")
            return None
        score = obj.get("score")
        if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 5:
            self.err(f"{where}.score", f"must be a whole number from 1 to 5, got {score!r}")
            return None
        needs_evidence = score >= 2
        ts = self.timestamp(obj.get("timestamp"), f"{where}.timestamp", allow_null=not needs_evidence)
        self.quote(obj.get("evidence_quote"), f"{where}.evidence_quote", needs_evidence, ts, speaker)
        self.text(obj, "why", where)
        return score


def load_call(paths: Paths, call_id: str) -> tuple[CallFile, float]:
    path = paths.calls / f"{call_id}.md"
    cf = callfile.read(path)
    duration = cf.meta.get("duration_sec")
    if not isinstance(duration, (int, float)) or duration <= 0:
        duration = max((ln.start for ln in cf.lines), default=0) + 60
    return cf, float(duration)


def validate_scorecard(path: Path, paths: Paths, rubric: list[RubricItem]) -> Report:
    call_id = path.stem
    report = Report(call_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        report.errors.append(f"file: not valid JSON (line {e.lineno}, column {e.colno}: {e.msg})")
        return report
    if not isinstance(data, dict):
        report.errors.append("file: must be one JSON object")
        return report
    report.data = data

    if not (paths.calls / f"{call_id}.md").exists():
        report.errors.append(f"file: there is no call file {paths.show(paths.calls / f'{call_id}.md')} "
                             "for this scorecard")
        return report
    cf, duration = load_call(paths, call_id)
    c = _Checker(report, cf, duration)

    for key in REQUIRED_KEYS:
        if key not in data:
            c.err(key, "is missing")
    if data.get("call_id") not in (None, call_id):
        c.err("call_id", f"says '{data.get('call_id')}' but the file is named {call_id}.json")

    # Rubric scores: every id exactly once, nothing unknown.
    wanted = [i.id for i in rubric]
    seen: dict[str, int] = {}
    scores = data.get("rubric_scores")
    if not isinstance(scores, list):
        if "rubric_scores" in data:
            c.err("rubric_scores", "must be a list")
        scores = []
    for n, item in enumerate(scores):
        rid = item.get("id") if isinstance(item, dict) else None
        where = f"rubric_scores[{rid or n}]"
        if rid not in wanted:
            c.err(where, f"'{rid}' is not an id in the rubric. Valid ids: {', '.join(wanted)}")
            continue
        seen[rid] = seen.get(rid, 0) + 1
        if seen[rid] > 1:
            c.err(where, "is scored more than once")
            continue
        c.scored(item, where)
    for rid in wanted:
        if rid not in seen:
            c.err(f"rubric_scores[{rid}]", "is missing. Every rubric behavior needs a score")

    for key in ("rapport", "tone_match"):
        if key in data:
            c.scored(data[key], key, speaker="REP")

    _check_price(c, data.get("price_handling"))
    _check_objections(c, data.get("objections"))

    if "first_pain_question_sec" in data:
        c.seconds(data["first_pain_question_sec"], "first_pain_question_sec", allow_null=True)

    misses = data.get("top_misses")
    if "top_misses" in data and (not isinstance(misses, list) or len(misses) != 3
                                 or not all(isinstance(m, str) and m.strip() for m in misses)):
        c.err("top_misses", "must be a list of exactly 3 non-empty sentences")

    rewrite = data.get("rewrite")
    if "rewrite" in data:
        if not isinstance(rewrite, dict):
            c.err("rewrite", "must be an object with timestamp, original_quote, and better_version")
        else:
            ts = c.timestamp(rewrite.get("timestamp"), "rewrite.timestamp")
            c.quote(rewrite.get("original_quote"), "rewrite.original_quote", True, ts,
                    speaker="REP", speaker_required=True)
            c.text(rewrite, "better_version", "rewrite")

    if "one_thing_to_change" in data and not (isinstance(data["one_thing_to_change"], str)
                                              and data["one_thing_to_change"].strip()):
        c.err("one_thing_to_change", "must be a non-empty sentence")
    return report


def _check_price(c: _Checker, price: Any) -> None:
    if price is None:
        return
    if not isinstance(price, dict):
        c.err("price_handling", "must be an object")
        return
    stated = price.get("price_stated")
    if not isinstance(stated, bool):
        c.err("price_handling.price_stated", "must be true or false")
        return
    if not stated:
        for key in PRICE_DETAIL_KEYS:
            if price.get(key) is not None:
                c.err(f"price_handling.{key}", "must be null when price_stated is false")
        c.quote(price.get("evidence_quote"), "price_handling.evidence_quote", False)
        return
    c.seconds(price.get("price_stated_end_sec"), "price_handling.price_stated_end_sec")
    for key in ("conceded_or_discounted", "prospect_objected"):
        if not isinstance(price.get(key), bool):
            c.err(f"price_handling.{key}", "must be true or false when price_stated is true")
    held = price.get("held_price")
    objected = price.get("prospect_objected")
    if objected is False:
        if held is not None:
            c.err("price_handling.held_price", "must be null when the prospect did not push back. "
                                               "Holding price only means something after pushback")
    elif not isinstance(held, bool):
        c.err("price_handling.held_price", "must be true or false when the prospect pushed back")
    if held is True and price.get("conceded_or_discounted") is True:
        c.err("price_handling.held_price", "cannot be true when conceded_or_discounted is true")
    c.quote(price.get("evidence_quote"), "price_handling.evidence_quote", True)
    c.text(price, "why", "price_handling")


def _check_objections(c: _Checker, objections: Any) -> None:
    if objections is None:
        return
    if not isinstance(objections, list):
        c.err("objections", "must be a list (use [] if there were none)")
        return
    for n, obj in enumerate(objections):
        where = f"objections[{n}]"
        if not isinstance(obj, dict):
            c.err(where, "must be an object")
            continue
        if not (isinstance(obj.get("type"), str) and obj["type"].strip()):
            c.err(f"{where}.type", "must name the objection, like price or timing")
        ts = c.timestamp(obj.get("timestamp"), f"{where}.timestamp")
        c.quote(obj.get("evidence_quote"), f"{where}.evidence_quote", True, ts, speaker="PROSPECT")
        if not isinstance(obj.get("handled"), bool):
            c.err(f"{where}.handled", "must be true or false")
        c.text(obj, "why", where)


def validate_all(paths: Paths, quiet: bool = False) -> list[Report]:
    rubric = parse_rubric(paths.rubric)
    files = sorted(paths.scorecards.glob("*.json")) if paths.scorecards.is_dir() else []
    reports = [validate_scorecard(p, paths, rubric) for p in files]
    if quiet:
        return reports

    heading(f"Validating {len(files)} scorecard(s) against {len(rubric)} rubric behaviors")
    for r in reports:
        if r.ok:
            ok(f"{r.call_id}" + (f" ({len(r.warnings)} warning(s))" if r.warnings else ""))
        else:
            print(f"  [FAIL]  {r.call_id}: {len(r.errors)} problem(s)")
            for e in r.errors:
                print(f"            - {e}")
        for w in r.warnings:
            print(f"            ~ {w}")
    scored = {r.call_id for r in reports}
    unscored = sorted(p.stem for p in paths.calls.glob("*.md") if p.stem not in scored) if paths.calls.is_dir() else []
    if unscored:
        note(f"{len(unscored)} call(s) have no scorecard yet: {', '.join(unscored[:5])}"
             + (" ..." if len(unscored) > 5 else "") + ". Run /coach-score in Claude Code.")
    bad = [r for r in reports if not r.ok]
    if bad:
        print(f"\n  {len(bad)} scorecard(s) failed. They are left out of results.csv until fixed.")
        print("  Fix: in Claude Code, ask it to re-score those calls using exact text from the transcript.")
    elif reports:
        print("\n  All scorecards passed. Every quote was found in its transcript.")
    return reports


# CSV inputs

def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read a user-edited CSV. Handles Excel's BOM and semicolon exports."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig")
    first = text.splitlines()[0] if text.strip() else ""
    delimiter = ";" if first.count(";") > first.count(",") else ","
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    rows = []
    for row in reader:
        clean = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        if any(clean.values()):
            rows.append(clean)
    return rows


def read_outcomes(paths: Paths, warn_bad: bool = True) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in read_csv_rows(paths.outcomes_csv):
        cid, outcome = row.get("call_id", ""), row.get("outcome", "").lower()
        if not cid:
            continue
        if outcome and outcome not in OUTCOME_VALUES:
            if warn_bad:
                note(f"outcomes.csv: '{row.get('outcome')}' for {cid} is not one of "
                     f"{', '.join(OUTCOME_VALUES)}. Treated as blank.")
            outcome = ""
        out[cid] = outcome
    return out


# Merge

def _flag(value: Any) -> str:
    if value is None:
        return ""
    return "1" if value else "0"


def results_columns(rubric: list[RubricItem]) -> list[str]:
    return (["call_id", "date", "prospect_initials", "stage", "outcome", "rubric_avg"]
            + [i.id for i in rubric]
            + ["rapport_score", "tone_match_score", "price_stated", "held_price", "conceded_or_discounted",
               "prospect_objected", "objections_count", "objections_unhandled_count", "first_pain_question_sec"])


def merge(paths: Paths, reports: list[Report]) -> list[dict[str, Any]]:
    """Valid scorecards plus outcomes to data/results.csv. Booleans are 1 (yes) or 0 (no)."""
    rubric = parse_rubric(paths.rubric)
    outcomes = read_outcomes(paths)
    rows = []
    for r in reports:
        if not r.ok or r.data is None:
            continue
        d = r.data
        meta = callfile.read(paths.calls / f"{r.call_id}.md").meta
        scores = {s["id"]: s["score"] for s in d["rubric_scores"]}
        price = d.get("price_handling") or {}
        objections = d.get("objections") or []
        row: dict[str, Any] = {
            "call_id": r.call_id,
            "date": meta.get("date", ""),
            "prospect_initials": meta.get("prospect_initials", ""),
            "stage": meta.get("stage", ""),
            "outcome": outcomes.get(r.call_id, ""),
            "rubric_avg": round(sum(scores.values()) / len(scores), 2),
        }
        row.update({i.id: scores[i.id] for i in rubric})
        row.update({
            "rapport_score": d["rapport"]["score"],
            "tone_match_score": d["tone_match"]["score"],
            "price_stated": _flag(price.get("price_stated")),
            "held_price": _flag(price.get("held_price")),
            "conceded_or_discounted": _flag(price.get("conceded_or_discounted")),
            "prospect_objected": _flag(price.get("prospect_objected")),
            "objections_count": len(objections),
            "objections_unhandled_count": sum(1 for o in objections if o.get("handled") is False),
            "first_pain_question_sec": d.get("first_pain_question_sec") if d.get("first_pain_question_sec") is not None else "",
        })
        rows.append(row)
    rows.sort(key=lambda x: (str(x["date"]), x["call_id"]))
    write_csv(paths.results_csv, results_columns(rubric), rows)
    return rows


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in columns})


# Locate: exact seconds for a quote, from code instead of guesswork

def locate(paths: Paths, call_id: str, quote: str) -> dict[str, Any]:
    raw_path = paths.raw / f"{call_id}.json"
    call_path = paths.calls / f"{call_id}.md"
    if not call_path.exists():
        raise CoachError(f"There is no call file for {call_id}.", "Check the call id. It is the file name without .md")
    cf = callfile.read(call_path)
    idx = find_quote(quote, cf.lines)
    if idx is None:
        raise CoachError("That quote is not in the transcript.", "Copy the words exactly from one line of the call file.")
    line = cf.lines[idx]
    result: dict[str, Any] = {"call_id": call_id, "line_timestamp": fmt_ts(line.start), "speaker": line.role,
                              "line_start_sec": line.start}
    utt = None
    raw = None
    if raw_path.exists():
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        utt = next((u for u in raw["utterances"] if abs(u["start"] - line.start) < 1 and
                    normalize(u["text"]) == normalize(line.text)), None)
    if utt is None:
        result.update({"quote_start_sec": line.start, "quote_end_sec": None, "method": "line start only (no raw file)"})
        return result

    hay = normalize(utt["text"])
    q = normalize(LEADING_LABEL_RE.sub("", quote).strip("\"' ")).rstrip(".,!?;:")
    first_piece = normalize(ELLIPSIS_RE.split(q)[0]).rstrip(".,!?;:")
    last_piece = normalize(ELLIPSIS_RE.split(q)[-1]).rstrip(".,!?;:")
    a = hay.find(first_piece)
    b = hay.find(last_piece, max(a, 0)) + len(last_piece)
    tokens = hay.split()
    words = [w for w in raw.get("words") or []
             if w["speaker"] == utt["speaker"] and utt["start"] - 0.01 <= w["start"] <= utt["end"] + 0.01]
    if words and len(words) == len(tokens):
        i = len(hay[:a].split())
        j = max(i, len(hay[:b].split()) - 1)
        result.update({"quote_start_sec": round(words[i]["start"], 2), "quote_end_sec": round(words[j]["end"], 2),
                       "method": "word timestamps"})
    else:
        span = utt["end"] - utt["start"]
        start = utt["start"] + span * a / max(len(hay), 1)
        # A quote that runs to the end of the line ends when the line ends.
        at_end = not hay[b:].strip(" .,!?;:\"'")
        end = utt["end"] if at_end else utt["start"] + span * b / max(len(hay), 1)
        result.update({
            "quote_start_sec": round(utt["start"] if a == 0 else start, 2),
            "quote_end_sec": round(end, 2),
            "method": ("line end (the quote runs to the end of the line)" if at_end else
                       "estimated from position in the line, because this call has no word timestamps"),
        })
    return result
