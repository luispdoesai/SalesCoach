"""Tone hints: one short read on the rep and the prospect per time window.

These come from an audio model listening to the call. They are hints, not
facts, and every place that shows them says so. If this step fails, the
transcript is still saved without tone notes.
"""

from __future__ import annotations

from coach.callfile import fmt_ts

SCHEMA = {
    "type": "object",
    "properties": {
        "windows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                    "rep_tone": {"type": "string"},
                    "prospect_tone": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["start", "end", "rep_tone", "prospect_tone", "note"],
            },
        }
    },
    "required": ["windows"],
}

PROMPT = """You are listening to a recorded sales call between a sales rep (REP) and a buyer (PROSPECT).
Give tone hints in {window}-second windows from 0 to {duration} seconds: 0-{window}, {window}-{window2}, and so on.

For each window return:
- start and end in whole seconds
- rep_tone: one or two plain words for how the rep sounds (for example warm, rushed, flat, confident, nervous)
- prospect_tone: one or two plain words for how the prospect sounds (for example guarded, engaged, impatient, warm)
- note: one short sentence on anything notable you hear (pace, pauses, interruptions, energy shifts). Under 15 words.

Judge from the voices, not only the words. If a side is silent in a window, use "silent".
These are hints for a coach to verify later. Do not invent events you cannot hear.

Here is how the call opens, so you know which voice is the rep:
{sample}

Return JSON only: {{"windows": [{{"start": 0, "end": {window}, "rep_tone": "...", "prospect_tone": "...", "note": "..."}}]}}"""


def build_prompt(utterances: list[dict], duration: float, window_sec: int, offset: float = 0.0) -> str:
    sample = "\n".join(
        f"[{fmt_ts(u['start'] - offset)}] {u['role']}: {u['text']}" for u in utterances[:6]
    )
    return PROMPT.format(window=window_sec, window2=window_sec * 2,
                         duration=int(round(duration)), sample=sample)


def _clean(value, limit: int) -> str:
    # A pipe would break the Tone Notes line format.
    text = " ".join(str(value or "").replace("|", "/").split())
    return text[:limit]


def clean_windows(resp: dict, duration: float, offset: float = 0.0) -> list[dict]:
    """Keep well-formed windows inside the call, shifted by offset, sorted by start."""
    out = []
    for w in (resp or {}).get("windows") or []:
        if not isinstance(w, dict):
            continue
        try:
            start, end = float(w["start"]), float(w["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start or start < 0 or start >= duration + 1:
            continue
        out.append({
            "start": int(round(start + offset)),
            "end": int(round(min(end, duration) + offset)),
            "rep_tone": _clean(w.get("rep_tone"), 30),
            "prospect_tone": _clean(w.get("prospect_tone"), 30),
            "note": _clean(w.get("note"), 160),
        })
    return sorted(out, key=lambda w: w["start"])
