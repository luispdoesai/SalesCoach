# Findings

Generated 2026-09-28. Sample: 14 calls. 6 won, 5 lost, 2 stalled, 1 open, 0 with no outcome yet.

This is an example written from the synthetic demo calls. Yours is written by `/coach-findings` from your own calls.

## 1. Summary

- Won calls tied the product to the prospect's own words. Lost calls walked through the platform.
- The biggest rubric gap is Tie the Solution to the Pain: 4.33 on won calls and 1.8 on lost calls (compare.csv: value_linking).
- Lost calls had the rep talking more: 70.88% of talk time against 59.87% on won calls (compare.csv: rep_talk_pct).
- The one skill for the next 5 calls: before showing anything, get the prospect to describe the problem and what it costs, then show only the part that fixes it.
- Trust this as a hint. There are 6 won and 5 lost calls, and fewer than 30 in total (sample_size_note.txt).

## 2. Won vs. lost

| Metric | Won (mean) | Won n | Lost (mean) | Lost n | Won minus lost |
|---|---|---|---|---|---|
| rep_talk_pct | 59.87 | 6 | 70.88 | 5 | -11.01 |
| rep_questions | 8.67 | 6 | 3.8 | 5 | 4.87 |
| longest_rep_monologue_sec | 14.32 | 6 | 29.7 | 5 | -15.38 |
| price_silence_sec | 2.32 | 5 | 0.2 | 5 | 2.12 |
| rubric_avg | 3.33 | 6 | 2.06 | 5 | 1.27 |
| agenda_setting | 3.0 | 6 | 2.0 | 5 | 1.0 |
| pain_discovery | 2.83 | 6 | 1.6 | 5 | 1.23 |
| cost_of_inaction | 3.83 | 6 | 1.8 | 5 | 2.03 |
| metrics_and_goals | 3.67 | 6 | 2.4 | 5 | 1.27 |
| decision_process | 3.33 | 6 | 2.4 | 5 | 0.93 |
| active_listening | 3.33 | 6 | 2.4 | 5 | 0.93 |
| value_linking | 4.33 | 6 | 1.8 | 5 | 2.53 |
| objection_handling | 2.67 | 6 | 1.6 | 5 | 1.07 |
| price_handling | 2.33 | 6 | 1.4 | 5 | 0.93 |
| next_steps | 4.0 | 6 | 3.2 | 5 | 0.8 |
| rapport_score | 3.67 | 6 | 3.2 | 5 | 0.47 |
| tone_match_score | 3.17 | 6 | 2.6 | 5 | 0.57 |
| held_price | 0.5 | 4 | 0.0 | 1 | 0.5 |
| conceded_or_discounted | 0.6 | 5 | 1.0 | 5 | -0.4 |
| objections_unhandled_count | 1.0 | 6 | 1.2 | 5 | -0.2 |

held_price and conceded_or_discounted are rates from 0 to 1 (1 means every call where it applied). Their n counts only calls where it applied.

## 3. Top 3 patterns

### Won calls linked the product to the pain the prospect described

Won calls scored 4.33 on value_linking and lost calls scored 1.8 (compare.csv: value_linking). In won calls the rep repeated the prospect's own words before showing the fix. In lost calls DC, TA, and RI, the rep listed features instead.

- Won, 2026-07-28_PL_Demo at 01:23: "You said our front desk lead spends two or three hours a day on the phone"
- Lost, 2026-07-21_DC_Demo at 00:18: "So let me walk you through the platform."

Confidence: medium. Both groups have 5 or more calls, but there are fewer than 30 calls in total.

### Lost calls had the rep talking more, in longer stretches

The rep's share of talk time was 70.88% on lost calls and 59.87% on won calls (compare.csv: rep_talk_pct). The longest stretch without a pause was 29.7 seconds on lost calls and 14.32 on won calls (compare.csv: longest_rep_monologue_sec). Lost calls DC, TA, and RI each had a 42.9 second stretch (stats.csv: longest_rep_monologue_sec). Won calls also had more questions: 8.67 against 3.8 (compare.csv: rep_questions).

- Lost, 2026-08-04_TA_Discovery at 00:15: "Most teams we talk to struggle with dispatch, so let me show you how we fix that."

Confidence: medium. Same sample size as above.

### Lost calls gave up price without being asked

Every lost call where price was stated included a discount or concession: conceded_or_discounted was 1.0 on lost calls and 0.6 on won calls (compare.csv). Silence after stating price was 0.2 seconds on lost calls and 2.32 on won calls (compare.csv: price_silence_sec). In TA, RI, LB, and BK the rep offered a discount in the same breath as the price, before any pushback.

- Lost, 2026-08-14_RI_Demo at 01:31: "if you sign this month I can take twenty percent off"
- Won, 2026-08-11_HM_Proposal at 02:02, right after pushback: "What were you comparing it to?"

Confidence: medium for the discount pattern. Low for held_price itself: only 1 lost call had pushback to hold against (compare.csv: held_price, lost n 1).

## 4. Where each lost deal turned

- **2026-07-21_DC_Demo**, 01:21: "I could probably do fifteen percent off if that helps." The prospect said the price was steep and the rep answered with a discount instead of a question.
- **2026-08-04_TA_Discovery**, 00:15: "Most teams we talk to struggle with dispatch, so let me show you how we fix that." The rep pitched before asking a single question about the prospect's problem.
- **2026-08-14_RI_Demo**, 00:43: "let me walk you through the platform" A long feature walk-through started with no link to anything the prospect said.
- **2026-08-28_LB_Demo**, 00:25: "Most teams we talk to struggle with time tracking, so let me show you how we fix that." Same move as TA: pitch first, no discovery.
- **2026-09-08_BK_Discovery**, 01:03: "if you sign this month I can take twenty percent off" The prospect had named a real cost earlier, but the rep discounted before any pushback.

## 5. What the wins did differently

- They asked what the problem costs. cost_of_inaction was 3.83 on won calls and 1.8 on lost calls (compare.csv). In 2026-08-11_HM_Proposal at 01:04 the prospect put a number on it: "roughly four thousand dollars a week in empty chairs".
- They tied the price back to that cost. In 2026-08-25_KV_Proposal at 01:38: "Fair. Earlier you mentioned a customer worth about sixty thousand a year. How does the price compare to that?"
- They got a measurable goal. metrics_and_goals was 3.67 on won calls and 2.4 on lost calls (compare.csv).

## 6. Ranked improvements

1. **Link what you show to what they said** (value_linking, gap 2.53).
   - Instead of: "So let me walk you through the platform." (2026-07-21_DC_Demo, 00:18)
   - Say: "You said your dispatcher spends most of every Friday afternoon on this. Here is the one part that fixes that."
2. **Ask what doing nothing costs** (cost_of_inaction, gap 2.03). Lost calls DC, TA, RI, and LB never got to a cost.
   - Instead of: "Most teams we talk to struggle with dispatch, so let me show you how we fix that." (2026-08-04_TA_Discovery, 00:15)
   - Say: "Before I show you anything, walk me through what happened the last time dispatch went wrong. What did that cost you?"
3. **Get one measurable goal** (metrics_and_goals, gap 1.27).
   - Instead of: "Our platform helps teams like yours schedule faster and keep everyone updated." (2026-09-08_BK_Discovery, 00:40)
   - Say: "If this worked, what number would be different by the end of the quarter?"
4. **Dig into the problem before pitching** (pain_discovery, gap 1.23).
   - Instead of: "What's the biggest challenge with time tracking right now?" followed by moving on (2026-08-14_RI_Demo, 00:17)
   - Say: "What makes that the hardest part? And when it goes wrong, what does it look like for you?"
5. **State the price and stop** (price_handling, gap 0.93).
   - Instead of: "if you sign this month I can take twenty percent off" (2026-08-14_RI_Demo, 01:31)
   - Say: "It's twelve thousand dollars a year." Then stay quiet until the prospect speaks.

## 7. The one skill for your next 5 calls

**Link every part of the demo to a pain the prospect said out loud, in their words.** It has the biggest won minus lost gap in your rubric, and it fixes the long feature walk-throughs that showed up in lost calls DC, TA, and RI. On every call, write down the prospect's exact phrase for their problem, and start each part of the demo with "You said...". Drill it with `/coach-practice` against the Silent Stakeholder persona, who only engages when you use their words.

## 8. Caveats

- Sample: 14 calls. 6 won, 5 lost, 2 stalled, 1 open, 0 with no outcome yet.
- Fewer than 30 calls in total: treat any pattern as a directional hint, not proof.
- This shows correlation, not cause. It shows what wins and losses had in common, not why they happened.
- Tone notes are hints from an audio model.
- No calls are marked needs_review, so the speaker labels are taken as correct.
- Scorecards are AI judgment backed by quotes. Spot-check a few.
- No rubric scores were marked "Not expected at the" stage, so every 1 counts as a real miss.
