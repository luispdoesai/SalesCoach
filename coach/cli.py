"""Command line entry point. Every command runs through friendly.run()."""

from __future__ import annotations

import argparse
import os
import re
import sys

from coach import friendly


class FriendlyParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        bad_choice = re.search(r"invalid choice: '([^']*)'", message)
        if bad_choice:
            message = f"'{bad_choice.group(1)}' is not a command"
        friendly.print_problem(message[:1].upper() + message[1:] + ".",
                               "Run: python coach.py --help  to see every command.")
        sys.exit(2)


def _setup():
    """Settings and paths. Imported lazily so doctor works before packages are installed."""
    from coach.config import Paths, load_config

    cfg = load_config()
    return cfg, Paths.from_config(cfg)


def cmd_doctor(args: argparse.Namespace) -> int:
    from coach.doctor import run_doctor

    return run_doctor()


def cmd_init(args: argparse.Namespace) -> int:
    from coach.workspace import init_workspace

    return init_workspace(_setup()[1])


def cmd_transcribe(args: argparse.Namespace) -> int:
    from coach.transcribe import run_transcribe

    cfg, paths = _setup()
    return run_transcribe(paths, cfg, file=args.file, force=args.force, mock=args.mock,
                          rep_speaker=args.rep_speaker, yes=args.yes)


def _analysis(name: str):
    def handler(args: argparse.Namespace) -> int:
        from coach import analyze

        paths = _setup()[1]
        if name == "locate":
            return analyze.run_locate(paths, args.call_id, args.quote)
        return getattr(analyze, f"run_{name}")(paths)

    return handler


def cmd_demo(args: argparse.Namespace) -> int:
    from coach.analyze import run_demo

    return run_demo()


def cmd_dashboard(args: argparse.Namespace) -> int:
    from coach.dashboard import run_dashboard

    run_dashboard(_setup()[1], open_it=args.open)
    return 0


def cmd_archive(args: argparse.Namespace) -> int:
    from coach.archive import run_archive

    return run_archive(_setup()[1], before=args.before, calls=args.calls, name=args.name,
                       yes=args.yes, list_only=args.list)


def cmd_restore(args: argparse.Namespace) -> int:
    from coach.archive import run_restore

    return run_restore(_setup()[1], args.name, yes=args.yes)


def cmd_index(args: argparse.Namespace) -> int:
    from coach.index import run_index

    return run_index(_setup()[1])


COMMANDS = {
    "doctor": cmd_doctor, "init": cmd_init, "transcribe": cmd_transcribe,
    "validate": _analysis("validate"), "merge": _analysis("merge"), "stats": _analysis("stats"),
    "compare": _analysis("compare"), "analyze": _analysis("analyze"), "locate": _analysis("locate"),
    "demo": cmd_demo, "index": cmd_index, "dashboard": cmd_dashboard,
    "archive": cmd_archive, "restore": cmd_restore,
}


def build_parser() -> argparse.ArgumentParser:
    # --debug works before or after the command name.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--debug", action="store_true", default=argparse.SUPPRESS,
                        help="show full error details")
    common.add_argument("--data-dir", metavar="DIR", default=argparse.SUPPRESS,
                        help="use a different data folder, like data/demo")

    parser = FriendlyParser(
        prog="python coach.py",
        description="AI Sales Coach. Turn your recorded sales calls into a coach.",
        epilog="New here? Start with: python coach.py doctor",
    )
    parser.add_argument("--debug", action="store_true", help="show full error details")
    parser.add_argument("--data-dir", metavar="DIR", default=None,
                        help="use a different data folder, like data/demo")
    sub = parser.add_subparsers(dest="command", metavar="command")

    def add(name: str, help_text: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, parents=[common], help=help_text, description=help_text)

    add("doctor", "check Python, packages, API key, folders, and that your data is not tracked by git")
    add("init", "create folders and starter files")

    t = add("transcribe", "audio in data/inbox to labeled call files")
    t.add_argument("--file", metavar="PATH_OR_CALL_ID",
                   help="one recording, or the call id of a call already transcribed")
    t.add_argument("--force", action="store_true", help="transcribe again even if already done")
    t.add_argument("--mock", action="store_true",
                   help="use bundled fixture responses: no network, no key (same as COACH_MOCK=1)")
    t.add_argument("--rep-speaker", metavar="SPK",
                   help="say which speaker is you, like spk_2. Fixes an existing call with no API call")
    t.add_argument("--yes", action="store_true",
                   help="accept file names that do not match YYYY-MM-DD_Initials_Stage")

    add("validate", "check scorecards against the rubric and verify every quote")
    add("merge", "scorecards + outcomes to results.csv")
    add("stats", "timestamps to stats.csv")
    add("compare", "won vs. lost comparison, sample-size note, and charts")
    add("analyze", "validate, merge, stats, and compare in one go")
    dash = add("dashboard", "one HTML page with outcomes, stats, and every score (analyze builds it too)")
    dash.add_argument("--open", action="store_true", help="open it in your browser")
    arc = add("archive", "move older calls out of your current numbers into their own period, without deleting them")
    arc.add_argument("--before", metavar="YYYY-MM-DD", help="archive calls dated before this day")
    arc.add_argument("--calls", metavar="ID1,ID2", help="archive these calls by id")
    arc.add_argument("--name", help="name for the archived period, like 2026-Q3 (default: its date range)")
    arc.add_argument("--list", action="store_true", help="show current calls and archived periods")
    arc.add_argument("--yes", action="store_true", help="move without asking")
    res = add("restore", "bring an archived period back into your current numbers")
    res.add_argument("name", help="the archive name, from: python coach.py archive --list")
    res.add_argument("--yes", action="store_true", help="restore without asking")
    add("index", "optional: build data/coach.db (SQLite) from the CSVs")
    add("demo", "run the analysis on bundled synthetic calls, no keys needed")

    loc = add("locate", "print the exact seconds where a quote is said (used by /coach-score)")
    loc.add_argument("call_id", help="for example 2026-09-28_JD_Discovery")
    loc.add_argument("quote", help="words copied exactly from one line of the call file")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    if args.data_dir:
        os.environ["COACH_DATA_DIR"] = args.data_dir
    return friendly.run(lambda: COMMANDS[args.command](args), debug=args.debug)
