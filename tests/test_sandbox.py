import pytest

from axiom3d.api import AxiomError, Workbench
from axiom3d.session_store import current_id, load
from axiom3d.tasks.reference import reference_commands

SHOULDER = {"frame": 12, "angles": {"left_shoulder.flexion": 20}, "expect": ["left_shoulder.flexion@12 ~= 20 ± 1"]}


def started(home, protocol=True, task="step_forward"):
    wb = Workbench(home, protocol=protocol)
    wb.start_session(task)
    if protocol:
        st = load(current_id(home), home)
        wb.answer_quiz({q["id"]: q["answer"] for q in st.quiz})
    return wb


def state(home):
    return load(current_id(home), home)


def test_dry_run_leaves_scene_untouched(home):
    wb = started(home)
    res = wb.set_pose(**SHOULDER, dry_run=True)
    assert res.text.startswith("DRY RUN: nothing changed") and "CHANGED:" in res.text and "PASS" in res.text
    st = state(home)
    assert st.commands == [] and st.pending_discrepancy is None
    assert st.ledger["dry_runs"] == 1 and st.ledger["predictions_total"] == 1


def test_commit_after_identical_dry_run_not_counted_again(home):
    wb = started(home)
    wb.set_pose(**SHOULDER, dry_run=True)
    res = wb.set_pose(**SHOULDER)
    assert res.text.startswith("APPLIED") and "seen in sandbox; not counted" in res.text
    st = state(home)
    assert len(st.commands) == 1 and st.ledger["predictions_total"] == 1


def test_failed_dry_run_prediction_does_not_block(home):
    wb = started(home)
    res = wb.set_pose(frame=12, angles={"left_hip.flexion": -30}, expect=["left_toe in_front_of pelvis"], dry_run=True)
    assert "FAIL" in res.text and "nothing is blocked" in res.text
    assert state(home).pending_discrepancy is None
    wb.set_pose(**SHOULDER)


def test_dry_run_allowed_while_discrepancy_pending(home):
    wb = started(home)
    wb.set_pose(frame=12, angles={"left_hip.flexion": -30}, expect=["left_toe in_front_of pelvis"])
    assert wb.set_pose(**SHOULDER, dry_run=True).text.startswith("DRY RUN")
    with pytest.raises(AxiomError, match="undo"):
        wb.set_pose(**SHOULDER)


def test_dry_run_gates_still_apply(home):
    wb = Workbench(home)
    wb.start_session("step_forward")
    with pytest.raises(AxiomError, match="quiz"):
        wb.set_pose(**SHOULDER, dry_run=True)
    wb2 = started(home)
    with pytest.raises(AxiomError, match="~="):
        wb2.set_pose(frame=12, angles={"left_shoulder.flexion": 20}, dry_run=True)


def test_batch_atomic_names_failing_edit(home):
    wb = started(home, protocol=False)
    edits = [{"op": "plant_foot", "side": "right", "start": 0, "end": 24},
             {"op": "plant_foot", "side": "left", "start": 0, "end": 6},
             {"op": "swing_foot", "side": "left", "start": 6, "end": 6}]
    with pytest.raises(AxiomError, match="batch edit #3"):
        wb.batch(edits)
    assert state(home).commands == []
    with pytest.raises(AxiomError, match="batch"):
        wb.batch([{"op": "batch", "edits": []}])
    with pytest.raises(AxiomError, match="1..40"):
        wb.batch([])


def test_batch_is_one_undo(home):
    wb = started(home, protocol=False)
    before = wb.observe().text
    wb.batch(reference_commands("step_forward"))
    assert len(state(home).commands) == 1 and state(home).ledger["batches"] == 1
    wb.undo()
    assert state(home).commands == [] and wb.observe().text == before


def test_batch_step_in_one_call_certifies(home):
    wb = started(home)
    res = wb.batch(reference_commands("step_forward"), expect=["left_ankle.forward@24 ~= 0.36 ± 0.02"])
    assert res.text.startswith("APPLIED: batch(") and "PASS" in res.text
    done = wb.finish(["left_ankle.forward@24 ~= 0.36 ± 0.02", "slide(right_heel) < 0.02"])
    assert "CERTIFIED" in done.text and "NOT CERTIFIED" not in done.text


def test_dry_run_after_done_rejected(home):
    wb = started(home, protocol=False)
    wb.finish([])
    with pytest.raises(AxiomError, match="finished"):
        wb.set_pose(**SHOULDER, dry_run=True)


def test_bare_dry_run_needs_no_predictions(home):
    wb = started(home, protocol=False)
    assert wb.set_root(frame=24, forward=0.2, dry_run=True).text.startswith("DRY RUN")
    assert state(home).commands == []
