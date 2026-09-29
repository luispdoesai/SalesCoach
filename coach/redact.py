"""Optional, best-effort redaction of transcript text.

Turn it on in config.yaml (redact.enabled). It masks email addresses,
phone numbers, and any names you list. It will miss things: names you did
not list, numbers read out as words, spelled-out emails. Review the output.
Redaction happens after transcription, so Google still receives the audio.
"""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# 7 or more digits with optional separators, an optional +country code and (area code).
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{2,4}(?:[\s.-]?\d{2,4}){1,3}(?!\w)")

EMAIL_MASK = "[EMAIL]"
PHONE_MASK = "[PHONE]"
NAME_MASK = "[NAME]"


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _digit_count(text: str) -> int:
    return sum(c.isdigit() for c in text)


def _mask_phone(match: re.Match) -> str:
    found = match.group()
    if _digit_count(found) < 7 or DATE_RE.match(found.strip()):
        return found
    return PHONE_MASK


class Redactor:
    def __init__(self, settings: dict):
        self.enabled = bool(settings.get("enabled"))
        self.emails = bool(settings.get("emails", True))
        self.phones = bool(settings.get("phone_numbers", True))
        names = [str(n).strip() for n in settings.get("names") or [] if str(n).strip()]
        # Longest first, so "Jordan Diaz" is masked before "Jordan".
        names.sort(key=len, reverse=True)
        self.name_res = [re.compile(r"(?<!\w)" + re.escape(n) + r"(?!\w)", re.IGNORECASE) for n in names]
        # Single words of listed names, used on word-level data.
        self.name_tokens = {part.lower() for n in names for part in n.split() if len(part) >= 3}

    def text(self, text: str) -> str:
        if not self.enabled:
            return text
        if self.emails:
            text = EMAIL_RE.sub(EMAIL_MASK, text)
        if self.phones:
            text = PHONE_RE.sub(_mask_phone, text)
        for name_re in self.name_res:
            text = name_re.sub(NAME_MASK, text)
        return text

    def word(self, word: str) -> str:
        """Redact a single transcribed word."""
        if not self.enabled:
            return word
        if self.emails and EMAIL_RE.search(word):
            return EMAIL_MASK
        if self.phones and _digit_count(word) >= 7 and not DATE_RE.match(word.strip(".,")):
            return PHONE_MASK
        if word.strip(".,!?;:'\"").lower() in self.name_tokens:
            return NAME_MASK
        return word
