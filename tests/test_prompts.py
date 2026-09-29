"""Phase 4: prompts, personas, slash commands, and repo-wide writing rules."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PROMPTS = sorted((REPO / "prompts").glob("*.md"))
COMMANDS = sorted((REPO / ".claude" / "commands").glob("*.md"))
PERSONAS = sorted((REPO / "personas").glob("*.md"))
HELD_PRICE = "did not concede or discount when the prospect pushed back"


def test_all_six_prompts_exist():
    assert [p.name for p in PROMPTS] == [
        "01_build_rubric.md", "02_relabel_speakers.md", "03_email_context.md",
        "04_score_call.md", "05_findings.md", "06_roleplay.md"]


@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda p: p.name)
def test_prompt_has_purpose_and_rules(prompt):
    text = prompt.read_text()
    assert re.search(r"^Purpose: ", text, re.M)
    assert re.search(r"^## Rules$", text, re.M)


def test_slash_commands_point_at_real_prompts():
    names = {c.stem for c in COMMANDS}
    assert names == {"coach-rubric", "coach-emails", "coach-score", "coach-findings", "coach-practice"}
    for cmd in COMMANDS:
        ref = re.search(r"`(prompts/[^`]+)`", cmd.read_text()).group(1)
        assert (REPO / ref).exists(), ref
        assert cmd.read_text().startswith("---\ndescription:")


def test_held_price_definition_is_in_the_prompts_and_rubric():
    for name in ("prompts/01_build_rubric.md", "prompts/04_score_call.md"):
        assert HELD_PRICE in (REPO / name).read_text(), name
    assert "does not concede or discount when the prospect pushes back" in (REPO / "rubric/rubric.example.md").read_text()


def test_gmail_is_read_only():
    text = (REPO / "prompts/03_email_context.md").read_text()
    for word in ("Never send", "draft", "label", "archive", "delete", "Read-only"):
        assert word in text


def test_findings_never_computes():
    text = (REPO / "prompts/05_findings.md").read_text()
    assert "Compute none" in text and "Never claim cause" in text
    for section in ("1. Summary", "2. Won vs. lost", "3. Top 3 patterns", "4. Where each lost deal turned",
                    "5. What the wins did differently", "6. Ranked improvements",
                    "7. The one skill for your next 5 calls", "8. Caveats"):
        assert section in text


def test_score_prompt_uses_locate_and_validate():
    text = (REPO / "prompts/04_score_call.md").read_text()
    assert "coach.py locate" in text and "coach.py validate" in text and "Tone notes are hints" in text


@pytest.mark.parametrize("persona", PERSONAS, ids=lambda p: p.name)
def test_persona_sections(persona):
    text = persona.read_text()
    for section in ("## Who they are", "## What they care about", "## Default stalling move", "## Objection lines"):
        assert section in text
    lines = text.split("## Objection lines")[1].split("##")[0]
    assert 2 <= lines.count('\n- "') <= 3


def test_four_personas():
    assert {p.stem for p in PERSONAS} == {"skeptical_cfo", "just_send_me_info", "price_shopper", "silent_stakeholder"}


def _repo_text_files():
    skip = {".venv", ".git", "data", "__pycache__", ".pytest_cache"}
    for p in REPO.rglob("*"):
        if p.is_file() and not skip.intersection(p.relative_to(REPO).parts) and p.suffix in {
                ".md", ".py", ".yaml", ".txt", ".json", ".csv", ".ini", ".example", ""}:
            yield p


def test_no_em_dashes_anywhere():
    offenders = [str(p.relative_to(REPO)) for p in _repo_text_files()
                 if chr(0x2014) in p.read_text(encoding="utf-8", errors="ignore")]
    assert offenders == []


def test_every_readme_command_exists():
    from coach.cli import COMMANDS, build_parser

    readme = (REPO / "README.md").read_text()
    named = set(re.findall(r"python coach\.py (\w+)", readme))
    assert named and named <= set(COMMANDS), named - set(COMMANDS)
    for flag in re.findall(r"`(--[a-z-]+)", readme):
        assert flag in build_parser().format_help() or any(
            flag in sub.format_help() for sub in build_parser()._subparsers._group_actions[0].choices.values()), flag
    slash = set(re.findall(r"`/(coach-\w+)`", readme))
    assert slash == {c.stem for c in COMMANDS_DIR.glob("*.md")}


COMMANDS_DIR = REPO / ".claude" / "commands"


def test_no_anthropic_dependency():
    assert "anthropic" not in (REPO / "requirements.txt").read_text().lower()
    for p in (REPO / "coach").glob("*.py"):
        assert "import anthropic" not in p.read_text()


def test_gitignore_protects_private_files(tmp_path):
    rules = (REPO / ".gitignore").read_text()
    for rule in ("/data/", ".env", "rubric/*", "!rubric/rubric.example.md", "*.m4a", "*.mp4"):
        assert rule in rules
    if subprocess.run(["git", "--version"], capture_output=True).returncode != 0:
        pytest.skip("git not installed")
    (tmp_path / ".gitignore").write_text(rules)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for path, ignored in [("data/calls/x.md", True), (".env", True), ("rubric/rubric.md", True),
                          ("rubric/rubric.backup-2026-09-28.md", True), ("rubric/rubric.example.md", False),
                          ("notes/call.wav", True), (".env.example", False), ("examples/demo/calls/x.md", False),
                          (".claude/commands/coach-score.md", False), (".claude/settings.local.json", True),
                          ("Open-Dashboard.html", False), ("data/reports/dashboard.html", True)]:
        code = subprocess.run(["git", "-C", str(tmp_path), "check-ignore", "-q", "--no-index", path]).returncode
        assert (code == 0) == ignored, path
