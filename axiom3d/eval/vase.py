"""Grade a vase run: an axiom3d session home, or a bare OBJ made without the tool, by the same criteria."""

from __future__ import annotations

from pathlib import Path

from axiom3d.model.vessel import VesselError, measure_obj, measure_spec
from axiom3d.rig.humanoid import build_mannequin
from axiom3d.session_store import ReplayError, current_id, load, rebuild
from axiom3d.tasks.library import MEIPING, grade_vessel

LEDGER_KEYS = ("edits", "rejected_edits", "predictions_total", "predictions_correct", "discrepancies",
               "undos", "dry_runs", "batches", "quiz_attempts", "exam_attempts")


def _scored(m) -> dict:
    criteria = grade_vessel(m, MEIPING)
    return {"criteria": criteria, "passed": sum(ok for _, ok, _ in criteria), "total": len(criteria), "measures": m}


def grade_home(home) -> dict:
    """The vessel in the home's current session, graded; a dict with "error" when there is nothing to grade."""
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
    if clip.vessel is None:
        return {**row, "error": "no profile: the session never called shape_profile"}
    return {**row, "spec": clip.vessel, **_scored(measure_spec(clip.vessel))}


def grade_obj(path) -> dict:
    """An OBJ file sliced as a vessel and graded; a dict with "error" when it is missing or unreadable."""
    try:
        m, watertight = measure_obj(path)
    except VesselError as e:
        return {"error": str(e)}
    return {"watertight": watertight, **_scored(m)}
