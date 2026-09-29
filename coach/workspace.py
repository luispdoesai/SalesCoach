"""The init command: create folders and starter files.

Safe to re-run. It never overwrites a file that already exists.
"""

from __future__ import annotations

import csv
import shutil
from pathlib import Path

from coach.config import (
    CONTACTS_HEADER,
    OUTCOMES_HEADER,
    REPO_ROOT,
    STARTER_RUBRIC_MARKER,
    Paths,
    gemini_key_status,
)
from coach.friendly import CoachError, heading, note, ok, warn


def _mkdir(folder: Path, paths: Paths) -> bool:
    if folder.is_dir():
        return False
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as err:
        raise CoachError(
            f"Could not create the folder {paths.show(folder)} ({err.strerror}).",
            "Check that you can write to the project folder, then run init again.",
        ) from None
    return True


def _write_csv_header(path: Path, header: list[str], paths: Paths) -> None:
    if path.exists():
        note(f"{paths.show(path)} already exists. Left it as is.")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh, lineterminator="\n").writerow(header)
    ok(f"Created {paths.show(path)} with the header: {','.join(header)}")


def _copy_env(paths: Paths, templates: Path) -> None:
    if paths.env_file.exists():
        note(".env already exists. Left it as is.")
        return
    source = templates / ".env.example"
    if not source.exists():
        warn(".env.example is missing, so .env was not created.",
             "Create a file named .env containing: GEMINI_API_KEY=your-key-here")
        return
    shutil.copyfile(source, paths.env_file)
    ok("Created .env from .env.example. Your key goes in there. It is gitignored.")


def _copy_rubric(paths: Paths, templates: Path) -> None:
    if paths.rubric.exists():
        note(f"{paths.show(paths.rubric)} already exists. Left it as is.")
        return
    source = templates / "rubric" / "rubric.example.md"
    if not source.exists():
        warn("rubric/rubric.example.md is missing, so no starter rubric was copied.",
             "Run /coach-rubric in Claude Code to build your rubric.")
        return
    _mkdir(paths.rubric.parent, paths)
    marker = (
        f"{STARTER_RUBRIC_MARKER}: copied from rubric.example.md by init. "
        "Run /coach-rubric in Claude Code to build your own, "
        "or edit this file and delete this line. -->\n\n"
    )
    paths.rubric.write_text(marker + source.read_text(encoding="utf-8"), encoding="utf-8")
    ok(f"Created {paths.show(paths.rubric)} from the example. It is private and gitignored.")


def init_workspace(paths: Paths, templates: Path = REPO_ROOT) -> int:
    heading("Setting up your workspace")

    made = [f for f in paths.folders() if _mkdir(f, paths)]
    for folder in made:
        ok(f"Created {paths.show(folder)}/")
    if len(made) < len(paths.folders()):
        note(f"{len(paths.folders()) - len(made)} data folders already existed. Left them as is.")

    _write_csv_header(paths.contacts_csv, CONTACTS_HEADER, paths)
    _write_csv_header(paths.outcomes_csv, OUTCOMES_HEADER, paths)
    _copy_env(paths, templates)
    _copy_rubric(paths, templates)

    heading("Next steps")
    step = 1
    if gemini_key_status(paths.root) != "ok":
        print(f"  {step}. Open .env and paste your Gemini API key after GEMINI_API_KEY=")
        step += 1
    print(f"  {step}. Open Claude Code in this folder and run /coach-rubric to build your rubric.")
    print(f"  {step + 1}. Drop recordings into {paths.show(paths.inbox)}/ named like "
          "2026-09-28_JD_Discovery.m4a")
    print(f"  {step + 2}. Run: python coach.py doctor")
    print("\n  Want to see it work first? Run: python coach.py demo")
    return 0
