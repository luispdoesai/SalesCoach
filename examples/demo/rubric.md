# Example Rubric: B2B Software, Discovery Through Proposal

Framework: MEDDIC for what to learn, SPIN-style questions for how to learn it.

This is a filled-in sample. `python coach.py init` copies it to `rubric/rubric.md` as a starter. That copy is private and gitignored. Replace it with your own by running `/coach-rubric` in Claude Code.

## Format rules

- Each behavior starts with a level-3 heading: `### snake_case_id: Human Name`
- Under it come three lines that start with `1:`, `3:`, and `5:`. Scores of 2 and 4 fall between them.
- Ids use lowercase letters, numbers, and underscores. They become column names in `results.csv`, so keep them the same once you start scoring.
- Every behavior must be something you can point to in a transcript. If you cannot quote it, you cannot score it.

## Behaviors

### agenda_setting: Agenda and Upfront Contract
1: No agenda. The rep jumps into a pitch, or small talk runs on with no plan.
3: The rep states an agenda but does not ask the prospect to confirm it or add to it.
5: The rep states the purpose, the time, and the outcome wanted, and the prospect agrees or adds an item.

### pain_discovery: Pain Discovery
1: The rep asks no questions about problems. The call is about features.
3: The rep asks about problems but accepts the first surface answer and moves on.
5: The rep asks an open question about a specific problem and follows up at least twice until the prospect describes the root cause in their own words.

### cost_of_inaction: Cost of Inaction
1: Nobody says what the problem costs or what happens if nothing changes.
3: The rep asks about impact, gets a vague answer, and moves on.
5: After the rep asks, the prospect states a concrete cost of doing nothing: money, hours, risk, or a missed goal.

### metrics_and_goals: Success Metrics
1: Nobody talks about what success would look like.
3: The prospect names a goal, but it has no number or date.
5: The rep gets the prospect to state a measurable goal with a number or a date.

### decision_process: Decision Process
1: The rep does not ask how the decision gets made.
3: The rep asks who decides, but not the steps, the timeline, or the criteria.
5: The rep confirms who signs, who else weighs in, the steps, and the timeline, and the prospect states them.

### active_listening: Active Listening
1: The rep interrupts, talks over the prospect, or answers a question the prospect did not ask.
3: The rep acknowledges what the prospect said but never plays it back.
5: The rep summarizes the prospect's situation using the prospect's words and asks if the summary is right.

### value_linking: Tie the Solution to the Pain
1: The rep lists features with no link to anything the prospect said.
3: The rep links features to the prospect's needs in general terms.
5: The rep shows only what solves the stated pains and repeats the prospect's own words while doing it.

### objection_handling: Objection Handling
1: The rep argues, gets defensive, or ignores the objection.
3: The rep answers the objection but does not check whether it is resolved.
5: The rep asks a question to understand the objection, answers the real concern, and confirms the prospect is satisfied.

### price_handling: Price Handling
1: The rep dodges a direct price question, or offers a discount before the prospect pushes back.
3: The rep states the price clearly, then concedes or discounts after the first pushback.
5: The rep holds price: states it clearly, does not concede or discount when the prospect pushes back, and stays silent or asks a question before any concession.

### next_steps: Next Step Commitment
1: The call ends with no next step, or only "I'll send over some info."
3: A next step is agreed, but with no date or time.
5: A specific next step with a date, a time, and the people who will attend is agreed on the call.
