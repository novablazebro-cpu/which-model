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


def test_vessel_cli_prompt_uses_vessel_tools_and_allows_its_images():
    text = make_prompt("meiping_vase", bare=False, via="cli", workdir="/tmp/v1", label="haiku-vase",
                       project="/work/tree")
    assert "--project /work/tree" in text and "shape_profile" in text and "paint_band" in text
    assert "plant_foot" not in text and "vessels" in text and "image: PATH" in text
    bare = make_prompt("meiping_vase", bare=True, via="cli", workdir="/tmp/v2")
    assert "answer_quiz" not in bare and "shape_profile" in bare


def test_raw_prompt_gives_the_same_task_without_the_tool():
    from axiom3d.eval.prompts import raw_prompt
    from axiom3d.tasks.library import get_task

    task = get_task("meiping_vase")
    text = raw_prompt("meiping_vase", workdir="/tmp/raw")
    assert task.goal in text and all(c.description in text for c in task.criteria)
    assert "/tmp/raw/vase.obj" in text and "v x y z r g b" in text and "Z is up" in text
    assert "#b3261e" in text and "watertight" in text and "60 tool calls" in text
    assert "axiom3d" not in text.split("Rules:")[0] and "shape_profile" not in text


def test_blocks_cli_prompt_uses_block_tools_and_allows_its_images():
    text = make_prompt("minecraft_creeper", bare=False, via="cli", workdir="/w", label="x")
    assert "3D modeling tool" in text and "add_box, remove_box, paint_face" in text
    assert "guide topics: conventions, blocks, predictions" in text and "image: PATH" in text
    assert "shape_profile" not in text and "plant_foot" not in text


def test_blocks_raw_prompt_gives_the_same_task_and_conventions_without_the_tool():
    from axiom3d.api import BLOCKS_CONVENTIONS
    from axiom3d.eval.prompts import raw_prompt
    from axiom3d.tasks.library import get_task

    text = raw_prompt("minecraft_creeper", "/w")
    task = get_task("minecraft_creeper")
    assert task.goal in text and all(c.description in text for c in task.criteria)
    assert BLOCKS_CONVENTIONS in text  # the same conventions the tool prints at start_session
    assert "/w/creeper.json" in text and '"op": "add_box"' in text and '"op": "paint_face"' in text
    assert "axiom3d call" not in text and "Do NOT read" in text
