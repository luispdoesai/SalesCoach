"""The HTML dashboard."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from coach import analyze, dashboard
from coach.config import Paths
from coach.friendly import CoachError

DEMO = Path(__file__).resolve().parent.parent / "examples" / "demo"


@pytest.fixture
def demo_paths(tmp_path) -> Paths:
    for sub in ("raw", "calls", "scorecards"):
        shutil.copytree(DEMO / sub, tmp_path / "data" / sub)
    for name in ("outcomes.csv", "contacts.csv", "rubric.md"):
        shutil.copyfile(DEMO / name, tmp_path / "data" / name)
    return Paths(root=tmp_path, data=tmp_path / "data", rubric=tmp_path / "data" / "rubric.md")


def test_analyze_builds_dashboard_with_every_call(demo_paths):
    analyze.run_analyze(demo_paths)
    html = (demo_paths.reports / "dashboard.html").read_text()
    for card in demo_paths.scorecards.glob("*.json"):
        assert card.stem in html
    assert html.startswith("<!doctype html>") and "<title>AI Sales Coach Dashboard</title>" in html
    assert "Directional hints only" in html


def test_dashboard_is_offline_and_self_contained(demo_paths):
    analyze.run_analyze(demo_paths)
    html = (demo_paths.reports / "dashboard.html").read_text()
    assert not re.search(r'(src|href)="https?://', html)
    assert "@import" not in html


def test_numbers_come_from_compare_csv(demo_paths):
    analyze.run_analyze(demo_paths)
    html = (demo_paths.reports / "dashboard.html").read_text()
    from coach.scorecards import read_csv_rows

    talk = next(r for r in read_csv_rows(demo_paths.reports / "compare.csv") if r["metric"] == "rep_talk_pct")
    assert f"{float(talk['won_mean']):.1f}%" in html and f"{float(talk['lost_mean']):.1f}%" in html


def test_text_is_escaped(demo_paths):
    card_path = next(demo_paths.scorecards.glob("*.json"))
    card = json.loads(card_path.read_text())
    card["one_thing_to_change"] = "<script>alert(1)</script> Ask more questions."
    card_path.write_text(json.dumps(card))
    analyze.run_analyze(demo_paths)
    html = (demo_paths.reports / "dashboard.html").read_text()
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;alert(1)" in html


def test_before_analyze_it_still_shows_next_steps(demo_paths):
    html = dashboard.build(demo_paths)
    assert "Start here" in html and "Charts appear here after" in html
    assert "call-2026-08-11_HM_Proposal" in html  # call cards work without the CSVs


def test_brand_new_workspace(tmp_path):
    paths = Paths(root=tmp_path, data=tmp_path / "data", rubric=tmp_path / "r.md")
    with pytest.raises(CoachError):
        dashboard.build(paths)
    (tmp_path / "data" / "inbox").mkdir(parents=True)
    (tmp_path / "data" / "inbox" / "2026-09-28_JD_Discovery.m4a").write_bytes(b"x")
    html = dashboard.build(paths)
    assert "1 recording waiting to be transcribed" in html


def test_call_cards_show_the_evidence(demo_paths):
    analyze.run_analyze(demo_paths)
    html = (demo_paths.reports / "dashboard.html").read_text()
    card = json.loads((demo_paths.scorecards / "2026-08-11_HM_Proposal.json").read_text())
    from html import escape
    assert escape(card["one_thing_to_change"]) in html
    assert escape(card["rewrite"]["better_version"]) in html
    quote = next(s["evidence_quote"] for s in card["rubric_scores"] if s["evidence_quote"])
    assert escape(quote) in html
    assert "Read the transcript" in html and "Quoted for:" in html
    assert "Scores, with the words that earned them" in html


def test_status_lists_whats_missing(demo_paths):
    (demo_paths.scorecards / "2026-08-11_HM_Proposal.json").unlink()
    rows = demo_paths.outcomes_csv.read_text().splitlines()
    demo_paths.outcomes_csv.write_text("\n".join(r for r in rows if "2026-09-22_ES" not in r) + "\n")
    analyze.run_analyze(demo_paths)
    html = (demo_paths.reports / "dashboard.html").read_text()
    assert "1 call not scored yet: 2026-08-11_HM_Proposal" in html
    assert "1 call with no outcome: 2026-09-22_ES_Discovery" in html
    assert "Your findings are not written yet" in html


def test_findings_markdown_is_rendered(demo_paths):
    analyze.run_analyze(demo_paths)
    (demo_paths.reports / "Findings.md").write_text(
        "# Findings\n\n## 1. Summary\n- **Talk less.** Won calls: `59.87`\n\n| Metric | Won |\n|---|---|\n| talk | 59.87 |\n\n"
        "<img src=x onerror=alert(1)>\n")
    html = dashboard.build(demo_paths)
    assert "<h3>1. Summary</h3>" in html and "<b>Talk less.</b>" in html and "<td>59.87</td>" in html
    assert "<img src=x" not in html and "&lt;img src=x" in html


def test_shortcut_points_at_dashboard_and_holds_no_data():
    shortcut = (Path(__file__).resolve().parent.parent / "Open-Dashboard.html").read_text()
    assert 'url=data/reports/dashboard.html' in shortcut
    assert "2026-" not in shortcut and "REP:" not in shortcut


def test_markdown_renderer_shapes():
    from coach.report import render_markdown
    out = render_markdown("1. one\n2. two\n\n> quoted\n\n```\ncode <b>\n```\n\nplain *em* text")
    assert "<ol><li>one</li><li>two</li></ol>" in out and "<blockquote>quoted</blockquote>" in out
    assert "<pre>code &lt;b&gt;</pre>" in out and "<i>em</i>" in out


def test_works_without_outcomes_or_rubric(demo_paths):
    demo_paths.outcomes_csv.write_text("call_id,outcome,deal_value,notes\n")
    analyze.run_analyze(demo_paths)
    demo_paths.rubric.unlink()
    html = dashboard.build(demo_paths)
    assert "Comparison not possible yet" in html and "No outcome yet" in html
    assert "value_linking" in html  # rubric ids recovered from results.csv


@pytest.mark.parametrize("lo,hi", [(0, 4.5), (0, 77.1), (0, 10), (0, 0.2), (3, 3)])
def test_ticks_cover_the_data(lo, hi):
    ticks = dashboard._nice_ticks(lo, hi)
    assert ticks[0] <= lo and ticks[-1] >= hi and len(ticks) <= 8


def test_fragment_mode_for_embedding(demo_paths):
    analyze.run_analyze(demo_paths)
    frag = dashboard.build(demo_paths, fragment=True)
    assert frag.startswith("<title>") and "<html" not in frag and "<body" not in frag
