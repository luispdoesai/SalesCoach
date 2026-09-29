"""Transcription pipeline, all offline with MockGemini."""

from __future__ import annotations

import json

import pytest

from coach import callfile, relabel, tone
from coach import transcribe as tr
from coach.config import DEFAULTS
from coach.friendly import CoachError
from coach.gemini import GeminiFatal, MockGemini, RawTranscript, friendly_api_error, parse_json_text, parse_offset
from coach.workspace import init_workspace

CALL = "2026-09-28_JD_Discovery"


# Utterance building

def _words(spec):
    return [{"speaker": s, "start": a, "end": b, "text": t} for s, a, b, t in spec]


def test_consecutive_same_speaker_words_merge():
    words = _words([("spk_1", 0, 0.3, "Hi"), ("spk_1", 0.4, 0.8, "there"),
                    ("spk_2", 1.0, 1.4, "Hello"), ("spk_1", 2.0, 2.3, "Okay")])
    utts = tr.build_utterances(words)
    assert [(u["speaker"], u["text"]) for u in utts] == [("spk_1", "Hi there"), ("spk_2", "Hello"), ("spk_1", "Okay")]
    assert utts[0]["start"] == 0 and utts[0]["end"] == 0.8


def test_punctuation_recovered_from_text_with_byte_offsets():
    text = "Hi, is this Jordan? Yes, it’s me."
    b = text.encode()
    words = []
    for spk, word in [("spk_1", "Hi"), ("spk_1", "is"), ("spk_1", "this"), ("spk_1", "Jordan"),
                      ("spk_2", "Yes"), ("spk_2", "it’s"), ("spk_2", "me")]:
        i = b.find(word.encode(), words[-1]["end_index"] if words else 0)
        words.append({"speaker": spk, "start": len(words), "end": len(words) + 0.5, "text": word,
                      "start_index": i, "end_index": i + len(word.encode())})
    utts = tr.build_utterances(words, text)
    assert [u["text"] for u in utts] == ["Hi, is this Jordan?", "Yes, it’s me."]


def test_punctuation_recovered_without_offsets_and_labels_stripped():
    text = "spk_1: Hi, is this Jordan?\nspk_2: Yes. Who is this?"
    words = _words([("spk_1", 0, 1, "Hi"), ("spk_1", 1, 2, "is"), ("spk_1", 2, 3, "this"), ("spk_1", 3, 4, "Jordan"),
                    ("spk_2", 5, 6, "Yes"), ("spk_2", 6, 7, "Who"), ("spk_2", 7, 8, "is"), ("spk_2", 8, 9, "this")])
    utts = tr.build_utterances(words, text)
    assert [u["text"] for u in utts] == ["Hi, is this Jordan?", "Yes. Who is this?"]


def test_bad_offsets_fall_back_to_search():
    text = "Hello there. Hi."
    words = [{"speaker": "spk_1", "start": 0, "end": 1, "text": "Hello", "start_index": 99, "end_index": 104},
             {"speaker": "spk_1", "start": 1, "end": 2, "text": "there", "start_index": 3, "end_index": 8},
             {"speaker": "spk_2", "start": 3, "end": 4, "text": "Hi", "start_index": 1, "end_index": 3}]
    assert [u["text"] for u in tr.build_utterances(words, text)] == ["Hello there.", "Hi."]


def test_words_without_timestamps_are_dropped():
    words = [{"speaker": "spk_1", "start": None, "end": None, "text": "ghost"},
             {"speaker": None, "start": 1.0, "end": 1.5, "text": "real"}]
    utts = tr.build_utterances(words)
    assert [u["text"] for u in utts] == ["real"]
    assert tr.build_utterances([]) == []


# Relabel

UTTS = [{"speaker": "spk_1", "role": "", "start": 0, "end": 2, "text": "Orsolo Freight, this is Jordan."},
        {"speaker": "spk_2", "role": "", "start": 2.5, "end": 9, "text": "Hi Jordan, this is Sam from Vantrellis."}]


def test_apply_mapping_changes_roles_not_text():
    before = json.dumps(UTTS)
    out = relabel.apply_mapping(UTTS, {"spk_1": "PROSPECT", "spk_2": "REP"})
    assert [u["role"] for u in out] == ["PROSPECT", "REP"]
    assert [(u["speaker"], u["start"], u["end"], u["text"]) for u in out] == \
           [(u["speaker"], u["start"], u["end"], u["text"]) for u in UTTS]
    assert json.dumps(UTTS) == before


def test_parse_response_forms():
    speakers = ["spk_1", "spk_2"]
    m, c, _ = relabel.parse_response({"speakers": [{"speaker": "spk_2", "role": "REP"},
                                                   {"speaker": "spk_1", "role": "PROSPECT"}],
                                      "confidence": "high"}, speakers)
    assert m == {"spk_1": "PROSPECT", "spk_2": "REP"} and c == "high"
    m, c, _ = relabel.parse_response({"mapping": {"spk_1": "REP", "spk_2": "PROSPECT"}, "confidence": "high"}, speakers)
    assert m["spk_1"] == "REP" and c == "high"


@pytest.mark.parametrize("resp", [
    {"speakers": [{"speaker": "spk_2", "role": "REP"}], "confidence": "high"},           # one speaker missing
    {"speakers": [{"speaker": "spk_1", "role": "PROSPECT"}, {"speaker": "spk_2", "role": "PROSPECT"}],
     "confidence": "high"},                                                                # nobody is the rep
    {"speakers": [{"speaker": "spk_1", "role": "REP"}, {"speaker": "spk_2", "role": "REP"}],
     "confidence": "high"},                                                                # everybody is the rep
    {"speakers": [{"speaker": "spk_1", "role": "PROSPECT"}, {"speaker": "spk_2", "role": "REP"}],
     "confidence": "medium"},                                                              # unknown confidence
])
def test_parse_response_lowers_confidence_when_odd(resp):
    assert relabel.parse_response(resp, ["spk_1", "spk_2"])[1] == "low"


def test_manual_mapping():
    assert relabel.manual_mapping(["spk_1", "spk_2"], "spk_1") == {"spk_1": "REP", "spk_2": "PROSPECT"}
    with pytest.raises(CoachError) as err:
        relabel.manual_mapping(["spk_1", "spk_2"], "spk_9")
    assert "spk_1, spk_2" in err.value.problem


def test_relabel_prompt_contains_only_the_opening():
    opening = UTTS + [{**u, "start": u["start"] + 10, "end": u["end"] + 10} for u in UTTS]
    long = opening + [{"speaker": "spk_1", "role": "", "start": 400, "end": 402, "text": "SECRET LATE LINE"}] * 5
    prompt = relabel.build_prompt(relabel.opening_lines(long, 120), "Sam", "Vantrellis")
    assert "SECRET LATE LINE" not in prompt
    assert "Rep name: Sam" in prompt and "JSON only" in prompt


# Tone

def test_clean_windows():
    resp = {"windows": [
        {"start": 60, "end": 120, "rep_tone": "warm | x", "prospect_tone": "guarded", "note": "n"},
        {"start": 0, "end": 60, "rep_tone": "warm", "prospect_tone": "guarded", "note": "n"},
        {"start": 90, "end": 30, "rep_tone": "bad", "prospect_tone": "bad", "note": "end before start"},
        {"start": 500, "end": 560, "rep_tone": "x", "prospect_tone": "x", "note": "past the end"},
        "junk",
    ]}
    out = tone.clean_windows(resp, duration=100, offset=1500)
    assert [(w["start"], w["end"]) for w in out] == [(1500, 1560), (1560, 1600)]
    assert "|" not in out[1]["rep_tone"]


# Gemini helpers

def test_parse_offset():
    assert parse_offset("0.100s") == 0.1 and parse_offset(2) == 2.0
    assert parse_offset({"seconds": 1, "nanos": 500_000_000}) == 1.5 and parse_offset("bad") is None


def test_parse_json_text():
    assert parse_json_text('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_text('Here you go: {"a": 1}') == {"a": 1}


class FakeAPIError(Exception):
    def __init__(self, code):
        super().__init__(f"Error code: {code} - {{'error': {{'message': 'boom'}}}}")
        self.status_code = code


@pytest.mark.parametrize("code,fatal,words", [
    (401, True, "API key"), (403, True, "API key"), (404, True, "does not recognize"),
    (429, True, "rate limit"), (400, False, "boom"), (503, False, "server problem"),
])
def test_friendly_api_errors(code, fatal, words):
    err = friendly_api_error(FakeAPIError(code), "transcribing", "gemini-x")
    assert isinstance(err, GeminiFatal) == fatal
    assert words in err.problem


def test_non_api_error_is_not_swallowed():
    assert friendly_api_error(ValueError("x"), "transcribing", "m") is None


# Chunk planning

def test_plan_chunks():
    assert tr.plan_chunks(None, 1800, 1500) == [(0.0, None)]
    assert tr.plan_chunks(1700, 1800, 1500) == [(0.0, None)]
    assert tr.plan_chunks(3700, 1800, 1500) == [(0.0, 1500), (1500.0, 1500), (3000.0, 700)]


# End to end with the mock

@pytest.fixture
def ws(workspace):
    init_workspace(workspace)
    return workspace


def _cfg(**over):
    cfg = json.loads(json.dumps(DEFAULTS))
    for k, v in over.items():
        cfg[k].update(v)
    return cfg


def _drop(ws, name=f"{CALL}.m4a"):
    p = ws.inbox / name
    p.write_bytes(b"placeholder")
    return p


def test_mock_transcribe_end_to_end(ws, capsys):
    _drop(ws)
    t = tr.Transcriber(ws, _cfg(), mock=True)
    assert t.run() == 0
    raw = json.loads((ws.raw / f"{CALL}.json").read_text())
    assert raw["speaker_mapping"] == {"spk_1": "PROSPECT", "spk_2": "REP"}
    assert raw["mapping_confidence"] == "high"
    assert raw["words"] and raw["utterances"][0]["role"] == "PROSPECT"
    assert set(raw) >= {"call_id", "audio_file", "duration_sec", "transcribe_model", "utterances",
                        "words", "speaker_mapping", "mapping_confidence", "tone_windows"}
    cf = callfile.read(ws.calls / f"{CALL}.md")
    assert cf.meta["rep_speaker"] == "spk_2" and cf.meta["needs_review"] is False
    assert cf.lines[1].text.startswith("Hi Jordan, this is Sam from Vantrellis.")
    assert "?" in cf.lines[1].text
    assert (ws.processed / f"{CALL}.m4a").exists() and not (ws.inbox / f"{CALL}.m4a").exists()
    # Every upload was deleted from Google's storage.
    assert t.backend.uploaded and t.backend.deleted == t.backend.uploaded


def test_mock_text_matches_fixture_exactly(ws):
    _drop(ws)
    tr.Transcriber(ws, _cfg(), mock=True).run()
    fixture = json.loads((tr.MockGemini().mock_dir / "transcript.json").read_text())["utterances"]
    raw = json.loads((ws.raw / f"{CALL}.json").read_text())
    assert [u["text"] for u in raw["utterances"]] == [u["text"] for u in fixture]


def test_rerun_skips_finished_work(ws, capsys):
    _drop(ws)
    tr.Transcriber(ws, _cfg(), mock=True).run()
    before = (ws.calls / f"{CALL}.md").read_text()
    _drop(ws)  # the same recording shows up again
    t = tr.Transcriber(ws, _cfg(), mock=True)
    assert t.run() == 0
    assert "Already transcribed" in capsys.readouterr().out
    assert t._backend is None  # no API work at all
    assert (ws.calls / f"{CALL}.md").read_text() == before
    assert t.counts["skipped"] == 1


def test_duplicate_recording_is_removed_not_piled_up(ws, capsys):
    _drop(ws)
    tr.Transcriber(ws, _cfg(), mock=True).run()
    _drop(ws)  # identical file again
    tr.Transcriber(ws, _cfg(), mock=True).run()
    assert "Removed a duplicate" in capsys.readouterr().out
    assert sorted(p.name for p in ws.processed.iterdir()) == [f"{CALL}.m4a"]
    assert not (ws.inbox / f"{CALL}.m4a").exists()


def test_different_file_with_same_name_is_kept(ws):
    _drop(ws)
    tr.Transcriber(ws, _cfg(), mock=True).run()
    (ws.inbox / f"{CALL}.m4a").write_bytes(b"a different recording")
    tr.Transcriber(ws, _cfg(), mock=True).run()
    assert sorted(p.name for p in ws.processed.iterdir()) == [f"{CALL}.m4a", f"{CALL}_1.m4a"]


def test_rep_speaker_fixes_labels_without_api(ws, capsys):
    _drop(ws)
    tr.Transcriber(ws, _cfg(), mock=True).run()
    path = ws.calls / f"{CALL}.md"
    path.write_text(callfile.replace_email_block(path.read_text(), "- pulled email summary"))
    old = callfile.read(path)

    t = tr.Transcriber(ws, _cfg(), mock=False, rep_speaker="spk_1")
    assert t.run(file=CALL) == 0
    assert t._backend is None
    new = callfile.read(path)
    assert [ln.text for ln in new.lines] == [ln.text for ln in old.lines]
    assert [ln.role for ln in new.lines] == ["REP" if r == "PROSPECT" else "PROSPECT" for r in (ln.role for ln in old.lines)]
    assert new.meta["speaker_mapping_confidence"] == "manual" and new.meta["rep_speaker"] == "spk_1"
    assert new.email_block == "- pulled email summary"


def test_force_retranscribes_from_processed_and_keeps_email(ws):
    _drop(ws)
    tr.Transcriber(ws, _cfg(), mock=True).run()
    path = ws.calls / f"{CALL}.md"
    path.write_text(callfile.replace_email_block(path.read_text(), "- kept"))
    t = tr.Transcriber(ws, _cfg(), mock=True, force=True)
    assert t.run(file=CALL) == 0 and t.counts["transcribed"] == 1
    assert callfile.read(path).email_block == "- kept"


def test_misnamed_file_skipped_unless_yes(ws, capsys):
    _drop(ws, "Zoom call 3.m4a")
    t = tr.Transcriber(ws, _cfg(), mock=True)
    assert t.run() == 0 and t.counts["skipped"] == 1
    assert "2026-09-28_JD_Discovery.m4a" in capsys.readouterr().out
    t = tr.Transcriber(ws, _cfg(), mock=True, yes=True)
    assert t.run() == 0
    assert (ws.calls / "Zoom_call_3.md").exists()


def test_redaction_applies_to_call_file_and_raw(ws):
    _drop(ws)
    tr.Transcriber(ws, _cfg(redact={"enabled": True, "names": ["Jordan"]}), mock=True).run()
    text = (ws.calls / f"{CALL}.md").read_text()
    raw = (ws.raw / f"{CALL}.json").read_text()
    assert "Jordan" not in text.split("# Transcript")[1] and "[NAME]" in text
    assert "Jordan" not in raw


class LowConfidenceMock(MockGemini):
    def json(self, model_key, prompt, schema, audio=None, kind=""):
        if model_key == "relabel":
            return {"speakers": [{"speaker": "spk_1", "role": "REP"}, {"speaker": "spk_2", "role": "PROSPECT"}],
                    "confidence": "low", "reason": "cues conflict"}
        raise RuntimeError("tone service down")


def test_low_confidence_marks_review_and_tone_failure_is_ok(ws, capsys):
    _drop(ws)
    t = tr.Transcriber(ws, _cfg(), mock=True)
    t._backend = LowConfidenceMock()
    assert t.run() == 0
    out = capsys.readouterr().out
    cf = callfile.read(ws.calls / f"{CALL}.md")
    assert cf.meta["needs_review"] is True
    assert "--rep-speaker spk_2" in out
    assert "Tone hints failed" in out
    assert callfile.NO_TONE in cf.tone_text


class FatalMock(MockGemini):
    def transcribe(self, handle):
        raise GeminiFatal("Google rejected your Gemini API key.", "Check .env")


def test_fatal_error_stops_the_run(ws, capsys):
    _drop(ws, "2026-09-28_AA_Demo.m4a")
    _drop(ws, "2026-09-29_BB_Demo.m4a")
    t = tr.Transcriber(ws, _cfg(), mock=True)
    t._backend = FatalMock()
    assert t.run() == 1
    assert t.counts["failed"] == 1
    assert "API key" in capsys.readouterr().err
    assert (ws.inbox / "2026-09-29_BB_Demo.m4a").exists()
    assert t._backend.deleted == t._backend.uploaded


class ChunkMock(MockGemini):
    def json(self, model_key, prompt, schema, audio=None, kind=""):
        if model_key == "relabel":
            prefix = "c2_" if "c2_spk_" in prompt else ""
            return {"speakers": [{"speaker": f"{prefix}spk_1", "role": "PROSPECT"},
                                 {"speaker": f"{prefix}spk_2", "role": "REP"}], "confidence": "high"}
        return super().json(model_key, prompt, schema, audio, kind)


def test_long_recording_is_split_with_offsets(ws, monkeypatch):
    _drop(ws)
    monkeypatch.setattr(tr, "probe_duration", lambda p: 1700.0)
    monkeypatch.setattr(tr, "has_ffmpeg", lambda: True)
    monkeypatch.setattr(tr, "ffmpeg_extract", lambda src, dst, start=None, length=None: src)
    t = tr.Transcriber(ws, _cfg(transcribe={"max_minutes": 20, "chunk_minutes": 15}), mock=False)
    t._backend = ChunkMock()
    assert t.run() == 0
    raw = json.loads((ws.raw / f"{CALL}.json").read_text())
    assert [c["offset_sec"] for c in raw["chunks"]] == [0.0, 900.0]
    second = [u for u in raw["utterances"] if u["speaker"].startswith("c2_")]
    assert second and second[0]["start"] >= 900
    assert raw["speaker_mapping"]["c2_spk_2"] == "REP"
    starts = [u["start"] for u in raw["utterances"]]
    assert starts == sorted(starts)
    assert len(t._backend.uploaded) == 2 == len(t._backend.deleted)


def test_long_recording_without_ffmpeg_fails_clearly(ws, monkeypatch, capsys):
    _drop(ws)
    monkeypatch.setattr(tr, "probe_duration", lambda p: 4000.0)
    monkeypatch.setattr(tr, "has_ffmpeg", lambda: False)
    t = tr.Transcriber(ws, _cfg(), mock=False)
    t._backend = MockGemini()
    assert t.run() == 1
    err = capsys.readouterr().err
    assert "67 minutes" in err and "ffmpeg" in err
    assert (ws.inbox / f"{CALL}.m4a").exists()


def test_missing_key_is_friendly(ws, capsys):
    _drop(ws, "2026-09-28_AA_Demo.m4a")
    _drop(ws, "2026-09-29_BB_Demo.m4a")
    t = tr.Transcriber(ws, _cfg(), mock=False)
    assert t.run() == 1
    err = capsys.readouterr().err
    assert "GEMINI_API_KEY" in err and err.count("Problem:") == 1


def test_empty_inbox_is_not_an_error(ws, capsys):
    assert tr.Transcriber(ws, _cfg(), mock=True).run() == 0
    assert "No recordings" in capsys.readouterr().out


def test_no_data_folder(workspace):
    with pytest.raises(CoachError) as err:
        tr.Transcriber(workspace, _cfg(), mock=True).run()
    assert "init" in err.value.fix


def test_rep_speaker_needs_file(ws):
    with pytest.raises(CoachError):
        tr.Transcriber(ws, _cfg(), mock=True, rep_speaker="spk_1").run()


def test_mock_raw_transcript_shape():
    raw = MockGemini().transcribe(None)
    assert isinstance(raw, RawTranscript) and raw.words[0]["start_index"] == 0
