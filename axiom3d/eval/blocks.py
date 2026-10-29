"""Grade a block run: an axiom3d session home, or a JSON command list made without the tool, by one criteria set."""

from __future__ import annotations

import json
from pathlib import Path

from axiom3d.eval.vase import LEDGER_KEYS
from axiom3d.model.blocks import BlockModel, commands_to_model
from axiom3d.rig.humanoid import build_mannequin
from axiom3d.session_store import ReplayError, current_id, load, rebuild
from axiom3d.tasks.library import CREEPER, grade_blocks


def _scored(model: BlockModel) -> dict:
    criteria = grade_blocks(model, CREEPER)
    return {"criteria": criteria, "passed": sum(ok for _, ok, _ in criteria), "total": len(criteria), "model": model}


def grade_home(home) -> dict:
    """The block model in the home's current session, graded; a dict with "error" when there is nothing to grade."""
    home = Path(home)
    sid = current_id(home)
    if sid is None:
        return {"error": f"no session in {home}"}
    try:
        st = load(sid, home)
        clip, _ = rebuild(st, build_mannequin())
    except (FileNotFoundError, ValueError, ReplayError) as e:
        return {"error": str(e)}
    row = {"session": sid, "phase": st.phase, "protocol": st.protocol,
           "certified": st.ledger.get("certified"), **{k: st.ledger.get(k, 0) for k in LEDGER_KEYS}}
    return {**row, **_scored(clip.blocks or BlockModel(()))}


def grade_json(path) -> dict:
    """A JSON list of add_box / remove_box / paint_face commands, replayed and graded.

    A command that fails stops the replay; what was built before it is graded, and `replay_error` says why.
    """
    path = Path(path)
    if not path.is_file():
        return {"error": f"no such file: {path}"}
    try:
        cmds = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return {"error": f"{path.name} is not valid JSON ({e})"}
    model, error = commands_to_model(cmds)
    return {"replay_error": error, **_scored(model)}
