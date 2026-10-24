import pytest

from axiom3d.api import AxiomError, Workbench
from axiom3d.eval.agents import correct_script
from axiom3d.session_store import current_id, load

TRUE = ["root.heading ~= 0 ± 1"]  # always true for step_forward, and precise


def started(home, protocol=True, task="step_forward"):
    wb = Workbench(home, protocol=protocol)
    wb.start_session(task)
    return wb


def pass_quiz(wb, home):
    st = load(current_id(home), home)
    return wb.answer_quiz({q["id"]: q["answer"] for q in st.quiz})


def solve_reference(wb, task="step_forward"):
    # The honest scripted agent's edits: each carries predictions computed by simulating the edit.
    for tool, kwargs in correct_script(task)[2:-1]:
        getattr(wb, tool)(**kwargs)


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
    wb.set_pose(frame=12, angles={"left_knee.flexion": -20}, expect=["left_knee.flexion@12 ~= -20 ± 1"])
    res = wb.finish(["root.heading ~= 0 ± 1", "slide(right_heel) < 0.02"])
    assert "NOT CERTIFIED" in res.text and "anatomy.joint_limits" in res.text
    wb.undo()
    solve_reference(wb)
    res = wb.finish(["left_ankle.forward@24 ~= 0.36 ± 0.02", "slide(right_heel) < 0.02"])
    assert "CERTIFIED" in res.text and "NOT CERTIFIED" not in res.text
    st = load(current_id(home), home)
    assert st.phase == "DONE" and st.ledger["certified"] is True and st.ledger["task_success"] is True


def test_finish_needs_two_claims(home):
    wb = started(home)
    pass_quiz(wb, home)
    solve_reference(wb)
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
    solve_reference(wb)
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
    wb.set_pose(frame=12, angles={"left_knee.flexion": -20}, expect=["left_knee.flexion@12 ~= -20 ± 1"])
    assert "hint:" in wb.check().text
    bare = started(home, protocol=False)
    bare.set_pose(frame=12, angles={"left_knee.flexion": -20})
    text = bare.check().text
    assert "anatomy.joint_limits" in text and "hint:" not in text


def test_gate_needs_a_prediction_the_edit_changes(home):
    # Review I3: a true-but-unaffected prediction ("head_top above left_toe") must not unlock an edit.
    wb = started(home)
    pass_quiz(wb, home)
    with pytest.raises(AxiomError, match="changes"):
        wb.set_pose(frame=12, angles={"left_shoulder.flexion": 20}, expect=["head_top above left_toe"])
    st = load(current_id(home), home)
    assert st.commands == [] and st.ledger["rejected_edits"] == 1
    res = wb.set_pose(frame=12, angles={"left_shoulder.flexion": 20},
                      expect=["head_top above left_toe", "left_shoulder.flexion@12 ~= 20 ± 1"])
    assert "UNCHANGED" in res.text and "PASS" in res.text
    st = load(current_id(home), home)
    assert st.ledger["predictions_total"] == 1 and st.ledger["predictions_correct"] == 1


def test_noop_edit_needs_no_relevant_prediction(home):
    wb = started(home)
    pass_quiz(wb, home)
    res = wb.set_pose(frame=0, angles={"left_shoulder.flexion": 0}, expect=["left_shoulder.flexion@0 ~= 0 ± 1"])
    assert res.text.startswith("APPLIED")


def test_swing_predictions_default_to_mid_swing(home):
    wb = started(home)
    pass_quiz(wb, home)
    for tool, kwargs in correct_script("step_forward")[2:-1]:  # everything except the swing, plants on both sides
        if tool != "swing_foot":
            getattr(wb, tool)(**kwargs)
    res = wb.swing_foot(side="left", start=6, end=18, apex=0.08, expect=["max_height(left_ankle) ~= 0.148 ± 0.01",
                                                                          "left_ankle.z ~= 0.148 ± 0.005"])
    assert res.text.count("PASS") == 2, res.text


def test_parallel_edits_all_kept(home):
    # Review I1: MCP runs sync tools in worker threads; concurrent edits must not overwrite each other.
    from concurrent.futures import ThreadPoolExecutor
    wb = started(home, protocol=False)
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(lambda f: wb.set_pose(frame=f, angles={"left_shoulder.flexion": f}), range(12)))
    st = load(current_id(home), home)
    assert sorted(c["frame"] for c in st.commands) == list(range(12)) and st.ledger["edits"] == 12


def test_server_workbench_only_sees_its_own_session(home):
    # Review I2: two MCP servers sharing a home must not edit each other's sessions through home/current.
    bare = Workbench(home, protocol=False, shared_current=False)
    strict = Workbench(home, protocol=True, shared_current=False)
    bare.start_session("step_forward")
    with pytest.raises(AxiomError, match="start_session"):
        strict.set_root(frame=0, height=0.9)
    strict.start_session("step_forward")
    bare.set_root(frame=0, height=0.9)
    assert load(bare.session_id, home).commands and not load(strict.session_id, home).commands


def test_calc_tool_and_variables_in_edits(home):
    wb = started(home)
    out = wb.calc("r = reach(0.89); s = 0.36")
    assert "r = 0.251" in out.text and "s = 0.360" in out.text          # allowed before the quiz
    pass_quiz(wb, home)
    res = wb.plant_foot(side="left", start=0, end=24, forward=0.36, expect=["left_ankle.forward ~= $s ± 0.05"])
    assert "PASS" in res.text or "FAIL" in res.text
    with pytest.raises(AxiomError, match="calc"):
        wb.set_pose(frame=12, angles={"left_shoulder.flexion": 10}, expect=["left_shoulder.flexion@12 ~= $nope ± 1"])
    assert Workbench(home).calc("s * 2").text.startswith("= 0.720")      # variables persist across instances
    with pytest.raises(AxiomError, match="left_toe"):
        wb.calc("left_tow.z")


def test_calc_in_bare_mode(home):
    wb = started(home, protocol=False)
    assert "= 0.068" in wb.calc("left_ankle.z").text
