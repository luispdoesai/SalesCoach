# AI Sales Coach

**Find out why you win deals and why you lose them, using your own sales calls.**

You record your calls. This tool listens to all of them, grades each one, and tells you in plain words what your winning calls did that your losing calls did not. Then it lets you practice against a tough buyer until you get better.

Free and open source. Built by Luis ([@LuisPDoesAI](https://instagram.com/LuisPDoesAI)).

---

## What it tells you

Here is a real excerpt from the built-in demo (14 made-up calls):

> - Won calls tied the product to the prospect's own words. Lost calls walked through the platform.
> - Lost calls had the rep talking more: 70.88% of talk time against 59.87% on won calls.
> - The one skill for the next 5 calls: before showing anything, get the prospect to describe the problem and what it costs, then show only the part that fixes it.

![Chart from the demo: the rep talked more on lost calls than on won calls](docs/images/demo_talk_pct.png)

Every call also gets a report card:

- **A score for each skill**, like finding the pain, handling objections, and holding your price
- **Proof for every score.** Each score quotes the exact words you said. If there is no quote, there is no score.
- **Your weakest moment, rewritten** the way it should have sounded
- **The one thing to change** on your next call

---

## Two ways to use it

| | **Option 1: Copy and paste** | **Option 2: Full tool** |
|---|---|---|
| Time to start | 10 minutes | About 30 minutes, once |
| Tech skill | None | Comfortable following steps |
| What you need | A Claude account and call transcripts | Claude Code, a free Google AI key, and this project |
| Best for | Trying it on a few calls | Every call, automatically |

**Not sure? Start with Option 1.**

---

## Option 1: Copy and paste (no setup)

You only need [Claude](https://claude.ai) and a transcript of your call. Zoom, Google Meet, Teams, Fathom, Otter, and Fireflies can all give you one.

**Step 1. Build your scorecard.** Paste this into Claude:

```
I sell [product] to [type of buyer]. Before you build anything, ask me 5 questions
about my sales process: deal size, sales cycle length, who I usually talk to, my
biggest struggle, and how I usually lose deals.

Then build a call scoring rubric with 8 to 10 behaviors I can point to in a
transcript. For each one, define what a 1, a 3, and a 5 looks like. Include one
behavior for handling price. Every score must require a direct quote as evidence.
```

Answer its questions. Cross out anything that does not fit how you sell. Save the result.

**Step 2. Grade a call.** Paste your scorecard and one transcript, then:

```
The sales rep is me. Grade me harshly. For each item on my scorecard, give a
score from 1 to 5, the timestamp, a word-for-word quote as proof, and one sentence
on why. No quote, no score above 1.

Then give me:
1. My top 3 misses
2. Did I state my price? Did I hold it?
3. My weakest moment, rewritten the way it should have sounded
4. The ONE thing to change on my next call
```

**Step 3. Find your patterns (after 10 or more calls).** Paste your graded calls and say which ones you won and lost:

```
I won these calls: [list]. I lost these: [list]. What did my wins do that my
losses did not? Rank my top 3 gaps by how much money they likely cost me. Quote
real lines. Tell me how sure you are, given how few calls this is.
```

**Step 4. Practice.**

```
Play a skeptical CFO who keeps saying "just send me the info." Be hard to
convince. Do not help me. When I type "end," grade me on my scorecard and tell me
which objection I handled worst.
```

Repeat the same buyer until your score goes up.

---

## Option 2: The full tool

Drop in your call recordings. Get a report card for every call, real numbers on how you talk, and one page that explains your wins and losses.

### What you need

1. **Python**, a free program that runs this tool. [Download it here](https://www.python.org/downloads/) (version 3.10 or newer).
2. **Claude Code**, the Claude app that works with files on your computer. [Get it here](https://claude.com/product/claude-code).
3. **A Google AI key** (free to start). It turns your audio into text. [Get one here](https://aistudio.google.com/).

### Set it up (one time)

Open the **Terminal** app (on a Mac, press Cmd + Space and type "Terminal"). Copy and paste these lines one at a time, pressing Enter after each:

```bash
git clone https://github.com/luispdoesai/SalesCoach.git
cd SalesCoach
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python coach.py init
```

On Windows, use `python` instead of `python3`, and `.venv\Scripts\activate` instead of the `source` line.

Now open the new file called `.env` in the `SalesCoach` folder and paste your Google key after the equals sign:

```
GEMINI_API_KEY=paste-your-key-here
```

Check that everything works:

```bash
python coach.py doctor
```

### See it work first (2 minutes, no key needed)

```bash
python coach.py demo
```

Then double-click **`Open-Dashboard.html`** in the project folder, or open `data/demo/reports/dashboard.html`. That is what your own results will look like.

### Use it on your calls

Open Claude Code inside the `SalesCoach` folder. Then:

| Step | Do this | What happens |
|---|---|---|
| 1 | Type `/coach-rubric` | Claude asks how you sell and builds your personal scorecard |
| 2 | Put recordings in `data/inbox/` | Name them like `2026-09-28_JD_Discovery.m4a` (date, buyer's initials, call type) |
| 3 | Fill in `data/outcomes.csv` and `data/contacts.csv` | Mark each call `won`, `lost`, `stalled`, or `open`, and say who it was with. This is how it learns what wins |
| 4 | Run `python coach.py transcribe` | Turns audio into text and figures out which speaker is you |
| 5 | Type `/coach-emails` (optional) | Reads your Gmail threads with each buyer for context. Read-only |
| 6 | Type `/coach-score` | Grades every call, with a quote as proof for each score |
| 7 | Run `python coach.py analyze` | Crunches the numbers and builds your charts |
| 8 | Type `/coach-findings` | Writes the page that explains your wins and losses |
| 9 | Type `/coach-practice` | Roleplay against a tough buyer, then get graded |

Double-click **`Open-Dashboard.html`** any time to see everything on one page. It tells you what is done and what to do next.

New calls? Drop them in `data/inbox/` and repeat steps 4 to 8. Finished calls are skipped automatically.

Stuck? Just ask Claude Code in plain words, like "why did my transcribe fail?" or "archive my calls from before September."

---

## Your privacy

- **Get consent to record.** Many places require everyone on the call to agree. Say it at the start of the call.
- **Check your company's rules** before using any AI tool on customer calls.
- **Know where your data goes.** Audio is sent to Google to turn it into text, then deleted from Google's storage. Claude reads the text to grade it. Check the data terms for your Google and Claude plans.
- **Your calls stay on your computer.** Your recordings, transcripts, key, and scorecard are never uploaded to GitHub. This project is set up to block that.
- **Gmail is read-only.** It never sends, drafts, labels, or deletes anything.

This is not legal advice.

## Keep it honest

- **Every score needs proof.** The tool checks that each quote really appears in the call. Made-up quotes are rejected.
- **The numbers come from code, not AI guesses.** Talk time, questions asked, and silence after your price are measured from the recording's timestamps.
- **Small samples can mislead.** You need at least 5 wins and 5 losses before comparisons mean much. Under 30 calls, treat patterns as hints.
- **Read a few report cards yourself.** If a score feels wrong, look at the quote.

---

## More help

- **[The full guide](docs/GUIDE.md)**: every command, where files live, what each number means, customizing, archiving old calls, and troubleshooting.
- **[Data formats](docs/DATA_FORMATS.md)**: the exact file formats, for anyone changing the code.
- **Found a bug?** Open a GitHub issue. Never paste real call data.

## Contributing

Pull requests are welcome. Run `pytest` first (it works offline, no keys needed). Never commit real call data.

## License

MIT. Free to use, change, and share.
