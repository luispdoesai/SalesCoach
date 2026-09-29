# Score a Call

Purpose: write one scorecard JSON per call, graded against the user's rubric, that passes `python coach.py validate`.

## Rules

1. **Grade harshly.** A 5 is rare and means the behavior was done fully and well. When in doubt between two scores, pick the lower one. No praise without evidence.
2. **No quote, no score.** Every score of 2 to 5 needs an `evidence_quote` copied word for word from the call file.
3. **Quote verbatim.** Copy the exact characters from one transcript line. Do not fix grammar, spelling, filler words, or punctuation. Do not include the `[MM:SS] REP:` label. Do not stitch two lines together. Keep quotes short: the words that prove the point, usually 5 to 25 words. The validator forgives case, spacing, and curly versus straight quotes, and nothing else.
   - Quote the right person. `rapport` and `tone_match` quote the rep. `objections` quote the prospect. `rewrite.original_quote` must be the rep's words, or validation fails. Rubric scores quote whoever proves the point (the prospect naming a cost can prove `cost_of_inaction`).
4. **One score per rubric id.** Score every id in the rubric exactly once. Use no other ids.
5. **Missing and done badly both score 1, but differ in evidence.**
   - Missing (it never happened): set `evidence_quote` and `timestamp` to `null` and say in `why` that it did not happen.
   - Done badly (the rep argued, discounted early, cut in): quote the moment and give its timestamp. A quote makes the 1 easier to trust and to coach.
   - Not expected at this stage (no price talk on a first discovery call, say): still score 1, and start `why` with exactly `Not expected at the <Stage> stage.` Findings uses that phrase to keep stage gaps apart from real misses.
6. **Numbers come from code.** For `price_stated_end_sec` and `first_pain_question_sec`, run the `locate` command below and copy the number it prints. Never estimate seconds yourself.
7. **Score only what happens on the call.** Read the Email History for context, but do not reward or penalize anything that happened only in email.
8. **Tone notes are hints.** They come from an audio model and can be wrong. Never score a behavior on a tone note alone. Quote the transcript.
9. **Never edit the call file.** Write only the scorecard.
10. **Fill every field.** Use the schema below exactly. `null` where a field does not apply, never a missing key.
11. **No em dashes** in any text you write.

## Which calls, which folder

- Use `data/` unless the user names another data folder (for example `data/demo`). Then read and write inside that folder, and add `--data-dir <folder>` to every `coach.py` command.
- Score the calls the user names. If they name none, score every call in `<folder>/calls/` that has no scorecard in `<folder>/scorecards/` yet. Never overwrite an existing scorecard unless the user asks.
- Use `python coach.py ...`, or `.venv/bin/python coach.py ...` if a `.venv` folder exists in the repo.
- If a call file says `needs_review: true`, tell the user the speaker labels are unconfirmed and ask whether to continue. Scores depend on knowing who the rep is.

## Inputs, for each call

- The rubric: `rubric/rubric.md`. If the data folder has its own `rubric.md` (like `data/demo/rubric.md`), use that one.
- The call file: `<folder>/calls/<call_id>.md`. Timestamps are `[MM:SS]` at the start of each line.

## Getting exact seconds: the locate command

```
python coach.py locate <call_id> "<words copied from one line>" [--data-dir <folder>]
```

It prints the line's timestamp and the start and end seconds of those words, computed from the audio timestamps. `method` says how: `word timestamps` is exact; `line end` is exact for the end; `estimated` means the call has no word timestamps and the seconds are proportional to position in the line.

- `price_stated_end_sec`: locate the rep's whole price sentence, through its final punctuation, for example `For a fleet your size it's forty-eight hundred dollars a month.` Copy `quote_end_sec`. If the rep kept talking after the price in the same line, locate only the price sentence.
- `first_pain_question_sec`: locate the rep's first question that asks how the prospect handles something today or what goes wrong with it, whichever comes first, and copy `quote_start_sec`. "How are you building the schedule right now?" counts. Small talk and agenda checks ("Does that work?") do not. If the rep never asked one, use `null`.

## Definitions

**held_price.** The rep stated a price, then did not concede or discount when the prospect pushed back, and stayed silent or asked a question before any concession.

- `price_stated`: the rep said a specific price or price range out loud. "It depends" is not a price.
- `prospect_objected`: the prospect pushed back on the price ("That's steep", "More than we budgeted").
- `conceded_or_discounted`: the rep offered a discount, a lower tier, free months, or any concession, whether or not the prospect pushed back.
- `held_price`: `true` or `false` only when `prospect_objected` is `true`. If the prospect never pushed back, `held_price` is `null`, because holding only means something after pushback. It can never be `true` when `conceded_or_discounted` is `true`.
- If `price_stated` is `false`, then `price_stated_end_sec`, `held_price`, `conceded_or_discounted`, and `prospect_objected` are all `null`. `evidence_quote` may quote the moment price came up, or be `null`.

**Objection.** A reason the prospect gives not to move forward. Quote the prospect's words. `type` is one of these exact values, so objections can be grouped across calls:

| type | Sounds like |
|---|---|
| `price` | "That's steep", "More than we budgeted" |
| `timing` | "Not this quarter", "Call me in the new year" |
| `authority` | "I'd have to take this to my boss" |
| `send_info` | "Just send me something" |
| `competitor` | "We already use another tool", "Their quote was lower" |
| `no_need` | "We're fine with the spreadsheet" |
| `trust` | "We tried something like this and it failed" |
| `other` | Anything else. Say what it was in `why` |

`handled` is `true` only if the rep asked a question to understand it, answered the real concern, and the prospect accepted or moved forward.

**Rapport** (1 to 5). Specific, personal, genuine connection, not generic small talk. Quote the rep.

**Tone match** (1 to 5). The rep's pace, energy, and formality fit the prospect's. Judge from the words (short answers met with a short reply, for example). You may mention a tone note in `why`, but the quote must come from the transcript.

**Scores of 2 and 4** sit between the rubric's 1, 3, and 5 definitions.

## Schema

```json
{
  "call_id": "2026-09-28_JD_Discovery",
  "scored_at": "YYYY-MM-DD",
  "rubric_scores": [
    {"id": "cost_of_inaction", "score": 2, "timestamp": "12:31",
     "evidence_quote": "verbatim words from one line", "why": "One sentence."}
  ],
  "rapport": {"score": 4, "timestamp": "02:10", "evidence_quote": "...", "why": "..."},
  "tone_match": {"score": 3, "timestamp": "08:44", "evidence_quote": "...", "why": "..."},
  "price_handling": {
    "price_stated": true,
    "price_stated_end_sec": 1201.4,
    "held_price": true,
    "conceded_or_discounted": false,
    "prospect_objected": true,
    "evidence_quote": "...",
    "why": "..."
  },
  "objections": [
    {"type": "price", "timestamp": "20:11", "evidence_quote": "prospect's exact words", "handled": false, "why": "..."}
  ],
  "first_pain_question_sec": 210.0,
  "top_misses": ["...", "...", "..."],
  "rewrite": {"timestamp": "20:15", "original_quote": "...", "better_version": "..."},
  "one_thing_to_change": "..."
}
```

- `timestamp` is the `[MM:SS]` of the line the quote comes from, written without brackets: `"12:31"`. Use `H:MM:SS` past one hour.
- `objections` is `[]` if there were none.
- `top_misses`: exactly 3 short sentences, the biggest gaps first. Each names a specific moment with its timestamp ("After the price pushback at 02:48, ...") or a specific absence ("Never asked who signs.").
- `rewrite`: the rep's single weakest moment. `original_quote` is the rep's exact words from that line. `better_version` is what the rep should have said instead, in their own voice, at most two sentences, spoken words only (no stage directions).
- The top-level `price_handling` object describes price behavior as facts. The rubric may also have a behavior with the id `price_handling`, scored 1 to 5 in `rubric_scores`. Fill both.
- `one_thing_to_change`: one sentence. One behavior. Specific enough to try on the very next call.

## Steps

1. Read the rubric. List its ids.
2. Read the whole call file once before scoring anything.
3. For each rubric id, find the strongest evidence line. Decide the score against the 1, 3, and 5 definitions. Copy the quote and the line's timestamp.
4. Fill rapport, tone match, price handling, objections, top misses, rewrite, and the one thing to change. Run `locate` for the two seconds fields.
5. Write `<folder>/scorecards/<call_id>.json`.
6. Run `python coach.py validate` (with `--data-dir` if you are not using `data/`).
7. If your scorecard shows `[FAIL]`, fix exactly the fields it names and run validate again. A "quote not found" error means you changed some words: go back to the line and copy it again. Repeat until it passes. Also fix any `~` warnings about timestamps.
8. After all calls pass, run `python coach.py analyze` (with `--data-dir` if needed). It refreshes the numbers and the dashboard.
9. Tell the user, per call: the call id and the one thing to change. Do not compute averages or totals. Then tell them everything, including each score's quote and the transcript, is on one page they can open by double-clicking `Open-Dashboard.html` in the project folder.
