"""Test prompts for driving axiom3d with a real model (the same wording every run, so runs compare)."""

from __future__ import annotations

from typing import Literal

PROTOCOL_TOOLS = ("start_session, answer_quiz, guide, observe, check, calc, set_root, set_pose, plant_foot, "
                  "swing_foot, batch, undo, accept_discrepancy, finish, export")
BARE_TOOLS = "start_session, guide, observe, check, calc, set_root, set_pose, plant_foot, swing_foot, batch, undo, finish, export"


def test_prompt(task_id: str, bare: bool, via: Literal["mcp", "cli"], workdir: str | None = None,
                label: str | None = None) -> str:
    """The instruction given to a model under test. `via="cli"` adds the shell command and file rules."""
    lines = [f'You are testing a 3D animation tool called axiom3d. Your job: complete the task "{task_id}".', ""]
    if via == "cli":
        if not workdir:
            raise ValueError("via='cli' needs workdir")
        cmd = f"cd {workdir} && UV_SYSTEM_CERTS=1 uv run -q --project /home/user/which-model axiom3d call"
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
    lines += [
        "", f"Tools: {BARE_TOOLS if bare else PROTOCOL_TOOLS}.",
        "Read every response carefully. guide topics: conventions, walking, predictions, calculator, tools.",
        "", "Rules:",
    ]
    if via == "cli":
        lines += [
            "- Use only the axiom3d CLI commands above. Do NOT read, list, grep, cat or open any files or directories "
            "(not source code, not the ./home directory, not images). Do not write or edit files.",
            "- Budget: at most 60 tool calls in total.",
        ]
    if bare:
        lines.append("- Call `finish` (for example with no claims) when you believe the task is complete.")
    else:
        lines.append("- The task is complete only when `finish` reports CERTIFIED. If it says NOT CERTIFIED, fix the "
                     "problems it lists and call finish again, until CERTIFIED or the budget runs out.")
    lines += ["", "When you stop, reply with: (1) the last line of your final finish output (or \"never called "
              "finish\"), (2) how many tool calls you used, (3) one short paragraph on what was hardest."]
    return "\n".join(lines)
