"""Settings, paths, and the API key.

Privacy: the Gemini key is read from .env or the environment. It is never
printed and never written to any file by this code.
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coach.friendly import CoachError

# The repo folder, found from this file so commands work from any directory.
REPO_ROOT = Path(__file__).resolve().parent.parent

CONTACTS_HEADER = ["call_id", "prospect_name", "prospect_email", "company"]
OUTCOMES_HEADER = ["call_id", "outcome", "deal_value", "notes"]
OUTCOME_VALUES = ("won", "lost", "stalled", "open")

# First line of a rubric that init copied from the example. /coach-rubric
# may replace a rubric with this line without asking.
STARTER_RUBRIC_MARKER = "<!-- STARTER RUBRIC"

PLACEHOLDER_KEYS = {"", "your-key-here", "your_key_here", "your-api-key", "changeme"}

DEFAULTS: dict[str, Any] = {
    "rep": {"name": "", "company": ""},
    "models": {
        "transcribe": "gemini-3.5-transcribe",
        "relabel": "gemini-3.5-flash-lite",
        "tone": "gemini-3.8-flash",
    },
    "transcribe": {
        "max_minutes": 30,
        "chunk_minutes": 25,
        "language_codes": [],
        "relabel_window_sec": 120,
        "tone_window_sec": 60,
        "audio_extensions": [
            ".m4a", ".mp3", ".wav", ".aac", ".ogg", ".opus", ".flac",
            ".webm", ".aif", ".aiff", ".mp4", ".mov",
        ],
    },
    "redact": {"enabled": False, "emails": True, "phone_numbers": True, "names": []},
    "archive": {"suggest_after_days": 90},
    "paths": {"data_dir": "data", "rubric": "rubric/rubric.md"},
}


def suggest_after_days() -> int:
    """The archive suggestion window from config.yaml, falling back to the default."""
    try:
        return int(load_config()["archive"]["suggest_after_days"] or 0)
    except (CoachError, KeyError, TypeError, ValueError):
        return int(DEFAULTS["archive"]["suggest_after_days"])


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Read config.yaml and fill in defaults for anything left out."""
    path = path or REPO_ROOT / "config.yaml"
    if not path.exists():
        raise CoachError(
            f"The settings file {path.name} is missing.",
            "Download config.yaml again from the repo and put it in the project folder.",
        )
    try:
        import yaml
    except ModuleNotFoundError:
        raise CoachError(
            "The Python package 'pyyaml' is not installed.",
            "Run: python -m pip install -r requirements.txt",
        ) from None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as err:
        mark = getattr(err, "problem_mark", None)
        where = f" near line {mark.line + 1}" if mark else ""
        raise CoachError(
            f"{path.name} has a formatting problem{where}.",
            "Check the indentation and the colon on that line. Use spaces, not tabs.",
        ) from None
    if not isinstance(data, dict):
        raise CoachError(
            f"{path.name} does not look like a settings file.",
            "Download config.yaml again from the repo.",
        )
    return _merge(DEFAULTS, data)


@dataclass(frozen=True)
class Paths:
    """Every file and folder the tool reads or writes."""

    root: Path
    data: Path
    rubric: Path

    @classmethod
    def from_config(cls, cfg: dict[str, Any], root: Path = REPO_ROOT) -> "Paths":
        # COACH_DATA_DIR lets tests and the demo point at a separate folder.
        override = os.environ.get("COACH_DATA_DIR", "").strip()
        data = Path(override or cfg["paths"]["data_dir"])
        data = data if data.is_absolute() else root / data
        rubric = Path(cfg["paths"]["rubric"])
        rubric = rubric if rubric.is_absolute() else root / rubric
        # A separate data folder (like data/demo) may carry its own rubric.md.
        if override and (data / "rubric.md").exists():
            rubric = data / "rubric.md"
        return cls(root=root, data=data, rubric=rubric)

    @property
    def inbox(self) -> Path:
        return self.data / "inbox"

    @property
    def processed(self) -> Path:
        return self.data / "processed"

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def calls(self) -> Path:
        return self.data / "calls"

    @property
    def emails(self) -> Path:
        return self.data / "emails"

    @property
    def scorecards(self) -> Path:
        return self.data / "scorecards"

    @property
    def reports(self) -> Path:
        return self.data / "reports"

    @property
    def charts(self) -> Path:
        return self.reports / "charts"

    @property
    def contacts_csv(self) -> Path:
        return self.data / "contacts.csv"

    @property
    def outcomes_csv(self) -> Path:
        return self.data / "outcomes.csv"

    @property
    def results_csv(self) -> Path:
        return self.data / "results.csv"

    @property
    def stats_csv(self) -> Path:
        return self.data / "stats.csv"

    @property
    def env_file(self) -> Path:
        return self.root / ".env"

    def folders(self) -> list[Path]:
        return [
            self.data, self.inbox, self.processed, self.raw, self.calls,
            self.emails, self.scorecards, self.reports, self.charts,
        ]

    def show(self, path: Path) -> str:
        """Path relative to the project folder, for messages."""
        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)


def missing_data_fix() -> str:
    """The fix for a missing data folder. A custom --data-dir is probably a typo, not a missing init."""
    if os.environ.get("COACH_DATA_DIR", "").strip():
        return ("Check the folder after --data-dir. It is relative to the project folder, "
                "for example --data-dir data/demo. For your own calls, leave --data-dir out.")
    return "Run: python coach.py init"


def load_env(root: Path = REPO_ROOT) -> bool:
    """Load .env into the environment. Values already set in the shell win."""
    env_file = root / ".env"
    if not env_file.exists():
        return False
    try:
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)
    except ModuleNotFoundError:
        # Minimal fallback so doctor still works before packages are installed.
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))
    return True


def gemini_key_status(root: Path = REPO_ROOT) -> str:
    """One of: ok, no_env_file, missing, placeholder. Never returns the key."""
    has_file = load_env(root)
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key and key.lower() not in PLACEHOLDER_KEYS:
        return "ok"
    if not has_file and not key:
        return "no_env_file"
    return "placeholder" if key else "missing"


def require_gemini_key(root: Path = REPO_ROOT) -> str:
    """Return the key for the Gemini client, or explain how to add it."""
    status = gemini_key_status(root)
    if status == "no_env_file":
        raise CoachError(
            "There is no .env file, so the Gemini API key is missing.",
            "Run: cp .env.example .env  Then open .env and paste your key after GEMINI_API_KEY=",
        )
    if status in ("missing", "placeholder"):
        raise CoachError(
            "GEMINI_API_KEY in .env is empty or still says your-key-here.",
            "Open .env and paste your key from https://aistudio.google.com/ after GEMINI_API_KEY=",
        )
    return os.environ["GEMINI_API_KEY"].strip()
