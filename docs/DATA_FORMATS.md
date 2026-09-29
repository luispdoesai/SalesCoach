# Data Formats

The exact formats for every file the tool reads and writes. If you change a format, update the code, the tests, the prompts, and this page together.

## Call names

Audio files are named `YYYY-MM-DD_ProspectInitials_Stage.ext`, for example `2026-09-28_JD_Discovery.m4a`. That stem is the `call_id` used everywhere. If a file does not match, `transcribe` warns with an example of a correct name. `--yes` uses the raw filename stem as the `call_id`.

## Call file: `data/calls/<call_id>.md`

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

## Raw file: `data/raw/<call_id>.json`

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

## `data/contacts.csv`

`call_id,prospect_name,prospect_email,company`

## `data/outcomes.csv`

`call_id,outcome,deal_value,notes`

`outcome` must be one of `won`, `lost`, `stalled`, `open`. `deal_value` and `notes` are optional.

## Rubric: `rubric/rubric.md`

Each behavior is a level-3 heading `### snake_case_id: Human Name`, followed by three lines starting `1:`, `3:`, and `5:` that define those score levels. The validator parses the ids from these headings. `rubric.example.md` ships as a filled-in sample. The user's real `rubric/rubric.md` is gitignored so nobody accidentally publishes an employer's sales playbook.

## Scorecard: `data/scorecards/<call_id>.json` (written by Claude Code)

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

Definition of `held_price` (observable): the rep stated a price, then did not concede or discount when the prospect pushed back, and stayed silent or asked a question before any concession. If `price_stated` is false, the other price fields are `null`.

Validation rules:
- Every rubric id in `rubric/rubric.md` is scored exactly once. No unknown ids.
- Scores are integers 1 to 5.
- Scores of 2 to 5 require a non-empty `evidence_quote` that appears in the call file transcript after normalizing case, whitespace, and punctuation spacing. A score of 1 may have a null quote (absence of a behavior has no quote) but needs a `why`.
- `timestamp` values fall inside the call duration.
- `objections[].evidence_quote` and `rewrite.original_quote` are verified the same way.
- A failed scorecard is reported with the exact field and reason. The validator never edits scorecards.

## Statistics: `data/stats.csv` (from code, no AI)

Columns: `call_id, duration_sec, rep_talk_pct, prospect_talk_pct, rep_questions, longest_rep_monologue_sec, price_silence_sec, price_next_speaker`

- `rep_talk_pct` is rep speaking time divided by rep plus prospect speaking time.
- `rep_questions` counts question marks in rep utterances. This is an approximation.
- `longest_rep_monologue_sec` is the longest run of consecutive rep speech.
- `price_silence_sec` is the gap from `price_stated_end_sec` (from the scorecard) to the start of the next utterance by anyone, and `price_next_speaker` says who spoke. Both are blank if no price was stated or no scorecard exists yet.

## Results: `data/results.csv`

One row per call: `call_id, date, prospect_initials, stage, outcome, rubric_avg`, one column per rubric id, then `rapport_score, tone_match_score, price_stated, held_price, conceded_or_discounted, prospect_objected, objections_count, objections_unhandled_count, first_pain_question_sec`. Outcome comes from `outcomes.csv`.

## Comparison: `data/reports/compare.csv` and `data/reports/charts/*.png`

For each metric in stats and results: mean for won, lost, and stalled calls, the counts, and the difference between won and lost. `compare` also prints and writes a sample-size note:
- Fewer than 5 won or fewer than 5 lost calls: the comparison is not meaningful yet.
- Fewer than 30 total calls: patterns are directional hints, not proof.
- It shows correlation, not cause.

Charts are bar charts of won vs. lost for talk percentage, questions asked, longest monologue, and price silence. Monochrome, labeled, with the sample size in each chart title.
