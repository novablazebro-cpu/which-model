"""Every tool writes only under --home.

Each test builds a small world:  base/home (the --home), base/cwd (where the process runs), base/bait (a
folder an escape could hit). After the run, nothing under base/ outside home may differ, and nothing may
appear in the fake home directory.
"""

import hashlib
import json

import pytest

from axiom3d.api import AxiomError, Workbench
from axiom3d.cli import TOOLS, main
from axiom3d.eval.agents import AUTO, correct_script
from axiom3d.session_store import load
from axiom3d.tasks.library import TASKS

# "{BAIT}" becomes an absolute path inside the sandbox, so even a failing test cannot write outside it.
HOSTILE_IDS = ["../../evil", "..", "../escaped-0a", "{BAIT}/evil-0a", "{BAIT}", "step_forward-0a/../../x",
               "step_forward-0a\n", "step_forward-0a/", "walk_forward-0a/../..", "..\\..\\evil", "~/evil", "%2e%2e/evil"]


@pytest.fixture
def world(tmp_path, monkeypatch):
    base = tmp_path / "base"
    (base / "cwd").mkdir(parents=True)
    (base / "bait").mkdir()
    (base / "bait" / "precious.txt").write_text("do not touch")
    (base / "fakehome").mkdir()
    monkeypatch.setenv("HOME", str(base / "fakehome"))
    monkeypatch.delenv("AXIOM3D_HOME", raising=False)
    monkeypatch.chdir(base / "cwd")
    return base


def snapshot(base):
    """Everything in base's parent (the whole test temp folder) except --home: path -> content hash."""
    seen = {}
    for p in sorted(base.parent.rglob("*")):
        if p == base / "home" or (base / "home") in p.parents:
            continue
        seen[str(p.relative_to(base.parent))] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    return seen


def run_cli(world, tool, args=None, session=None, extra=()):
    argv = ["call", tool, "--home", str(world / "home")]
    if args is not None:
        argv += ["--json", json.dumps(args)]
    if session is not None:
        argv += ["--session", session]
    return main(argv + list(extra))


def home_files(world):
    return sorted(str(p.relative_to(world / "home")) for p in (world / "home").rglob("*") if p.is_file())


def play(world, task_id, called):
    """A whole honest run of one task through the CLI, then every other tool once; returns the session id."""
    for tool, args in correct_script(task_id):
        if args.get("answers") == AUTO:
            sid = (world / "home" / "current").read_text()
            args = {"answers": {q["id"]: q["answer"] for q in load(sid, world / "home").quiz}}
        called.add(tool)
        run_cli(world, tool, args)
    sid = (world / "home" / "current").read_text()
    for tool, args in [("guide", {"topic": "tools"}), ("calc", {"expr": "1 + 1"}), ("observe", {"views": ["sheet"]} if task_id in ("step_forward", "walk_forward", "turn_then_step") else {}),
                       ("check", {}), ("batch", {"edits": [{"op": "set_root", "frame": 0, "height": 0.9}], "dry_run": True}),
                       ("remove_box", {"name": "head"}), ("undo", {}), ("accept_discrepancy", {"reason": "no reason needed"}), ("export", {})]:
        called.add(tool)
        run_cli(world, tool, args)
    return sid


def test_every_tool_writes_only_under_home(world):
    before = snapshot(world)
    called = set()
    for task_id in TASKS:
        play(world, task_id, called)
    assert called == set(TOOLS), f"tools never exercised: {set(TOOLS) - called}"
    assert snapshot(world) == before
    assert list((world / "fakehome").iterdir()) == []
    # ...and the work did land in the three places the design allows.
    files = home_files(world)
    assert any(f.startswith("sessions/") and f.endswith(".json") for f in files)
    assert any(f.startswith("exports/") and f.endswith(".glb") for f in files)
    assert any(f.startswith("images/") and f.endswith(".png") for f in files)
    assert all(f == "current" or f.split("/")[0] in {"sessions", "exports", "images"} for f in files), files


@pytest.mark.parametrize("bad", HOSTILE_IDS)
def test_hostile_session_ids_are_refused_and_contained(world, bad):
    bad = bad.replace("{BAIT}", str(world / "bait"))
    run_cli(world, "start_session", {"task": "step_forward"})
    before = snapshot(world)
    files_before = home_files(world)
    for tool in ("observe", "check", "calc", "undo", "export", "finish"):
        args = {"expr": "1 + 1"} if tool == "calc" else {"claims": []} if tool == "finish" else {}
        assert run_cli(world, tool, args, session=bad) == 1, tool
    assert snapshot(world) == before
    assert home_files(world) == files_before


@pytest.mark.parametrize("bad", HOSTILE_IDS)
def test_hostile_session_ids_through_the_mcp_server_object(world, bad):
    bad = bad.replace("{BAIT}", str(world / "bait"))
    wb = Workbench(world / "home", shared_current=False)
    before = snapshot(world)
    for call in (lambda: wb.observe(session=bad), lambda: wb.export(session=bad), lambda: wb.undo(session=bad)):
        with pytest.raises(AxiomError):
            call()
    assert snapshot(world) == before and not (world / "home").exists()


@pytest.mark.parametrize("bad_task", ["../../evil", "step_forward/../..", "", "{BAIT}/evil"])
def test_hostile_task_names_are_refused(world, bad_task):
    bad_task = bad_task.replace("{BAIT}", str(world / "bait"))
    before = snapshot(world)
    assert run_cli(world, "start_session", {"task": bad_task}) == 1
    assert snapshot(world) == before and home_files(world) == []


@pytest.mark.parametrize("tampered", ["../../evil", "../../../evil-0a", "{BAIT}/evil", "step_forward-0a/../../x"])
def test_tampered_current_pointer_cannot_redirect_writes(world, tampered):
    tampered = tampered.replace("{BAIT}", str(world / "bait"))
    run_cli(world, "start_session", {"task": "step_forward"})
    real = (world / "home" / "current").read_text()
    (world / "home" / "current").write_text(tampered)
    before = snapshot(world)
    # No --session: the tool must trust the pointer and refuse it.
    for tool in ("observe", "check", "undo", "export"):
        assert run_cli(world, tool, {}) == 1, tool
    # With a valid --session the call works, but images must not follow the tampered pointer out of home.
    assert run_cli(world, "observe", {"views": ["sheet"]}, session=real) == 0
    assert snapshot(world) == before
    assert all(f.startswith(("sessions/", "images/", "exports/")) or f == "current" for f in home_files(world))


def test_session_file_with_a_tampered_inner_id_cannot_redirect_export(world):
    run_cli(world, "start_session", {"task": "step_forward"})
    sid = (world / "home" / "current").read_text()
    path = world / "home" / "sessions" / f"{sid}.json"
    data = json.loads(path.read_text())
    data["id"] = "../../escaped"
    path.write_text(json.dumps(data))
    before = snapshot(world)
    for tool in ("export", "observe", "undo"):
        run_cli(world, tool, {}, session=sid)  # refusing or working are both fine; escaping is not
    assert snapshot(world) == before
    assert not (world / "escaped.glb").exists()
    assert all(f.startswith(("sessions/", "images/", "exports/")) or f == "current" for f in home_files(world))
