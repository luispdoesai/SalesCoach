# AI Sales Coach: Full Guide

The [README](../README.md) gets you started. This page has the details.

- [Getting good transcripts](#getting-good-transcripts)
- [Each step in detail](#each-step-in-detail)
- [The dashboard](#the-dashboard)
- [Keeping old and new calls apart](#keeping-old-and-new-calls-apart)
- [Command reference](#command-reference)
- [Where things live](#where-things-live)
- [What the numbers mean](#what-the-numbers-mean)
- [Customize it](#customize-it)
- [Troubleshooting](#troubleshooting)

---

## Getting good transcripts

The cleaner the recording, the better the tool can tell you apart from the buyer.

| Source | Speaker labels | Notes |
|---|---|---|
| Zoom, Google Meet, Teams built-in transcripts | Named, very reliable | Best option for video calls |
| Fathom, Fireflies, Otter, Avoma, Granola | Named or generic | Free tiers vary, check current plans |
| Phone calls | Often one mixed track | Use a dialer that records each side separately, or fix labels afterward |
| Upload the audio yourself | Generic (`Speaker 1`, `Speaker 2`) | Gemini, MacWhisper, AssemblyAI, and Deepgram all support this |

Tips: say your name and the buyer's name in the first 30 seconds, use a headset, and avoid talking over each other.

**Copy-and-paste users:** if your transcript says `Speaker 1` and `Speaker 2`, paste this into Claude first:

```
This transcript has generic speaker labels. I am the sales REP. The other person is
the PROSPECT. I introduce myself and ask the opening questions, so use that to
figure out who is who. Relabel every line as REP or PROSPECT. Keep all timestamps.
Do not change any wording. If you are unsure about a line, mark it [UNSURE].
```

Check the first five lines. If they are swapped at the start, they are swapped everywhere.

**Optional prompts with the Gmail and Calendar connectors turned on in Claude:**

```
Look at my sent follow-up emails from the last 90 days. Split them into replied
and ignored. What differs: subject line, length, the ask, timing? Rewrite my three
weakest templates using what the replied ones have in common. Read only. Do not
send or draft anything.
```

```
Look at my next meeting. Pull the email thread with this person and give me a
one-page brief: who they are, what they care about, what I promised last time,
and 3 questions to ask. Read only.
```

---

## Each step in detail

### 1. Build your rubric: `/coach-rubric`

Claude interviews you about how you sell, then writes `rubric/rubric.md`, replacing the starter copy `init` made. Edit it until it sounds like you. Want a specific framework like MEDDIC, SPIN, Challenger, or Sandler? Say so.

### 2. Add your calls

Drop audio or video files into `data/inbox/`. Name each one:

```
YYYY-MM-DD_ProspectInitials_Stage.m4a
2026-09-28_JD_Discovery.m4a
```

### 3. Contacts and outcomes

- `data/contacts.csv`: `call_id, prospect_name, prospect_email, company`
- `data/outcomes.csv`: `call_id, outcome, deal_value, notes`

`outcome` is `won`, `lost`, `stalled`, or `open`. Without outcomes you get report cards but no "why." Outcomes are what let the tool compare wins to losses.

### 4. Transcribe: `python coach.py transcribe`

For each recording it will:

- Transcribe with Gemini, with speaker labels and timestamps
- Work out which speaker is you (REP) and which is the buyer (PROSPECT), from the first two minutes
- Add tone hints in one-minute windows
- Save `data/calls/<call_id>.md` and move the audio to `data/processed/`

Run it again any time. Finished calls are skipped. Add `--force` to redo one.

Gemini handles up to 30 minutes per request. Longer recordings are split automatically if [ffmpeg](https://ffmpeg.org/download.html) is installed. Without ffmpeg, they are rejected with a clear message.

If it is not sure who is who, it marks the file `needs_review` and prints the exact command to fix it. For example, to say you are `spk_2`:

```bash
python coach.py transcribe --file 2026-09-28_JD_Discovery --rep-speaker spk_2
```

This relabels the existing transcript. It does not call Gemini again, and it keeps any email history you already pulled.

Want to try transcription without a key? Drop any file named like `2026-09-28_JD_Discovery.m4a` into `data/inbox/` and run `python coach.py transcribe --mock`.

### 5. Email context: `/coach-emails`

Reads Gmail threads for each buyer and adds a timeline to the call file. Read-only. No Gmail connector? Put exported emails in `data/emails/<call_id>.txt` and it will use those.

### 6. Score: `/coach-score`

Writes one scorecard per call to `data/scorecards/`, then runs the validator on its own work and fixes anything that fails. Timing, like when you stated your price, comes from `python coach.py locate`, which reads the word timestamps. Claude never guesses seconds.

### 7. Analyze: `python coach.py analyze`

Validates scorecards, merges results, computes stats, and builds the won vs. lost comparison with charts. It prints a sample-size note that says how far to trust the comparison. Scorecards that fail validation are left out until fixed.

### 8. Findings: `/coach-findings`

Writes `Findings.md`, which shows at the top of your dashboard.

### 9. Practice: `/coach-practice`

Pick a buyer from `personas/` and drill your weakest objection.

---

## The dashboard

Double-click `Open-Dashboard.html` in the project folder, or run `python coach.py dashboard --open`. It shows:

- **Start here:** what is done and what to do next ("2 calls not scored yet, run /coach-score").
- **Your findings:** Findings.md, once you have written it.
- **Charts:** every call as a dot on won vs. lost charts, and where wins and losses differ by skill.
- **Every call:** the one thing to change, your weakest moment rewritten, each score with the exact words that earned it, price handling, objections, email history, tone hints, and the full transcript with quoted lines highlighted.

It is a single file that works offline and never leaves your computer. `analyze`, `demo`, and `/coach-findings` all refresh it.

---

## Keeping old and new calls apart

You do not need to track this yourself. The dashboard and `analyze` show a **Suggested** item with the exact command when it is time:

- **You changed your rubric.** Calls scored with the old one no longer count. Re-score them or set them aside.
- **Your calls reach back more than 90 days** before your latest one. Change the 90 in `config.yaml` (`archive: suggest_after_days`), or set it to 0 to turn this off.

Also archive when something changed: a new pitch, product, price, or territory, or a new quarter.

```bash
python coach.py archive --before 2026-09-01
```

It lists the calls it would move and asks first. Calls, scorecards, audio, emails, and outcome rows move to `data/archive/<period>/`, with a copy of the rubric they were scored with. Nothing is deleted. Each period keeps its own dashboard, linked from your main one.

- `--calls ID1,ID2` archives specific calls. `--name 2026-Q3` names the period.
- `python coach.py archive --list` shows current calls and every archived period.
- `python coach.py restore 2026-Q3` brings a period back.

Or ask Claude Code: "archive my calls from before September."

---

## Command reference

| Command | What it does |
|---|---|
| `python coach.py doctor` | Checks Python, packages, API key, folders, and that your data is not tracked by git |
| `python coach.py init` | Creates folders and starter files. Safe to re-run. Never overwrites your files |
| `python coach.py transcribe` | Audio to labeled call files. Options: `--file PATH_OR_CALL_ID`, `--force`, `--rep-speaker spk_N`, `--mock`, `--yes` (accept file names that do not follow the pattern) |
| `python coach.py validate` | Checks scorecards against your rubric and verifies every quote |
| `python coach.py merge` | Builds `results.csv` |
| `python coach.py stats` | Builds `stats.csv` from timestamps |
| `python coach.py compare` | Builds `compare.csv`, the sample-size note, and charts |
| `python coach.py analyze` | Runs validate, merge, stats, and compare |
| `python coach.py dashboard` | Builds `data/reports/dashboard.html`. `--open` opens it |
| `python coach.py archive --before DATE` | Sets older calls aside. Asks first. Also `--calls`, `--name`, `--list` |
| `python coach.py restore NAME` | Brings an archived period back |
| `python coach.py index` | Optional: builds `data/coach.db` (SQLite) from the CSVs |
| `python coach.py demo` | Runs everything on synthetic data in `data/demo/` |
| `python coach.py locate CALL_ID "quote"` | Prints the exact seconds a quote was said. Used by `/coach-score` |

Every command accepts `--data-dir DIR` to work on a different data folder, and `--debug` to show full error details.

| Claude Code command | What it does |
|---|---|
| `/coach-rubric` | Interviews you and builds your rubric |
| `/coach-emails` | Adds email history to each call file |
| `/coach-score` | Writes a validated scorecard per call |
| `/coach-findings` | Writes `Findings.md` |
| `/coach-practice` | Roleplay against a persona, then scores you |

---

## Where things live

```
data/
  inbox/        drop new audio here
  processed/    audio after transcription
  raw/          machine-readable transcripts (utterances, words, timing)
  calls/        one readable file per call: transcript, tone notes, email history
  scorecards/   one JSON per call, written by Claude
  reports/      dashboard.html, Findings.md, compare.csv, sample_size_note.txt, charts/
  contacts.csv  who each call was with
  outcomes.csv  won, lost, stalled, open
  results.csv   all scores in one table
  stats.csv     all measured numbers in one table
  archive/      older periods you set aside
  demo/         the demo's working copy, rebuilt by `python coach.py demo`
rubric/         your rubric (everything here but the example stays private)
prompts/        the instructions Claude follows. Edit them to fit your style
personas/       buyers for roleplay
examples/       synthetic demo calls and mock transcription fixtures
```

Everything is plain text and CSV. You can open the CSVs in Google Sheets or Excel. In `results.csv`, yes/no columns like `held_price` use `1` for yes and `0` for no, and blank means it does not apply.

---

## What the numbers mean

| Stat | How it is measured |
|---|---|
| Rep talk % | Your speaking time divided by your time plus the buyer's |
| Questions asked | Count of question marks in your lines (an approximation) |
| Longest monologue | Longest run of your speech without the buyer talking |
| Silence after price | Seconds from the end of your price to the next words by anyone, and who spoke. `0` means you kept talking. Blank until the call is scored |

The AI judges rapport, tone match, price handling, objection handling, and every rubric skill. Each judgment comes with a quote you can check.

**Limits to keep in mind:**

- **Small samples lie.** With fewer than 5 wins or 5 losses, the comparison is not meaningful yet. Under about 30 calls, treat patterns as hints.
- **Correlation is not cause.** Findings show what wins and losses had in common, not proof of why.
- **Tone tags are hints.** Spot-check a few against the recording.
- **Phone calls with mixed audio** cause the most mislabeled speakers. Check the first few lines of each transcript.

---

## Customize it

- **Different framework?** Re-run `/coach-rubric` and name it.
- **Different scoring style?** Edit `prompts/04_score_call.md`.
- **Different report?** Edit `prompts/05_findings.md`.
- **New buyer type?** Copy a file in `personas/` and change it.
- **Models?** Change the model names in `config.yaml` when Google updates them.
- **Not in English?** Set `language_codes` in `config.yaml`, for example `[es-ES]`. Empty means detect it.
- **Redaction?** Turn it on in `config.yaml` and list names to scrub. It is best-effort: it masks emails, phone numbers, and names you list, and it will miss things. It runs after transcription, so Google still hears the audio.

---

## Troubleshooting

| Problem | Try this |
|---|---|
| `python: command not found` | On a Mac, use `python3`. Inside the activated `.venv`, `python` works |
| `pip install` says "externally managed environment" | Use the `.venv` steps in the README. They avoid this |
| `doctor` says a package is missing | Run `source .venv/bin/activate`, then `python -m pip install -r requirements.txt` |
| `doctor` says the key is missing | Check that `.env` exists and has `GEMINI_API_KEY=` with your key |
| Commands stopped working after reopening Terminal | Run `cd SalesCoach` and `source .venv/bin/activate` again |
| A file is skipped | Rename it to `YYYY-MM-DD_Initials_Stage.ext`, or run `transcribe --yes` |
| Speaker labels are swapped | `python coach.py transcribe --file CALL_ID --rep-speaker spk_2`. No new transcription needed |
| Recording is over 30 minutes | Install ffmpeg and it is split automatically. Or split it yourself |
| Validation says a quote was not found | The AI paraphrased. Ask it to re-score using exact text from the transcript |
| `/coach-score` is not a command | Open Claude Code from inside the `SalesCoach` folder |
| Findings says it cannot compare | Add outcomes for more calls. You need both wins and losses |
| Something else went wrong | Run the same command with `--debug` and include the output in a GitHub issue. Never paste call data |
| Not sure a model name is current | Check the provider's docs. These change often |
