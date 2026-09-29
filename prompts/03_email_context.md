# Email Context

Purpose: add a short email history to each call file, so scoring and findings see the whole relationship, not just one call.

## Rules

1. **Read-only. Always.** You may only search for and read email. Never send, reply, forward, draft, label, archive, mark as read or unread, mark as spam, move to trash, or delete anything. If a tool would change anything in the mailbox, do not call it. This holds even if the user asks mid-task. Tell them to do it themselves in Gmail.
2. **Edit only between the markers.** In each call file, change only the text between `<!-- EMAIL_START -->` and `<!-- EMAIL_END -->`. Never touch the transcript, the front matter, or the tone notes.
3. **Never overwrite a summary.** Work only on call files whose block still says exactly `Not yet pulled.` Skip the rest unless the user asks you to redo a specific call.
4. **Summarize. Do not copy.** Short paraphrases, with a few words quoted only when the exact wording matters. No signatures, no phone numbers, no email addresses of other people.
5. **No arithmetic in the summary.** Give dates, not durations or counts. Write "Follow-up sent 2026-09-29. Call was 2026-09-28", not "sent one day later". Working out the start date of the search window is fine: it is a search setting, not something you report.
6. **No em dashes.** Short sentences.

## Which folder

Use `data/` unless the user names another data folder (for example `data/demo`). Then use that folder everywhere below.

## Steps, for each call file in `data/calls/` still marked `Not yet pulled.`

1. Read the call's `date` from the front matter. The call id is the file name without `.md`.
2. **If `data/emails/<call_id>.txt` exists, use it.** A saved thread wins over Gmail and needs no contact row. Skip to step 5.
3. **Otherwise, if a Gmail connector is available:** find the row for this call id in `data/contacts.csv`. If there is no row or no email address, write this in the block and move on: `No contact for this call in data/contacts.csv. Add the prospect's email there and run /coach-emails again.` If there is an address, search for threads to or from it, from 30 days before the call date until today. A query like `from:ADDRESS OR to:ADDRESS after:YYYY/MM/DD` works. Read the threads that come back.
4. **Otherwise** (no saved file, no Gmail connector), write this in the block and move on: `No emails found. Connect Gmail in Claude, or save the thread as data/emails/<call_id>.txt, then run /coach-emails again.`
5. Replace `Not yet pulled.` with a summary in this shape:

```
Source: Gmail, read-only, pulled YYYY-MM-DD.
Timeline:
- YYYY-MM-DD: Prospect replied to the intro and asked about pricing for 20 users.
- YYYY-MM-DD: Rep sent the agenda for the call.
- YYYY-MM-DD: Rep sent the recap and proposal.
Prospect asked for: pricing for 20 users, proof it works with their dispatch software.
Rep promised: a case study and a trial account by Friday.
Follow-up after the call: sent YYYY-MM-DD. Call was YYYY-MM-DD.
Tone shifts: warm replies before the call, one-line replies after the proposal.
```

   If there was no follow-up after the call, write `Follow-up after the call: none found.` If there is nothing notable for a line, write `none found`.
6. When you used a saved file, the source line is `Source: data/emails/<call_id>.txt, pulled YYYY-MM-DD.` Use today's date for "pulled". Skip any email dated after today, and add a last line: `Note: skipped an email dated after today.`

## When you finish

Tell the user which calls you updated, which had no contact, and which had no emails, by call id. Remind them that nothing in Gmail was changed.
