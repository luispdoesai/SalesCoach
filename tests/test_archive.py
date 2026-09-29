"""Archiving older calls into their own period, and restoring them."""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest

from coach import analyze, archive
from coach.config import Paths
from coach.friendly import CoachError
from coach.scorecards import read_csv_rows

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo"
OLD = ["2026-07-14_MO_Discovery", "2026-07-21_DC_Demo", "2026-07-28_PL_Demo",
       "2026-08-04_TA_Discovery", "2026-08-11_HM_Proposal", "2026-08-14_RI_Demo"]


@pytest.fixture
def ws(tmp_path) -> Paths:
    for sub in ("raw", "calls", "scorecards"):
        shutil.copytree(DEMO / sub, tmp_path / "data" / sub)
    for name in ("outcomes.csv", "contacts.csv", "rubric.md"):
        shutil.copyfile(DEMO / name, tmp_path / "data" / name)
    paths = Paths(root=tmp_path, data=tmp_path / "data", rubric=tmp_path / "data" / "rubric.md")
    for f in paths.folders():
        f.mkdir(parents=True, exist_ok=True)
    (paths.processed / f"{OLD[0]}.m4a").write_bytes(b"audio")
    (paths.processed / f"{OLD[0]}_1.m4a").write_bytes(b"audio 2")
    (paths.emails / f"{OLD[1]}.txt").write_text("email thread")
    analyze.run_analyze(paths)
    return paths


def _ids(csv_path: Path) -> set[str]:
    return {r["call_id"] for r in read_csv_rows(csv_path)}


def test_preview_moves_nothing_without_yes(ws, capsys):
    assert archive.run_archive(ws, before="2026-08-15") == 0
    out = capsys.readouterr().out
    assert "Nothing was moved" in out and all(cid in out for cid in OLD)
    assert len(list(ws.calls.glob("*.md"))) == 14


def test_archive_moves_everything_for_those_calls(ws):
    archive.run_archive(ws, before="2026-08-15", name="2026-July", yes=True)
    dst = archive.archive_paths(ws, "2026-July")
    assert sorted(p.stem for p in dst.calls.glob("*.md")) == OLD
    assert sorted(p.stem for p in dst.scorecards.glob("*.json")) == OLD
    assert sorted(p.stem for p in dst.raw.glob("*.json")) == OLD
    assert (dst.processed / f"{OLD[0]}.m4a").exists() and (dst.processed / f"{OLD[0]}_1.m4a").exists()
    assert (dst.emails / f"{OLD[1]}.txt").exists()
    assert dst.rubric.read_text() == ws.rubric.read_text()
    assert _ids(dst.outcomes_csv) == set(OLD) and _ids(dst.contacts_csv) == set(OLD)
    assert not _ids(ws.outcomes_csv) & set(OLD) and len(_ids(ws.outcomes_csv)) == 8


def test_current_numbers_exclude_archived_calls(ws):
    archive.run_archive(ws, before="2026-08-15", name="2026-July", yes=True)
    assert len(read_csv_rows(ws.stats_csv)) == 8 and not _ids(ws.stats_csv) & set(OLD)
    note = (ws.reports / "sample_size_note.txt").read_text()
    assert note.startswith("Sample: 8 calls.")
    dst = archive.archive_paths(ws, "2026-July")
    assert (dst.reports / "sample_size_note.txt").read_text().startswith("Sample: 6 calls.")


def test_dashboards_say_which_calls_they_show(ws):
    archive.run_archive(ws, before="2026-08-15", name="2026-July", yes=True)
    current = (ws.reports / "dashboard.html").read_text()
    assert "8 current calls" in current and "2026-08-18" in current
    assert 'href="../archive/2026-July/reports/dashboard.html"' in current
    old = (archive.archive_paths(ws, "2026-July").reports / "dashboard.html").read_text()
    assert "Archived calls: 2026-July" in old and "Archived period" in old
    assert 'href="../../../reports/dashboard.html"' in old
    assert "say: use data/archive/2026-July" in old


def test_archive_specific_calls(ws):
    archive.run_archive(ws, calls=f"{OLD[2]}, {OLD[4]}", name="picked", yes=True)
    assert sorted(p.stem for p in archive.archive_paths(ws, "picked").calls.glob("*.md")) == [OLD[2], OLD[4]]


@pytest.mark.parametrize("kwargs,words", [
    ({}, "Say which calls"),
    ({"before": "Sept 1"}, "not a date"),
    ({"calls": "2026-01-01_ZZ_Demo"}, "No current call"),
    ({"before": "2026-08-15", "name": "../escape"}, "cannot be used as a folder name"),
])
def test_bad_requests_are_friendly(ws, kwargs, words):
    with pytest.raises(CoachError) as err:
        archive.run_archive(ws, yes=True, **kwargs)
    assert words in err.value.problem


def test_different_rubric_needs_a_new_archive(ws):
    archive.run_archive(ws, calls=OLD[0], name="old", yes=True)
    ws.rubric.write_text(ws.rubric.read_text() + "\n### extra_behavior: Extra\n1: a\n3: b\n5: c\n")
    with pytest.raises(CoachError) as err:
        archive.run_archive(ws, calls=OLD[1], name="old", yes=True)
    assert "different rubric" in err.value.problem


def test_restore_brings_everything_back(ws):
    before_outcomes = ws.outcomes_csv.read_text().splitlines()
    archive.run_archive(ws, before="2026-08-15", name="2026-July", yes=True)
    archive.run_restore(ws, "2026-July", yes=True)
    assert len(list(ws.calls.glob("*.md"))) == 14 and (ws.processed / f"{OLD[0]}_1.m4a").exists()
    assert sorted(ws.outcomes_csv.read_text().splitlines()[1:]) == sorted(before_outcomes[1:])
    assert not archive.archive_paths(ws, "2026-July").data.exists()  # empty archive removed
    assert len(read_csv_rows(ws.stats_csv)) == 14


def test_restore_keeps_an_archive_holding_the_only_copy_of_an_old_rubric(ws):
    archive.run_archive(ws, calls=OLD[0], name="old", yes=True)
    ws.rubric.write_text(ws.rubric.read_text() + "\n### extra_behavior: Extra\n1: a\n3: b\n5: c\n")
    archive.run_restore(ws, "old", yes=True)
    assert archive.archive_paths(ws, "old").rubric.exists()


def test_restore_skips_calls_that_exist_again(ws, capsys):
    archive.run_archive(ws, calls=OLD[0], name="old", yes=True)
    shutil.copyfile(archive.archive_paths(ws, "old").calls / f"{OLD[0]}.md", ws.calls / f"{OLD[0]}.md")
    archive.run_restore(ws, "old", yes=True)
    assert "will stay archived" in capsys.readouterr().out
    assert (archive.archive_paths(ws, "old").calls / f"{OLD[0]}.md").exists()


def test_restore_unknown_name(ws):
    with pytest.raises(CoachError, match="no archive"):
        archive.run_restore(ws, "nope", yes=True)


def test_semicolon_csv_keeps_its_format(ws):
    rows = list(csv.reader(ws.outcomes_csv.read_text().splitlines()))
    ws.outcomes_csv.write_text("\n".join(";".join(r) for r in rows) + "\n")
    archive.run_archive(ws, calls=OLD[0], name="old", yes=True)
    assert ws.outcomes_csv.read_text().splitlines()[0] == "call_id;outcome;deal_value;notes"
    assert archive.archive_paths(ws, "old").outcomes_csv.read_text().startswith("call_id;outcome")


def test_cannot_archive_from_inside_an_archive(ws):
    archive.run_archive(ws, calls=OLD[0], name="old", yes=True)
    with pytest.raises(CoachError, match="already an archive"):
        archive.run_archive(archive.archive_paths(ws, "old"), before="2027-01-01", yes=True)


# When to archive

def test_no_suggestion_for_a_recent_consistent_set(ws):
    assert archive.suggestions(ws, after_days=90) == []  # demo spans about 70 days, one rubric


def test_suggests_archiving_old_calls_with_a_clean_date(ws):
    tips = archive.suggestions(ws, after_days=30)
    assert len(tips) == 1
    why, what = tips[0]
    assert "from before 2026-09-01" in why and "more than 30 days" in why
    assert what.endswith("python coach.py archive --before 2026-09-01")


def test_suggestion_turned_off(ws):
    assert archive.suggestions(ws, after_days=0) == []


def test_suggests_when_the_rubric_changed(ws):
    ws.rubric.write_text(ws.rubric.read_text() + "\n### extra_behavior: Extra\n1: a\n3: b\n5: c\n")
    tips = archive.suggestions(ws, after_days=0)
    assert len(tips) == 1 and "older version of your rubric" in tips[0][0]
    assert "/coach-score" in tips[0][1] and "archive --calls 2026-07-14_MO_Discovery," in tips[0][1]


def test_suggestion_shows_on_dashboard_and_after_analyze(ws, capsys, monkeypatch):
    monkeypatch.setattr("coach.config.suggest_after_days", lambda: 30)
    capsys.readouterr()
    analyze.run_analyze(ws)
    assert "Suggested: keep old calls apart" in capsys.readouterr().out
    html = (ws.reports / "dashboard.html").read_text()
    assert "Suggested" in html and "archive --before 2026-09-01" in html


def test_no_suggestions_inside_an_archive(ws):
    archive.run_archive(ws, before="2026-08-15", name="old", yes=True)
    assert archive.suggestions(archive.archive_paths(ws, "old"), after_days=1) == []


def test_list(ws, capsys):
    archive.run_archive(ws, before="2026-08-15", name="2026-July", yes=True)
    capsys.readouterr()
    archive.run_archive(ws, list_only=True)
    out = capsys.readouterr().out
    assert "8 call(s), 2026-08-18 to 2026-09-22" in out and "2026-July" in out and "2026-07-14 to 2026-08-14" in out
