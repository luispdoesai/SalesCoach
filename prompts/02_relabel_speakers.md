# Relabel Speakers

Purpose: say which generic speaker label is the sales rep and which is the prospect, using only the opening of the call.

Code sends you this prompt, then some hints and the opening of a sales call. Code applies your answer to the transcript. You never rewrite transcript text.

## Rules

- Output JSON only. No prose before or after it.
- Map every speaker label that appears in the opening to `REP` or `PROSPECT`. Leave none out.
- The rep is the seller. Cues, strongest first:
  1. Introduces themselves and their company: "This is Sam from ...".
  2. Matches the rep name or rep company in the hints, when they are given.
  3. Asks for permission to record, or mentions the recording.
  4. Sets or runs the agenda: "I was hoping to spend 20 minutes on ...".
  5. Asks the opening discovery questions.
- The prospect is the buyer. They answer the questions, describe their situation, raise objections, and ask what it costs.
- Who speaks first is not a reliable cue. Prospects often answer the phone.
- More than two speakers: people on the seller's side (a sales engineer, a manager) are `REP`. People on the buyer's side are `PROSPECT`.
- If a Context section is given, it is the end of the previous part of the same call, already labeled. The same people keep talking across the break. Use the flow of the conversation to match them.
- Confidence is `high` only when at least one strong cue (1 to 3) points one way and nothing points the other way. Say `low` if the cues conflict, if the opening is too short to tell, or if you are guessing.
- `reason` is one sentence naming the cue you used, with a short quote.

## Output format

```json
{"speakers": [{"speaker": "spk_1", "role": "PROSPECT"}, {"speaker": "spk_2", "role": "REP"}],
 "confidence": "high",
 "reason": "spk_2 says 'this is Sam from Vantrellis' and sets the agenda."}
```
