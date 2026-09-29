"""Everything that talks to Google's Gemini API lives here.

Privacy: audio is uploaded to Google for transcription. The uploaded copy is
deleted from Google's file storage as soon as the call is done. The API key
is never printed.

MockGemini replays bundled fixtures from examples/mock/ so tests and demos
run with no network and no key.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from coach.config import REPO_ROOT
from coach.friendly import CoachError

MOCK_DIR = REPO_ROOT / "examples" / "mock"

# Audio formats Gemini accepts, by file extension.
MIME_TYPES = {
    ".m4a": "audio/m4a", ".mp3": "audio/mp3", ".wav": "audio/wav", ".aac": "audio/aac",
    ".ogg": "audio/ogg", ".oga": "audio/ogg", ".opus": "audio/opus", ".flac": "audio/flac",
    ".webm": "audio/webm", ".aif": "audio/aiff", ".aiff": "audio/aiff",
}

RETRYABLE = {429, 500, 502, 503, 504}


class GeminiFatal(CoachError):
    """A problem that will hit every file (bad key, wrong model, no internet). Stop the run."""


@dataclass
class AudioHandle:
    uri: str
    mime_type: str
    name: str | None = None


@dataclass
class RawTranscript:
    text: str
    words: list[dict] = field(default_factory=list)


def parse_offset(value: Any) -> float | None:
    """'0.100s' or 12.5 or {'seconds': 1, 'nanos': 5e8} to seconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        return float(value.get("seconds", 0)) + float(value.get("nanos", 0)) / 1e9
    text = str(value).strip().rstrip("s")
    try:
        return float(text)
    except ValueError:
        return None


def parse_json_text(text: str) -> Any:
    """Parse model output as JSON, tolerating code fences around it."""
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            return json.loads(cleaned[start:end + 1])
        raise


def _status(err: Exception) -> int | None:
    for attr in ("code", "status_code"):
        value = getattr(err, attr, None)
        if isinstance(value, int):
            return value
    return None


def _short_message(err: Exception) -> str:
    text = str(err)
    m = re.search(r"'message': '([^']*)'", text) or re.search(r'"message": "([^"]*)"', text)
    return (m.group(1) if m else text)[:200]


def _is_network(err: Exception) -> bool:
    names = " ".join(k.__name__ for k in type(err).__mro__)
    return any(w in names for w in ("ConnectError", "Connection", "Timeout", "TransportError"))


def friendly_api_error(err: Exception, doing: str, model: str | None) -> CoachError | None:
    """Turn an SDK error into a CoachError. None means it is not an API error."""
    status = _status(err)
    if status in (401, 403):
        return GeminiFatal("Google rejected your Gemini API key.",
                           "Check GEMINI_API_KEY in .env. Make a new key at https://aistudio.google.com/ if needed.")
    if status == 404:
        return GeminiFatal(f"Google does not recognize the model '{model}' (while {doing}).",
                           "Check current names at https://ai.google.dev/gemini-api/docs/models and update config.yaml.")
    if status == 429:
        return GeminiFatal("Gemini says you hit a rate limit or your quota.",
                           "Wait a few minutes and run the same command again. Finished calls are skipped.")
    if status is not None and 400 <= status < 500:
        return CoachError(f"Gemini refused the request while {doing}: {_short_message(err)}",
                          "Check the recording plays and is under 30 minutes. Run with --debug for details.")
    if status is not None and status >= 500:
        return CoachError(f"Gemini had a server problem while {doing}.",
                          "Wait a minute and run the same command again. Finished calls are skipped.")
    if _is_network(err):
        return GeminiFatal("Could not reach Google's servers.",
                           "Check your internet connection and run the same command again.")
    return None


class RealGemini:
    """The live API. Needs GEMINI_API_KEY."""

    def __init__(self, api_key: str, models: dict, language_codes: list[str] | None = None):
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.models = models
        self.language_codes = list(language_codes or [])
        self._json_style = "typed"

    def _call(self, fn, doing: str, model: str | None):
        delay = 3.0
        for attempt in range(3):
            try:
                return fn()
            except CoachError:
                raise
            except Exception as err:  # noqa: BLE001  mapped to friendly errors below
                if _status(err) in RETRYABLE and attempt < 2:
                    time.sleep(delay)
                    delay *= 3
                    continue
                friendly = friendly_api_error(err, doing, model)
                if friendly is None:
                    raise
                raise friendly from None

    def upload(self, path: Path, mime_type: str) -> AudioHandle:
        f = self._call(lambda: self.client.files.upload(file=str(path), config={"mime_type": mime_type}),
                       "uploading audio", None)
        # Wait until Google has finished processing the upload.
        for _ in range(60):
            state = str(getattr(f, "state", "") or "")
            if "PROCESSING" not in state:
                break
            time.sleep(2)
            f = self._call(lambda: self.client.files.get(name=f.name), "checking the upload", None)
        if "FAILED" in str(getattr(f, "state", "") or ""):
            raise CoachError("Google could not process this audio file.",
                             "Check that the recording plays on your computer, then try again.")
        return AudioHandle(uri=f.uri, mime_type=f.mime_type or mime_type, name=f.name)

    def delete(self, handle: AudioHandle) -> None:
        if not handle.name:
            return
        try:
            self.client.files.delete(name=handle.name)
        except Exception:  # noqa: BLE001  cleanup should never stop the run
            pass

    def transcribe(self, handle: AudioHandle) -> RawTranscript:
        model = self.models["transcribe"]
        transcription_config: dict[str, Any] = {
            # Diarization and word timestamps need verbatim mode.
            # Custom vocabulary and smart mode cannot be combined with them.
            "mode": {
                "type": "verbatim",
                "diarization_mode": "speaker",
                "timestamp_granularities": ["word"],
            },
        }
        if self.language_codes:
            transcription_config["language_codes"] = self.language_codes
        interaction = self._call(
            lambda: self.client.interactions.create(
                model=model,
                input=[{"type": "audio", "uri": handle.uri, "mime_type": handle.mime_type}],
                generation_config={"transcription_config": transcription_config},
            ),
            "transcribing", model,
        )
        return RawTranscript(text=interaction.output_text or "", words=extract_words(interaction))

    def json(self, model_key: str, prompt: str, schema: dict, audio: AudioHandle | None = None,
             kind: str = "") -> dict:
        model = self.models[model_key]
        parts: list[dict] = [{"type": "text", "text": prompt}]
        if audio is not None:
            parts.append({"type": "audio", "uri": audio.uri, "mime_type": audio.mime_type})

        def create(style: str):
            if style == "typed":
                fmt = {"response_format": {"type": "text", "mime_type": "application/json", "schema": schema}}
            else:
                fmt = {"response_format": schema, "response_mime_type": "application/json"}
            return self.client.interactions.create(model=model, input=parts, **fmt)

        doing = kind or "asking Gemini"
        try:
            interaction = self._call(lambda: create(self._json_style), doing, model)
        except GeminiFatal:
            raise
        except CoachError:
            # The API has accepted two shapes for JSON output over time. Try the other one.
            self._json_style = "plain" if self._json_style == "typed" else "typed"
            interaction = self._call(lambda: create(self._json_style), doing, model)
        try:
            return parse_json_text(interaction.output_text or "")
        except (json.JSONDecodeError, ValueError):
            raise CoachError(f"Gemini sent back something that is not valid JSON while {doing}.",
                             "Run the same command again. If it keeps happening, run with --debug.") from None


def extract_words(interaction: Any) -> list[dict]:
    """Pull word_info annotations out of an interaction response."""
    words = []
    for step in getattr(interaction, "steps", None) or []:
        for content in getattr(step, "content", None) or []:
            for ann in getattr(content, "annotations", None) or []:
                if getattr(ann, "type", None) != "word_info":
                    continue
                words.append({
                    "text": getattr(ann, "text", "") or "",
                    "speaker": getattr(ann, "speaker", None),
                    "start": parse_offset(getattr(ann, "start_offset", None)),
                    "end": parse_offset(getattr(ann, "end_offset", None)),
                    "start_index": getattr(ann, "start_index", None),
                    "end_index": getattr(ann, "end_index", None),
                })
    return words


class MockGemini:
    """Offline stand-in. Replays examples/mock/ fixtures. Synthetic data only."""

    def __init__(self, mock_dir: Path = MOCK_DIR):
        self.mock_dir = mock_dir
        self.uploaded: list[AudioHandle] = []
        self.deleted: list[AudioHandle] = []

    def _load(self, name: str) -> Any:
        return json.loads((self.mock_dir / name).read_text(encoding="utf-8"))

    def upload(self, path: Path, mime_type: str) -> AudioHandle:
        handle = AudioHandle(uri=f"mock://{path.name}", mime_type=mime_type, name=f"files/mock-{len(self.uploaded)}")
        self.uploaded.append(handle)
        return handle

    def delete(self, handle: AudioHandle) -> None:
        self.deleted.append(handle)

    def transcribe(self, handle: AudioHandle) -> RawTranscript:
        """Build word annotations the way the live API returns them.

        Words carry byte offsets into the full text and no punctuation, so the
        code path that recovers punctuation from the full text gets exercised.
        """
        script = self._load("transcript.json")["utterances"]
        text_parts: list[str] = []
        words: list[dict] = []
        cursor = 0
        for u in script:
            if text_parts:
                text_parts.append("\n")
                cursor += 1
            tokens = u["text"].split()
            step = (u["end"] - u["start"]) / max(len(tokens), 1)
            for i, token in enumerate(tokens):
                if i:
                    text_parts.append(" ")
                    cursor += 1
                bare = token.strip(".,!?;:")
                lead = len(token) - len(token.lstrip(".,!?;:"))
                start_byte = cursor + len(token[:lead].encode())
                words.append({
                    "text": bare,
                    "speaker": u["speaker"],
                    "start": round(u["start"] + i * step, 3),
                    "end": round(u["start"] + (i + 1) * step - 0.05, 3),
                    "start_index": start_byte,
                    "end_index": start_byte + len(bare.encode()),
                })
                text_parts.append(token)
                cursor += len(token.encode())
        return RawTranscript(text="".join(text_parts), words=words)

    def json(self, model_key: str, prompt: str, schema: dict, audio: AudioHandle | None = None,
             kind: str = "") -> dict:
        name = "relabel.json" if model_key == "relabel" else "tone.json"
        return self._load(name)
