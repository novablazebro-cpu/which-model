"""MCP server: the 13 axiom3d tools, each a thin wrapper over the Workbench."""

from __future__ import annotations

from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer

from axiom3d.api import AxiomError, ToolResult, Workbench

INSTRUCTIONS = """\
axiom3d is a 3D workbench built for AI models. The tool computes the geometry; you decide.
1) start_session(task), then answer_quiz: editing unlocks when every answer is right.
2) observe: trust the numbers in the report over your reading of images.
3) Edit with set_root / set_pose / plant_foot / swing_foot; every edit needs expect=[precise predictions].
4) A failed prediction blocks edits until undo() or accept_discrepancy(reason).
5) finish(claims) only certifies passing work. NOT CERTIFIED means the task is not done."""


def _reply(call) -> list | str:
    try:
        result: ToolResult = call()
    except AxiomError as e:
        return f"ERROR: {e}"
    return [result.text] + [Image(data=png, format="png") for _, png in result.images]


def build_server(home: Path, protocol: bool = True, label: str | None = None) -> MCPServer:
    # Each server works only on the session it started, never on another server's via home/current.
    wb = Workbench(home, protocol=protocol, label=label, shared_current=False)
    server = MCPServer("axiom3d", instructions=INSTRUCTIONS)
    tool = server.tool(structured_output=False)

    @tool
    def start_session(task: str) -> list | str:
        """Start a task: step_forward, walk_forward or turn_then_step. Returns the goal, conventions and quiz."""
        return _reply(lambda: wb.start_session(task))

    @tool
    def answer_quiz(answers: dict[str, str]) -> list | str:
        """Answer the briefing quiz, e.g. {"q1": "-Y", "q2": "+X", "q3": "behind", "q4": "front", "q5": "0.50"}."""
        return _reply(lambda: wb.answer_quiz(answers))

    @tool
    def guide(topic: str) -> list | str:
        """Read a guide topic: conventions, walking, predictions or tools."""
        return _reply(lambda: wb.guide(topic))

    @tool
    def observe(frames: list[int] | None = None, views: list[str] | None = None) -> list | str:
        """Measure the scene. views: report, timeline (default both), sheet, filmstrip, footprints (images)."""
        return _reply(lambda: wb.observe(frames, views))

    @tool
    def check() -> list | str:
        """Run every check (geometry, anatomy, gait) and show the acceptance criteria status."""
        return _reply(lambda: wb.check())

    @tool
    def set_root(frame: int, forward: float | None = None, left: float | None = None, height: float | None = None,
                 heading: float | None = None, expect: list[str] | None = None) -> list | str:
        """Key the pelvis at a frame: track forward/left (m), height (m), heading (deg). expect: predictions."""
        return _reply(lambda: wb.set_root(frame, forward, left, height, heading, expect))

    @tool
    def set_pose(frame: int, angles: dict[str, float], expect: list[str] | None = None) -> list | str:
        """Key anatomical angles at a frame, e.g. {"left_shoulder.flexion": 15}. expect: predictions."""
        return _reply(lambda: wb.set_pose(frame, angles, expect))

    @tool
    def plant_foot(side: str, start: int, end: int, forward: float | None = None, left: float | None = None,
                   expect: list[str] | None = None) -> list | str:
        """Pin a foot to the ground at track (forward, left) from start to end; the tool solves the leg."""
        return _reply(lambda: wb.plant_foot(side, start, end, forward, left, expect))

    @tool
    def swing_foot(side: str, start: int, end: int, apex: float = 0.08, expect: list[str] | None = None) -> list | str:
        """Carry a foot in an arc (apex in m) from the plant ending at start to the plant starting at end."""
        return _reply(lambda: wb.swing_foot(side, start, end, apex, expect))

    @tool
    def undo() -> list | str:
        """Revert the last edit (also clears a failed prediction)."""
        return _reply(lambda: wb.undo())

    @tool
    def accept_discrepancy(reason: str) -> list | str:
        """Keep the last edit despite a failed prediction; say why the prediction was wrong."""
        return _reply(lambda: wb.accept_discrepancy(reason))

    @tool
    def finish(claims: list[str]) -> list | str:
        """Submit at least 2 claims about the final result. Certifies only if every check, criterion and claim passes."""
        return _reply(lambda: wb.finish(claims))

    @tool
    def export() -> list | str:
        """Write the animation as a glTF 2.0 .glb file (opens in Blender)."""
        return _reply(lambda: wb.export())

    return server
