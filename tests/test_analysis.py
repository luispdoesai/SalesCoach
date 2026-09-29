"""Phase 3: rubric, quotes, scorecard validation, stats, compare, demo."""

from __future__ import annotations

import copy
import csv
import json
import shutil
from pathlib import Path

import pytest

from coach import analyze, callfile, compare, scorecards, stats
from coach.config import Paths
from coach.friendly import CoachError
from coach.scorecards import find_quote, normalize, parse_rubric, validate_scorecard

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "examples" / "demo"


# Rubric parsing

def test_example_rubric_parses():
    items = parse_rubric(REPO / "rubric" / "rubric.example.md")
    assert len(items) == 10
    assert items[8].id == "price_handling" and set(items[8].levels) == {"1", "3", "5"}


def test_rubric_errors(tmp_path):
    p = tmp_path / "rubric.md"
    p.write_text("### Price Handling: x\n1: a\n")
    with pytest.raises(CoachError, match="lowercase"):
        parse_rubric(p)
    p.write_text("### a: x\n### a: y\n")
    with pytest.raises(CoachError, match="twice"):
        parse_rubric(p)
    p.write_text("# nothing here\n")
    with pytest.raises(CoachError, match="no behaviors"):
        parse_rubric(p)
    with pytest.raises(CoachError, match="does not exist"):
        parse_rubric(tmp_path / "missing.md")


def test_starter_marker_is_ignored(tmp_path):
    p = tmp_path / "rubric.md"
    p.write_text("<!-- STARTER RUBRIC: x -->\n\n" + (REPO / "rubric" / "rubric.example.md").read_text())
    assert len(parse_rubric(p)) == 10


# Quote verification

LINES = [callfile.TranscriptLine(0, "REP", "Hi Jordan, this is Sam from Vantrellis. Is it okay if I record?"),
         callfile.TranscriptLine(10, "PROSPECT", "Honestly it’s a big spreadsheet , and it takes   forever.")]


@pytest.mark.parametrize("quote,expected", [
    ("this is Sam from Vantrellis", 0),                               # exact
    ("THIS IS SAM FROM VANTRELLIS.", 0),                              # case
    ("this  is\nSam   from Vantrellis", 0),                           # whitespace
    ("honestly it's a big spreadsheet, and it takes forever", 1),     # curly quote and punctuation spacing
    ('"Is it okay if I record?"', 0),                                 # wrapped in quotation marks
    ("[00:10] PROSPECT: Honestly it's a big spreadsheet", 1),         # label copied along
    ("Hi Jordan ... Is it okay if I record?", 0),                     # ellipsis joins pieces of one line
])
def test_quote_found(quote, expected):
    assert find_quote(quote, LINES) == expected


@pytest.mark.parametrize("quote", [
    "this is Sam from Acme",                                          # changed word
    "it's a huge spreadsheet",                                        # paraphrase
    "Is it okay if I record? Honestly it's a big spreadsheet",        # spans two speakers
    "Is it okay ... Hi Jordan",                                       # pieces out of order
    "",
])
def test_quote_not_found(quote):
    assert find_quote(quote, LINES) is None


def test_normalize():
    assert normalize("  Hello ,World!  ") == "hello, world!"


# Scorecard validation, using a demo call as the base

@pytest.fixture
def demo_paths(tmp_path) -> Paths:
    for sub in ("raw", "calls", "scorecards"):
        shutil.copytree(DEMO / sub, tmp_path / "data" / sub)
    for name in ("outcomes.csv", "contacts.csv", "rubric.md"):
        shutil.copyfile(DEMO / name, tmp_path / "data" / name)
    return Paths(root=tmp_path, data=tmp_path / "data", rubric=tmp_path / "data" / "rubric.md")


CALL = "2026-08-11_HM_Proposal"


def _card(paths: Paths) -> dict:
    return json.loads((paths.scorecards / f"{CALL}.json").read_text())


def _check(paths: Paths, card: dict) -> scorecards.Report:
    p = paths.scorecards / f"{CALL}.json"
    p.write_text(json.dumps(card))
    return validate_scorecard(p, paths, parse_rubric(paths.rubric))


def _scored(card, minimum=2):
    return next(s for s in card["rubric_scores"] if s["score"] >= minimum)


def test_demo_scorecards_all_pass(demo_paths):
    reports = scorecards.validate_all(demo_paths, quiet=True)
    assert len(reports) == 14 and all(r.ok for r in reports), [r.errors for r in reports if not r.ok]


def test_missing_id(demo_paths):
    card = _card(demo_paths)
    card["rubric_scores"] = [s for s in card["rubric_scores"] if s["id"] != "next_steps"]
    r = _check(demo_paths, card)
    assert "rubric_scores[next_steps]: is missing. Every rubric behavior needs a score" in r.errors


def test_unknown_and_duplicate_id(demo_paths):
    card = _card(demo_paths)
    card["rubric_scores"].append({**card["rubric_scores"][0]})
    card["rubric_scores"].append({**card["rubric_scores"][0], "id": "charisma"})
    errors = " | ".join(_check(demo_paths, card).errors)
    assert "is scored more than once" in errors and "'charisma' is not an id" in errors


@pytest.mark.parametrize("bad", [0, 6, 3.5, "4", True, None])
def test_bad_score(demo_paths, bad):
    card = _card(demo_paths)
    card["rubric_scores"][0]["score"] = bad
    r = _check(demo_paths, card)
    assert any("must be a whole number from 1 to 5" in e for e in r.errors)


def test_missing_quote_for_score_of_two_or_more(demo_paths):
    card = _card(demo_paths)
    item = _scored(card)
    item["evidence_quote"] = ""
    r = _check(demo_paths, card)
    assert f"rubric_scores[{item['id']}].evidence_quote: is empty. Scores of 2 to 5 need a word-for-word quote from the transcript" in r.errors


def test_score_of_one_may_have_no_quote_but_needs_why(demo_paths):
    card = _card(demo_paths)
    card["rubric_scores"][0].update(score=1, evidence_quote=None, timestamp=None)
    assert _check(demo_paths, card).ok
    card["rubric_scores"][0]["why"] = ""
    assert not _check(demo_paths, card).ok


def test_paraphrased_quote_rejected(demo_paths):
    card = _card(demo_paths)
    item = _scored(card)
    item["evidence_quote"] = item["evidence_quote"].replace(" ", " really ", 1)
    r = _check(demo_paths, card)
    assert any("quote not found in the transcript" in e for e in r.errors)


def test_timestamp_out_of_range(demo_paths):
    card = _card(demo_paths)
    _scored(card)["timestamp"] = "59:00"
    card["rewrite"]["timestamp"] = "banana"
    errors = " | ".join(_check(demo_paths, card).errors)
    assert "is after the call ends" in errors and "'banana' is not a timestamp" in errors


def test_far_timestamp_is_a_warning(demo_paths):
    card = _card(demo_paths)
    item = next(s for s in card["rubric_scores"] if s["score"] >= 2 and callfile.parse_ts(s["timestamp"]) > 120)
    item["timestamp"] = "00:00"
    r = _check(demo_paths, card)
    assert r.ok and any("the quote is at" in w for w in r.warnings)


def test_price_rules(demo_paths):
    card = _card(demo_paths)
    base = copy.deepcopy(card)
    card["price_handling"].update(held_price=True, conceded_or_discounted=True)
    assert any("cannot be true when conceded" in e for e in _check(demo_paths, card).errors)
    card = copy.deepcopy(base)
    card["price_handling"].update(price_stated=False)
    assert any("must be null when price_stated is false" in e for e in _check(demo_paths, card).errors)
    card = copy.deepcopy(base)
    card["price_handling"].update(prospect_objected=False, held_price=True)
    assert any("must be null when the prospect did not push back" in e for e in _check(demo_paths, card).errors)
    card = copy.deepcopy(base)
    card["price_handling"]["price_stated_end_sec"] = 99999
    assert any("outside the call" in e for e in _check(demo_paths, card).errors)


def test_objection_and_rewrite_quotes_verified(demo_paths):
    card = _card(demo_paths)
    card["objections"][0]["evidence_quote"] = "This was never said."
    card["rewrite"]["original_quote"] = "Neither was this."
    errors = " | ".join(_check(demo_paths, card).errors)
    assert "objections[0].evidence_quote: quote not found" in errors
    assert "rewrite.original_quote: quote not found" in errors


def test_bad_json_and_wrong_call(demo_paths):
    good = _card(demo_paths)
    p = demo_paths.scorecards / f"{CALL}.json"
    p.write_text("{ not json")
    r = validate_scorecard(p, demo_paths, parse_rubric(demo_paths.rubric))
    assert r.errors[0].startswith("file: not valid JSON (line 1")
    orphan = demo_paths.scorecards / "2026-01-01_ZZ_Demo.json"
    orphan.write_text(json.dumps(good))
    r = validate_scorecard(orphan, demo_paths, parse_rubric(demo_paths.rubric))
    assert "no call file" in r.errors[0]


def test_misses_must_be_three(demo_paths):
    card = _card(demo_paths)
    card["top_misses"] = card["top_misses"][:2]
    assert any(e.startswith("top_misses") for e in _check(demo_paths, card).errors)


def test_validator_never_edits_scorecards(demo_paths):
    before = {p.name: p.read_bytes() for p in demo_paths.scorecards.glob("*.json")}
    scorecards.validate_all(demo_paths)
    assert before == {p.name: p.read_bytes() for p in demo_paths.scorecards.glob("*.json")}


# Merge

def test_merge_skips_failed_and_joins_outcomes(demo_paths):
    card = _card(demo_paths)
    _scored(card)["evidence_quote"] = "made up"
    (demo_paths.scorecards / f"{CALL}.json").write_text(json.dumps(card))
    reports = scorecards.validate_all(demo_paths, quiet=True)
    rows = scorecards.merge(demo_paths, reports)
    assert len(rows) == 13 and CALL not in {r["call_id"] for r in rows}
    with demo_paths.results_csv.open() as fh:
        header = next(csv.reader(fh))
    assert header[:6] == ["call_id", "date", "prospect_initials", "stage", "outcome", "rubric_avg"]
    assert header[-1] == "first_pain_question_sec" and "price_handling" in header
    won = next(r for r in rows if r["call_id"] == "2026-08-25_KV_Proposal")
    assert won["outcome"] == "won" and won["price_stated"] in ("0", "1")


def test_outcomes_csv_tolerates_excel(tmp_path):
    paths = Paths(root=tmp_path, data=tmp_path, rubric=tmp_path / "r.md")
    paths.outcomes_csv.write_text("﻿call_id;outcome;deal_value;notes\nA;Won;;\nB; LOST ;;\nC;maybe;;\n")
    assert scorecards.read_outcomes(paths, warn_bad=False) == {"A": "won", "B": "lost", "C": ""}


# Stats with hand-computed answers

def _u(role, start, end, text, spk=None):
    return {"speaker": spk or ("spk_1" if role == "REP" else "spk_2"), "role": role, "start": start, "end": end, "text": text}


STATS_RAW = {
    "call_id": "x", "duration_sec": 100,
    "speaker_mapping": {"spk_1": "REP", "spk_2": "PROSPECT"},
    "utterances": [
        _u("REP", 0, 10, "Hi there. How are you? Good?"),       # 10s rep, 2 questions
        _u("PROSPECT", 11, 21, "Fine. What does it cost?"),     # 10s prospect; its ? does not count
        _u("REP", 22, 30, "It's ten thousand a year."),         # 8s rep, price ends at 30
        _u("PROSPECT", 34, 44, "Hmm, that's a lot."),           # 10s, starts 4s after price
        _u("REP", 45, 55, "What were you expecting?"),          # run: 45 to 70
        _u("REP", 56, 70, "Most teams see value fast.", spk="spk_3"),
    ],
    "words": [],
}


def test_stats_known_answers():
    row = stats.call_stats(STATS_RAW, price_end=30)
    # rep time 10+8+10+14 = 42, prospect 20, total 62
    assert row["rep_talk_pct"] == round(100 * 42 / 62, 1) == 67.7
    assert row["prospect_talk_pct"] == 32.3
    assert row["rep_questions"] == 3
    assert row["longest_rep_monologue_sec"] == 25.0
    assert row["price_silence_sec"] == 4.0 and row["price_next_speaker"] == "PROSPECT"


def test_price_silence_zero_when_rep_keeps_talking():
    assert stats.price_silence(STATS_RAW, 50) == (0.0, "REP")


def test_price_silence_uses_words_when_present():
    raw = {**STATS_RAW, "words": [
        {"speaker": "spk_1", "start": 29.5, "end": 30.0, "text": "year."},
        {"speaker": "spk_2", "start": 36.25, "end": 36.5, "text": "Hmm"},
    ]}
    assert stats.price_silence(raw, 30.0) == (6.2, "PROSPECT")


def test_price_silence_blank_without_price():
    row = stats.call_stats(STATS_RAW, price_end=None)
    assert row["price_silence_sec"] is None and row["price_next_speaker"] == ""


def test_stats_with_no_speech():
    assert stats.talk_split([]) == (None, None)


# Compare

def _rows(won: int, lost: int):
    return ([{"call_id": f"w{i}", "outcome": "won", "m": 10.0} for i in range(won)]
            + [{"call_id": f"l{i}", "outcome": "lost", "m": 4.0} for i in range(lost)])


def test_compare_table_math():
    table = compare.compare_table(["m"], _rows(3, 2) + [{"call_id": "s", "outcome": "stalled", "m": None}])
    assert table == [{"metric": "m", "won_mean": 10.0, "won_n": 3, "lost_mean": 4.0, "lost_n": 2,
                      "stalled_mean": None, "stalled_n": 0, "diff_won_minus_lost": 6.0}]


def test_sample_note_under_five():
    note = " ".join(compare.sample_note(_rows(4, 6)))
    assert "not meaningful yet" in note and "directional hint" in note and "correlation, not cause" in note


def test_sample_note_no_losses():
    note = " ".join(compare.sample_note(_rows(6, 0)))
    assert "No lost calls yet" in note and "impossible" in note


def test_sample_note_big_enough():
    note = " ".join(compare.sample_note(_rows(20, 15)))
    assert "not meaningful" not in note and "directional" not in note and "correlation, not cause" in note


# End to end and idempotency

def test_analyze_twice_gives_identical_outputs(demo_paths, capsys):
    assert analyze.run_analyze(demo_paths) == 0
    files = [demo_paths.results_csv, demo_paths.stats_csv, demo_paths.reports / "compare.csv",
             demo_paths.reports / "sample_size_note.txt"]
    first = [f.read_bytes() for f in files]
    assert analyze.run_analyze(demo_paths) == 0
    assert first == [f.read_bytes() for f in files]
    assert len(list(demo_paths.charts.glob("*.png"))) == 4


def test_demo_command(tmp_path, capsys):
    assert analyze.run_demo(root=tmp_path) == 0
    out = capsys.readouterr().out
    assert "Won vs. lost" in out and "Sample-size note" in out and "correlation, not cause" in out
    assert len(list((tmp_path / "data" / "demo" / "reports" / "charts").glob("*.png"))) == 4
    assert analyze.run_demo(root=tmp_path) == 0  # re-runnable


def test_rewrite_must_quote_the_rep(demo_paths):
    card = _card(demo_paths)
    cf = callfile.read(demo_paths.calls / f"{CALL}.md")
    prospect = next(ln for ln in cf.lines if ln.role == "PROSPECT" and len(ln.text) > 30)
    card["rewrite"].update(original_quote=prospect.text, timestamp=callfile.fmt_ts(prospect.start))
    assert any("must be REP words" in e for e in _check(demo_paths, card).errors)


def test_objection_quoting_the_rep_is_a_warning(demo_paths):
    card = _card(demo_paths)
    rep = next(ln for ln in callfile.read(demo_paths.calls / f"{CALL}.md").lines if ln.role == "REP")
    card["objections"][0].update(evidence_quote=rep.text, timestamp=callfile.fmt_ts(rep.start))
    r = _check(demo_paths, card)
    assert r.ok and any("usually quotes the PROSPECT" in w for w in r.warnings)


def test_locate_line_end_without_word_timestamps(demo_paths):
    raw = json.loads((demo_paths.raw / "2026-08-25_KV_Proposal.json").read_text())
    assert raw["words"] == []
    utt = next(u for u in raw["utterances"] if "dollars a year" in u["text"])
    loc = scorecards.locate(demo_paths, "2026-08-25_KV_Proposal", utt["text"])
    assert loc["quote_end_sec"] == utt["end"]
    # And stats reads that end as silence, not as the rep still talking.
    silence, who = stats.price_silence(raw, loc["quote_end_sec"])
    assert silence > 3 and who == "PROSPECT"


def test_data_dir_typo_gets_a_useful_fix(tmp_path, monkeypatch):
    monkeypatch.setenv("COACH_DATA_DIR", "data/nope")
    paths = Paths(root=tmp_path, data=tmp_path / "data" / "nope", rubric=tmp_path / "r.md")
    with pytest.raises(CoachError) as err:
        analyze.run_validate(paths)
    assert "--data-dir" in err.value.fix


def test_index_builds_sqlite(demo_paths, capsys):
    import sqlite3

    from coach.index import run_index

    with pytest.raises(CoachError) as err:
        run_index(demo_paths)
    assert "analyze" in err.value.fix
    analyze.run_analyze(demo_paths)
    assert run_index(demo_paths) == 0
    assert run_index(demo_paths) == 0  # rebuilds cleanly
    with sqlite3.connect(demo_paths.data / "coach.db") as conn:
        by_outcome = dict(conn.execute("SELECT outcome, COUNT(*) FROM calls GROUP BY outcome").fetchall())
        talk = conn.execute("SELECT ROUND(AVG(rep_talk_pct), 2) FROM calls WHERE outcome = 'won'").fetchone()[0]
    assert by_outcome == {"won": 6, "lost": 5, "stalled": 2, "open": 1}
    compare_rows = scorecards.read_csv_rows(demo_paths.reports / "compare.csv")
    assert talk == float(next(r for r in compare_rows if r["metric"] == "rep_talk_pct")["won_mean"])


def test_locate(demo_paths):
    card = _card(demo_paths)
    quote = card["price_handling"]["evidence_quote"]
    loc = scorecards.locate(demo_paths, CALL, quote)
    raw = json.loads((demo_paths.raw / f"{CALL}.json").read_text())
    utt = next(u for u in raw["utterances"] if quote.lower().rstrip(".") in u["text"].lower())
    assert utt["start"] <= loc["quote_start_sec"] < loc["quote_end_sec"] <= utt["end"] + 0.01
    with pytest.raises(CoachError):
        scorecards.locate(demo_paths, CALL, "never said this")
