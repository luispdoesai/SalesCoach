"""Optional: build data/coach.db (SQLite) from the CSVs.

The CSVs stay the source of truth. This database is a convenience for people
who like SQL or want to connect a BI tool. It is rebuilt from scratch on every
run and lives in data/, so it is gitignored.
"""

from __future__ import annotations

import sqlite3

from coach.config import Paths
from coach.friendly import CoachError, heading, note, ok

VIEW = """
CREATE VIEW calls AS
SELECT s.*, r.date, r.prospect_initials, r.stage, r.rubric_avg, o.outcome, o.deal_value
FROM stats s
LEFT JOIN results r ON r.call_id = s.call_id
LEFT JOIN outcomes o ON o.call_id = s.call_id
"""


def run_index(paths: Paths) -> int:
    import pandas as pd

    sources = {
        "stats": paths.stats_csv,
        "results": paths.results_csv,
        "outcomes": paths.outcomes_csv,
        "contacts": paths.contacts_csv,
        "compare": paths.reports / "compare.csv",
    }
    present = {name: p for name, p in sources.items() if p.exists() and p.stat().st_size > 0}
    if "stats" not in present:
        raise CoachError("There is no stats.csv to index yet.", "Run: python coach.py analyze  first.")

    db_path = paths.data / "coach.db"
    tmp_path = db_path.with_suffix(".db.tmp")
    tmp_path.unlink(missing_ok=True)
    heading(f"Building {paths.show(db_path)}")
    with sqlite3.connect(tmp_path) as conn:
        for name, path in present.items():
            try:
                frame = pd.read_csv(path, encoding="utf-8-sig", sep=None, engine="python")
            except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError):
                note(f"Skipped {paths.show(path)}: it could not be read as a CSV.")
                continue
            frame.columns = [str(c).strip().lower() for c in frame.columns]
            frame.to_sql(name, conn, index=False)
            ok(f"{name}: {len(frame)} rows from {paths.show(path)}")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if {"stats", "results", "outcomes"} <= tables:
            conn.execute(VIEW)
            ok("calls: a view joining stats, results, and outcomes")
    tmp_path.replace(db_path)
    print(f"\n  Try: sqlite3 {paths.show(db_path)} \"SELECT outcome, AVG(rep_talk_pct) FROM calls GROUP BY outcome;\"")
    print("  The CSVs stay the source of truth. Re-run this after analyze to refresh the database.")
    return 0
