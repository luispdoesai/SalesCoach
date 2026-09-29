"""The transcribe command: audio in data/inbox to raw JSON and call files.

Per recording:
1. Upload to Gemini and transcribe with speaker labels and word timestamps.
2. Build utterances: consecutive words from the same speaker become one line.
3. Relabel: a small model reads only the opening and says which speaker is the rep.
4. Tone: an audio model gives tone hints per window. Optional. Failure is fine.
5. Redact if turned on in config.yaml.
6. Write data/raw/<call_id>.json and data/calls/<call_id>.md, then move the audio
   to data/processed/.

Privacy: audio goes to Google. The uploaded copy is deleted when the call is done.
"""

from __future__ import annotations

import filecmp
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from coach import callfile, relabel, tone
from coach.callfile import EXAMPLE_NAME, fmt_ts, parse_call_name
from coach.config import Paths, missing_data_fix, require_gemini_key
from coach.friendly import CoachError, heading, note, ok, print_problem, warn
from coach.gemini import MIME_TYPES, GeminiFatal, MockGemini, RealGemini
from coach.redact import Redactor

LABEL_LINE_RE = re.compile(r"(?im)^\s*(?:\[[\d:.]+\]\s*)?(?:spk_\d+|speaker[ _]?\d+)\s*:\s*")
TS_LINE_RE = re.compile(r"(?m)^\s*\[[\d:.]+\]\s*")


# Utterances

def _norm(text: str) -> str:
    return re.sub(r"[^\w]", "", text.lower())


def _join(words: list[dict]) -> str:
    return re.sub(r"\s+([,.!?;:])", r"\1", " ".join(w["text"].strip() for w in words))


def _word_positions(words: list[dict], text_bytes: bytes) -> list[int] | None:
    """Byte position of each word inside the full transcript text, or None."""
    given = [w.get("start_index") for w in words]
    if words and all(isinstance(i, int) for i in given) and given == sorted(given):
        good = sum(
            1 for w, i in zip(words, given)
            if _norm(text_bytes[i:i + len(w["text"].encode())].decode("utf-8", "ignore")) == _norm(w["text"])
        )
        if good >= 0.9 * len(words):
            return given
    # No usable offsets from the API. Find each word in order instead.
    lower = text_bytes.lower()
    pos, out = 0, []
    for w in words:
        needle = w["text"].strip().encode().lower()
        found = lower.find(needle, pos) if needle else pos
        if found == -1 or found - pos > 200:
            return None
        out.append(found)
        pos = found + len(needle)
    return out


def build_utterances(words: list[dict], text: str = "") -> list[dict]:
    """Group consecutive same-speaker words into utterances.

    When the full transcript text is available, each utterance's text is cut
    from it so punctuation (like question marks) survives. Otherwise words are
    joined with spaces.
    """
    words = [w for w in words if w.get("start") is not None and str(w.get("text") or "").strip()]
    if not words:
        return []
    last = "spk_1"
    for w in words:
        w["speaker"] = w.get("speaker") or last
        last = w["speaker"]

    groups: list[list[int]] = []
    for i, w in enumerate(words):
        if groups and words[groups[-1][0]]["speaker"] == w["speaker"]:
            groups[-1].append(i)
        else:
            groups.append([i])

    text_bytes = text.encode()
    positions = _word_positions(words, text_bytes) if text.strip() else None
    utterances = []
    for gi, group in enumerate(groups):
        members = [words[i] for i in group]
        segment = ""
        if positions is not None:
            a = positions[group[0]]
            b = positions[groups[gi + 1][0]] if gi + 1 < len(groups) else len(text_bytes)
            segment = text_bytes[a:b].decode("utf-8", "ignore")
            segment = TS_LINE_RE.sub("", LABEL_LINE_RE.sub("", segment))
            segment = " ".join(segment.split())
        if not segment or not _norm(segment).startswith(_norm(members[0]["text"])):
            segment = _join(members)
        utterances.append({
            "speaker": members[0]["speaker"],
            "role": "",
            "start": round(members[0]["start"], 2),
            "end": round(max((m.get("end") or m["start"]) for m in members), 2),
            "text": segment,
        })
    return utterances


# Audio helpers (ffmpeg is optional)

def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe_duration(path: Path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        return float(out.stdout.strip())
    except (ValueError, subprocess.SubprocessError, OSError):
        return None


def ffmpeg_extract(src: Path, dst: Path, start: float | None = None, length: float | None = None) -> Path:
    """Write mono 16 kHz FLAC, optionally one slice of the recording."""
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(src)]
    if length:
        cmd += ["-t", f"{length:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "flac", str(dst)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not dst.exists():
        raise CoachError(f"ffmpeg could not read {src.name}.",
                         "Check that the recording plays on your computer.")
    return dst


def plan_chunks(duration: float | None, max_sec: float, chunk_sec: float) -> list[tuple[float, float | None]]:
    """(start, length) pieces. One piece when the recording fits in one request."""
    if duration is None or duration <= max_sec:
        return [(0.0, None)]
    pieces, start = [], 0.0
    while start < duration:
        pieces.append((start, min(chunk_sec, duration - start)))
        start += chunk_sec
    return pieces


# The pipeline

@dataclass
class Part:
    offset: float
    length: float | None
    handle: Any
    words: list[dict]
    utterances: list[dict]


class Transcriber:
    def __init__(self, paths: Paths, cfg: dict, mock: bool = False, force: bool = False,
                 rep_speaker: str | None = None, yes: bool = False):
        self.paths = paths
        self.cfg = cfg
        self.tcfg = cfg["transcribe"]
        self.mock = mock
        self.force = force
        self.rep_speaker = rep_speaker
        self.yes = yes
        self._backend = None
        self.counts = {"transcribed": 0, "skipped": 0, "relabeled": 0, "needs_review": 0, "failed": 0}

    @property
    def backend(self):
        # Created only when there is real work, so skipped runs need no key.
        if self._backend is None:
            if self.mock:
                self._backend = MockGemini()
            else:
                try:
                    key = require_gemini_key(self.paths.root)
                except CoachError as err:
                    raise GeminiFatal(err.problem, err.fix) from None
                self._backend = RealGemini(key, self.cfg["models"], self.tcfg.get("language_codes"))
        return self._backend

    # Finding recordings

    def _audio_exts(self) -> set[str]:
        return {e.lower() for e in self.tcfg["audio_extensions"]}

    def _find_audio(self, call_id: str) -> Path | None:
        for folder in (self.paths.inbox, self.paths.processed):
            if folder.is_dir():
                for p in sorted(folder.iterdir()):
                    if p.stem == call_id and p.suffix.lower() in self._audio_exts():
                        return p
        return None

    def targets(self, file: str | None) -> list[tuple[Path | None, str | None]]:
        if file:
            p = Path(file).expanduser()
            if p.is_file():
                return [(p, None)]
            call_id = Path(file).name
            if Path(call_id).suffix.lower() in self._audio_exts():
                call_id = Path(call_id).stem
            if (self.paths.raw / f"{call_id}.json").exists() or self._find_audio(call_id):
                return [(self._find_audio(call_id), call_id)]
            raise CoachError(f"Could not find '{file}'.",
                             "Give a path to a recording, or a call id like 2026-09-28_JD_Discovery. "
                             f"New recordings go in {self.paths.show(self.paths.inbox)}/")
        if self.rep_speaker:
            raise CoachError("--rep-speaker fixes one call at a time.",
                             "Add --file with the call id, for example: "
                             "python coach.py transcribe --file 2026-09-28_JD_Discovery --rep-speaker spk_2")
        found = []
        for p in sorted(self.paths.inbox.iterdir()):
            if p.name.startswith("."):
                continue
            if p.suffix.lower() in self._audio_exts():
                found.append((p, None))
            elif p.is_file():
                note(f"Ignoring {p.name}: not an audio file this tool knows "
                     f"({', '.join(sorted(self._audio_exts()))}).")
        return found

    def _call_id_for(self, audio: Path) -> str | None:
        name = parse_call_name(audio.stem)
        if name.valid:
            return name.call_id
        warn(f"'{audio.name}' does not match the naming pattern YYYY-MM-DD_Initials_Stage.",
             f"Rename it like {EXAMPLE_NAME}")
        if self.yes:
            note(f"Continuing with '{name.call_id}' as the call id because you passed --yes.")
            return name.call_id
        if sys.stdin.isatty():
            answer = input(f"          Use '{name.call_id}' as the call id anyway? [y/N] ").strip().lower()
            if answer in ("y", "yes"):
                return name.call_id
        note("Skipped. Rename the file, or run again with --yes to use the file name as is.")
        return None

    # Main loop

    def run(self, file: str | None = None) -> int:
        if not self.paths.data.is_dir() or not self.paths.inbox.is_dir():
            raise CoachError(f"The {self.paths.show(self.paths.data)}/ folders do not exist yet.", missing_data_fix())
        work = self.targets(file)
        if not work:
            print(f"No recordings in {self.paths.show(self.paths.inbox)}/. "
                  f"Drop audio files there named like {EXAMPLE_NAME}, then run this again.")
            return 0
        if self.mock:
            note("Mock mode: using bundled fixture responses. No audio leaves your computer.")

        for n, (audio, call_id) in enumerate(work, 1):
            label = audio.name if audio else call_id
            heading(f"[{n}/{len(work)}] {label}")
            try:
                call_id = call_id or self._call_id_for(audio)
                if call_id is None:
                    self.counts["skipped"] += 1
                    continue
                self.process(audio, call_id)
            except GeminiFatal as err:
                self.counts["failed"] += 1
                print_problem(err.problem, err.fix)
                print("Stopped. This problem would affect every recording.", file=sys.stderr)
                break
            except CoachError as err:
                self.counts["failed"] += 1
                print_problem(err.problem, err.fix)

        heading("Summary")
        c = self.counts
        print(f"  Transcribed {c['transcribed']}, relabeled {c['relabeled']}, skipped {c['skipped']}, "
              f"failed {c['failed']}. Needs review: {c['needs_review']}.")
        return 1 if c["failed"] else 0

    def process(self, audio: Path | None, call_id: str) -> None:
        raw_path = self.paths.raw / f"{call_id}.json"
        if raw_path.exists() and not self.force:
            if self.rep_speaker:
                self.relabel_existing(call_id)
                return
            note("Already transcribed. Skipping. Use --force to redo it.")
            if audio is not None:
                self._move_to_processed(audio)
            self.counts["skipped"] += 1
            return
        if audio is None:
            raise CoachError(
                f"The recording for {call_id} is not in {self.paths.show(self.paths.inbox)}/ "
                f"or {self.paths.show(self.paths.processed)}/, so it cannot be transcribed again.",
                "Put the recording back in the inbox, or use --rep-speaker to fix labels without re-transcribing.",
            )
        self.transcribe_one(audio, call_id)

    def transcribe_one(self, audio: Path, call_id: str) -> None:
        backend = self.backend
        max_sec = float(self.tcfg["max_minutes"]) * 60
        chunk_sec = float(self.tcfg["chunk_minutes"]) * 60
        duration = None if self.mock else probe_duration(audio)
        mime = MIME_TYPES.get(audio.suffix.lower())
        pieces = plan_chunks(duration, max_sec, chunk_sec)

        if len(pieces) > 1 and not has_ffmpeg():
            raise CoachError(
                f"This recording is {duration / 60:.0f} minutes. Gemini transcribes up to "
                f"{max_sec / 60:.0f} minutes at a time with speaker labels.",
                "Install ffmpeg (https://ffmpeg.org/download.html) so the tool can split it, "
                "or split the recording into parts under 30 minutes.",
            )
        if mime is None and not self.mock and not has_ffmpeg():
            raise CoachError(f"{audio.suffix} files cannot be sent to Gemini directly.",
                             "Install ffmpeg (https://ffmpeg.org/download.html), or convert the file to .m4a or .mp3.")
        if len(pieces) > 1:
            note(f"{duration / 60:.0f} minute recording. Splitting it into {len(pieces)} parts.")

        parts: list[Part] = []
        with tempfile.TemporaryDirectory(prefix="coach_") as tmp:
            try:
                for k, (start, length) in enumerate(pieces):
                    src, src_mime = audio, mime or "audio/flac"
                    if not self.mock and (len(pieces) > 1 or mime is None):
                        src = ffmpeg_extract(audio, Path(tmp) / f"part{k + 1}.flac", start, length)
                        src_mime = "audio/flac"
                    part_label = f" part {k + 1} of {len(pieces)}" if len(pieces) > 1 else ""
                    target = "the mock (nothing leaves your computer)" if self.mock else "Gemini"
                    print(f"  Uploading{part_label} to {target}...")
                    handle = backend.upload(src, src_mime)
                    parts.append(Part(start, length, handle, [], []))
                    print(f"  Transcribing{part_label} with speaker labels. This can take a few minutes...")
                    raw = backend.transcribe(handle)
                    utts = build_utterances(raw.words, raw.text)
                    if not utts:
                        raise CoachError("Gemini returned an empty transcript for this recording.",
                                         "Check that the recording has speech in it and plays on your computer.")
                    words = [{"speaker": w["speaker"], "start": w["start"],
                              "end": w.get("end") if w.get("end") is not None else w["start"],
                              "text": w["text"]} for w in raw.words if w.get("start") is not None]
                    if k:
                        for item in utts + words:
                            item["speaker"] = f"c{k + 1}_{item['speaker']}"
                            item["start"] = round(item["start"] + start, 2)
                            item["end"] = round(item["end"] + start, 2)
                    parts[-1].words, parts[-1].utterances = words, utts

                mapping, confidence, reason = self._relabel(parts)
                for part in parts:
                    part.utterances = relabel.apply_mapping(part.utterances, mapping)
                tone_windows = self._tone(parts)
            finally:
                for part in parts:
                    backend.delete(part.handle)

        utterances = [u for p in parts for u in p.utterances]
        words = [w for p in parts for w in p.words]
        redactor = Redactor(self.cfg["redact"])
        if redactor.enabled:
            for u in utterances:
                u["text"] = redactor.text(u["text"])
            for w in words:
                w["text"] = redactor.word(w["text"])
            for t in tone_windows:
                t["note"] = redactor.text(t["note"])
            note("Redaction applied (best-effort). Review the call file.")

        last_end = max([u["end"] for u in utterances] + [w["end"] for w in words] + [0])
        total = max(duration or 0.0, last_end)
        raw_doc = {
            "call_id": call_id,
            "audio_file": audio.name,
            "duration_sec": round(total, 1),
            "transcribe_model": self.cfg["models"]["transcribe"] + (" (mock)" if self.mock else ""),
            "utterances": utterances,
            "words": words,
            "speaker_mapping": mapping,
            "mapping_confidence": confidence,
            "mapping_reason": reason,
            "tone_windows": tone_windows,
            "chunks": [{"offset_sec": p.offset, "length_sec": p.length} for p in parts],
            "redacted": redactor.enabled,
            "created_at": date.today().isoformat(),
        }
        self._write(call_id, raw_doc, audio.name)
        self._move_to_processed(audio)
        self.counts["transcribed"] += 1

    def _relabel(self, parts: list[Part]) -> tuple[dict[str, str], str, str]:
        window = float(self.tcfg["relabel_window_sec"])
        rep = self.cfg["rep"]
        mapping: dict[str, str] = {}
        confidence, reasons = "high", []
        for k, part in enumerate(parts):
            speakers = relabel.speakers_in(part.utterances)
            if k == 0 and self.rep_speaker:
                mapping.update(relabel.manual_mapping(speakers, self.rep_speaker))
                confidence = "manual"
                continue
            if len(speakers) == 1 and k == 0:
                # One voice only. Assume it is the rep, but flag it.
                mapping[speakers[0]] = "REP"
                confidence, reasons = "low", reasons + ["Only one speaker was detected."]
                continue
            context = ""
            if k:
                prev = relabel.apply_mapping(parts[k - 1].utterances[-5:], mapping)
                context = "\n".join(f"[{fmt_ts(u['start'])}] {u['role']}: {u['text']}" for u in prev)
            print(f"  Working out which speaker is you{' (part ' + str(k + 1) + ')' if k else ''}...")
            prompt = relabel.build_prompt(
                relabel.opening_lines(part.utterances, window, offset=part.offset),
                rep.get("name", ""), rep.get("company", ""), context)
            resp = self.backend.json("relabel", prompt, relabel.SCHEMA, kind="working out who the rep is")
            part_map, part_conf, reason = relabel.parse_response(resp, speakers)
            mapping.update(part_map)
            if part_conf == "low" and confidence != "manual":
                confidence = "low"
            if reason:
                reasons.append(reason)
        reps = [s for s, r in mapping.items() if r == "REP"]
        ok(f"{', '.join(reps) or 'nobody'} is REP (confidence: {confidence})")
        return mapping, confidence, " ".join(reasons)

    def _tone(self, parts: list[Part]) -> list[dict]:
        window = int(self.tcfg["tone_window_sec"])
        print("  Getting tone hints from the audio...")
        windows: list[dict] = []
        try:
            for part in parts:
                length = part.length or max(u["end"] for u in part.utterances) - part.offset
                prompt = tone.build_prompt(part.utterances, length, window, offset=part.offset)
                resp = self.backend.json("tone", prompt, tone.SCHEMA, audio=part.handle, kind="getting tone hints")
                windows += tone.clean_windows(resp, length, offset=part.offset)
        except Exception as err:  # noqa: BLE001  tone is optional by design
            detail = err.problem if isinstance(err, CoachError) else type(err).__name__
            warn(f"Tone hints failed ({detail}). The transcript is saved without them.")
            return []
        ok(f"{len(windows)} tone windows (hints only)")
        return windows

    # Writing

    def _meta(self, call_id: str, raw_doc: dict, source_audio: str) -> dict:
        name = parse_call_name(call_id)
        conf = raw_doc["mapping_confidence"]
        return {
            "call_id": call_id,
            "date": name.date or "",
            "prospect_initials": name.prospect_initials or "",
            "stage": name.stage or "",
            "duration_sec": int(round(raw_doc["duration_sec"])),
            "source_audio": source_audio,
            "rep_speaker": ", ".join(s for s, r in raw_doc["speaker_mapping"].items() if r == "REP"),
            "speaker_mapping_confidence": conf,
            "needs_review": conf == "low",
        }

    def _write(self, call_id: str, raw_doc: dict, source_audio: str) -> None:
        raw_path = self.paths.raw / f"{call_id}.json"
        call_path = self.paths.calls / f"{call_id}.md"
        email = callfile.EMAIL_PLACEHOLDER
        if call_path.exists():
            email = callfile.read(call_path).email_block  # keep pulled email history
        callfile.atomic_write(raw_path, json.dumps(raw_doc, indent=2, ensure_ascii=False) + "\n")
        meta = self._meta(call_id, raw_doc, source_audio)
        callfile.atomic_write(call_path, callfile.render(meta, raw_doc["utterances"], raw_doc["tone_windows"], email))
        ok(f"Saved {self.paths.show(call_path)}")
        if meta["needs_review"]:
            self.counts["needs_review"] += 1
            self._review_notice(call_id, raw_doc)

    def _review_notice(self, call_id: str, raw_doc: dict) -> None:
        warn("Not sure which speaker is you. The call file is marked needs_review: true.")
        print("          First lines as labeled now:")
        for u in raw_doc["utterances"][:4]:
            print(f"            [{fmt_ts(u['start'])}] {u['role']} ({u['speaker']}): {u['text'][:70]}")
        speakers = relabel.speakers_in(raw_doc["utterances"])
        print("          If you are not the REP above, tell it which speaker you are:")
        for s in speakers:
            print(f"            python coach.py transcribe --file {call_id} --rep-speaker {s}")

    def relabel_existing(self, call_id: str) -> None:
        """Apply --rep-speaker to a call that is already transcribed. No API call."""
        raw_path = self.paths.raw / f"{call_id}.json"
        try:
            raw_doc = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise CoachError(f"{self.paths.show(raw_path)} could not be read.",
                             "Transcribe the call again with --force.") from None
        speakers = relabel.speakers_in(raw_doc["utterances"])
        mapping = relabel.manual_mapping(speakers, self.rep_speaker or "")
        raw_doc["utterances"] = relabel.apply_mapping(raw_doc["utterances"], mapping)
        raw_doc["speaker_mapping"] = mapping
        raw_doc["mapping_confidence"] = "manual"
        raw_doc["mapping_reason"] = f"Set by hand with --rep-speaker {self.rep_speaker}."
        self._write(call_id, raw_doc, raw_doc.get("audio_file", ""))
        ok(f"Relabeled with {self.rep_speaker} as REP. No new transcription was needed.")
        self.counts["relabeled"] += 1

    def _move_to_processed(self, audio: Path) -> None:
        try:
            in_inbox = audio.resolve().parent == self.paths.inbox.resolve()
        except OSError:
            in_inbox = False
        if not in_inbox or not audio.exists():
            return
        self.paths.processed.mkdir(parents=True, exist_ok=True)
        dest = self.paths.processed / audio.name
        if dest.exists() and filecmp.cmp(audio, dest, shallow=False):
            # An identical copy is already processed. Drop the duplicate instead of piling up copies.
            audio.unlink()
            note(f"Removed a duplicate of {self.paths.show(dest)} from the inbox. The processed copy is kept.")
            return
        n = 1
        while dest.exists():
            dest = self.paths.processed / f"{audio.stem}_{n}{audio.suffix}"
            n += 1
        shutil.move(str(audio), str(dest))
        note(f"Moved the recording to {self.paths.show(dest)}")


def run_transcribe(paths: Paths, cfg: dict, file: str | None = None, force: bool = False,
                   mock: bool = False, rep_speaker: str | None = None, yes: bool = False) -> int:
    mock = mock or os.environ.get("COACH_MOCK", "").strip().lower() in ("1", "true", "yes")
    return Transcriber(paths, cfg, mock=mock, force=force, rep_speaker=rep_speaker, yes=yes).run(file)
