import pytest

from axiom3d.api import AxiomError, Workbench
from axiom3d.session_store import current_id, load
from axiom3d.tasks.reference import reference_commands

TRUE = ["root.heading ~= 0 ± 1"]  # always true for step_forward, and precise


def started(home, protocol=True, task="step_forward"):
    wb = Workbench(home, protocol=protocol)
    wb.start_session(task)
    return wb


def pass_quiz(wb, home):
    st = load(current_id(home), home)
    return wb.answer_quiz({q["id"]: q["answer"] for q in st.quiz})


def edit(wb, cmd, expect):
    args = {k: v for k, v in cmd.items() if k != "op"}
    return getattr(wb, cmd["op"])(**args, expect=expect)


def test_start_session_text(home):
    wb = Workbench(home)
    text = wb.start_session("step_forward").text
    assert "GOAL" in text and "q5" in text and "answer_quiz" in text and "STATUS: phase=BRIEFING" in text


def test_edit_locked_before_quiz(home):
    wb = started(home)
    with pytest.raises(AxiomError, match="quiz"):
        wb.set_root(frame=0, height=0.9, expect=TRUE)


def test_quiz_feedback_then_pass(home):
    wb = started(home)
    res = wb.answer_quiz({"q1": "+Y"})
    assert "wrong" in res.text and "Not yet" in res.text
    assert "PASSED" in pass_quiz(wb, home).text
    st = load(current_id(home), home)
    assert st.phase == "WORKING" and st.ledger["quiz_attempts"] == 2


def test_edit_without_expect_rejected(home):
    wb = started(home)
    pass_quiz(wb, home)
    with pytest.raises(AxiomError, match="~="):
        wb.set_root(frame=0, height=0.9)
    assert load(current_id(home), home).ledger["rejected_edits"] == 1


def test_vacuous_expect_rejected(home):
    wb = started(home)
    pass_quiz(wb, home)
    with pytest.raises(AxiomError, match="precise"):
        wb.set_root(frame=0, height=0.9, expect=["left_toe.x < 1000"])


def test_failed_prediction_blocks_next_edit(home):
    wb = started(home)
    pass_quiz(wb, home)
    res = wb.set_pose(frame=12, angles={"left_hip.flexion": -30}, expect=["left_toe in_front_of pelvis"])
    assert "FAIL" in res.text and "DISCREPANCY" in res.text
    with pytest.raises(AxiomError, match="undo"):
        wb.set_root(frame=0, height=0.9, expect=TRUE)
    wb.undo()
    st = load(current_id(home), home)
    assert st.commands == [] and st.pending_discrepancy is None and st.ledger["discrepancies"] == 1
    wb.set_pose(frame=12, angles={"left_hip.flexion": -30}, expect=["left_toe in_front_of pelvis"])
    wb.accept_discrepancy("I meant to extend the hip here")
    st = load(current_id(home), home)
    assert st.pending_discrepancy is None and st.ledger["accepted_discrepancies"] == 1
    assert st.ledger["predictions_total"] == 2 and st.ledger["predictions_correct"] == 0


def test_finish_blocked_by_errors_then_certified(home):
    wb = started(home)
    pass_quiz(wb, home)
    wb.set_pose(frame=12, angles={"left_knee.flexion": -20}, expect=TRUE)
    res = wb.finish(["root.heading ~= 0 ± 1", "slide(right_heel) < 0.02"])
    assert "NOT CERTIFIED" in res.text and "anatomy.joint_limits" in res.text
    wb.undo()
    for cmd in reference_commands("step_forward"):
        edit(wb, cmd, TRUE)
    res = wb.finish(["left_ankle.forward@24 ~= 0.36 ± 0.02", "slide(right_heel) < 0.02"])
    assert "CERTIFIED" in res.text and "NOT CERTIFIED" not in res.text
    st = load(current_id(home), home)
    assert st.phase == "DONE" and st.ledger["certified"] is True and st.ledger["task_success"] is True


def test_finish_needs_two_claims(home):
    wb = started(home)
    pass_quiz(wb, home)
    for cmd in reference_commands("step_forward"):
        edit(wb, cmd, TRUE)
    res = wb.finish(["slide(right_heel) < 0.02"])
    assert "NOT CERTIFIED" in res.text and "at least 2 claims" in res.text


def test_bare_mode_finish_always_done_records_success(home):
    wb = started(home, protocol=False)
    wb.set_root(frame=24, forward=0.2)
    res = wb.finish([])
    st = load(current_id(home), home)
    assert st.phase == "DONE" and st.ledger["task_success"] is False and st.ledger["certified"] is None
    assert "CERTIFIED" not in res.text and "STATUS" not in res.text


def test_bad_names_and_frames_are_axiom_errors(home):
    wb = started(home)
    pass_quiz(wb, home)
    with pytest.raises(AxiomError, match="left_hip.flexion"):
        wb.set_pose(frame=0, angles={"hip_left": 10}, expect=TRUE)
    with pytest.raises(AxiomError, match="0..24"):
        wb.set_pose(frame=99, angles={"left_hip.flexion": 10}, expect=TRUE)
    with pytest.raises(AxiomError, match="left_toe"):
        wb.set_root(frame=0, height=0.9, expect=["left_tow.z < 0.1 @3"])
    res = wb.set_pose(frame=0, angles={"left_hip.flexion": "30"}, expect=["left_hip.flexion ~= 30 ± 1"])
    assert "PASS" in res.text


def test_wrong_phase_messages(home):
    wb = started(home)
    pass_quiz(wb, home)
    wb.set_pose(frame=12, angles={"left_hip.flexion": -30}, expect=["left_toe in_front_of pelvis"])
    with pytest.raises(AxiomError, match="undo"):
        wb.finish(["a", "b"])
    wb.undo()
    for cmd in reference_commands("step_forward"):
        edit(wb, cmd, TRUE)
    wb.finish(["left_ankle.forward@24 ~= 0.36 ± 0.02", "slide(right_heel) < 0.02"])
    with pytest.raises(AxiomError, match="finished"):
        wb.set_root(frame=0, height=0.9, expect=TRUE)
    bare = started(home, protocol=False)
    with pytest.raises(AxiomError, match="bare mode"):
        bare.answer_quiz({"q1": "-Y"})


def test_unknown_session(home):
    wb = Workbench(home)
    with pytest.raises(AxiomError, match="start_session"):
        wb.observe()
    wb.start_session("step_forward")
    with pytest.raises(AxiomError, match="start_session"):
        wb.observe(session="nope")
    with pytest.raises(AxiomError, match="walk_forward"):
        wb.start_session("dance")


def test_observe_text_and_images(home):
    wb = started(home)
    res = wb.observe()
    assert "POINTS" in res.text and "support" in res.text and res.images == []
    res = wb.observe(frames=[0, 12], views=["sheet", "footprints"])
    assert [label for label, _ in res.images] == ["sheet@0", "sheet@12", "footprints"]
    assert all(png.startswith(b"\x89PNG") for _, png in res.images)
    with pytest.raises(AxiomError, match="filmstrip"):
        wb.observe(views=["xray"])


def test_check_lists_hints_only_in_protocol(home):
    wb = started(home)
    pass_quiz(wb, home)
    wb.set_pose(frame=12, angles={"left_knee.flexion": -20}, expect=TRUE)
    assert "hint:" in wb.check().text
    bare = started(home, protocol=False)
    bare.set_pose(frame=12, angles={"left_knee.flexion": -20})
    text = bare.check().text
    assert "anatomy.joint_limits" in text and "hint:" not in text
