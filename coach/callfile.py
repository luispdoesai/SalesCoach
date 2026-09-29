"""Read and write call files: data/calls/<call_id>.md

A call file has YAML-style front matter, then three sections:
Transcript, Tone Notes, and Email History. Code writes the transcript once.
Relabeling changes speaker labels only. Spoken text is never edited.
Email History is only ever changed between the two marker comments.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

EMAIL_START = "<!-- EMAIL_START -->"
EMAIL_END = "<!-- EMAIL_END -->"
EMAIL_PLACEHOLDER = "Not yet pulled."
TONE_CAVEAT = "Hints generated from the audio. Verify before trusting."
NO_TONE = "No tone hints for this call. The tone step was skipped or failed."

EXAMPLE_NAME = "2026-09-28_JD_Discovery.m4a"
CALL_ID_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_([A-Za-z]{1,5})_([A-Za-z0-9][A-Za-z0-9-]*)$")
LINE_RE = re.compile(r"^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s+([A-Z][A-Z_]*):\s?(.*)$")

FRONT_KEYS = [
    "call_id", "date", "prospect_initials", "stage", "duration_sec", "source_audio",
    "rep_speaker", "speaker_mapping_confidence", "needs_review",
]


@dataclass
class CallName:
    call_id: str
    date: str | None
    prospect_initials: str | None
    stage: str | None
    valid: bool


def parse_call_name(stem: str) -> CallName:
    """Split YYYY-MM-DD_Initials_Stage. valid is False if the name does not match."""
    m = CALL_ID_RE.match(stem)
    if m:
        try:
            datetime.strptime(m.group(1), "%Y-%m-%d")
            return CallName(stem, m.group(1), m.group(2).upper(), m.group(3), True)
        except ValueError:
            pass
    return CallName(safe_call_id(stem), None, None, None, False)


def safe_call_id(stem: str) -> str:
    """A call id that is safe to use as a file name."""
    return re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_") or "call"


def fmt_ts(seconds: float) -> str:
    """Seconds to MM:SS, or H:MM:SS past one hour."""
    total = max(0, int(seconds))
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def parse_ts(value: Any) -> float:
    """MM:SS, H:MM:SS, [MM:SS], or plain seconds to seconds. Raises ValueError."""
    if isinstance(value, bool):
        raise ValueError(f"not a timestamp: {value!r}")
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().strip("[]")
    parts = text.split(":")
    if not 1 <= len(parts) <= 3 or not all(p.strip().replace(".", "", 1).isdigit() for p in parts):
        raise ValueError(f"not a timestamp: {value!r}")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


@dataclass
class TranscriptLine:
    start: float
    role: str
    text: str


@dataclass
class CallFile:
    meta: dict[str, Any]
    lines: list[TranscriptLine] = field(default_factory=list)
    tone_text: str = ""
    email_block: str = EMAIL_PLACEHOLDER

    @property
    def transcript(self) -> str:
        return "\n".join(f"[{fmt_ts(line.start)}] {line.role}: {line.text}" for line in self.lines)


def _front_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, float):
        return str(int(round(value)))
    return str(value)


def _coerce(value: str) -> Any:
    if value in ("true", "false"):
        return value == "true"
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def render_tone(tone_windows: list[dict]) -> str:
    if not tone_windows:
        return NO_TONE
    rows = []
    for w in tone_windows:
        rows.append(
            f"- {fmt_ts(w['start'])}-{fmt_ts(w['end'])} | REP: {w.get('rep_tone', '')} | "
            f"PROSPECT: {w.get('prospect_tone', '')} | note: {w.get('note', '')}"
        )
    return "\n".join(rows)


def render(meta: dict[str, Any], utterances: list[dict], tone_windows: list[dict],
           email_block: str = EMAIL_PLACEHOLDER) -> str:
    """Build the full call file text. Utterance text is written as spoken."""
    front = [f"{key}: {_front_value(meta.get(key))}" for key in FRONT_KEYS]
    lines = []
    for u in utterances:
        # Line breaks inside one utterance become spaces so it stays one line.
        text = " ".join(str(u["text"]).split())
        lines.append(f"[{fmt_ts(u['start'])}] {u['role']}: {text}")
    return (
        "---\n" + "\n".join(front) + "\n---\n\n"
        "# Transcript\n" + "\n".join(lines) + "\n\n"
        "# Tone Notes\n" + TONE_CAVEAT + "\n" + render_tone(tone_windows) + "\n\n"
        "# Email History\n" + EMAIL_START + "\n" + email_block.strip() + "\n" + EMAIL_END + "\n"
    )


def parse(text: str) -> CallFile:
    meta: dict[str, Any] = {}
    body = text
    if text.startswith("---"):
        _, _, rest = text.partition("---\n")
        front, sep, body = rest.partition("\n---")
        if sep:
            for raw in front.splitlines():
                key, colon, value = raw.partition(":")
                if colon:
                    meta[key.strip()] = _coerce(value.strip())
            body = body.lstrip("-\n")

    section = None
    lines: list[TranscriptLine] = []
    tone: list[str] = []
    for raw in body.splitlines():
        if raw.startswith("# "):
            section = raw[2:].strip().lower()
            continue
        if section == "transcript":
            m = LINE_RE.match(raw.strip())
            if m:
                lines.append(TranscriptLine(parse_ts(m.group(1)), m.group(2), m.group(3)))
        elif section == "tone notes":
            tone.append(raw)

    email = EMAIL_PLACEHOLDER
    if EMAIL_START in text and EMAIL_END in text:
        email = text.split(EMAIL_START, 1)[1].split(EMAIL_END, 1)[0].strip()
    return CallFile(meta, lines, "\n".join(tone).strip(), email)


def read(path: Path) -> CallFile:
    return parse(path.read_text(encoding="utf-8"))


def replace_email_block(text: str, new_block: str) -> str:
    """Swap only what sits between the EMAIL markers."""
    if EMAIL_START not in text or EMAIL_END not in text:
        raise ValueError("the EMAIL_START and EMAIL_END markers are missing")
    before, rest = text.split(EMAIL_START, 1)
    _, after = rest.split(EMAIL_END, 1)
    return before + EMAIL_START + "\n" + new_block.strip() + "\n" + EMAIL_END + after


def atomic_write(path: Path, text: str) -> None:
    """Write to a temp file, then rename, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
