"""Friendly errors and plain output.

Rule: a user never sees a raw traceback for an expected problem.
Expected problems raise CoachError with one sentence on what is wrong
and one on how to fix it. run() turns that into a short message.
"""

from __future__ import annotations

import sys
from typing import Callable

# Import names that differ from the pip package name.
PACKAGE_FOR_MODULE = {
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "google": "google-genai",
    "genai": "google-genai",
}


class CoachError(Exception):
    """An expected problem the user can fix."""

    def __init__(self, problem: str, fix: str | None = None):
        super().__init__(problem)
        self.problem = problem
        self.fix = fix


def fail(problem: str, fix: str | None = None) -> None:
    raise CoachError(problem, fix)


def print_problem(problem: str, fix: str | None = None) -> None:
    print(f"\nProblem: {problem}", file=sys.stderr)
    if fix:
        print(f"Fix: {fix}", file=sys.stderr)


def missing_package_error(module_name: str | None) -> CoachError:
    top = (module_name or "").split(".")[0]
    package = PACKAGE_FOR_MODULE.get(top, top or "a required package")
    return CoachError(
        f"The Python package '{package}' is not installed.",
        "Run: python -m pip install -r requirements.txt",
    )


def run(func: Callable[[], int | None], debug: bool = False) -> int:
    """Run a command and turn expected problems into short messages.

    Returns the process exit code.
    """
    try:
        return int(func() or 0)
    except CoachError as err:
        print_problem(err.problem, err.fix)
        return 1
    except KeyboardInterrupt:
        print("\nStopped. Nothing half-finished was saved as done.", file=sys.stderr)
        return 130
    except ModuleNotFoundError as err:
        if debug:
            raise
        e = missing_package_error(err.name)
        print_problem(e.problem, e.fix)
        return 1
    except Exception as err:  # noqa: BLE001  last-resort guard for users
        if debug:
            raise
        print_problem(
            f"Something unexpected went wrong ({type(err).__name__}: {err}).",
            "Run the same command again with --debug to see details. "
            "If it keeps happening, open an issue on GitHub.",
        )
        return 1


# Plain status lines. Words, not symbols, so every terminal shows them.

def ok(msg: str) -> None:
    print(f"  [ok]    {msg}")


def warn(msg: str, fix: str | None = None) -> None:
    print(f"  [warn]  {msg}")
    if fix:
        print(f"          Fix: {fix}")


def bad(msg: str, fix: str | None = None) -> None:
    print(f"  [FAIL]  {msg}")
    if fix:
        print(f"          Fix: {fix}")


def note(msg: str) -> None:
    print(f"  [info]  {msg}")


def heading(msg: str) -> None:
    print(f"\n{msg}")
