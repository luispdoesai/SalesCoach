"""Build the synthetic demo data in examples/demo/.

Everything here is invented: the rep, the prospects, the companies, the
numbers. Outcomes are assigned first, then each call's behaviors are drawn
at random with better odds for won calls, so the demo has patterns to find
but is not perfectly clean. The output is fixed by the seed.

Run from the repo root:  python examples/demo/build_demo.py
"""

from __future__ import annotations

import csv
import json
import random
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from coach import callfile  # noqa: E402

SEED = 20260928
REP_NAME, REP_CO = "Sam", "Vantrellis"
WPS = {"REP": 2.7, "PROSPECT": 2.4}  # speaking pace, words per second

# (date, first, last, company, slug, stage, outcome, deal_value, pain)
PAINS = {
    "crews": dict(task="building the crew schedule", short="crew scheduling", person="our office manager",
                  hours="about six hours every week", incident="we sent two crews to the same job last month",
                  cost="around eighteen thousand dollars in overtime last quarter", unit="jobs",
                  target="an hour a week", solution="the schedule updates every crew's phone the moment it changes"),
    "dispatch": dict(task="dispatching drivers", short="dispatch", person="our dispatcher",
                     hours="most of every Friday afternoon", incident="we missed three pickups in August",
                     cost="a customer worth about sixty thousand a year", unit="pickups",
                     target="thirty minutes a day", solution="drivers confirm every change from their phone"),
    "clinics": dict(task="filling last-minute cancellations", short="cancellations", person="our front desk lead",
                    hours="two or three hours a day on the phone", incident="we had eleven empty slots last Tuesday",
                    cost="roughly four thousand dollars a week in empty chairs", unit="appointments",
                    target="under five empty slots a week", solution="open slots go out to the waitlist by text automatically"),
    "field": dict(task="tracking technician hours", short="time tracking", person="our payroll coordinator",
                  hours="a full day at every month end", incident="we underbilled a client by forty hours",
                  cost="close to nine thousand dollars in unbilled time last quarter", unit="timesheets",
                  target="a two hour month end", solution="hours come straight from the job check-ins"),
}
PROSPECTS = [
    ("2026-07-14", "Marisol", "Okafor", "Tarnhollow Builders", "tarnhollow", "Discovery", "won", 24000, "crews"),
    ("2026-07-21", "Dev", "Castellan", "Orsolo Freight", "orsolo", "Demo", "lost", None, "dispatch"),
    ("2026-07-28", "Priya", "Lindqvist", "Kestrelmoor Clinics", "kestrelmoor", "Demo", "won", 31000, "clinics"),
    ("2026-08-04", "Tomasz", "Achebe", "Pellwyn Supply", "pellwyn", "Discovery", "lost", None, "dispatch"),
    ("2026-08-11", "Hana", "Moreau", "Quenby Dental Studio", "quenby", "Proposal", "won", 18000, "clinics"),
    ("2026-08-14", "Rafael", "Istvan", "Brackwater Electric", "brackwater", "Demo", "lost", None, "field"),
    ("2026-08-18", "Ines", "Halvorsen", "Glimmerdale Homes", "glimmerdale", "Discovery", "stalled", None, "crews"),
    ("2026-08-25", "Kofi", "Varga", "Ashcombe Haulage", "ashcombe", "Proposal", "won", 42000, "dispatch"),
    ("2026-08-28", "Lena", "Bramwell", "Fenwright HVAC", "fenwright", "Demo", "lost", None, "field"),
    ("2026-09-02", "Arjun", "Pelletier", "Mossgate Physio", "mossgate", "Demo", "won", 15000, "clinics"),
    ("2026-09-08", "Beatriz", "Kowal", "Stonerill Roofing", "stonerill", "Discovery", "lost", None, "crews"),
    ("2026-09-11", "Oisin", "Takeda", "Larchfield Plumbing", "larchfield", "Proposal", "stalled", None, "field"),
    ("2026-09-16", "Yara", "Delacroix", "Corvane Logistics", "corvane", "Demo", "won", 36000, "dispatch"),
    ("2026-09-22", "Emeka", "Sorensen", "Wrenbury Dental", "wrenbury", "Discovery", "open", None, "clinics"),
]
BOSSES = [("Dana", "COO"), ("Morgan", "operations director"), ("Casey", "owner"), ("Robin", "CFO")]
PRICES = ["twelve thousand", "eighteen thousand", "twenty-four thousand", "thirty thousand", "thirty-six thousand"]
LEVEL_ODDS = {"won": (0.6, 0.3), "lost": (0.15, 0.4), "stalled": (0.3, 0.45), "open": (0.4, 0.4)}

RUBRIC_IDS = ["agenda_setting", "pain_discovery", "cost_of_inaction", "metrics_and_goals", "decision_process",
              "active_listening", "value_linking", "objection_handling", "price_handling", "next_steps"]
WHY = {
    "agenda_setting": {5: "The rep set purpose, time, and outcome, and asked the prospect to add to it.",
                       3: "The rep stated a plan but never asked the prospect to confirm or add to it.",
                       1: "The rep started pitching with no agenda."},
    "pain_discovery": {5: "The rep asked an open question and followed up twice to reach the root cause.",
                       3: "The rep asked about problems once and moved on after the first answer.",
                       1: "The rep asked no questions about problems before pitching."},
    "cost_of_inaction": {5: "The prospect named a concrete cost of doing nothing after the rep asked.",
                         3: "The rep asked about impact but accepted a vague answer.",
                         1: "Nobody discussed what the problem costs."},
    "metrics_and_goals": {5: "The prospect stated a measurable goal with a number.",
                          3: "The goal stayed vague, with no number or date.",
                          1: "Success was never discussed."},
    "decision_process": {5: "The rep confirmed who signs, who weighs in, and the timeline.",
                         3: "The rep asked who decides but not the steps or timeline.",
                         1: "The rep never asked how the decision gets made."},
    "active_listening": {5: "The rep played the situation back in the prospect's words and checked it.",
                         3: "The rep acknowledged answers but never summarized them.",
                         1: "The rep cut in and answered a question the prospect had not asked."},
    "value_linking": {5: "The rep tied the product directly to the pain the prospect described.",
                      3: "The rep described the product in general terms.",
                      1: "The rep delivered a long feature list with no link to the prospect's problems."},
    "objection_handling": {5: "The rep asked a question to understand the objection and checked it was resolved.",
                           3: "The rep answered the objection but did not check it was resolved.",
                           1: "The rep got defensive and argued with the objection."},
    "price_handling": {5: "The rep stated price, stayed silent, and answered pushback with a question.",
                       3: "The rep stated price clearly, then offered a discount after the first pushback.",
                       1: "The rep offered a discount before the prospect pushed back at all."},
    "next_steps": {5: "A specific meeting with a day, time, and attendees was agreed on the call.",
                   3: "A next step was agreed with no date or time.",
                   1: "The call ended with only a promise to send information."},
}
MISS = {
    "agenda_setting": "No upfront agreement on what the call would cover or decide.",
    "pain_discovery": "Pitched before understanding the problem in the prospect's own words.",
    "cost_of_inaction": "Never got the prospect to put a number on the cost of doing nothing.",
    "metrics_and_goals": "Left without a measurable goal to anchor the value.",
    "decision_process": "Does not know who signs or how the decision gets made.",
    "active_listening": "Never played the prospect's situation back to confirm it.",
    "value_linking": "Talked features instead of tying the product to the stated pain.",
    "objection_handling": "Answered objections without finding the real concern.",
    "price_handling": "Gave up price without being asked to.",
    "next_steps": "Ended without a dated next step.",
}
BETTER = {
    "agenda_setting": "Thanks for the time. I'd like to spend thirty minutes on how {short} works today, show you one thing if it fits, and decide together if a next step makes sense. What would you add?",
    "pain_discovery": "Before I show you anything, walk me through what happened the last time {short} went wrong.",
    "cost_of_inaction": "If nothing changes for the next six months, what does that cost you?",
    "metrics_and_goals": "If this worked, what number would be different by the end of the quarter?",
    "decision_process": "Who else weighs in on a decision like this, and how did you buy the last tool like it?",
    "active_listening": "Let me make sure I have this right. Did I miss anything?",
    "value_linking": "You said {person} spends {hours} on {task}. Here is the one part of the product that fixes that.",
    "objection_handling": "Happy to. So I send the right thing, what would you need to see in it?",
    "price_handling": "That's a fair reaction. What were you comparing it to?",
    "next_steps": "Can we put thirty minutes on the calendar with {boss} for Thursday at ten?",
}
ONE_THING = {
    "agenda_setting": "Open every call with a three-part agenda and ask the prospect what they would add.",
    "pain_discovery": "Ask two follow-up questions about the problem before you show anything.",
    "cost_of_inaction": "Ask what doing nothing costs, and wait for a number.",
    "metrics_and_goals": "Get one measurable goal, with a number, on every discovery call.",
    "decision_process": "Ask who signs and how they bought the last tool before the call ends.",
    "active_listening": "Summarize the prospect's problem in their words and ask if you got it right.",
    "value_linking": "Show only the part of the product that solves the pain they named, and name it back to them.",
    "objection_handling": "Answer every objection with a question first.",
    "price_handling": "State the price, then stay silent until the prospect speaks.",
    "next_steps": "Do not hang up without a day and time on the calendar.",
}


def better_version(rid: str, facts: dict, fill: dict) -> str:
    # Discounting before any pushback, or dodging the price, is fixed by stating it plainly and stopping.
    if rid == "price_handling" and facts["price_mode"] in ("early_discount", "dodged"):
        return "For a team your size it's {price} dollars a year.".format(**fill)
    return BETTER[rid].format(**fill)


def pick_level(rng: random.Random, outcome: str) -> int:
    p5, p3 = LEVEL_ODDS[outcome]
    x = rng.random()
    return 5 if x < p5 else 3 if x < p5 + p3 else 1


class Script:
    """Turns with evidence markers. Consecutive turns must alternate speakers."""

    def __init__(self):
        self.turns: list[dict] = []

    def say(self, role: str, text: str, key: str | None = None, quote: str | None = None,
            gap: float | None = None, mark_first_sentence: bool = False) -> None:
        if self.turns and self.turns[-1]["role"] == role:
            raise ValueError(f"two {role} turns in a row: {text[:40]}")
        self.turns.append({"role": role, "text": text, "key": key, "quote": quote or text, "gap": gap,
                           "mark": mark_first_sentence})


def write_script(p: dict, levels: dict[str, int], price_mode: str, rng: random.Random) -> tuple[Script, dict]:
    pain = PAINS[p["pain"]]
    first, company = p["first"], p["company"]
    boss, boss_title = p["boss"]
    s = Script()
    facts: dict = {"price_mode": price_mode}

    s.say("PROSPECT", f"{company}, this is {first}.")
    if levels["rapport"] >= 4:
        s.say("REP", f"Hi {first}, it's {REP_NAME} from {REP_CO}. I saw your team finished the Harlow Street job last week. How did that land?",
              key="rapport", quote="How did that land?")
        s.say("PROSPECT", "Ha, it was a sprint, but we got there. Thanks for asking.")
    else:
        s.say("REP", f"Hi {first}, {REP_NAME} from {REP_CO}. Okay, let's get started.", key="rapport",
              quote="Okay, let's get started.")
        s.say("PROSPECT", "Sure.")

    a = levels["agenda_setting"]
    if a == 5:
        s.say("REP", f"I was hoping to use our thirty minutes to understand how {pain['short']} works for you today, share what similar teams do, and then decide together if a next step makes sense. Anything you'd add to that?",
              key="agenda_setting", quote="decide together if a next step makes sense. Anything you'd add to that?")
        s.say("PROSPECT", "No, that works. Leave some time for pricing.")
    elif a == 3:
        s.say("REP", "Today I'll walk you through how we work and then show you the product.", key="agenda_setting")
        s.say("PROSPECT", "Okay.")
    else:
        facts["no_agenda"] = True

    d = levels["pain_discovery"]
    if d == 5:
        s.say("REP", f"Walk me through what {pain['task']} looks like today?", key="pain_discovery",
              quote=f"Walk me through what {pain['task']} looks like today?")
        facts["first_pain_q"] = len(s.turns) - 1
        s.say("PROSPECT", f"Honestly it's a spreadsheet. {pain['person'].capitalize()} spends {pain['hours']} on it.")
        s.say("REP", "What makes that the hardest part?")
        s.say("PROSPECT", f"Things change after it's done. Last time, {pain['incident']}.")
        s.say("REP", "And when that happens, what does it look like for you personally?")
        s.say("PROSPECT", "I'm the one on the phone apologizing. It's the part of the job I hate.")
    elif d == 3:
        s.say("REP", f"What's the biggest challenge with {pain['short']} right now?", key="pain_discovery")
        facts["first_pain_q"] = len(s.turns) - 1
        s.say("PROSPECT", f"It takes too long. {pain['person'].capitalize()} spends {pain['hours']} on it.")
    else:
        s.say("REP", f"Most teams we talk to struggle with {pain['short']}, so let me show you how we fix that.",
              key="pain_discovery")
        s.say("PROSPECT", "Okay, go ahead.")

    c = levels["cost_of_inaction"]
    if c == 5:
        s.say("REP", "If nothing changes over the next six months, what does that cost you?")
        s.say("PROSPECT", f"Honestly? {pain['cost'][0].upper() + pain['cost'][1:]}. And people are tired of it.",
              key="cost_of_inaction", quote=pain["cost"])
    elif c == 3:
        s.say("REP", "Is that costing you much?", key="cost_of_inaction")
        s.say("PROSPECT", "Some, I'd guess. Hard to say.")

    m = levels["metrics_and_goals"]
    if m == 5:
        s.say("REP", "What would success look like by the end of the quarter?")
        s.say("PROSPECT", f"Get {pain['short']} down to {pain['target']}, and zero missed {pain['unit']}.",
              key="metrics_and_goals", quote=f"down to {pain['target']}")
    elif m == 3:
        s.say("REP", "What are you hoping a new tool would do for you?")
        s.say("PROSPECT", "Just make it easier, really.", key="metrics_and_goals")

    listen = levels["active_listening"]
    if listen == 5:
        s.say("REP", f"Let me make sure I have this right. {pain['person'].capitalize()} spends {pain['hours']} on {pain['task']}, and things still slip. Did I miss anything?",
              key="active_listening", quote="Did I miss anything?")
        s.say("PROSPECT", "No, that's it exactly.")
    elif listen == 3:
        s.say("REP", "Okay, that makes sense.", key="active_listening")
        s.say("PROSPECT", "Yeah.")

    v = levels["value_linking"]
    if v == 5:
        s.say("REP", f"You said {pain['person']} spends {pain['hours']} on {pain['task']}. With us, {pain['solution']}. That's the part that would have caught it when {pain['incident']}.",
              key="value_linking", quote=f"You said {pain['person']} spends {pain['hours']}")
    elif v == 3:
        s.say("REP", "Our platform helps teams like yours schedule faster and keep everyone updated. It has mobile alerts, reporting, and integrations with the tools you already use.",
              key="value_linking", quote="helps teams like yours schedule faster")
    else:
        s.say("REP", "So let me walk you through the platform. There's the scheduling board, which has drag and drop, color coding, and templates. Then there's the mobile app, which works on iPhone and Android, with push alerts and offline mode. We also have reporting, with twelve standard reports and a custom report builder, and we integrate with payroll, accounting, and most CRMs. There's an admin console for permissions, single sign-on, audit logs, and we have a customer success team that does onboarding. We also just launched route optimization and a customer portal, and there's an API if your team wants to build anything custom. Most customers start with the scheduling board and then add modules as they grow.",
              key="value_linking", quote="let me walk you through the platform")
    if levels["active_listening"] == 1:
        s.say("PROSPECT", "Right, and the thing that worries me is whether my")
        s.say("REP", "Right, right, so that's exactly what our dispatch module handles.", key="active_listening")
    s.say("PROSPECT", "Okay. What does something like that cost?")

    price = p["price"]
    objections: list[dict] = []
    if price_mode == "held":
        s.say("REP", f"For a team your size it's {price} dollars a year.", key="price_handling", quote=f"it's {price} dollars a year")
        facts["price_turn"] = len(s.turns) - 1
        s.say("PROSPECT", "Hmm. That's more than we budgeted for.", gap=round(rng.uniform(4.0, 7.0), 1))
        objections.append({"type": "price", "turn": len(s.turns) - 1, "handled": True,
                           "why": "The rep answered with a question instead of a concession."})
        s.say("REP", "What were you comparing it to?")
        s.say("PROSPECT", "I guess I was thinking of the cost of the spreadsheet, which is nothing.")
        s.say("REP", f"Fair. Earlier you mentioned {pain['cost']}. How does the price compare to that?")
        s.say("PROSPECT", "When you put it that way, it's not crazy.")
        facts.update(held=True, conceded=False, objected=True)
    elif price_mode == "conceded":
        s.say("REP", f"It's {price} dollars a year.")
        facts["price_turn"] = len(s.turns) - 1
        s.say("PROSPECT", "That's steep for us.", gap=round(rng.uniform(0.8, 1.8), 1))
        objections.append({"type": "price", "turn": len(s.turns) - 1, "handled": False,
                           "why": "The rep conceded instead of exploring the concern."})
        # The evidence is the concession, since that is the moment to coach.
        s.say("REP", "I hear you. I could probably do fifteen percent off if that helps.", key="price_handling",
              quote="I could probably do fifteen percent off if that helps.")
        s.say("PROSPECT", "Maybe. I'd have to think about it.")
        facts.update(held=False, conceded=True, objected=True)
    elif price_mode == "early_discount":
        s.say("REP", f"It's {price} dollars a year. But honestly, if you sign this month I can take twenty percent off, so it's really a lot less than that.",
              key="price_handling", quote="if you sign this month I can take twenty percent off", mark_first_sentence=True)
        facts["price_turn"] = len(s.turns) - 1
        s.say("PROSPECT", "Okay. I'll have to think about it.")
        facts.update(held=None, conceded=True, objected=False)
    else:  # price dodged: prospect asked, rep avoided it
        s.say("REP", "It depends on a lot of things. Let's talk about that once we know it's a fit.", key="price_handling",
              quote="It depends on a lot of things.")
        s.say("PROSPECT", "Sure, I guess.")
        facts.update(price_stated=False)

    dp = levels["decision_process"]
    if dp == 5:
        s.say("REP", "Who else weighs in on a decision like this, and how have you bought software like this before?",
              key="decision_process", quote="Who else weighs in on a decision like this")
        s.say("PROSPECT", f"I'd bring in {boss}, our {boss_title}. {boss} signs anything over ten thousand. Last time it took about a month with a trial first.")
        s.say("REP", f"So a trial, then {boss}, about a month. Is there a date you'd want this live by?")
        s.say("PROSPECT", "Before the busy season, so November.")
    elif dp == 3:
        s.say("REP", "Are you the one who makes the call on this?", key="decision_process")
        s.say("PROSPECT", f"Me and {boss}, mostly.")

    o = levels["objection_handling"]
    s.say("REP", "Does what you've seen so far make sense for your team?")
    s.say("PROSPECT", "Can you just send me some info and I'll look it over?")
    info_turn = len(s.turns) - 1
    if o == 5:
        s.say("REP", "Happy to. So I send the right thing, what would you need to see in it?", key="objection_handling",
              quote="what would you need to see in it?")
        s.say("PROSPECT", f"Probably proof it works with our current tools, and something I can show {boss}.")
        objections.append({"type": "send_info", "turn": info_turn, "handled": True,
                           "why": "The rep asked what the prospect needed before agreeing to send anything."})
    elif o == 3:
        s.say("REP", "Sure, I'll send over our deck and a case study.", key="objection_handling")
        s.say("PROSPECT", "Great.")
        objections.append({"type": "send_info", "turn": info_turn, "handled": False,
                           "why": "The rep agreed without finding out what the prospect actually needed."})
    else:
        s.say("REP", "Well, honestly, the info won't show you much. We're actually cheaper than most of the market.",
              key="objection_handling", quote="We're actually cheaper than most of the market.")
        s.say("PROSPECT", "Okay. Send it anyway.")
        objections.append({"type": "send_info", "turn": info_turn, "handled": False,
                           "why": "The rep argued instead of asking what the prospect needed."})

    n = levels["next_steps"]
    if n == 5:
        s.say("REP", f"Can we put thirty minutes on the calendar with {boss} for Thursday at ten, so you both see it running with your tools?")
        s.say("PROSPECT", f"Thursday at ten works. I'll forward the invite to {boss}.", key="next_steps",
              quote="Thursday at ten works.")
    elif n == 3:
        s.say("REP", "Let's reconnect sometime next week.", key="next_steps")
        s.say("PROSPECT", "Sure, sounds good.")
    else:
        s.say("REP", "I'll send over some info and you can let me know what you think.", key="next_steps")
        s.say("PROSPECT", "Sounds good.")
    s.say("REP", f"Thanks {first}, really appreciate the time.")
    s.say("PROSPECT", "Thanks, bye.")
    facts["objections"] = objections
    return s, facts


def lay_out(s: Script, rng: random.Random, speaker_of: dict[str, str]) -> tuple[list[dict], list[dict], dict]:
    t = 0.4
    utts, words = [], []
    marks: dict = {}
    for i, turn in enumerate(s.turns):
        if i:
            t += turn["gap"] if turn["gap"] is not None else round(rng.uniform(0.3, 1.1), 2)
        tokens = turn["text"].split()
        per = 1 / WPS[turn["role"]]
        start = round(t, 2)
        for k, tok in enumerate(tokens):
            words.append({"speaker": speaker_of[turn["role"]], "start": round(t + k * per, 2),
                          "end": round(t + (k + 1) * per - 0.05, 2), "text": tok})
            if turn["mark"] and tok.endswith(".") and "sentence_end" not in marks.get(i, {}):
                marks.setdefault(i, {})["sentence_end"] = round(t + (k + 1) * per - 0.05, 2)
        t += len(tokens) * per
        utts.append({"speaker": speaker_of[turn["role"]], "role": turn["role"], "start": start,
                     "end": round(t - 0.05, 2), "text": turn["text"]})
    return utts, words, marks


def tone_windows(utts: list[dict], levels: dict[str, int], duration: float) -> list[dict]:
    rep_good = levels["rapport"] >= 4
    out, start = [], 0
    while start < duration:
        end = int(min(start + 60, duration))
        in_window = [u for u in utts if start <= u["start"] < end]
        rep_words = sum(len(u["text"].split()) for u in in_window if u["role"] == "REP")
        pro_words = sum(len(u["text"].split()) for u in in_window if u["role"] == "PROSPECT")
        rep_tone = "warm" if rep_good else "brisk"
        if rep_words > 3 * max(pro_words, 1):
            rep_tone, note = "rushed", "Rep does most of the talking in this stretch."
        elif pro_words > rep_words:
            note = "Prospect talks more than the rep here."
        else:
            note = "Even back and forth."
        pro_tone = "guarded" if start == 0 else ("engaged" if pro_words > rep_words else "flat")
        out.append({"start": start, "end": end, "rep_tone": rep_tone, "prospect_tone": pro_tone, "note": note})
        start += 60
    return out


def build(out_dir: Path) -> None:
    rng = random.Random(SEED)
    for sub in ("raw", "calls", "scorecards"):
        if (out_dir / sub).exists():
            shutil.rmtree(out_dir / sub)
        (out_dir / sub).mkdir(parents=True)

    outcomes, contacts = [], []
    for n, (date, first, last, company, slug, stage, outcome, deal, pain) in enumerate(PROSPECTS):
        initials = first[0] + last[0]
        call_id = f"{date}_{initials}_{stage}"
        levels = {k: pick_level(rng, outcome) for k in RUBRIC_IDS}
        levels["rapport"] = 4 if rng.random() < (0.7 if outcome == "won" else 0.35) else 2
        pl = levels["price_handling"]
        if stage == "Discovery" and n % 4 == 0:
            price_mode = "dodged"
            levels["price_handling"] = 1
        else:
            price_mode = {5: "held", 3: "conceded", 1: "early_discount"}[pl]
        p = {"first": first, "company": company, "pain": pain, "boss": BOSSES[n % len(BOSSES)],
             "price": PRICES[n % len(PRICES)]}
        script, facts = write_script(p, levels, price_mode, rng)
        rep_spk = "spk_2" if n % 3 else "spk_1"
        speaker_of = {"REP": rep_spk, "PROSPECT": "spk_1" if rep_spk == "spk_2" else "spk_2"}
        utts, words, marks = lay_out(script, rng, speaker_of)
        duration = round(utts[-1]["end"] + 1.0, 1)
        tones = tone_windows(utts, levels, duration)
        keep_words = n % 2 == 0  # half the demo calls have word timestamps, half do not

        raw = {
            "call_id": call_id, "audio_file": f"{call_id}.m4a", "duration_sec": duration,
            "transcribe_model": "synthetic demo data", "utterances": utts, "words": words if keep_words else [],
            "speaker_mapping": {v: k for k, v in speaker_of.items()}, "mapping_confidence": "high",
            "mapping_reason": "Synthetic demo call.", "tone_windows": tones,
            "chunks": [{"offset_sec": 0.0, "length_sec": None}], "redacted": False, "created_at": "2026-09-28",
        }
        (out_dir / "raw" / f"{call_id}.json").write_text(json.dumps(raw, indent=2) + "\n")
        meta = {"call_id": call_id, "date": date, "prospect_initials": initials, "stage": stage,
                "duration_sec": int(round(duration)), "source_audio": f"{call_id}.m4a", "rep_speaker": rep_spk,
                "speaker_mapping_confidence": "high", "needs_review": False}
        email = "Not yet pulled." if n % 5 else (
            f"- {date}: {first} replied to the intro email asking for a quick call about {PAINS[pain]['short']}.\n"
            f"- Rep promised a short agenda before the call. It went out the same day.")
        (out_dir / "calls" / f"{call_id}.md").write_text(callfile.render(meta, utts, tones, email))

        card = scorecard(call_id, utts, levels, facts, marks, p, rng, script)
        (out_dir / "scorecards" / f"{call_id}.json").write_text(json.dumps(card, indent=2) + "\n")
        outcomes.append({"call_id": call_id, "outcome": outcome, "deal_value": deal or "",
                         "notes": {"won": "Signed", "lost": "Went quiet after proposal", "stalled": "Waiting on budget",
                                   "open": "Follow-up booked"}[outcome]})
        contacts.append({"call_id": call_id, "prospect_name": f"{first} {last}",
                         "prospect_email": f"{first.lower()}@{slug}.example", "company": company})

    for name, rows, cols in (("outcomes.csv", outcomes, ["call_id", "outcome", "deal_value", "notes"]),
                             ("contacts.csv", contacts, ["call_id", "prospect_name", "prospect_email", "company"])):
        with (out_dir / name).open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
    rubric = (HERE.parent.parent / "rubric" / "rubric.example.md").read_text()
    (out_dir / "rubric.md").write_text(rubric)
    print(f"Wrote {len(PROSPECTS)} synthetic calls to {out_dir}")


def scorecard(call_id, utts, levels, facts, marks, p, rng, script: Script) -> dict:
    by_key = {}
    ts = callfile.fmt_ts

    def evidence(key):
        """The line marked as evidence for a behavior, and the quote taken from it."""
        for i, turn in enumerate(script.turns):
            if turn["key"] == key:
                return utts[i], turn["quote"]
        return None, None

    rubric_scores = []
    for rid in RUBRIC_IDS:
        level = levels[rid]
        u, quote = evidence(rid)
        score = level
        if level == 5 and rng.random() < 0.35:
            score = 4
        elif level == 3 and u is not None:
            score = rng.choice([2, 3, 3, 4])
        if score >= 2 and u is None:
            score = 1
        item = {"id": rid, "score": score, "timestamp": ts(u["start"]) if u and score >= 2 else None,
                "evidence_quote": quote if u and score >= 2 else None, "why": WHY[rid][level]}
        if score == 1 and u is not None:
            item["timestamp"], item["evidence_quote"] = ts(u["start"]), quote
        rubric_scores.append(item)
        by_key[rid] = (score, u, quote)

    ru, rq = evidence("rapport")
    rapport = {"score": levels["rapport"], "timestamp": ts(ru["start"]), "evidence_quote": rq,
               "why": "The rep opened with a specific, personal question." if levels["rapport"] >= 4
               else "The rep skipped any personal connection and went straight to business."}
    tone_score = 4 if levels["active_listening"] == 5 else 3 if levels["active_listening"] == 3 else 2
    tu, tq = evidence("active_listening")
    if tu is None:
        tu, tq = ru, rq
    tone_match = {"score": tone_score, "timestamp": ts(tu["start"]), "evidence_quote": tq,
                  "why": "The rep's pace and wording tracked the prospect's." if tone_score >= 4
                  else "The rep's energy did not match the prospect's guarded mood."}

    pu, pq = evidence("price_handling")
    if facts.get("price_stated") is False:
        price = {"price_stated": False, "price_stated_end_sec": None, "held_price": None,
                 "conceded_or_discounted": None, "prospect_objected": None, "evidence_quote": pq,
                 "why": "The prospect asked for price and the rep avoided giving one."}
    else:
        end = marks.get(facts["price_turn"], {}).get("sentence_end", utts[facts["price_turn"]]["end"])
        price = {"price_stated": True, "price_stated_end_sec": end, "held_price": facts["held"],
                 "conceded_or_discounted": facts["conceded"], "prospect_objected": facts["objected"],
                 "evidence_quote": pq, "why": WHY["price_handling"][levels["price_handling"]]}

    objections = [{"type": o["type"], "timestamp": ts(utts[o["turn"]]["start"]), "evidence_quote": utts[o["turn"]]["text"],
                   "handled": o["handled"], "why": o["why"]} for o in facts["objections"]]
    first_q = facts.get("first_pain_q")

    order = sorted(RUBRIC_IDS, key=lambda r: (by_key[r][0], RUBRIC_IDS.index(r)))
    # The rewrite must replace something the rep said.
    worst_with_line = next(r for r in order if by_key[r][1] is not None and by_key[r][1]["role"] == "REP")
    wu, wq = by_key[worst_with_line][1], by_key[worst_with_line][2]
    pain = PAINS[p["pain"]]
    fill = dict(short=pain["short"], person=pain["person"], hours=pain["hours"], task=pain["task"],
                price=p["price"], boss=p["boss"][0])
    return {
        "call_id": call_id,
        "scored_at": "2026-09-28",
        "rubric_scores": rubric_scores,
        "rapport": rapport,
        "tone_match": tone_match,
        "price_handling": price,
        "objections": objections,
        "first_pain_question_sec": utts[first_q]["start"] if first_q is not None else None,
        "top_misses": [MISS[r] + (f" See {ts(by_key[r][1]['start'])}." if by_key[r][1] is not None else "")
                       for r in order[:3]],
        "rewrite": {"timestamp": ts(wu["start"]), "original_quote": wq,
                    "better_version": better_version(worst_with_line, facts, fill)},
        "one_thing_to_change": ONE_THING[order[0]],
    }


if __name__ == "__main__":
    build(HERE)
