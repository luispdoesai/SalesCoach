# Write Findings

Purpose: write `data/reports/Findings.md`, which explains what the user's won and lost calls had in common and what to change, with every number copied from files that code produced.

## Rules

1. **Copy every number. Compute none.** Every statistic in Findings.md comes from `compare.csv`, `results.csv`, `stats.csv`, or `sample_size_note.txt`. Do not add, subtract, average, count, round, or convert anything yourself. If a number you want is not in those files, say it is not measured. Name the file and column next to important numbers, for example `(compare.csv: rep_talk_pct)`.
   - You may name which calls show a pattern, by call id ("DC, TA, and RI"). Do not turn that list into a count or a percent.
   - Not statistics, so allowed: today's date, call ids, timestamps, numbers inside verbatim quotes, and the thresholds written in this prompt (5, 30).
2. **Evidence for every pattern.** Each pattern names the call ids it comes from and includes at least one verbatim quote from a call file, with the call id and timestamp.
3. **Verbatim quotes.** Copy quotes exactly from the call files, or from scorecard quotes (the validator has already checked those). Never paraphrase inside quotation marks.
4. **Confidence on every pattern**, from the sample size in `sample_size_note.txt` and `compare.csv`:
   - **low:** `won_n` or `lost_n` for that metric in compare.csv is under 5, or you can name only one or two calls that show it.
   - **medium:** `won_n` and `lost_n` are both 5 or more, but the sample note says there are fewer than 30 calls.
   - **high:** `won_n` and `lost_n` are both 5 or more, there are 30 or more calls, and the calls you name show it on both sides.
5. **Say when a comparison is impossible.** With no won calls or no lost calls, say so plainly in the Summary and in the table section, and skip "what the wins did differently" or "where each lost deal turned" as needed. Do not invent a comparison.
6. **Never claim cause.** Write "won calls had" or "lost calls tended to", never "this caused" or "because of this you lost".
7. **Use only this user's data.** No outside benchmarks, no industry averages, no "top performers usually".
8. **Tone notes and email history are context.** Label anything from them as a hint.
9. **No em dashes.** Short sentences. Plain words. Write for a busy salesperson.

## Which folder

Use `data/` unless the user names another data folder (for example `data/demo`). Then read and write inside that folder, and add `--data-dir <folder>` to every `coach.py` command. Use `.venv/bin/python` instead of `python` if a `.venv` folder exists.

## Steps

1. Run `python coach.py analyze` so every CSV is fresh. If it reports failed scorecards, tell the user those calls are left out and name them.
2. Read `<folder>/reports/sample_size_note.txt`, `<folder>/reports/compare.csv`, `<folder>/results.csv`, `<folder>/stats.csv`, `<folder>/outcomes.csv`, every scorecard in `<folder>/scorecards/`, and the call files you quote.
3. Write `<folder>/reports/Findings.md` in the structure below. If the file exists, replace it.
4. Check your draft before saving: every number appears in one of the input files, every quote appears in a call file, no sentence claims cause, no em dashes.
5. Run `python coach.py dashboard` (with `--data-dir` if you are not using `data/`) so the findings appear on the dashboard page.
6. Tell the user the one skill to focus on, and that everything is on one page: `<folder>/reports/dashboard.html`. They can double-click `Open-Dashboard.html` in the project folder, or run `python coach.py dashboard --open`.

## Structure

```markdown
# Findings

Generated YYYY-MM-DD. <copy the first line of sample_size_note.txt>

## 1. Summary
Exactly 5 bullet points: what separates wins from losses so far, the biggest gap, the one skill to work on, and how much to trust this.

## 2. Won vs. lost
A table copied from compare.csv. Rows: rep_talk_pct, rep_questions, longest_rep_monologue_sec, price_silence_sec, rubric_avg, each rubric id, rapport_score, tone_match_score, held_price, conceded_or_discounted, objections_unhandled_count. Columns: Metric, Won (mean), Won n, Lost (mean), Lost n, Won minus lost. Copy values exactly. Use "-" for blanks.
Under the table, one line: held_price and conceded_or_discounted are rates from 0 to 1 (1 means every call where it applied). Their n counts only calls where it applied.

## 3. Top 3 patterns
For each: a one-line headline, two or three sentences, the supporting numbers (copied, with file and column), the call ids, at least one quote with call id and timestamp, and "Confidence: low/medium/high" with a one-line reason.

## 4. Where each lost deal turned
One entry per lost call: call id, the moment (timestamp), the quote, and one sentence on what happened there. Use the scorecard's rewrite, objections, and price_handling to find the moment.

## 5. What the wins did differently
Behaviors that show up in won calls and not in lost ones. Quotes from won calls, with call ids.

## 6. Ranked improvements
Most important first. Rank the rubric behaviors by their diff_won_minus_lost in compare.csv, largest first. Use only rubric id rows for the ranking, since they share the 1 to 5 scale. Use the stats rows (talk %, monologue, silence) as supporting evidence, not for ranking. Mention the lost calls whose top_misses name the same issue, by call id. For each:
- What to change, in one sentence.
- Instead of: "<verbatim quote from one of the user's calls>" (call id, timestamp)
- Say: "<the better version>"

## 7. The one skill for your next 5 calls
One skill. Why this one, in two sentences. One thing to say or do on each call to practice it. Suggest one persona from the files in `personas/` to drill it with `/coach-practice`.

## 8. Caveats
Copy every line of sample_size_note.txt. Then add: tone notes are hints from an audio model; speaker labels may be wrong on calls marked needs_review (name them, or say there are none); scorecards are AI judgment backed by quotes, so spot-check a few. If any rubric score's `why` starts with "Not expected at the", name those calls and behaviors: those 1s reflect the call stage, not a miss, and they pull the averages down.
```
