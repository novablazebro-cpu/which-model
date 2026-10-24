import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from axiom3d.session_store import current_id, load
from axiom3d.tasks.reference import reference_commands

TOOLS = {"start_session", "answer_quiz", "guide", "observe", "check", "set_root", "set_pose", "plant_foot",
         "swing_foot", "undo", "accept_discrepancy", "finish", "export"}


def texts(result):
    return "\n".join(c.text for c in result.content if c.type == "text")


def test_mcp_end_to_end(home):
    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "axiom3d.cli", "serve", "--home", str(home)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                assert {t.name for t in (await s.list_tools()).tools} == TOOLS
                started = texts(await s.call_tool("start_session", {"task": "step_forward"}))
                assert "BRIEFING QUIZ" in started
                st = load(current_id(home), home)
                quiz = texts(await s.call_tool("answer_quiz", {"answers": {q["id"]: q["answer"] for q in st.quiz}}))
                assert "PASSED" in quiz
                for cmd in reference_commands("step_forward"):
                    args = {k: v for k, v in cmd.items() if k != "op"}
                    out = texts(await s.call_tool(cmd["op"], {**args, "expect": ["root.heading ~= 0 ± 1"]}))
                    assert out.startswith("APPLIED"), out
                bad = texts(await s.call_tool("set_pose", {"frame": 3, "angles": {"left_knee.flexion": 10}}))
                assert bad.startswith("ERROR:") and "~=" in bad
                obs = await s.call_tool("observe", {"views": ["sheet"]})
                assert any(c.type == "image" for c in obs.content)
                done = texts(await s.call_tool("finish", {"claims": ["left_ankle.forward@24 ~= 0.36 ± 0.02",
                                                                     "slide(right_heel) < 0.02"]}))
                assert "CERTIFIED" in done and "NOT CERTIFIED" not in done

    anyio.run(run)
