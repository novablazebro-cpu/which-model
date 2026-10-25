import pytest

from axiom3d.anim.commands import CommandError, apply_command
from axiom3d.anim.evaluate import evaluate_clip
from axiom3d.api import AxiomError, Workbench
from axiom3d.checks.base import CheckContext, run_checks
from axiom3d.guide import read_topic
from axiom3d.model.vessel import measure_spec
from axiom3d.protocol.predict import PredictionError, evaluate_prediction, is_precise, parse_prediction
from axiom3d.session_store import current_id, load
from axiom3d.tasks.library import get_task, grade_vessel, new_clip
from axiom3d.tasks.reference import reference_commands

TID = "meiping_vase"


def build(skel, cmds):
    clip = new_clip(get_task(TID), skel)
    for c in cmds:
        clip = apply_command(skel, clip, c)
    return clip, evaluate_clip(skel, clip)


def shape(points, wall=None):
    cmd = {"op": "shape_profile", "points": points}
    return cmd if wall is None else dict(cmd, wall=wall)


def found(skel, cmds, severity=None):
    clip, states = build(skel, cmds)
    return {r.id for r in run_checks(CheckContext(skel, clip, states, "vessel")) if severity in (None, r.severity)}


def ref_profile():
    return reference_commands(TID)[0]["points"]


def test_reference_vase_passes_every_criterion_cleanly(skel):
    clip, states = build(skel, reference_commands(TID))
    for c in get_task(TID).criteria:
        ok, measured = c.fn(skel, clip, states)
        assert ok, (c.id, measured)
    assert not found(skel, reference_commands(TID))


def test_diameters_typed_as_radii_fail_the_width_criterion(skel):
    # The classic mistake: typing the diameter where the profile wants a radius.
    doubled = [[h, 2 * r] for h, r in ref_profile()]
    clip, _ = build(skel, [shape(doubled)] + reference_commands(TID)[1:])
    results = {cid: ok for cid, ok, _ in grade_vessel(measure_spec(clip.vessel))}
    assert results["width"] is False and results["height"] is True


def test_shape_profile_rejects_bad_input(skel):
    with pytest.raises(CommandError, match="strictly increase"):
        build(skel, [shape([[0, 0.05], [0.2, 0.06], [0.1, 0.07]])])
    with pytest.raises(CommandError, match="wall"):
        build(skel, [shape(ref_profile(), wall=0.1)])
    with pytest.raises(CommandError, match=r"\[height, radius\]"):
        build(skel, [shape([[0, 0.05], [0.2], [0.3, 0.02]])])
    with pytest.raises(CommandError, match="points"):
        build(skel, [{"op": "shape_profile", "points": "tall"}])


def test_paint_band_rules(skel):
    with pytest.raises(CommandError, match="shape_profile first"):
        build(skel, [{"op": "paint_band", "start": 0, "end": 0.1, "color": "red"}])
    with pytest.raises(CommandError, match="start must be below end"):
        build(skel, [shape(ref_profile()), {"op": "paint_band", "start": 0.2, "end": 0.1, "color": "red"}])
    with pytest.raises(CommandError, match="unknown colour"):
        build(skel, [shape(ref_profile()), {"op": "paint_band", "start": 0, "end": 0.1, "color": "mauve"}])


def test_reshaping_keeps_the_paint(skel):
    clip, _ = build(skel, reference_commands(TID) + [shape([[h, r * 0.9] for h, r in ref_profile()])])
    assert len(clip.vessel.bands) == 3


def test_ops_belong_to_their_task_kind(home):
    wb = Workbench(home, protocol=False)
    wb.start_session(TID)
    with pytest.raises(AxiomError, match="shape_profile"):
        wb.set_root(frame=0, forward=0.2)
    wb2 = Workbench(home / "b", protocol=False)
    wb2.start_session("step_forward")
    with pytest.raises(AxiomError, match="vessel"):
        wb2.shape_profile(points=ref_profile())
    with pytest.raises(AxiomError, match="vessel"):
        wb2.batch([{"op": "paint_band", "start": 0, "end": 0.1, "color": "red"}])


def test_vessel_checks_teach_the_common_failures(skel):
    assert found(skel, []) == {"vessel.no_profile"}
    narrow_neck = [[0, 0.06], [0.2, 0.1], [0.35, 0.007], [0.4, 0.02]]
    assert "vessel.too_thin" in found(skel, [shape(narrow_neck)], "error")
    closed = [[0, 0.06], [0.2, 0.1], [0.4, 0.01]]
    assert "vessel.mouth_closed" in found(skel, [shape(closed)], "error")
    tippy = [[0, 0.01], [0.05, 0.03], [0.3, 0.12], [0.4, 0.03]]
    assert "vessel.unstable" in found(skel, [shape(tippy)], "error")
    step = [[0, 0.05], [0.1, 0.05], [0.101, 0.1], [0.3, 0.1]]
    assert "vessel.kink" in found(skel, [shape(step)], "warning")
    high = [shape(ref_profile()), {"op": "paint_band", "start": 0.3, "end": 0.6, "color": "red"}]
    assert "vessel.band_outside" in found(skel, high, "warning")


def test_vessel_predictions(skel):
    clip, states = build(skel, reference_commands(TID))
    p = parse_prediction("vessel.max_diameter ~= 0.21 ± 0.02", skel)
    assert is_precise(p) and evaluate_prediction(p, skel, clip, states, 0).passed
    assert not is_precise(parse_prediction("vessel.height ~= 0.4 ± 0.05", skel))
    assert is_precise(parse_prediction("vessel.shoulder_ratio ~= 0.7 ± 0.05", skel))
    assert is_precise(parse_prediction("vessel.capacity in [6.9, 7.4]", skel))
    assert is_precise(parse_prediction("vessel.tip_angle ~= 18 ± 5", skel))
    assert evaluate_prediction(parse_prediction("vessel.neck_diameter < vessel.mouth_diameter", skel),
                               skel, clip, states, 0).passed
    red = parse_prediction("color(0.2) is red", skel)
    assert is_precise(red) and evaluate_prediction(red, skel, clip, states, 0).passed
    out = evaluate_prediction(parse_prediction("color(0.39) is red", skel), skel, clip, states, 0)
    assert not out.passed and "blue" in out.measured
    with pytest.raises(PredictionError, match="shoulder_ratio"):
        parse_prediction("vessel.shoulder ~= 0.7 ± 0.05", skel)
    with pytest.raises(PredictionError, match="red"):
        parse_prediction("color(0.2) is crimson", skel)


def test_vessel_quiz_is_about_vessels(home):
    wb = Workbench(home)
    text = wb.start_session(TID).text
    assert "radius" in text and "BRIEFING QUIZ" in text and "heading" not in text.lower()
    st = load(current_id(home), home)
    wrong = wb.answer_quiz({q["id"]: "diameter" for q in st.quiz}).text
    assert "Not yet" in wrong
    ok = wb.answer_quiz({q["id"]: q["answer"] for q in st.quiz}).text
    assert "PASSED" in ok


def started(home, protocol=True):
    wb = Workbench(home, protocol=protocol)
    wb.start_session(TID)
    if protocol:
        st = load(current_id(home), home)
        wb.answer_quiz({q["id"]: q["answer"] for q in st.quiz})
    return wb


def test_protocol_vase_end_to_end(home):
    wb = started(home)
    cmds = reference_commands(TID)
    res = wb.shape_profile(points=cmds[0]["points"], expect=["vessel.height ~= 0.40 ± 0.01"])
    assert res.text.startswith("APPLIED: shape_profile(13 points") and "PASS" in res.text
    assert "CHANGED:" in res.text and "vessel.max_diameter" in res.text and "FIXED vessel.no_profile" in res.text
    with pytest.raises(AxiomError, match="changes"):
        wb.paint_band(start=0.04, end=0.37, color="red", expect=["vessel.height ~= 0.40 ± 0.01"])
    for c in cmds[1:]:
        mid = (c["start"] + c["end"]) / 2
        out = wb.paint_band(start=c["start"], end=c["end"], color=c["color"], expect=[f"color({mid}) is {c['color']}"])
        assert out.text.startswith("APPLIED") and "PASS" in out.text
    obs = wb.observe().text
    for word in ("height 0.400", "max diameter 0.214", "shoulder ratio 0.725", "PROFILE", "COLOUR ZONES",
                 "0.040–0.370 red"):
        assert word in obs, word
    with pytest.raises(AxiomError, match="report, sheet"):
        wb.observe(views=["timeline"])
    checked = wb.check().text
    assert "PASS  width" in checked and "FAIL" not in checked
    done = wb.finish(["vessel.shoulder_ratio ~= 0.725 ± 0.02", "color(0.2) is red"])
    assert "CERTIFIED" in done.text and "NOT CERTIFIED" not in done.text


def test_bare_vase_and_calc(home):
    wb = started(home, protocol=False)
    with pytest.raises(AxiomError, match="no profile"):
        wb.calc("radius_at(0.2)")
    wb.shape_profile(points=ref_profile())
    out = wb.calc("r = radius_at(0.29); d = 2 * r; vessel.height; vessel.shoulder_ratio").text
    assert "r = 0.107" in out and "d = 0.214" in out and "= 0.400" in out and "= 0.725" in out
    with pytest.raises(AxiomError, match="shoulder_ratio"):
        wb.calc("vessel.shoulder")
    dry = wb.paint_band(start=0, end=0.4, color="gold", dry_run=True).text
    assert dry.startswith("DRY RUN") and "colour" in dry
    assert len(load(current_id(home), home).commands) == 1


# Friction found by the Haiku vase runs (docs/eval/2026-10-25-haiku-vase.md, F1-F4).

def test_band_ends_are_inclusive_and_the_docs_say_so(home, skel):
    # F3: a run predicted that paint_band leaves out its end height.
    clip, _ = build(skel, [shape(ref_profile()), {"op": "paint_band", "start": 0, "end": 0.4, "color": "red"},
                           {"op": "paint_band", "start": 0, "end": 0.05, "color": "blue"}])
    assert clip.vessel.color_at(0.05) == "#1f3f8f"
    assert "both included" in Workbench(home).start_session(TID).text
    assert "both included" in read_topic("vessels")


def test_start_text_shows_finish_claims_as_a_list(home):
    # F4: a run sent its claims as one prose string and lost a call.
    assert 'finish(claims=["vessel.' in Workbench(home).start_session(TID).text


def test_tools_guide_covers_vessels_and_says_the_quiz_is_protocol_only():
    # F1: the bare run read guide('tools'), expected a quiz and found only walking tools.
    text = read_topic("tools")
    assert "shape_profile" in text and "paint_band" in text and "vessels" in text
    assert "protocol" in text.split("answer_quiz", 1)[1][:160]


def test_bare_finish_reports_the_acceptance_result(home):
    # F2: bare finish said only "Session closed.", so the run could not tell whether it passed.
    wb = Workbench(home, protocol=False)
    wb.start_session(TID)
    wb.batch(reference_commands(TID))
    assert wb.finish().text.startswith("Session closed. Acceptance: 11/11 criteria pass.")
    wb.start_session(TID)
    text = wb.finish().text
    assert "Acceptance: 0/11" in text and "FAIL  height" in text


# The hourglass the user saw: the protocol run of 2026-10-25 put its waist at 0.07 m (0.175 H), above the
# blue foot band, and every criterion passed because none measured where the waist is.
HOURGLASS = [[0, 0.064], [0.03, 0.06], [0.07, 0.05], [0.14, 0.072], [0.2, 0.094], [0.288, 0.108], [0.315, 0.09],
             [0.345, 0.04], [0.37, 0.018], [0.4, 0.02]]


def test_the_waist_height_is_measured(skel):
    assert measure_spec(build(skel, [shape(ref_profile())])[0].vessel).waist_height == pytest.approx(0.04, abs=1e-6)
    assert measure_spec(build(skel, [shape(HOURGLASS)])[0].vessel).waist_height == pytest.approx(0.07, abs=1e-6)


def test_a_waist_high_above_the_foot_fails_the_meiping(skel):
    graded = {cid: (ok, why) for cid, ok, why in grade_vessel(measure_spec(build(skel, [shape(HOURGLASS)])[0].vessel))}
    assert graded["waist_low"] == (False, "waist at h 0.070 m = 0.175 x height")
    assert dict((c, ok) for c, ok, _ in grade_vessel(measure_spec(build(skel, [shape(ref_profile())])[0].vessel)))["waist_low"]


def test_the_report_and_calc_show_where_the_waist_is(home):
    wb = Workbench(home, protocol=False)
    wb.start_session(TID)
    wb.shape_profile(HOURGLASS)
    assert "waist 0.100 at h 0.070" in wb.observe(views=["report"]).text
    assert "0.07" in wb.calc("vessel.waist_height").text
