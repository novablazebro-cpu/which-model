import json
from pathlib import Path

import pytest

from axiom3d.api import Workbench
from axiom3d.cli import main
from axiom3d.guide import TOPICS, read_topic


def test_cli_start_session_prints_id(home, capsys):
    assert main(["call", "start_session", "--json", '{"task": "step_forward"}', "--home", str(home)]) == 0
    assert "SESSION step_forward-" in capsys.readouterr().out


def test_cli_protocol_off_and_label(home, capsys):
    main(["call", "start_session", "--json", '{"task": "walk_forward"}', "--home", str(home),
          "--protocol", "off", "--label", "flash"])
    out = capsys.readouterr().out
    assert "BRIEFING QUIZ" not in out
    sid = (home / "current").read_text()
    data = json.loads((home / "sessions" / f"{sid}.json").read_text())
    assert data["protocol"] is False and data["ledger"]["label"] == "flash"


def test_cli_bad_tool_and_bad_json(home, capsys):
    assert main(["call", "fly", "--home", str(home)]) == 1
    assert "start_session" in capsys.readouterr().out
    assert main(["call", "start_session", "--json", "{nope", "--home", str(home)]) == 1
    assert main(["call", "start_session", "--json", '{"task": "step_forward", "speed": 3}', "--home", str(home)]) == 1
    assert "ERROR" in capsys.readouterr().out


def test_cli_axiom_error_exit_code(home, capsys):
    main(["call", "start_session", "--json", '{"task": "step_forward"}', "--home", str(home)])
    assert main(["call", "set_root", "--json", '{"frame": 0, "height": 0.9}', "--home", str(home)]) == 1
    assert "quiz" in capsys.readouterr().out


def test_cli_saves_images(home, capsys):
    main(["call", "start_session", "--json", '{"task": "step_forward"}', "--home", str(home)])
    capsys.readouterr()
    assert main(["call", "observe", "--json", '{"views": ["sheet"]}', "--home", str(home)]) == 0
    paths = [l.split("image: ", 1)[1] for l in capsys.readouterr().out.splitlines() if l.startswith("image: ")]
    assert len(paths) == 1 and Path(paths[0]).read_bytes().startswith(b"\x89PNG")


def test_cli_tasks(capsys):
    assert main(["tasks"]) == 0
    out = capsys.readouterr().out
    assert "step_forward" in out and "walk_forward" in out and "turn_then_step" in out


def test_guide_topics(home):
    assert set(TOPICS) == {"conventions", "walking", "vessels", "predictions", "calculator", "tools"}
    assert "lower the pelvis" in read_topic("walking").lower()
    assert "~=" in read_topic("predictions")
    with pytest.raises(KeyError, match="walking"):
        read_topic("dancing")
    assert "flexion" in Workbench(home).guide("conventions").text


def test_home_expands_tilde(monkeypatch, tmp_path, capsys):
    # MCP clients spawn servers without a shell, so "~" in a JSON config arrives literally.
    monkeypatch.setenv("HOME", str(tmp_path))
    assert main(["call", "start_session", "--json", '{"task": "step_forward"}', "--home", "~/.axiom3d"]) == 0
    assert (tmp_path / ".axiom3d" / "current").exists()
