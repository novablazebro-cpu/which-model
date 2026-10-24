import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from axiom3d.session_store import current_id, load
from axiom3d.eval.agents import correct_script

TOOLS = {"start_session", "answer_quiz", "guide", "observe", "check", "calc", "set_root", "set_pose", "plant_foot",
         "swing_foot", "batch", "undo", "accept_discrepancy", "finish", "export"}


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
                for tool, args in correct_script("step_forward")[2:-1]:
                    out = texts(await s.call_tool(tool, args))
                    assert out.startswith("APPLIED"), out
                bad = texts(await s.call_tool("set_pose", {"frame": 3, "angles": {"left_knee.flexion": 10}}))
                assert bad.startswith("ERROR:") and "~=" in bad
                obs = await s.call_tool("observe", {"views": ["sheet"]})
                assert any(c.type == "image" for c in obs.content)
                done = texts(await s.call_tool("finish", {"claims": ["left_ankle.forward@24 ~= 0.36 ± 0.02",
                                                                     "slide(right_heel) < 0.02"]}))
                assert "CERTIFIED" in done and "NOT CERTIFIED" not in done

    anyio.run(run)


def test_mcp_accepts_lenient_arguments(home):
    # Review M2: models send numbers for q5, a bare frame number, or one prediction as a string.
    from axiom3d.mcp_server import build_server

    async def run():
        server = build_server(home)
        await server.call_tool("start_session", {"task": "step_forward"})
        quiz = load(current_id(home), home).quiz
        answers = {q["id"]: (float(q["answer"]) if q["id"] == "q5" else q["answer"]) for q in quiz}
        assert "PASSED" in str(await server.call_tool("answer_quiz", {"answers": answers}))
        assert "POINTS" in str(await server.call_tool("observe", {"frames": 24}))
        out = str(await server.call_tool("set_pose", {"frame": 12, "angles": {"left_shoulder.flexion": 20},
                                                      "expect": "left_shoulder.flexion@12 ~= 20 ± 1"}))
        assert "APPLIED" in out

    anyio.run(run)
