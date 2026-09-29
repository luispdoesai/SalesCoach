# Build Your Rubric

Purpose: interview the user about how they sell, then write `rubric/rubric.md`: 8 to 10 behaviors a coach can point to in a transcript, each with what a 1, a 3, and a 5 look like.

## Rules

1. **Ask before you write.** Your first message asks the five questions below and nothing else. Do not draft anything until the user answers. If they skip a question, ask once more, then work with what you have.
2. **Observable only.** Every behavior must be something you can quote from a transcript. "Builds trust" is not observable. "Summarizes the prospect's problem in their words and asks if it is right" is.
3. **Exact format.** The validator parses this file. Follow the format section to the character.
4. **Include price handling.** One behavior must use this definition of held price: the rep stated a price, then did not concede or discount when the prospect pushed back, and stayed silent or asked a question before any concession.
5. **Fit their sale.** A two-call transactional sale and a six-month committee sale need different behaviors. Cut anything that does not match what the user told you.
6. **The rubric is private.** It is gitignored. Never copy it anywhere else in the repo. It may hold an employer's playbook.
7. **No em dashes.** Short sentences. Plain words.

## Step 1: Ask these five questions, in one message

1. What do you sell, in one sentence?
2. Who buys it? Their role, and the kind of company.
3. What is a typical deal size?
4. How long is a typical sales cycle, from first call to signature?
5. Who do you usually talk to on calls: the person who signs, a user, a committee, a gatekeeper?

End with: "If you already use a framework (MEDDIC, SPIN, Challenger, Sandler, or your company's own), tell me and I will build on it."

## Step 2: Pick one framework

Use the one the user named. Otherwise pick one and say why in two sentences:

- **Short cycle, one decision maker, smaller deals:** SPIN questioning with Sandler-style upfront contracts and pain funnels.
- **Long cycle, several stakeholders, larger deals:** MEDDIC or MEDDPICC.
- **The buyer does not know they have a problem yet, or the product changes how they work:** Challenger (teach, tailor, take control).

## Step 3: Draft 8 to 10 behaviors

Cover the whole call: opening, discovery, impact, decision process, presenting, objections, price, next steps. Show the draft in the chat first. Then ask: "Cut or change anything that does not match how you sell. What should go?" Revise until the user is happy.

## Step 4: Write the file

1. If `rubric/rubric.md` exists and its first line starts with `<!-- STARTER RUBRIC`, replace it without asking.
2. If it exists without that line, the user wrote or edited it. Ask before replacing. If they say yes, first copy it to `rubric/rubric.backup-YYYY-MM-DD.md` (today's date). Everything in `rubric/` except the example is gitignored.
3. If scorecards already exist in `data/scorecards/`, warn: "Changing or renaming ids means existing scorecards will fail validation until those calls are scored again."
4. Write the file. Then run `python coach.py validate` (or `.venv/bin/python coach.py validate` if a `.venv` folder exists). The first line of its output must say "against N rubric behaviors" with the number you wrote. If it reports a rubric problem, fix the file and run it again.
5. Tell the user in two or three sentences what you built and that the next step is adding calls to `data/inbox/`.

## Format (the validator depends on this)

```markdown
# Rubric: <what they sell>

Framework: <name>. <One sentence on why.>

### snake_case_id: Human Name
1: What a weak version looks like, as something you could quote.
3: What a partial version looks like.
5: What a strong version looks like.
```

- Headings are exactly three `#`, a space, the id, a colon, a space, the name.
- Ids: lowercase letters, numbers, and underscores, starting with a letter. They become column names in `results.csv`. Keep them stable once scoring starts.
- The three level lines start with `1:`, `3:`, and `5:` at the start of the line. One line each.
- No other `###` headings in the file.
- The price behavior's `5:` line states the held price definition. Its `1:` line describes dodging a direct price question or discounting before any pushback.

See `rubric/rubric.example.md` for a complete sample.
