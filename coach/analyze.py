"""validate, merge, stats, compare, analyze, demo, and locate commands."""

from __future__ import annotations

import json
import shutil

from coach import compare, scorecards, stats
from coach.config import REPO_ROOT, Paths, missing_data_fix
from coach.friendly import CoachError, heading, note

DEMO_SRC = REPO_ROOT / "examples" / "demo"


def _need_data(paths: Paths) -> None:
    if not paths.data.is_dir():
        raise CoachError(f"The {paths.show(paths.data)}/ folder does not exist yet.", missing_data_fix())


def run_validate(paths: Paths) -> int:
    _need_data(paths)
    reports = scorecards.validate_all(paths)
    if not reports:
        print("  No scorecards yet. In Claude Code, run /coach-score to write them.")
    return 1 if any(not r.ok for r in reports) else 0


def run_merge(paths: Paths, reports=None) -> int:
    _need_data(paths)
    reports = reports if reports is not None else scorecards.validate_all(paths, quiet=True)
    rows = scorecards.merge(paths, reports)
    heading("Results")
    skipped = [r.call_id for r in reports if not r.ok]
    print(f"  Saved {paths.show(paths.results_csv)} with {len(rows)} scored call(s).")
    if skipped:
        note(f"Left out {len(skipped)} scorecard(s) that failed validation: {', '.join(skipped)}. "
             "Run: python coach.py validate  to see why.")
    no_outcome = [r["call_id"] for r in rows if not r["outcome"]]
    if no_outcome:
        note(f"{len(no_outcome)} call(s) have no outcome in {paths.show(paths.outcomes_csv)}: "
             f"{', '.join(no_outcome[:5])}{' ...' if len(no_outcome) > 5 else ''}")
    return 0


def run_stats(paths: Paths, reports=None) -> int:
    _need_data(paths)
    reports = reports if reports is not None else scorecards.validate_all(paths, quiet=True)
    rows = stats.build_stats(paths, reports)
    if rows:
        stats.print_stats(rows)
    else:
        print("  No transcribed calls yet. Run: python coach.py transcribe")
    return 0


def run_compare(paths: Paths) -> int:
    _need_data(paths)
    compare.run_compare(paths)
    return 0


def run_analyze(paths: Paths) -> int:
    _need_data(paths)
    reports = scorecards.validate_all(paths)
    run_merge(paths, reports)
    run_stats(paths, reports)
    result = compare.run_compare(paths)
    if result["rows"]:
        from coach.dashboard import run_dashboard

        run_dashboard(paths)
    from coach.archive import suggestions
    from coach.config import suggest_after_days

    tips = suggestions(paths, reports, suggest_after_days())
    if tips:
        heading("Suggested: keep old calls apart")
        for why, what in tips:
            print(f"  {why}\n  {what}")
    heading("Next step")
    print(f"  In Claude Code, run /coach-findings to write {paths.show(paths.reports / 'Findings.md')}")
    if any("impossible" in line for line in result["note"]):
        print("  It will say the won vs. lost comparison is not possible yet. Add outcomes to outcomes.csv first.")
    return 1 if any(not r.ok for r in reports) else 0


def run_demo(root=REPO_ROOT) -> int:
    """Copy the synthetic demo into data/demo/ and run the whole analysis on it."""
    if not (DEMO_SRC / "scorecards").is_dir():
        raise CoachError("The demo data in examples/demo/ is missing.", "Download the repo again.")
    target = root / "data" / "demo"
    if target.exists():
        shutil.rmtree(target)  # data/demo is rebuilt on every run
    for sub in ("raw", "calls", "scorecards"):
        shutil.copytree(DEMO_SRC / sub, target / sub)
    for name in ("outcomes.csv", "contacts.csv", "rubric.md"):
        shutil.copyfile(DEMO_SRC / name, target / name)
    paths = Paths(root=root, data=target, rubric=target / "rubric.md")
    for folder in paths.folders():
        folder.mkdir(parents=True, exist_ok=True)

    print("AI Sales Coach demo. 14 synthetic calls with invented people and companies.")
    print(f"Working copy: {paths.show(target)}/ (rebuilt each time you run the demo)")
    code = run_analyze(paths)
    # An example Findings.md, as /coach-findings would write it, so the dashboard shows the full picture.
    if (DEMO_SRC / "Findings.md").exists():
        shutil.copyfile(DEMO_SRC / "Findings.md", paths.reports / "Findings.md")
        from coach.dashboard import run_dashboard

        run_dashboard(paths, quiet=True)
    heading("Where to look")
    places = [(paths.show(paths.stats_csv), "numbers measured from timestamps"),
              (paths.show(paths.results_csv), "scores from the scorecards"),
              (paths.show(paths.reports / "dashboard.html"), "open this in your browser: everything on one page"),
              (paths.show(paths.reports / "compare.csv"), "won vs. lost"),
              (paths.show(paths.charts) + "/", "charts")]
    width = max(len(p) for p, _ in places)
    for place, what in places:
        print(f"  {place:<{width}}  {what}")
    print(f"\n  Open {paths.show(paths.reports / 'dashboard.html')} to see it all on one page,")
    print("  or run: python coach.py dashboard --data-dir data/demo --open")
    return code


def run_locate(paths: Paths, call_id: str, quote: str) -> int:
    print(json.dumps(scorecards.locate(paths, call_id, quote), indent=2))
    return 0
