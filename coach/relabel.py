"""Work out which generic speaker (spk_1, spk_2) is the REP and which is the PROSPECT.

Only the opening of the call goes to a small Gemini text model, using
prompts/02_relabel_speakers.md. The model returns a mapping. Code applies it.
The model never sees or rewrites the rest of the transcript, and relabeling
changes the role on each utterance, never the words.
"""

from __future__ import annotations

from coach.callfile import fmt_ts
from coach.config import REPO_ROOT
from coach.friendly import CoachError

PROMPT_FILE = REPO_ROOT / "prompts" / "02_relabel_speakers.md"
ROLES = ("REP", "PROSPECT")

SCHEMA = {
    "type": "object",
    "properties": {
        "speakers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {"type": "string"},
                    "role": {"type": "string", "enum": list(ROLES)},
                },
                "required": ["speaker", "role"],
            },
        },
        "confidence": {"type": "string", "enum": ["high", "low"]},
        "reason": {"type": "string"},
    },
    "required": ["speakers", "confidence"],
}


def speakers_in(utterances: list[dict]) -> list[str]:
    seen: list[str] = []
    for u in utterances:
        if u["speaker"] not in seen:
            seen.append(u["speaker"])
    return seen


def opening_lines(utterances: list[dict], window_sec: float, offset: float = 0.0,
                  min_lines: int = 4) -> str:
    """Transcript lines from the first window_sec seconds, with generic labels."""
    picked = [u for u in utterances if u["start"] - offset < window_sec]
    if len(picked) < min_lines:
        picked = utterances[:min_lines]
    return "\n".join(f"[{fmt_ts(u['start'])}] {u['speaker']}: {u['text']}" for u in picked)


def build_prompt(opening: str, rep_name: str = "", rep_company: str = "",
                 context: str = "") -> str:
    if not PROMPT_FILE.exists():
        raise CoachError("prompts/02_relabel_speakers.md is missing.",
                         "Download it again from the repo.")
    parts = [PROMPT_FILE.read_text(encoding="utf-8").strip(), "", "## Hints"]
    parts.append(f"Rep name: {rep_name.strip() or 'not given'}")
    parts.append(f"Rep company: {rep_company.strip() or 'not given'}")
    if context:
        parts += ["", "## Context: end of the previous part of this call, already labeled", context]
    parts += ["", "## Opening transcript", opening]
    return "\n".join(parts)


def parse_response(resp: dict, speakers: list[str]) -> tuple[dict[str, str], str, str]:
    """Return (mapping, confidence, reason). Anything odd lowers confidence."""
    mapping: dict[str, str] = {}
    items = resp.get("speakers")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("role") in ROLES:
                mapping[str(item.get("speaker"))] = item["role"]
    elif isinstance(resp.get("mapping"), dict):
        mapping = {str(k): v for k, v in resp["mapping"].items() if v in ROLES}

    confidence = "high" if resp.get("confidence") == "high" else "low"
    reason = str(resp.get("reason") or "").strip()
    mapping = {k: v for k, v in mapping.items() if k in speakers}
    for spk in speakers:
        if spk not in mapping:
            mapping[spk] = "PROSPECT"
            confidence = "low"
    roles = set(mapping.values())
    if "REP" not in roles or ("PROSPECT" not in roles and len(speakers) > 1):
        confidence = "low"
    return mapping, confidence, reason


def manual_mapping(speakers: list[str], rep_speaker: str) -> dict[str, str]:
    """The user said which speaker is the rep. Everyone else is the prospect."""
    reps = [s.strip() for s in rep_speaker.split(",") if s.strip()]
    unknown = [s for s in reps if s not in speakers]
    if unknown:
        raise CoachError(
            f"This call has no speaker called {', '.join(unknown)}. It has: {', '.join(speakers)}.",
            f"Use one of those, for example --rep-speaker {speakers[-1]}",
        )
    return {s: ("REP" if s in reps else "PROSPECT") for s in speakers}


def apply_mapping(utterances: list[dict], mapping: dict[str, str]) -> list[dict]:
    """Set each utterance's role. Text, times, and speaker ids are copied untouched."""
    return [{**u, "role": mapping.get(u["speaker"], "PROSPECT")} for u in utterances]
