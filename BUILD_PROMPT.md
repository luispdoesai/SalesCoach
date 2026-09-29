# BUILD_PROMPT: AI Sales Coach

## How to use this file

1. Create an empty folder called `ai-sales-coach`.
2. Copy this file and `README.md` into it.
3. Open Claude Code in that folder and paste this:

> Read BUILD_PROMPT.md and README.md. Build the project one phase at a time. After each phase, stop and tell me in plain English what you built, how to run it, and how I can test it. Wait for my go-ahead before starting the next phase.

Everything below the line is the prompt Claude Code follows.

---

# Project brief

You are building an open-source tool called **AI Sales Coach**. It turns a salesperson's own recorded calls into a coach. It transcribes calls, labels who is speaking, adds email context, scores each call against the user's rubric, computes real statistics, compares won vs. lost deals, and writes a `Findings.md` that explains why calls won or lost and what to change.

The people using this are salespeople, many of them non-technical. The repo will be public. Build for both facts.

`README.md` in this folder is the user-facing spec. Build to match it. If your implementation must differ (command names, paths, formats), update the README so it stays accurate, and tell me what changed.

## Ground rules

1. **Two layers, kept separate.**
   - **Scripts (Python) do everything deterministic:** transcription calls, file handling, statistics, validation, charts.
   - **Claude Code does the judgment work** by following prompt files in `prompts/`: building the rubric, pulling email context, scoring calls, writing Findings.md, running practice roleplays. Do not add an Anthropic API dependency. Users run these steps inside Claude Code with their existing subscription.
2. **Never let AI do math.** Every number in a report comes from code. The findings prompt must copy numbers from generated CSVs, not compute them.
3. **Evidence or it does not count.** Every score of 2 to 5 must carry a verbatim quote from the transcript. A validator script must check that each quote actually appears in the call file. Scores that fail validation are rejected with a clear message.
4. **Files and folders first.** Plain markdown, CSV, and JSON files. No database required. SQLite is an optional add-on (Phase 5).
5. **Privacy by default.** Call data never enters git. Gmail access is read-only. Say so in code comments, prompts, and the README.
6. **Friendly errors.** A non-technical user must never see a raw Python traceback for an expected problem (missing key, wrong filename, missing folder). Catch it, say what is wrong in one sentence, and say how to fix it.
7. **Idempotent.** Re-running any command must not redo finished work. Provide `--force` where it makes sense.
8. **Plain writing.** No em dashes anywhere in code comments, prompts, or docs. Short sentences. No filler.
9. **Verify before you build the Gemini part.** The Gemini API and SDK change often. Before writing any Gemini code, fetch and read the current docs:
   - https://ai.google.dev/gemini-api/docs/transcribe
   - https://ai.google.dev/gemini-api/docs/audio

   Use the current SDK and model names from those pages. As of September 2026 the dedicated transcription model was `gemini-3.5-transcribe`, with speaker diarization (labels like `spk_1`, `spk_2`), word-level timestamps, audio files up to about 1 hour, and up to 8 speakers. Known limits to design around: custom vocabulary cannot be combined with diarization or word timestamps, and smart transcription mode cannot be combined with diarization or word timestamps. Model names go in `config.yaml`, never hardcoded.

## Tech choices

- Python 3.10+
- Dependencies (keep this list short): `google-genai`, `pandas`, `matplotlib`, `pyyaml`, `python-dotenv`, `pytest`
- One CLI entry point: `coach.py` using `argparse`, with the code in a `coach/` package
- Secrets in `.env` (`GEMINI_API_KEY`). Ship `.env.example`.
- License: MIT

## Repo layout

```
ai-sales-coach/
  README.md
  BUILD_PROMPT.md
  CLAUDE.md
  LICENSE
  .env.example
  .gitignore
  config.yaml
  requirements.txt
  coach.py
  coach/
    __init__.py
    config.py
    callfile.py        read and write call markdown files
    transcribe.py      Gemini transcription and diarization
    relabel.py         map spk_1 / spk_2 to REP / PROSPECT
    tone.py            time-window tone notes
    redact.py          optional regex redaction
    scorecards.py      schema, validation, quote verification, merge
    stats.py           statistics from raw JSON
    compare.py         won vs. lost tables and charts
    index.py           optional SQLite index (Phase 5)
    friendly.py        friendly error helpers
  prompts/
    01_build_rubric.md
    02_relabel_speakers.md
    03_email_context.md
    04_score_call.md
    05_findings.md
    06_roleplay.md
  personas/
    skeptical_cfo.md
    just_send_me_info.md
    price_shopper.md
    silent_stakeholder.md
  rubric/
    rubric.example.md
  examples/
    demo/              synthetic raw JSON, call files, scorecards, outcomes
  tests/
  .claude/
    commands/
      coach-rubric.md
      coach-emails.md
      coach-score.md
      coach-findings.md
      coach-practice.md
  data/                gitignored, created by `init`
    inbox/             drop audio here
    processed/         audio moves here after transcription
    raw/               <call_id>.json  (utterances, words, mapping, tone windows)
    calls/             <call_id>.md
    emails/            optional manual email exports: <call_id>.txt
    scorecards/        <call_id>.json  (written by Claude Code)
    reports/           Findings.md, compare.csv, charts/
    contacts.csv
    outcomes.csv
    results.csv
    stats.csv
```

## Naming convention

Audio files are named `YYYY-MM-DD_ProspectInitials_Stage.ext`, for example `2026-09-28_JD_Discovery.m4a`. That stem is the `call_id` used everywhere. If a file does not match, warn with an example of a correct name and offer to continue using the raw filename stem as the `call_id`.

## Data contracts

### Call file: `data/calls/<call_id>.md`

```markdown
---
call_id: 2026-09-28_JD_Discovery
date: 2026-09-28
prospect_initials: JD
stage: Discovery
duration_sec: 1834
source_audio: 2026-09-28_JD_Discovery.m4a
rep_speaker: spk_1
speaker_mapping_confidence: high
needs_review: false
---

# Transcript
[00:00] REP: Hi, this is Sam from ...
[00:07] PROSPECT: Hey Sam, thanks for ...

# Tone Notes
Hints generated from the audio. Verify before trusting.
- 00:00-01:00 | REP: warm | PROSPECT: guarded | note: short answers at the start

# Email History
<!-- EMAIL_START -->
Not yet pulled.
<!-- EMAIL_END -->
```

Rules:
- One transcript line per utterance. Merge consecutive lines from the same speaker.
- Timestamp format is `[MM:SS]`, or `[H:MM:SS]` past one hour.
- Relabeling changes speaker labels only. It never edits spoken text.
- The Email History section is edited only between the two marker comments so re-runs are safe.

### Raw file: `data/raw/<call_id>.json`

```json
{
  "call_id": "...",
  "audio_file": "...",
  "duration_sec": 1834.2,
  "transcribe_model": "gemini-3.5-transcribe",
  "utterances": [
    {"speaker": "spk_1", "role": "REP", "start": 0.4, "end": 6.9, "text": "..."}
  ],
  "words": [
    {"speaker": "spk_1", "start": 0.4, "end": 0.7, "text": "Hi"}
  ],
  "speaker_mapping": {"spk_1": "REP", "spk_2": "PROSPECT"},
  "mapping_confidence": "high",
  "tone_windows": [
    {"start": 0, "end": 60, "rep_tone": "warm", "prospect_tone": "guarded", "note": "..."}
  ]
}
```

`words` may be empty if the API does not return them. Statistics must still work from `utterances`.

### `data/contacts.csv`

`call_id,prospect_name,prospect_email,company`

### `data/outcomes.csv`

`call_id,outcome,deal_value,notes`

`outcome` must be one of `won`, `lost`, `stalled`, `open`. `deal_value` and `notes` are optional.

### Rubric: `rubric/rubric.md`

Each behavior is a level-3 heading `### snake_case_id: Human Name`, followed by three lines starting `1:`, `3:`, and `5:` that define those score levels. The validator parses the ids from these headings. `rubric.example.md` ships as a filled-in sample. The user's real `rubric/rubric.md` is gitignored so nobody accidentally publishes an employer's sales playbook.

### Scorecard: `data/scorecards/<call_id>.json` (written by Claude Code)

```json
{
  "call_id": "2026-09-28_JD_Discovery",
  "scored_at": "2026-09-28",
  "rubric_scores": [
    {"id": "cost_of_inaction", "score": 2, "timestamp": "12:31",
     "evidence_quote": "verbatim text from the transcript", "why": "one sentence"}
  ],
  "rapport": {"score": 4, "timestamp": "02:10", "evidence_quote": "...", "why": "..."},
  "tone_match": {"score": 3, "timestamp": "08:44", "evidence_quote": "...", "why": "..."},
  "price_handling": {
    "price_stated": true,
    "price_stated_end_sec": 1201,
    "held_price": true,
    "conceded_or_discounted": false,
    "prospect_objected": true,
    "evidence_quote": "...",
    "why": "..."
  },
  "objections": [
    {"type": "price", "timestamp": "20:11", "evidence_quote": "...", "handled": false, "why": "..."}
  ],
  "first_pain_question_sec": 210,
  "top_misses": ["...", "...", "..."],
  "rewrite": {"timestamp": "20:15", "original_quote": "...", "better_version": "..."},
  "one_thing_to_change": "..."
}
```

Definition of `held_price` (observable, put this in the prompt too): the rep stated a price, then did not concede or discount when the prospect pushed back, and stayed silent or asked a question before any concession. If `price_stated` is false, the other price fields are `null`.

Validation rules:
- Every rubric id in `rubric/rubric.md` is scored exactly once. No unknown ids.
- Scores are integers 1 to 5.
- Scores of 2 to 5 require a non-empty `evidence_quote` that appears in the call file transcript after normalizing case, whitespace, and punctuation spacing. A score of 1 may have a null quote (absence of a behavior has no quote) but needs a `why`.
- `timestamp` values fall inside the call duration.
- `objections[].evidence_quote` and `rewrite.original_quote` are verified the same way.
- A failed scorecard is reported with the exact field and reason. The validator never edits scorecards.

### Statistics: `data/stats.csv` (from code, no AI)

Columns: `call_id, duration_sec, rep_talk_pct, prospect_talk_pct, rep_questions, longest_rep_monologue_sec, price_silence_sec, price_next_speaker`

- `rep_talk_pct` is rep speaking time divided by rep plus prospect speaking time.
- `rep_questions` counts question marks in rep utterances. Document that this is an approximation.
- `longest_rep_monologue_sec` is the longest run of consecutive rep speech.
- `price_silence_sec` is the gap from `price_stated_end_sec` (from the scorecard) to the start of the next utterance by anyone, and `price_next_speaker` says who spoke. Leave both blank if no price was stated or no scorecard exists yet.

### Results: `data/results.csv`

One row per call: `call_id, date, prospect_initials, stage, outcome, rubric_avg`, one column per rubric id, then `rapport_score, tone_match_score, price_stated, held_price, conceded_or_discounted, prospect_objected, objections_count, objections_unhandled_count, first_pain_question_sec`. Outcome comes from `outcomes.csv`.

### Comparison: `data/reports/compare.csv` and `data/reports/charts/*.png`

For each metric in stats and results: mean for won, lost, and stalled calls, the counts, and the difference between won and lost. Also print and write a sample-size note:
- Fewer than 5 won or fewer than 5 lost calls: say the comparison is not meaningful yet.
- Fewer than 30 total calls: say patterns are directional hints, not proof.
- Say plainly that this shows correlation, not cause.

Charts: bar charts of won vs. lost for talk percentage, questions asked, longest monologue, and price silence. Monochrome, labeled, with the sample size in each chart title.

## CLI

```
python coach.py doctor        check Python, packages, API key, folders, and that data/ is not tracked by git
python coach.py init          create folders, contacts.csv and outcomes.csv headers, copy templates
python coach.py transcribe    audio in data/inbox -> raw JSON + call files (options: --file PATH, --force, --mock)
python coach.py validate      check scorecards against the rubric and verify every quote
python coach.py merge         scorecards + outcomes -> results.csv
python coach.py stats         raw JSON (+ scorecards for price timing) -> stats.csv
python coach.py compare       results + stats -> compare.csv and charts
python coach.py analyze       validate, merge, stats, compare in one go
python coach.py index         optional: build data/coach.db (SQLite) from the CSVs
python coach.py demo          run the analysis on bundled synthetic data, no API keys needed
```

`transcribe` steps per audio file:
1. Upload to Gemini and transcribe with diarization and timestamps.
2. Build utterances (merge consecutive same-speaker words if needed).
3. **Relabel:** send only the first two minutes of transcript to a small Gemini text call using `prompts/02_relabel_speakers.md`. It returns a mapping such as `{"spk_1": "REP", "spk_2": "PROSPECT"}` plus a confidence of `high` or `low`. Code applies the mapping. The model never rewrites transcript text. If confidence is low, set `needs_review: true`, print a clear notice, and let the user override with `--rep-speaker spk_2`. If `config.yaml` has a rep name, include it as a hint.
4. **Tone:** ask a Gemini audio-capable model for time-window tone notes as structured JSON (60-second windows, rep tone, prospect tone, one short note). Label these as hints everywhere. If this step fails, continue without it and say so.
5. If `redact.enabled` is true, apply regex redaction (emails, phone numbers) plus any names listed in config to the call file text. State clearly in the README that redaction is best-effort.
6. Write `data/raw/<call_id>.json` and `data/calls/<call_id>.md`, then move the audio to `data/processed/`.
7. Audio longer than about 55 minutes: fail with a clear message at minimum. If `ffmpeg` is installed, splitting into chunks with correct timestamp offsets is a welcome extra.

`--mock` (also `COACH_MOCK=1`) uses bundled fixture responses so tests and the demo run with no network and no API key.

## Claude Code slash commands

Create thin command files in `.claude/commands/`. Each tells Claude Code to read the matching file in `prompts/` and follow it exactly.

- `/coach-rubric` follows `prompts/01_build_rubric.md`. It interviews the user about their sales process first, then writes `rubric/rubric.md`.
- `/coach-emails` follows `prompts/03_email_context.md`.
- `/coach-score` follows `prompts/04_score_call.md`.
- `/coach-findings` follows `prompts/05_findings.md`.
- `/coach-practice` follows `prompts/06_roleplay.md`.

## Prompt files: content requirements

Write these carefully. They are the product. Each starts with a short "Purpose" line and a "Rules" list.

**01_build_rubric.md.** Ask the user five questions about their sales process before writing anything (what they sell, who buys, typical deal size, sales cycle length, who they usually talk to). Then propose one framework (or use the one they name) and produce 8 to 10 observable behaviors in the exact `### id: Name` format with 1, 3, and 5 definitions. Include a price-handling behavior using the observable definition of `held_price`. Ask the user to review and cut anything that does not match how they sell.

**02_relabel_speakers.md.** Input is the opening two minutes of a two-person sales call with generic speaker labels. Output is JSON only: the mapping and a confidence. Explain the cues: the rep usually introduces themselves and their company, runs the agenda, and asks the opening questions. Say "low" if the cues conflict.

**03_email_context.md.** For each call file whose Email History is still "Not yet pulled": look up the prospect in `data/contacts.csv`; search Gmail threads with that address from 30 days before the call to now; summarize between the EMAIL markers as a timeline, what the prospect asked, what the rep promised, whether the follow-up went out and how fast, and any tone shifts. **Read-only: never send, draft, label, archive, or delete anything.** If no Gmail connector is available, use `data/emails/<call_id>.txt` if present, otherwise say what is missing. Never overwrite an existing summary unless asked.

**04_score_call.md.** Purpose: produce a scorecard JSON that passes the validator. Rules: grade harshly; no praise without evidence; quote verbatim and do not fix grammar; one score per rubric id; give timestamps; fill every field in the schema; write `first_pain_question_sec` and `price_stated_end_sec` as seconds; identify the top three misses, one rewrite of the weakest moment as it should have sounded, and the single thing to change next call. Read the Email History for context but score only what happens on the call. Do not edit the call file. After writing, run `python coach.py validate` and fix any reported errors. Include the `held_price` definition and the tone caveat (tone notes are hints).

**05_findings.md.** Purpose: write `data/reports/Findings.md`. Inputs: `results.csv`, `stats.csv`, `compare.csv`, the scorecards, and the call files. Rules: copy every number from the CSVs, never compute your own; every pattern must cite call ids and include at least one verbatim quote; give each pattern a confidence of high, medium, or low based on the sample size; say when a comparison is impossible (no losses, no wins); never claim cause. Required structure:
1. Summary (5 lines)
2. Won vs. lost table
3. Top 3 patterns, each with a quote and a confidence
4. Where each lost deal turned (the moment, the quote, the call id)
5. What the wins did differently
6. Ranked improvements, each with a rewrite of what to say instead
7. The one skill to focus on for the next 5 calls
8. Caveats

**06_roleplay.md.** Purpose: realistic practice. Read the chosen persona from `personas/`. Stay in character, be hard to convince, and do not help the rep. Never reveal the rubric during the roleplay. When the user says "end", score the roleplay against the rubric with quotes, name the objection handled worst, and suggest a drill for the next round. Offer to save a short practice log to `data/reports/practice_log.md`.

**Personas.** Four short files, each with: who they are, what they care about, their default stalling move, and two or three realistic objection lines.

## Privacy and safety requirements

- `.gitignore` must exclude `data/`, `.env`, `rubric/rubric.md`, and common audio and video extensions.
- `doctor` warns loudly if any file under `data/` is tracked by git.
- The README must state: get consent to record, some places require all-party consent, check company policy before using any AI tool on customer conversations, audio goes to Google and transcripts go through Claude Code, and the user should check current data-use terms for their Gemini plan. This is not legal advice.
- Gmail is read-only in every prompt and command.
- Never print the API key. Never write it to any file except `.env`.

## Testing

- `pytest` runs with no network and no keys.
- Tests: filename parsing; utterance building; applying a speaker mapping without changing text; call file round trip; quote verification (pass, fail, whitespace and case differences); scorecard validation (missing id, bad score, missing quote, timestamp out of range); statistics on a small fixture with known answers; compare with fewer than 5 wins or losses; idempotent re-runs.
- `python coach.py demo` must work on a fresh clone. The bundled demo data is fully synthetic (12 to 15 fake calls with mixed outcomes, invented names, no real companies or people).

## Phases

**Phase 1: Skeleton.** Repo layout, `config.yaml`, `requirements.txt`, `.gitignore`, `.env.example`, LICENSE, `CLAUDE.md` (project rules for future Claude Code sessions: read-only Gmail, verbatim quotes, never commit data, never edit transcript text, no em dashes), `friendly.py`, `doctor`, `init`. Acceptance: on a fresh clone, `doctor` and `init` run and give clear messages.

**Phase 2: Transcription.** `callfile.py`, `transcribe.py`, `relabel.py`, `tone.py`, `redact.py`, and the `transcribe` command with `--mock`. Read the Gemini docs first. Acceptance: with `--mock`, a sample audio placeholder produces a valid raw JSON and call file; tests pass.

**Phase 3: Analysis.** `scorecards.py`, `stats.py`, `compare.py`, `analyze`, `demo`, and the synthetic demo data. Acceptance: `python coach.py demo` prints stats, a won vs. lost table with the sample-size note, and saves charts.

**Phase 4: Prompts and commands.** All six prompt files, four personas, `rubric.example.md`, and the five slash commands. Acceptance: running `/coach-score` on a demo call file produces a scorecard that passes `validate`.

**Phase 5: Polish.** Optional `index` command that builds `data/coach.db` from the CSVs, README sync with the real commands, and a final check of the friendly error messages. Acceptance: a non-technical reader can follow the README from clone to `Findings.md` without guessing.

## Definition of done

- A fresh clone runs `doctor`, `init`, and `demo` successfully.
- `pytest` passes offline.
- Every command in the README exists and behaves as described.
- No call data, keys, or personal rubric can be committed by accident.
- Every number in a generated report traces to a CSV produced by code.
- You have told me, in plain English, what each phase built and how to test it.

## Do not

- Add a web server, database requirement, or paid service beyond a Gemini API key.
- Add an Anthropic API dependency.
- Let any prompt send, draft, label, or delete email.
- Invent statistics, quotes, or benchmarks in any report or README.
- Use em dashes.
