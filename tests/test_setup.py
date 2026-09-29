"""Phase 1: init, doctor, config, and friendly errors."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from coach import doctor
from coach.cli import main
from coach.config import (
    CONTACTS_HEADER,
    OUTCOMES_HEADER,
    STARTER_RUBRIC_MARKER,
    gemini_key_status,
    load_config,
    require_gemini_key,
)
from coach.friendly import CoachError, run
from coach.workspace import init_workspace

REPO = Path(__file__).resolve().parent.parent


# init

def test_init_creates_folders_and_files(workspace):
    assert init_workspace(workspace) == 0
    for folder in workspace.folders():
        assert folder.is_dir(), folder
    assert workspace.contacts_csv.read_text().strip() == ",".join(CONTACTS_HEADER)
    assert workspace.outcomes_csv.read_text().strip() == ",".join(OUTCOMES_HEADER)
    assert workspace.env_file.read_text() == (REPO / ".env.example").read_text()
    assert workspace.rubric.read_text().startswith(STARTER_RUBRIC_MARKER)


def test_init_twice_keeps_user_edits(workspace, capsys):
    init_workspace(workspace)
    workspace.contacts_csv.write_text("call_id,prospect_name,prospect_email,company\nA,B,C,D\n")
    workspace.env_file.write_text("GEMINI_API_KEY=abc123realkey\n")
    workspace.rubric.write_text("### my_id: Mine\n1: a\n3: b\n5: c\n")
    capsys.readouterr()

    assert init_workspace(workspace) == 0
    out = capsys.readouterr().out
    assert "A,B,C,D" in workspace.contacts_csv.read_text()
    assert workspace.env_file.read_text() == "GEMINI_API_KEY=abc123realkey\n"
    assert workspace.rubric.read_text().startswith("### my_id")
    assert "Created" not in out
    assert "already exist" in out


# doctor

@pytest.fixture
def all_packages(monkeypatch):
    """Doctor results should not depend on what is installed on the test machine."""
    monkeypatch.setattr(doctor, "_installed", lambda name: True)


def test_doctor_on_fresh_folder_warns_but_passes(workspace, all_packages, capsys):
    assert doctor.run_doctor(workspace.root) == 0
    out = capsys.readouterr().out
    assert "python coach.py init" in out
    assert "0 problems" in out


def test_doctor_after_init(workspace, all_packages, capsys):
    init_workspace(workspace)
    capsys.readouterr()
    assert doctor.run_doctor(workspace.root) == 0
    out = capsys.readouterr().out
    assert "All data folders exist" in out
    assert "starter example" in out


def test_doctor_never_prints_the_key(workspace, all_packages, capsys):
    workspace.env_file.write_text("GEMINI_API_KEY=sk-test-secret-98765\n")
    doctor.run_doctor(workspace.root)
    captured = capsys.readouterr()
    assert "sk-test-secret-98765" not in captured.out + captured.err
    assert "GEMINI_API_KEY is set (not shown)" in captured.out


def test_doctor_fails_without_gitignore(workspace, all_packages, capsys):
    (workspace.root / ".gitignore").unlink()
    assert doctor.run_doctor(workspace.root) == 1
    assert ".gitignore is missing" in capsys.readouterr().out


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@needs_git
def test_doctor_confirms_gitignore_protects_data(workspace, all_packages, capsys):
    _git(workspace.root, "init", "-q")
    init_workspace(workspace)
    capsys.readouterr()
    assert doctor.run_doctor(workspace.root) == 0
    out = capsys.readouterr().out
    assert ".gitignore protects" in out
    assert "No call data" in out


@needs_git
def test_doctor_shouts_when_data_is_tracked(workspace, all_packages, capsys):
    _git(workspace.root, "init", "-q")
    init_workspace(workspace)
    leaked = workspace.calls / "2026-09-28_JD_Discovery.md"
    leaked.write_text("secret call\n")
    _git(workspace.root, "add", "-f", str(leaked))
    capsys.readouterr()

    assert doctor.run_doctor(workspace.root) == 1
    out = capsys.readouterr().out
    assert "PRIVATE FILES ARE TRACKED BY GIT" in out
    assert "data/calls/2026-09-28_JD_Discovery.md" in out
    assert "git rm -r --cached" in out


# config and key

def test_key_status(workspace):
    assert gemini_key_status(workspace.root) == "no_env_file"
    workspace.env_file.write_text("GEMINI_API_KEY=your-key-here\n")
    assert gemini_key_status(workspace.root) == "placeholder"
    with pytest.raises(CoachError) as err:
        require_gemini_key(workspace.root)
    assert "your-key-here" in err.value.problem


def test_real_key_is_returned(workspace):
    workspace.env_file.write_text("GEMINI_API_KEY=abc123realkey\n")
    assert require_gemini_key(workspace.root) == "abc123realkey"


def test_bad_yaml_gives_line_number(tmp_path):
    bad = tmp_path / "config.yaml"
    bad.write_text("rep:\n  name: Sam\n\tcompany: x\n")
    with pytest.raises(CoachError) as err:
        load_config(bad)
    assert "line" in err.value.problem


def test_config_fills_defaults(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("rep:\n  name: Sam\n")
    cfg = load_config(cfg_file)
    assert cfg["rep"]["name"] == "Sam"
    assert cfg["models"]["transcribe"]
    assert cfg["redact"]["enabled"] is False


def test_shipped_config_loads():
    cfg = load_config()
    assert set(cfg["models"]) >= {"transcribe", "relabel", "tone"}


# friendly errors

def test_expected_problem_has_no_traceback(capsys):
    def boom():
        raise CoachError("The inbox is empty.", "Drop a recording into data/inbox/")

    assert run(boom) == 1
    err = capsys.readouterr().err
    assert "Problem: The inbox is empty." in err
    assert "Fix: Drop a recording" in err
    assert "Traceback" not in err


def test_missing_package_names_the_pip_package(capsys):
    def boom():
        raise ModuleNotFoundError("No module named 'yaml'", name="yaml")

    assert run(boom) == 1
    assert "pyyaml" in capsys.readouterr().err


def test_unexpected_error_points_to_debug(capsys):
    def boom():
        raise ValueError("odd")

    assert run(boom) == 1
    assert "--debug" in capsys.readouterr().err
    with pytest.raises(ValueError):
        run(boom, debug=True)


def test_cli_help_and_unknown_command(capsys):
    assert main([]) == 0
    assert "doctor" in capsys.readouterr().out
    with pytest.raises(SystemExit) as exit_info:
        main(["dance"])
    assert exit_info.value.code == 2
    assert "Problem:" in capsys.readouterr().err
