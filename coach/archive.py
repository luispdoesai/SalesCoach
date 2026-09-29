"""Archive: keep old calls out of your current numbers without losing them.

python coach.py archive --before 2026-09-01    move calls dated before that day
python coach.py archive --calls ID1,ID2         move specific calls
python coach.py archive --list                  show archived periods
python coach.py restore NAME                    bring an archived period back

An archive is a self-contained data folder at data/archive/<name>/ with the
calls, raw transcripts, scorecards, emails, audio, and the matching rows of
outcomes.csv and contacts.csv. It keeps a copy of the rubric those calls were
scored with, so changing your rubric later never breaks old scorecards. Each
archive gets its own dashboard. Nothing is deleted.
"""

from __future__ import annotations

import contextlib
import csv
import filecmp
import io
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

from coach.callfile import parse_call_name
from coach.config import Paths
from coach.friendly import CoachError, heading, note, ok, warn

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,60}$")


def archive_root(paths: Paths) -> Path:
    return paths.data / "archive"


def archive_paths(paths: Paths, name: str) -> Paths:
    folder = archive_root(paths) / name
    return Paths(root=paths.root, data=folder, rubric=folder / "rubric.md")


def is_archive(paths: Paths) -> bool:
    return paths.data.parent.name == "archive"


def active_call_ids(paths: Paths) -> list[str]:
    return sorted(p.stem for p in paths.calls.glob("*.md")) if paths.calls.is_dir() else []


def date_range(ids: list[str]) -> tuple[str | None, str | None]:
    dates = sorted(d for d in (parse_call_name(i).date for i in ids) if d)
    return (dates[0], dates[-1]) if dates else (None, None)


def list_archives(paths: Paths) -> list[dict]:
    root = archive_root(paths)
    out = []
    for folder in sorted(root.iterdir()) if root.is_dir() else []:
        if folder.is_dir():
            ids = active_call_ids(archive_paths(paths, folder.name))
            first, last = date_range(ids)
            out.append({"name": folder.name, "count": len(ids), "first": first, "last": last,
                        "dashboard": folder / "reports" / "dashboard.html"})
    return out


# When to archive: suggestions made by code, shown on the dashboard and after analyze

RUBRIC_MISMATCH = ("is not an id in the rubric", "Every rubric behavior needs a score")


def _cutoff(newest: str, days: int) -> str:
    """The first day of the month after (newest call minus days), so periods break on a clean date."""
    d = datetime.strptime(newest, "%Y-%m-%d") - timedelta(days=days)
    first_next = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
    return first_next.strftime("%Y-%m-%d")


def suggestions(paths: Paths, reports: list | None = None, after_days: int = 90) -> list[tuple[str, str]]:
    """(why, what to do) pairs. Empty when nothing needs archiving."""
    if is_archive(paths):
        return []
    out: list[tuple[str, str]] = []
    ids = active_call_ids(paths)

    # 1. Calls scored with an older version of the rubric.
    if reports is None:
        from coach.scorecards import validate_all

        try:
            reports = validate_all(paths, quiet=True)
        except CoachError:
            reports = []
    old_rubric = [r.call_id for r in reports
                  if not r.ok and any(m in e for e in r.errors for m in RUBRIC_MISMATCH)]
    if old_rubric:
        n = len(old_rubric)
        out.append((f"{n} call{'s were' if n != 1 else ' was'} scored with an older version of your rubric, "
                    "so they no longer count.",
                    "Re-score them with /coach-score in Claude Code to keep them, or set them aside with: "
                    f"python coach.py archive --calls {','.join(old_rubric)}"))

    # 2. Calls much older than your latest ones.
    if after_days and after_days > 0:
        dated = sorted(d for d in (parse_call_name(i).date for i in ids) if d)
        if dated:
            cut = _cutoff(dated[-1], after_days)
            older = [d for d in dated if d < cut]
            newer = [d for d in dated if d >= cut]
            if older and len(newer) >= 3:
                out.append((f"{len(older)} call{'s are' if len(older) != 1 else ' is'} from before {cut}, "
                            f"more than {after_days} days before your latest call. Old calls can hide how you "
                            "sell now.",
                            f"If they belong to an earlier period, set them aside with: "
                            f"python coach.py archive --before {cut}"))
    return out


# Moving files

def _files_for(paths: Paths, cid: str) -> list[Path]:
    files = [paths.calls / f"{cid}.md", paths.raw / f"{cid}.json", paths.scorecards / f"{cid}.json",
             paths.emails / f"{cid}.txt"]
    if paths.processed.is_dir():
        audio = re.compile(rf"^{re.escape(cid)}(_\d+)?\.[A-Za-z0-9]+$")
        files += [p for p in paths.processed.iterdir() if audio.match(p.name)]
    return [f for f in files if f.exists()]


def _move(src: Paths, dst: Paths, cid: str) -> None:
    for f in _files_for(src, cid):
        target = dst.data / f.relative_to(src.data)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise CoachError(f"{dst.show(target)} already exists, so {cid} was not moved.",
                             "Move or delete that file by hand, then run the command again.")
        shutil.move(str(f), str(target))


def _split_csv(src: Path, dst: Path, ids: set[str]) -> int:
    """Move rows for these call ids from src to dst. Keeps the header, the delimiter, and every other row."""
    if not src.exists():
        return 0
    text = src.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    if not lines:
        return 0
    delimiter = ";" if lines[0].count(";") > lines[0].count(",") else ","
    rows = list(csv.reader(lines, delimiter=delimiter))
    header = rows[0]
    try:
        col = [h.strip().lower() for h in header].index("call_id")
    except ValueError:
        return 0
    moving = [r for r in rows[1:] if r and len(r) > col and r[col].strip() in ids]
    staying = [r for r in rows[1:] if r not in moving]
    if not moving:
        return 0
    existing: list[list[str]] = []
    if dst.exists():
        existing = [r for r in csv.reader(dst.read_text(encoding="utf-8-sig").splitlines(), delimiter=delimiter)][1:]
    dst.parent.mkdir(parents=True, exist_ok=True)
    for path, body in ((dst, existing + moving), (src, staying)):
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=delimiter, lineterminator="\n")
        w.writerow(header)
        w.writerows(body)
        path.write_text(buf.getvalue(), encoding="utf-8")
    return len(moving)


def _refresh(paths: Paths) -> None:
    """Rebuild numbers and the dashboard for a data folder, without the usual printout."""
    from coach import analyze

    if not active_call_ids(paths):
        return
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            analyze.run_analyze(paths)
        except CoachError:
            pass


def _confirm(prompt: str, yes: bool) -> bool:
    if yes:
        return True
    if sys.stdin.isatty():
        return input(f"\n  {prompt} [y/N] ").strip().lower() in ("y", "yes")
    print("\n  Nothing was moved. Run the same command again with --yes to go ahead.")
    return False


def _outcomes(paths: Paths) -> dict[str, str]:
    from coach.scorecards import read_outcomes

    return read_outcomes(paths, warn_bad=False)


# Commands

def run_archive(paths: Paths, before: str | None = None, calls: str | None = None, name: str | None = None,
                yes: bool = False, list_only: bool = False) -> int:
    if is_archive(paths):
        raise CoachError("This is already an archive folder.", "Run archive on your main data folder.")
    if list_only:
        return _print_list(paths)
    if not before and not calls:
        raise CoachError("Say which calls to archive.",
                         "Use --before 2026-09-01 for calls before a date, or --calls ID1,ID2 for specific calls. "
                         "Use --list to see what is archived already.")
    ids = active_call_ids(paths)
    if before:
        try:
            datetime.strptime(before, "%Y-%m-%d")
        except ValueError:
            raise CoachError(f"'{before}' is not a date.", "Use the form YYYY-MM-DD, for example --before 2026-09-01") from None
        chosen = [i for i in ids if (parse_call_name(i).date or "9999") < before]
        undated = [i for i in ids if not parse_call_name(i).date]
        if undated:
            note(f"{len(undated)} call(s) have no date in their name and stay put: {', '.join(undated[:5])}. "
                 "Use --calls to archive them by name.")
    else:
        wanted = [c.strip() for c in calls.split(",") if c.strip()]
        unknown = [c for c in wanted if c not in ids]
        if unknown:
            raise CoachError(f"No current call named {', '.join(unknown)}.",
                             "Copy the call id from the dashboard or from data/calls/, without .md")
        chosen = wanted
    if not chosen:
        print("No calls match, so nothing needs archiving.")
        return 0

    first, last = date_range(chosen)
    name = name or (f"{first}_to_{last}" if first else f"archive-{datetime.now():%Y-%m-%d}")
    if not NAME_RE.match(name):
        raise CoachError(f"'{name}' cannot be used as a folder name.",
                         "Use letters, numbers, dashes, dots, and underscores, for example --name 2026-Q3")
    dst = archive_paths(paths, name)
    if dst.rubric.exists() and paths.rubric.exists() and not filecmp.cmp(dst.rubric, paths.rubric, shallow=False):
        raise CoachError(f"The archive '{name}' was scored with a different rubric than your current one.",
                         "Pick a new name with --name, so calls scored with different rubrics stay apart.")

    outcomes = _outcomes(paths)
    heading(f"Archive {len(chosen)} call(s) to {paths.show(dst.data)}/")
    for cid in chosen:
        print(f"  {cid}  {outcomes.get(cid) or 'no outcome'}")
    remaining = [i for i in ids if i not in chosen]
    print(f"\n  {len(remaining)} call(s) stay in your current numbers.")
    print("  Nothing is deleted. Undo any time with: python coach.py restore " + name)
    if not _confirm("Move these calls?", yes):
        return 0

    for folder in dst.folders():
        folder.mkdir(parents=True, exist_ok=True)
    if paths.rubric.exists() and not dst.rubric.exists():
        shutil.copyfile(paths.rubric, dst.rubric)
    for cid in chosen:
        _move(paths, dst, cid)
    moved_rows = _split_csv(paths.outcomes_csv, dst.outcomes_csv, set(chosen))
    _split_csv(paths.contacts_csv, dst.contacts_csv, set(chosen))
    for csv_path, header in ((dst.outcomes_csv, "call_id,outcome,deal_value,notes"),
                             (dst.contacts_csv, "call_id,prospect_name,prospect_email,company")):
        if not csv_path.exists():
            csv_path.write_text(header + "\n", encoding="utf-8")

    _refresh(dst)
    _refresh(paths)
    ok(f"Archived {len(chosen)} call(s) and {moved_rows} outcome row(s) to {paths.show(dst.data)}/")
    ok(f"Its dashboard: {paths.show(dst.reports / 'dashboard.html')}")
    if (paths.reports / "Findings.md").exists():
        note("Your Findings.md still describes the old mix of calls. Run /coach-findings again in Claude Code.")
    return 0


def run_restore(paths: Paths, name: str, yes: bool = False) -> int:
    src = archive_paths(paths, name)
    if not src.data.is_dir():
        names = ", ".join(a["name"] for a in list_archives(paths)) or "none yet"
        raise CoachError(f"There is no archive called '{name}'.", f"Archives: {names}")
    ids = active_call_ids(src)
    clash = [i for i in ids if (paths.calls / f"{i}.md").exists()]
    moving = [i for i in ids if i not in clash]
    heading(f"Restore {len(moving)} call(s) from {paths.show(src.data)}/")
    if clash:
        warn(f"{len(clash)} call(s) already exist in your current folder and will stay archived: {', '.join(clash[:5])}")
    if src.rubric.exists() and paths.rubric.exists() and not filecmp.cmp(src.rubric, paths.rubric, shallow=False):
        warn("These calls were scored with a different rubric than your current one. Their scorecards may fail "
             "validation until you re-score them with /coach-score.")
    if not moving:
        print("  Nothing to restore.")
        return 0
    if not _confirm("Bring these calls back into your current numbers?", yes):
        return 0
    for cid in moving:
        _move(src, paths, cid)
    _split_csv(src.outcomes_csv, paths.outcomes_csv, set(moving))
    _split_csv(src.contacts_csv, paths.contacts_csv, set(moving))
    same_rubric = not src.rubric.exists() or (paths.rubric.exists()
                                               and filecmp.cmp(src.rubric, paths.rubric, shallow=False))
    if not active_call_ids(src) and same_rubric:
        # Only an empty shell is left: folders, header-only CSVs, and a rubric identical to yours.
        shutil.rmtree(src.data)
        note(f"The archive '{name}' is now empty and was removed.")
    elif not active_call_ids(src):
        note(f"The archive '{name}' is empty but kept, because its rubric.md is the only copy of an older rubric.")
    else:
        _refresh(src)
    _refresh(paths)
    ok(f"Restored {len(moving)} call(s).")
    return 0


def _print_list(paths: Paths) -> int:
    archives = list_archives(paths)
    ids = active_call_ids(paths)
    first, last = date_range(ids)
    heading("Current calls")
    print(f"  {len(ids)} call(s)" + (f", {first} to {last}" if first else ""))
    heading("Archived periods")
    if not archives:
        print("  None yet. Example: python coach.py archive --before 2026-09-01")
    for a in archives:
        span = f"{a['first']} to {a['last']}" if a["first"] else "no dated calls"
        print(f"  {a['name']:<28} {a['count']:>3} call(s)  {span}")
        print(f"  {'':<28} dashboard: {paths.show(a['dashboard'])}")
    return 0
