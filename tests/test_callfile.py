"""Call file format, names, timestamps, redaction."""

from __future__ import annotations

import pytest

from coach import callfile
from coach.callfile import fmt_ts, parse_call_name, parse_ts
from coach.redact import Redactor


def test_valid_name():
    n = parse_call_name("2026-09-28_JD_Discovery")
    assert n.valid and n.date == "2026-09-28" and n.prospect_initials == "JD" and n.stage == "Discovery"


def test_lowercase_initials_are_uppercased():
    assert parse_call_name("2026-09-28_jd_Demo").prospect_initials == "JD"


@pytest.mark.parametrize("stem", [
    "Zoom recording 3", "2026-13-40_JD_Discovery", "2026-09-28_JD", "28-09-2026_JD_Discovery",
    "2026-09-28_J1_Discovery",
])
def test_invalid_names(stem):
    n = parse_call_name(stem)
    assert not n.valid
    assert n.call_id and " " not in n.call_id


def test_safe_call_id():
    assert callfile.safe_call_id("Zoom recording (3)") == "Zoom_recording_3"


@pytest.mark.parametrize("seconds,text", [(0, "00:00"), (59.9, "00:59"), (751, "12:31"), (3600, "1:00:00"), (3725, "1:02:05")])
def test_fmt_ts(seconds, text):
    assert fmt_ts(seconds) == text


@pytest.mark.parametrize("text,seconds", [("12:31", 751), ("[12:31]", 751), ("1:02:05", 3725), (90, 90), ("45", 45)])
def test_parse_ts(text, seconds):
    assert parse_ts(text) == seconds


@pytest.mark.parametrize("bad", ["abc", "12:xx", "", True, "1:2:3:4"])
def test_parse_ts_rejects(bad):
    with pytest.raises(ValueError):
        parse_ts(bad)


UTTS = [
    {"speaker": "spk_2", "role": "REP", "start": 0.4, "end": 6.9, "text": "Hi, this is Sam.\nHow are you?"},
    {"speaker": "spk_1", "role": "PROSPECT", "start": 7.2, "end": 9.0, "text": "Good, thanks."},
    {"speaker": "spk_2", "role": "REP", "start": 3700, "end": 3702, "text": "Late in the call."},
]
META = {"call_id": "2026-09-28_JD_Discovery", "date": "2026-09-28", "prospect_initials": "JD",
        "stage": "Discovery", "duration_sec": 3702.4, "source_audio": "x.m4a", "rep_speaker": "spk_2",
        "speaker_mapping_confidence": "high", "needs_review": False}
TONE = [{"start": 0, "end": 60, "rep_tone": "warm", "prospect_tone": "guarded", "note": "short answers"}]


def test_round_trip():
    text = callfile.render(META, UTTS, TONE)
    cf = callfile.parse(text)
    assert cf.meta["call_id"] == "2026-09-28_JD_Discovery"
    assert cf.meta["duration_sec"] == 3702
    assert cf.meta["needs_review"] is False
    assert cf.meta["date"] == "2026-09-28"
    assert [(line.role, line.text) for line in cf.lines] == [
        ("REP", "Hi, this is Sam. How are you?"), ("PROSPECT", "Good, thanks."), ("REP", "Late in the call.")]
    assert cf.lines[2].start == 3700
    assert "[1:01:40] REP: Late in the call." in text
    assert "00:00-01:00 | REP: warm | PROSPECT: guarded | note: short answers" in cf.tone_text
    assert cf.email_block == "Not yet pulled."
    assert callfile.render(cf.meta, [{"start": ln.start, "role": ln.role, "text": ln.text} for ln in cf.lines],
                           TONE) == text


def test_tone_caveat_always_present():
    assert callfile.TONE_CAVEAT in callfile.render(META, UTTS, [])
    assert callfile.NO_TONE in callfile.render(META, UTTS, [])


def test_replace_email_block_touches_only_the_block():
    text = callfile.render(META, UTTS, TONE)
    new = callfile.replace_email_block(text, "- 2026-09-20: prospect asked for pricing")
    assert callfile.parse(new).email_block == "- 2026-09-20: prospect asked for pricing"
    assert new.split("# Email History")[0] == text.split("# Email History")[0]


def test_atomic_write(tmp_path):
    target = tmp_path / "sub" / "a.md"
    callfile.atomic_write(target, "hello")
    assert target.read_text() == "hello"
    assert not list(target.parent.glob(".tmp_*"))


def test_redaction():
    r = Redactor({"enabled": True, "names": ["Jordan Diaz", "Orsolo"]})
    out = r.text("Email jordan@orsolo.example or call (555) 123-4567. Jordan Diaz at Orsolo said 2026-09-28, $4,800.")
    assert "jordan@orsolo.example" not in out and "[EMAIL]" in out
    assert "123-4567" not in out and "[PHONE]" in out
    assert "Jordan Diaz" not in out and "Orsolo" not in out
    assert "2026-09-28" in out and "$4,800" in out
    assert r.word("Jordan,") == "[NAME]" and r.word("5551234567") == "[PHONE]" and r.word("hello") == "hello"


def test_redaction_off_changes_nothing():
    text = "Email jordan@orsolo.example"
    assert Redactor({"enabled": False, "names": ["Jordan"]}).text(text) == text
