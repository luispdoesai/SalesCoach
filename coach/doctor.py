"""The doctor command: check that everything is ready.

It only reads. It never changes files. It never prints the API key.
"""

from __future__ import annotations

import csv
import importlib.metadata
import importlib.util
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from coach.config import (
    CONTACTS_HEADER,
    DEFAULTS,
    OUTCOMES_HEADER,
    REPO_ROOT,
    STARTER_RUBRIC_MARKER,
    Paths,
    gemini_key_status,
    load_config,
)
from coach.friendly import CoachError, bad, heading, note, ok, warn

# (pip name, import name, what it is used for, required)
PACKAGES = [
    ("google-genai", "google.genai", "transcription", True),
    ("pandas", "pandas", "statistics", True),
    ("matplotlib", "matplotlib", "charts", True),
    ("pyyaml", "yaml", "reading config.yaml", True),
    ("python-dotenv", "dotenv", "reading .env", True),
    ("pytest", "pytest", "running the tests", False),
]

AUDIO_EXTENSIONS = {
    ".m4a", ".mp3", ".wav", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wma",
    ".aif", ".aiff", ".amr", ".3gp", ".caf", ".mp4", ".m4v", ".mov", ".mkv",
    ".avi", ".wmv", ".webm",
}


class Tally:
    def __init__(self) -> None:
        self.problems = 0
        self.warnings = 0

    def bad(self, msg: str, fix: str | None = None) -> None:
        self.problems += 1
        bad(msg, fix)

    def warn(self, msg: str, fix: str | None = None) -> None:
        self.warnings += 1
        warn(msg, fix)


def _installed(import_name: str) -> bool:
    try:
        return importlib.util.find_spec(import_name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def check_python(t: Tally) -> None:
    heading("Python")
    version = platform.python_version()
    if sys.version_info >= (3, 10):
        ok(f"Python {version}")
    else:
        t.bad(f"Python {version} is too old. This tool needs 3.10 or newer.",
              "Install a newer Python from https://www.python.org/downloads/")


def check_packages(t: Tally) -> None:
    heading("Packages")
    missing = False
    for pip_name, import_name, used_for, required in PACKAGES:
        if _installed(import_name):
            try:
                ver = importlib.metadata.version(pip_name)
            except importlib.metadata.PackageNotFoundError:
                ver = "installed"
            ok(f"{pip_name} {ver}")
            continue
        missing = True
        if required:
            t.bad(f"{pip_name} is not installed. It is needed for {used_for}.")
        else:
            t.warn(f"{pip_name} is not installed. It is only needed for {used_for}.")
    if missing:
        print("          To install them all: python -m pip install -r requirements.txt")
        print(f"          (This checked the Python at {sys.executable})")


def check_settings(t: Tally) -> dict:
    heading("Settings")
    if not _installed("yaml"):
        note("config.yaml not checked yet. Reading it needs pyyaml, listed above.")
        return DEFAULTS
    try:
        cfg = load_config()
        ok("config.yaml loaded")
        return cfg
    except CoachError as err:
        t.bad(err.problem, err.fix)
        note("Using default settings for the rest of these checks.")
        return DEFAULTS


def check_key(t: Tally, paths: Paths) -> None:
    heading("Gemini API key")
    status = gemini_key_status(paths.root)
    if status == "ok":
        ok("GEMINI_API_KEY is set (not shown)")
        return
    only_for = "Only transcription needs it. The demo and analysis work without it."
    if status == "no_env_file":
        t.warn(f"No .env file found. {only_for}",
               "Run: python coach.py init  Then paste your key into .env")
    else:
        t.warn(f"GEMINI_API_KEY in .env is empty or still says your-key-here. {only_for}",
               "Open .env and paste your key from https://aistudio.google.com/")


def _csv_header(path: Path) -> list[str]:
    # utf-8-sig handles the invisible marker Excel adds to CSV files.
    with path.open(newline="", encoding="utf-8-sig") as fh:
        first = next(csv.reader(fh), [])
    return [c.strip().lower() for c in first]


def _csv_rows(path: Path) -> int:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return max(0, sum(1 for row in csv.reader(fh) if any(c.strip() for c in row)) - 1)


def check_folders(t: Tally, paths: Paths) -> None:
    heading("Folders and files")
    if not paths.data.is_dir():
        t.warn(f"The {paths.show(paths.data)}/ folder does not exist yet.",
               "Run: python coach.py init")
        return
    missing = [paths.show(f) + "/" for f in paths.folders() if not f.is_dir()]
    if missing:
        t.warn(f"Missing folders: {', '.join(missing)}", "Run: python coach.py init")
    else:
        ok(f"All data folders exist under {paths.show(paths.data)}/")

    for path, header in ((paths.contacts_csv, CONTACTS_HEADER), (paths.outcomes_csv, OUTCOMES_HEADER)):
        name = paths.show(path)
        if not path.exists():
            t.warn(f"{name} does not exist yet.", "Run: python coach.py init")
            continue
        try:
            found = _csv_header(path)
            rows = _csv_rows(path)
        except (OSError, UnicodeDecodeError, csv.Error):
            t.warn(f"{name} could not be read.", "Save it again as a plain CSV (UTF-8).")
            continue
        if found != header:
            t.warn(f"{name} has an unexpected first line: {','.join(found) or '(empty)'}",
                   f"Make the first line exactly: {','.join(header)}")
        else:
            ok(f"{name} ({rows} rows)")

    if paths.inbox.is_dir():
        waiting = [p for p in paths.inbox.iterdir() if p.suffix.lower() in AUDIO_EXTENSIONS]
        if waiting:
            note(f"{len(waiting)} recording(s) waiting in {paths.show(paths.inbox)}/")
        from coach.callfile import EXAMPLE_NAME, parse_call_name

        misnamed = [p.name for p in waiting if not parse_call_name(p.stem).valid]
        if misnamed:
            t.warn(f"These names do not match YYYY-MM-DD_Initials_Stage: {', '.join(misnamed[:5])}",
                   f"Rename them like {EXAMPLE_NAME}")


def check_rubric(t: Tally, paths: Paths) -> None:
    heading("Rubric")
    name = paths.show(paths.rubric)
    if not paths.rubric.exists():
        t.warn(f"{name} does not exist yet.",
               "Run: python coach.py init  for a starter copy, then run /coach-rubric "
               "in Claude Code to build your own.")
        return
    text = paths.rubric.read_text(encoding="utf-8", errors="replace")
    count = sum(1 for line in text.splitlines() if line.startswith("### "))
    if text.lstrip().startswith(STARTER_RUBRIC_MARKER):
        t.warn(f"{name} is still the starter example ({count} behaviors).",
               "Run /coach-rubric in Claude Code to build yours, or edit it and delete the first line.")
    elif count == 0:
        t.warn(f"{name} has no behaviors. Each one needs a line like: ### price_handling: Price Handling",
               "Run /coach-rubric in Claude Code, or copy the format from rubric/rubric.example.md")
    else:
        ok(f"{name} has {count} behaviors")


def _relative(path: Path, root: Path) -> str | None:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return None


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def check_git(t: Tally, paths: Paths) -> None:
    heading("Privacy")
    root = paths.root
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        t.bad(".gitignore is missing. Your calls and key could be committed by accident.",
              "Download .gitignore again from the repo and put it in the project folder.")

    if shutil.which("git") is None:
        note("git is not installed, so nothing can be committed. Skipping the git checks.")
        return
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        note("This folder is not a git repository, so nothing can be committed by accident.")
        return

    # Private paths that live inside the repo folder.
    data_rel = _relative(paths.data, root)
    rubric_rel = _relative(paths.rubric, root)
    private = [".env"] + [p for p in (data_rel, rubric_rel) if p]

    listed = _git(root, "ls-files", "-z", "--", *private).stdout
    tracked = [f for f in listed.split("\0") if f]
    everything = _git(root, "ls-files", "-z").stdout.split("\0")
    tracked += [f for f in everything if f and Path(f).suffix.lower() in AUDIO_EXTENSIONS]
    tracked = sorted(set(tracked))

    if tracked:
        t.problems += 1
        line = "  " + "!" * 66
        print(line)
        print("  [FAIL]  PRIVATE FILES ARE TRACKED BY GIT. They could be published.")
        for f in tracked[:10]:
            print(f"            {f}")
        if len(tracked) > 10:
            print(f"            ...and {len(tracked) - 10} more")
        print("          Fix: git rm -r --cached " + " ".join(private))
        print("               Then commit. If you already pushed, the files are still in")
        print("               your git history. Get help before making the repo public.")
        print(line)
    else:
        ok("No call data, audio, .env, or personal rubric is tracked by git")

    # Ask git whether example private files would be ignored.
    probes = [".env", "recording.m4a"]
    if data_rel:
        probes.append(f"{data_rel}/calls/probe.md")
    if rubric_rel:
        probes += [rubric_rel, str(Path(rubric_rel).parent / "rubric.backup-2026-01-01.md")]
    not_ignored = [p for p in probes
                   if _git(root, "check-ignore", "-q", "--no-index", p).returncode != 0]
    if not_ignored:
        t.bad(f".gitignore does not protect: {', '.join(not_ignored)}",
              "Restore .gitignore from the repo. Its privacy rules must stay.")
    else:
        ok(f".gitignore protects {', '.join(private)}, and audio files")


def check_tools() -> None:
    heading("Optional tools")
    if shutil.which("ffmpeg"):
        ok("ffmpeg found. Recordings over 30 minutes can be split automatically.")
    else:
        note("ffmpeg not found. That is fine unless a recording is over 30 minutes "
             "or is a video file. Get it at https://ffmpeg.org/download.html")


def run_doctor(root: Path = REPO_ROOT) -> int:
    print("AI Sales Coach doctor. Checking your setup. Nothing is changed.")
    t = Tally()
    check_python(t)
    check_packages(t)
    cfg = check_settings(t)
    paths = Paths.from_config(cfg, root)
    check_key(t, paths)
    check_folders(t, paths)
    check_rubric(t, paths)
    check_git(t, paths)
    check_tools()

    heading("Summary")
    p = "problem" if t.problems == 1 else "problems"
    w = "warning" if t.warnings == 1 else "warnings"
    print(f"  {t.problems} {p}, {t.warnings} {w}.")
    if t.problems:
        print("  Fix the [FAIL] lines above, then run doctor again.")
        return 1
    if t.warnings:
        print("  Nothing is broken. The [warn] lines are things to finish setting up.")
    else:
        print("  Everything looks ready.")
    return 0
