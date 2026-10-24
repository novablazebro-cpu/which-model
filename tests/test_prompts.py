from axiom3d.eval.prompts import test_prompt as make_prompt


def test_mcp_prompt_protocol():
    text = make_prompt("walk_forward", bare=False, via="mcp")
    assert "walk_forward" in text and "CERTIFIED" in text
    assert "calc" in text and "batch" in text and "answer_quiz" in text
    assert "Do NOT read" not in text  # MCP users have no file access to forbid


def test_mcp_prompt_bare():
    text = make_prompt("step_forward", bare=True, via="mcp")
    assert "CERTIFIED" not in text and "answer_quiz" not in text and "finish" in text


def test_cli_prompt_has_command_and_rules():
    text = make_prompt("turn_then_step", bare=False, via="cli", workdir="/tmp/run1", label="haiku-v2")
    assert "cd /tmp/run1 && UV_SYSTEM_CERTS=1 uv run -q --project" in text
    assert "--label haiku-v2" in text and "Do NOT read" in text and "60 tool calls" in text
    bare = make_prompt("turn_then_step", bare=True, via="cli", workdir="/tmp/run2", label="haiku-v2-bare")
    assert "--protocol off" in bare and "CERTIFIED" not in bare
