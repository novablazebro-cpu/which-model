"""Test prompts for driving axiom3d with a real model (the same wording every run, so runs compare)."""

from __future__ import annotations

from typing import Literal

PROTOCOL_TOOLS = ("start_session, answer_quiz, guide, observe, check, calc, set_root, set_pose, plant_foot, "
                  "swing_foot, batch, undo, accept_discrepancy, finish, export")
BARE_TOOLS = "start_session, guide, observe, check, calc, set_root, set_pose, plant_foot, swing_foot, batch, undo, finish, export"
VESSEL_PROTOCOL_TOOLS = ("start_session, answer_quiz, guide, observe, check, calc, shape_profile, paint_band, batch, "
                         "undo, accept_discrepancy, finish, export")
VESSEL_BARE_TOOLS = "start_session, guide, observe, check, calc, shape_profile, paint_band, batch, undo, finish, export"
BLOCKS_PROTOCOL_TOOLS = ("start_session, answer_quiz, guide, observe, check, calc, add_box, remove_box, paint_face, "
                         "batch, undo, accept_discrepancy, finish, export")
BLOCKS_BARE_TOOLS = ("start_session, guide, observe, check, calc, add_box, remove_box, paint_face, batch, undo, "
                     "finish, export")
PROJECT = "/home/user/which-model"
BUDGET = 60


def test_prompt(task_id: str, bare: bool, via: Literal["mcp", "cli"], workdir: str | None = None,
                label: str | None = None, project: str = PROJECT) -> str:
    """The instruction given to a model under test. `via="cli"` adds the shell command and file rules."""
    from axiom3d.tasks.library import get_task

    kind = get_task(task_id).kind
    modeling = kind in ("vessel", "blocks")  # static models: the model may look at the images the tool draws
    lines = [f'You are testing a 3D {"modeling" if modeling else "animation"} tool called axiom3d. Your job: complete '
             f'the task "{task_id}".', ""]
    if via == "cli":
        if not workdir:
            raise ValueError("via='cli' needs workdir")
        cmd = f"cd {workdir} && UV_SYSTEM_CERTS=1 uv run -q --project {project} axiom3d call"
        flags = f"--home ./home{' --protocol off' if bare else ''}{f' --label {label}' if label else ''}"
        lines += [
            "You control it ONLY through its command-line interface. How to call a tool (one shell command per call):",
            f"  {cmd} TOOL --home ./home --json 'JSON_ARGUMENTS'",
            "", "Start with:",
            f"  {cmd} start_session {flags} --json '{{\"task\": \"{task_id}\"}}'",
        ]
    else:
        lines += ["Use the axiom3d tools. Start by calling start_session with task "
                  f'"{task_id}", then read what it returns and follow it.']
    if kind == "vessel":
        tools, topics = (VESSEL_BARE_TOOLS if bare else VESSEL_PROTOCOL_TOOLS), "conventions, vessels, predictions, calculator, tools"
    elif kind == "blocks":
        tools, topics = (BLOCKS_BARE_TOOLS if bare else BLOCKS_PROTOCOL_TOOLS), "conventions, blocks, predictions, calculator, tools"
    else:
        tools, topics = (BARE_TOOLS if bare else PROTOCOL_TOOLS), "conventions, walking, predictions, calculator, tools"
    lines += [
        "", f"Tools: {tools}.",
        f"Read every response carefully. guide topics: {topics}.",
        "", "Rules:",
    ]
    if via == "cli":
        if modeling:
            lines += [
                "- Use only the axiom3d CLI commands above. Do NOT read, list, grep, cat or open any files or "
                "directories (not source code, not the ./home directory). Do not write or edit files.",
                "- One exception: when a tool prints `image: PATH`, you may open that exact PNG to look at it.",
            ]
        else:
            lines.append("- Use only the axiom3d CLI commands above. Do NOT read, list, grep, cat or open any files or "
                         "directories (not source code, not the ./home directory, not images). Do not write or edit files.")
        lines.append(f"- Budget: at most {BUDGET} tool calls in total.")
    if bare:
        lines.append("- Call `finish` (for example with no claims) when you believe the task is complete.")
    else:
        lines.append("- The task is complete only when `finish` reports CERTIFIED. If it says NOT CERTIFIED, fix the "
                     "problems it lists and call finish again, until CERTIFIED or the budget runs out.")
    lines += ["", "When you stop, reply with: (1) the last line of your final finish output (or \"never called "
              "finish\"), (2) how many tool calls you used, (3) one short paragraph on what was hardest."]
    return "\n".join(lines)


def raw_prompt(task_id: str, workdir: str) -> str:
    """The same task for a model WITHOUT axiom3d, graded by the same criteria."""
    from axiom3d.model.vessel import PALETTE
    from axiom3d.tasks.library import get_task

    task = get_task(task_id)
    if task.kind == "blocks":
        return _raw_blocks_prompt(task, workdir)
    palette = ", ".join(f"{name} {hexc}" for name, hexc in PALETTE.items())
    lines = [
        "You are a 3D modeler working in Python. Build this object as a triangle mesh and save it as an OBJ file.",
        "", f"TASK: {task.goal}", "", "ACCEPTANCE (measured from your file by a grader; every line must pass):",
        *[f"- {c.description}" for c in task.criteria],
        "", "CONVENTIONS:",
        "- Units are metres. Z is up. The object stands on z = 0, with its axis of revolution on the Z axis.",
        "- A real vessel: hollow, open at the mouth, with a wall about 6 mm thick, as ONE closed (watertight) "
        "surface: every edge shared by exactly two triangles.",
        "- Diameters are measured on the outside surface. The grader slices your mesh by height to find them.",
        f"- Colours are per vertex. The grader names each colour by the nearest of: {palette}.",
        "", "OUTPUT:",
        f"- Write {workdir}/vase.obj with lines `v x y z r g b` (colour components 0..1) and `f i j k` (1-based "
        "vertex indices, triangles).",
        f"- Write your code in {workdir} (for example {workdir}/make_vase.py) and run it with "
        f"`cd {workdir} && python3 make_vase.py`. Python 3 with numpy is available; matplotlib is not.",
        "", "Rules:",
        f"- Work only inside {workdir}. Do NOT read, list or search anything outside it (no repository, no other "
        "projects, no installed 3D tools such as axiom3d).",
        "- You may write and run your own scripts there, including code that measures your own mesh, and view "
        "images you create there.",
        f"- Budget: at most {BUDGET} tool calls in total.",
        "", "When you stop, reply with: (1) whether vase.obj exists and what you believe it measures, (2) how many "
        "tool calls you used, (3) one short paragraph on what was hardest.",
    ]
    return "\n".join(lines)


def _raw_blocks_prompt(task, workdir: str) -> str:
    """Blocks without the tool: the same conventions text start_session prints, and a plain JSON command list.

    No guide, renders, checks, quiz or feedback: those are what the tool adds."""
    from axiom3d.api import BLOCKS_CONVENTIONS
    from axiom3d.model.blocks import DEFAULT_KEY

    key = ", ".join(f"{k} = {v}" for k, v in DEFAULT_KEY.items())
    lines = [
        "You are a 3D modeler. Build this object from boxes and save it as a JSON list of commands.",
        "", f"TASK: {task.goal}", "", "ACCEPTANCE (measured from your file by a grader; every line must pass):",
        *[f"- {c.description}" for c in task.criteria],
        "", "CONVENTIONS:", BLOCKS_CONVENTIONS,
        "", "OUTPUT:",
        f"- Write {workdir}/creeper.json: a JSON list of commands, applied in order. Two kinds:",
        '  {"op": "add_box", "name": "head", "low": [x, y, z], "high": [x, y, z], "color": "green"}',
        '  {"op": "paint_face", "box": "head", "face": "front", "pixels": ["row 1 (top)", "row 2", ...]}',
        "- Names: lowercase letters, digits and _. Corners: whole pixels within ±64; every high value greater "
        "than the low one. At most 32 boxes.",
        f"- Pixel letters: {key}. Each face needs exactly as many rows as it is tall and as many letters per row "
        "as it is wide. A command the grader cannot apply stops the replay there.",
        f"- You may write and run Python 3 (numpy is available; matplotlib and PIL may not be) in {workdir}, "
        f"including code that checks your own model, e.g. `cd {workdir} && python3 make_creeper.py`.",
        "", "Rules:",
        f"- Work only inside {workdir}. Do NOT read, list or search anything outside it (no repository, no other "
        "projects, no installed 3D tools such as axiom3d).",
        f"- Budget: at most {BUDGET} tool calls in total.",
        "", "When you stop, reply with: (1) whether creeper.json exists and what you believe it builds, (2) how "
        "many tool calls you used, (3) one short paragraph on what was hardest.",
    ]
    return "\n".join(lines)
