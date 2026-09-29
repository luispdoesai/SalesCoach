# CLAUDE.md

Rules for Claude Code sessions in this repo. Read them before you change anything or run a `/coach-*` command.

## What this is

AI Sales Coach turns a salesperson's recorded calls into coaching. It has two layers, kept separate:

- **Python scripts** (`coach.py` and `coach/`) do everything deterministic: transcription calls, file handling, statistics, validation, charts.
- **Claude Code** does the judgment work by following the prompt files in `prompts/`: building the rubric, pulling email context, scoring calls, writing Findings.md, running roleplays.

The users are salespeople, many non-technical. The repo is public.

## Hard rules

1. **Never commit call data.** `data/`, `.env`, `rubric/rubric.md`, and audio or video files are gitignored. Never force-add them. Never copy call data outside `data/`. Never weaken `.gitignore`.
2. **Gmail is read-only.** Only search and read. Never send, draft, reply, forward, label, archive, mark, trash, or delete anything.
3. **Quotes are verbatim.** Copy evidence exactly from one line of the call file. Do not fix grammar, spelling, or filler words. The validator forgives only case, spacing, and curly versus straight quotes. No quote, no score of 2 or higher.
4. **Never edit transcript text.** Relabeling changes speaker labels only. Scoring never touches the call file. Email History is edited only between `<!-- EMAIL_START -->` and `<!-- EMAIL_END -->`.
5. **Never do math in prose.** Every number in a report is copied from a CSV that code produced. If you need a number that is not in a CSV, add it to the code. Do not compute it yourself.
6. **Never print the API key.** Never write it to any file except `.env`.
7. **No em dashes.** Anywhere: code comments, prompts, docs, reports. Short sentences. Plain words. No filler.
8. **No Anthropic API dependency.** Judgment steps run inside Claude Code on the user's own subscription.
9. **Model names live in `config.yaml`.** Never hardcode them.
10. **Friendly errors.** Expected problems raise `CoachError(problem, fix)` from `coach/friendly.py`: one sentence on what is wrong, one on how to fix it. Users never see a traceback for an expected problem.
11. **Idempotent.** Re-running a command skips finished work. `--force` redoes it.
12. **Never invent** statistics, quotes, benchmarks, or outcomes.

## Layout

- `coach.py`: the CLI entry point. Commands live in `coach/cli.py`.
- `coach/`: the Python package. `config.py` has paths and settings. `friendly.py` has errors and output helpers.
- `prompts/`: the instructions Claude Code follows for judgment steps. They are the product. Edit them with care.
- `.claude/commands/`: thin slash commands that point at `prompts/`.
- `rubric/rubric.example.md`: the shareable sample. `rubric/rubric.md`: the user's private rubric.
- `personas/`: buyers for roleplay practice.
- `examples/demo/`: fully synthetic demo data. Invented names only. No real people or companies.
- `data/`: the user's private workspace, created by `python coach.py init`.

## Data contracts

`BUILD_PROMPT.md` defines the exact formats for call files, raw JSON, scorecards, and CSVs. Follow them. If you change a format, update the code, the tests, the prompts, and the README together.

## Commands

```
python coach.py doctor                   check the setup
python coach.py init                     create folders and starter files
python coach.py transcribe [--mock]      audio in data/inbox to call files
python coach.py validate                 check scorecards and verify every quote
python coach.py analyze                  validate, merge, stats, compare
python coach.py locate CALL_ID "quote"   exact seconds for a quote (use this, never estimate)
python coach.py demo                     full analysis on synthetic data in data/demo
python coach.py --help                   list every command
pytest                                   run the tests (offline, no keys)
```

**Point users to the dashboard.** Many users are not technical. After scoring, analysis, or findings, tell them to double-click `Open-Dashboard.html` (or run `python coach.py dashboard --open`) instead of sending them into `data/` folders. It shows status, findings, charts, and every call's scores, quotes, emails, and transcript on one page.

**Keeping periods apart.** When a user wants old calls out of their numbers ("archive everything before September"), run `python coach.py archive --before YYYY-MM-DD` without `--yes` first, show them the list it prints, and add `--yes` only after they agree. Use `--calls` for specific calls and `--name` if they name the period. `restore NAME` undoes it. Archived periods live in `data/archive/<name>/` with their own rubric copy. To score or write findings for one, use it as the data folder (`--data-dir data/archive/<name>`). Never mix calls from different archives by hand.

`--mock` (or `COACH_MOCK=1`) runs transcription on bundled fixtures with no network. `--data-dir DIR` (or `COACH_DATA_DIR`) points commands at a different data folder, which may hold its own `rubric.md`. Use `.venv/bin/python` if a `.venv` folder exists.

When editing `examples/demo/build_demo.py`, rebuild with `python examples/demo/build_demo.py` and keep every name invented.
