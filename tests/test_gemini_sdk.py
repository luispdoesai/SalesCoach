"""The live Gemini code path, run against the real google-genai SDK with a fake network.

No request leaves the machine. httpx is patched to answer like the API does,
so this checks request shapes, response parsing, retries, and error mapping.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from coach import gemini
from coach.friendly import CoachError
from coach.gemini import AudioHandle, GeminiFatal, RealGemini

MODELS = {"transcribe": "gemini-3.5-transcribe", "relabel": "gemini-3.5-flash-lite", "tone": "gemini-3.8-flash"}
TEXT = "Hi, is this Jordan? Yes."


def _transcript_response():
    words = []
    for spk, word in [("spk_1", "Hi"), ("spk_1", "is"), ("spk_1", "this"), ("spk_1", "Jordan"), ("spk_2", "Yes")]:
        i = TEXT.find(word, words[-1]["end_index"] if words else 0)
        words.append({"type": "word_info", "text": word, "speaker": spk, "start_offset": f"{len(words) * 0.5:.3f}s",
                      "end_offset": f"{len(words) * 0.5 + 0.4:.3f}s", "start_index": i, "end_index": i + len(word)})
    return {"id": "i1", "status": "completed", "model": MODELS["transcribe"],
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": TEXT, "annotations": words}]}]}


def _json_response(payload):
    return {"id": "i2", "status": "completed", "model": MODELS["relabel"],
            "steps": [{"type": "model_output", "content": [{"type": "text", "text": json.dumps(payload)}]}]}


class FakeNet:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def send(self, client, request, **kw):
        self.requests.append(json.loads(request.content or b"{}"))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        status, body = item
        return httpx.Response(status, json=body, request=request)


@pytest.fixture
def net(monkeypatch):
    def install(*responses):
        fake = FakeNet(responses)
        monkeypatch.setattr(httpx.Client, "send", lambda self, request, **kw: fake.send(self, request, **kw))
        monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
        return fake
    return install


def _client():
    return RealGemini("fake-key", MODELS)


HANDLE = AudioHandle(uri="https://generativelanguage.googleapis.com/v1beta/files/abc", mime_type="audio/m4a")


def test_transcribe_request_and_parse(net):
    fake = net((200, _transcript_response()))
    raw = _client().transcribe(HANDLE)
    body = fake.requests[0]
    assert body["model"] == "gemini-3.5-transcribe"
    mode = body["generation_config"]["transcription_config"]["mode"]
    assert mode == {"type": "verbatim", "diarization_mode": "speaker", "timestamp_granularities": ["word"]}
    assert "custom_vocabulary" not in json.dumps(body)  # cannot be combined with diarization
    assert raw.text == TEXT
    assert [w["text"] for w in raw.words] == ["Hi", "is", "this", "Jordan", "Yes"]
    assert raw.words[1]["start"] == 0.5 and raw.words[4]["speaker"] == "spk_2"


def test_transcript_builds_punctuated_utterances(net):
    from coach.transcribe import build_utterances

    net((200, _transcript_response()))
    raw = _client().transcribe(HANDLE)
    assert [u["text"] for u in build_utterances(raw.words, raw.text)] == ["Hi, is this Jordan?", "Yes."]


def test_language_codes_are_sent(net):
    fake = net((200, _transcript_response()))
    RealGemini("k", MODELS, ["es-ES"]).transcribe(HANDLE)
    assert fake.requests[0]["generation_config"]["transcription_config"]["language_codes"] == ["es-ES"]


def test_json_call_with_schema_and_audio(net):
    fake = net((200, _json_response({"speakers": [], "confidence": "low"})))
    out = _client().json("tone", "prompt", {"type": "object"}, audio=HANDLE)
    assert out == {"speakers": [], "confidence": "low"}
    body = fake.requests[0]
    assert body["model"] == "gemini-3.8-flash"
    assert body["response_format"]["type"] == "text" and body["response_format"]["schema"] == {"type": "object"}
    kinds = [c["type"] for c in body["input"][0]["content"]]
    assert kinds == ["text", "audio"]


def test_json_falls_back_to_other_format_on_400(net):
    fake = net((400, {"error": {"code": 400, "message": "bad response_format"}}),
               (200, _json_response({"ok": True})))
    assert _client().json("relabel", "p", {"type": "object"}) == {"ok": True}
    assert fake.requests[1]["response_mime_type"] == "application/json"
    assert fake.requests[1]["response_format"] == {"type": "object"}


def test_non_json_output_is_friendly(net):
    bad = _json_response({})
    bad["steps"][0]["content"][0]["text"] = "Sorry, I cannot help."
    net((200, bad))
    with pytest.raises(CoachError, match="not valid JSON"):
        _client().json("relabel", "p", {})


@pytest.mark.parametrize("status,fatal,words", [(401, True, "API key"), (404, True, "does not recognize"),
                                                (400, False, "refused")])
def test_http_errors(net, status, fatal, words):
    net(*[(status, {"error": {"code": status, "message": "nope"}})] * 4)
    with pytest.raises(CoachError) as err:
        _client().transcribe(HANDLE)
    assert isinstance(err.value, GeminiFatal) == fatal and words in err.value.problem


def test_server_errors_retry_then_succeed(net):
    fake = net((503, {"error": {"code": 503, "message": "busy"}}), (200, _transcript_response()))
    assert _client().transcribe(HANDLE).text == TEXT
    assert len(fake.requests) >= 2


def test_network_down_is_fatal(net):
    net(*[httpx.ConnectError("no route")] * 10)
    with pytest.raises(GeminiFatal, match="Could not reach"):
        _client().transcribe(HANDLE)


def test_upload_waits_for_processing_and_delete_never_raises(monkeypatch):
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)
    c = _client()
    states = iter(["PROCESSING", "ACTIVE"])
    f = lambda state: SimpleNamespace(name="files/abc", uri="u", mime_type="audio/m4a", state=state)  # noqa: E731
    monkeypatch.setattr(c.client.files, "upload", lambda **kw: f("PROCESSING"))
    monkeypatch.setattr(c.client.files, "get", lambda **kw: f(next(states)))
    handle = c.upload(__import__("pathlib").Path("x.m4a"), "audio/m4a")
    assert handle.name == "files/abc"

    def boom(**kw):
        raise RuntimeError("already gone")
    monkeypatch.setattr(c.client.files, "delete", boom)
    c.delete(handle)  # cleanup failures are swallowed


def test_failed_upload_is_friendly(monkeypatch):
    c = _client()
    monkeypatch.setattr(c.client.files, "upload",
                        lambda **kw: SimpleNamespace(name="files/x", uri="u", mime_type="a", state="FAILED"))
    with pytest.raises(CoachError, match="could not process"):
        c.upload(__import__("pathlib").Path("x.m4a"), "audio/m4a")
