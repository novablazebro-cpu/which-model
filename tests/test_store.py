import numpy as np
import pytest

from axiom3d.protocol.ledger import calibration, new_ledger
from axiom3d.session_store import current_id, load, new_session, rebuild, save
from axiom3d.tasks.reference import reference_commands


def test_new_session_shape(skel, home):
    st = new_session("step_forward", True, "tester", home, skel)
    assert st.id.startswith("step_forward-") and st.phase == "BRIEFING"
    assert len(st.quiz) == 5 and st.ledger["label"] == "tester" and st.ledger["protocol"] is True
    bare = new_session("step_forward", False, None, home, skel)
    assert bare.phase == "WORKING" and bare.quiz == []


def test_save_load_roundtrip_and_current(skel, home):
    st = new_session("walk_forward", True, None, home, skel, session_id="walk_forward-abc")
    st.commands = reference_commands("walk_forward")
    save(st, home)
    assert load("walk_forward-abc", home) == st
    assert current_id(home) == "walk_forward-abc"


def test_seed_from_id_is_deterministic(skel, home):
    a = new_session("step_forward", True, None, home, skel, session_id="step_forward-0000beef")
    b = new_session("step_forward", True, None, home, skel, session_id="step_forward-0000beef")
    assert a.seed == 0xBEEF and a.quiz == b.quiz


def test_rebuild_is_deterministic(skel, home):
    st = new_session("step_forward", True, None, home, skel)
    st.commands = reference_commands("step_forward")
    _, s1 = rebuild(st, skel)
    _, s2 = rebuild(st, skel)
    assert all(np.array_equal(a.points[k], b.points[k]) for a, b in zip(s1, s2) for k in a.points)


def test_unknown_and_corrupt_sessions(skel, home):
    with pytest.raises(FileNotFoundError, match="start_session"):
        load("nope", home)
    st = new_session("step_forward", True, None, home, skel, session_id="step_forward-bad")
    save(st, home)
    (home / "sessions" / "step_forward-bad.json").write_text("{not json")
    with pytest.raises(ValueError, match="start_session"):
        load("step_forward-bad", home)
    with pytest.raises(FileNotFoundError, match="start_session"):
        load("../../etc/passwd", home)


def test_ledger_calibration():
    led = new_ledger("m", "step_forward", True)
    assert calibration(led) is None
    led["predictions_total"], led["predictions_correct"] = 4, 3
    assert calibration(led) == 0.75
    assert {"quiz_attempts", "discrepancies", "certified", "task_success", "rejected_edits"} <= set(led)
