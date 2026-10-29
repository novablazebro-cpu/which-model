import pytest

from axiom3d.anim.commands import CommandError, apply_command
from axiom3d.anim.evaluate import evaluate_clip
from axiom3d.api import AxiomError, Workbench
from axiom3d.checks.base import CheckContext, run_checks
from axiom3d.guide import read_topic
from axiom3d.protocol.predict import evaluate_prediction, is_precise, parse_prediction
from axiom3d.session_store import current_id, load
from axiom3d.tasks.library import CREEPER_FACE, get_task, grade_blocks, new_clip
from axiom3d.tasks.reference import reference_commands

TID = "minecraft_creeper"
REF = reference_commands(TID)


def build(skel, cmds):
    clip = new_clip(get_task(TID), skel)
    for c in cmds:
        clip = apply_command(skel, clip, c)
    return clip, evaluate_clip(skel, clip)


def graded(skel, cmds) -> dict:
    clip, _ = build(skel, cmds)
    return {cid: (ok, why) for cid, ok, why in grade_blocks(clip.blocks)}


def failed(skel, cmds) -> set:
    return {cid for cid, (ok, _) in graded(skel, cmds).items() if not ok}


def found(skel, cmds) -> set:
    clip, states = build(skel, cmds)
    return {r.id for r in run_checks(CheckContext(skel, clip, states, "blocks"))}


def place(cmds, name, low, high):
    return [dict(c, low=list(low), high=list(high)) if c.get("name") == name else c for c in cmds]


def face_on(face, rows=CREEPER_FACE):
    return [c for c in REF if c["op"] != "paint_face"] + [
        {"op": "paint_face", "box": "head", "face": face, "pixels": list(rows)}]


def test_reference_creeper_passes_every_criterion_cleanly(skel):
    g = graded(skel, REF)
    assert len(g) == 12 and all(ok for ok, _ in g.values()), {k: v for k, v in g.items() if not v[0]}
    assert not found(skel, REF)
    assert all(c.fn(skel, *build(skel, REF))[0] for c in get_task(TID).criteria)


def test_each_classic_mistake_fails_the_criterion_meant_for_it(skel):
    row = REF[:0]
    for i, x in enumerate((-8, -4, 0, 4)):  # four legs side by side under the body
        row.append({"op": "add_box", "name": f"leg{i}", "low": [x, -2, 0], "high": [x + 4, 2, 6]})
    in_a_row = row + [c for c in REF if not c.get("name", "").startswith("leg")]
    assert failed(skel, in_a_row) == {"stance"}
    turned = place(REF, "body", (-2, -4, 6), (2, 4, 18))  # turned 90 degrees: 4 wide, 8 deep
    assert "body" in failed(skel, turned) and "turned 90 deg" in graded(skel, turned)["body"][1]
    # Without an 8 x 4 x 12 body, the criteria that measure from the body cannot pass either.
    assert failed(skel, turned) <= {"body", "stack", "stance", "centred"}
    assert failed(skel, face_on("back")) == {"face_front", "face_only_front"}
    assert failed(skel, face_on("front", CREEPER_FACE[::-1])) == {"face_front"}  # upside down
    floating = place(REF, "head", (-4, -4, 19), (4, 4, 27))
    assert {"stack", "connected"} <= failed(skel, floating)
    assert "blocks.floating" in found(skel, floating)


def test_an_empty_model_fails_politely(skel):
    clip, states = build(skel, [])
    assert "blocks.empty" in {r.id for r in run_checks(CheckContext(skel, clip, states, "blocks"))}
    assert not any(ok for _, ok, _ in grade_blocks(clip.blocks))
    with pytest.raises(CommandError, match="unknown box"):
        build(skel, [{"op": "paint_face", "box": "head", "face": "front", "pixels": ["g"]}])


def test_block_predictions(skel):
    clip, states = build(skel, REF)
    def holds(text):
        p = parse_prediction(text, skel)
        return evaluate_prediction(p, skel, clip, states, 0).passed, is_precise(p)
    assert holds("box.head.min_z ~= 18 ± 0.5") == (True, True)
    assert holds("box.leg_front_right.max_y <= box.body.min_y") == (True, True)
    assert holds("model.height ~= 26 ± 1") == (True, True)
    assert holds("model.height ~= 26 ± 5") == (True, False)
    assert holds("pixel(head, front, 3, 2) is black") == (True, True)  # row 3, column 2: left eye as seen
    assert holds("pixel(head, back, 3, 2) is black") == (False, True)
    assert holds("box.nobody.min_z ~= 1 ± 1")[0] is False


def test_protocol_creeper_end_to_end(home):
    wb = Workbench(home, protocol=True)
    start = wb.start_session(TID).text
    assert "faces -Y" in start and "top row first" in start and "add_box" in start
    st = load(current_id(home), home)
    assert any("left" in q["text"] and "right" in q["text"] for q in st.quiz)  # the mirror question
    assert "PASSED" in wb.answer_quiz({q["id"]: q["answer"] for q in st.quiz}).text
    with pytest.raises(AxiomError, match="vessel"):
        wb.shape_profile([[0, 0.05], [0.1, 0.05], [0.2, 0.02]], expect=["vessel.height ~= 0.2 ± 0.01"])
    res = wb.add_box("leg_front_right", [-4, -6, 0], [0, -2, 6], expect=["box.leg_front_right.max_z ~= 6 ± 0.5"])
    assert "PASS" in res.text and "CHANGED:" in res.text and "leg_front_right" in res.text
    with pytest.raises(AxiomError, match="measures something this edit changes"):
        wb.add_box("leg_front_left", [0, -6, 0], [4, -2, 6], expect=["box.leg_front_right.max_z ~= 6 ± 0.5"])
    for c in REF[1:]:
        if c["op"] == "add_box":
            wb.add_box(c["name"], c["low"], c["high"], expect=[f"box.{c['name']}.max_z ~= {c['high'][2]} ± 0.5"])
        else:
            wb.paint_face(c["box"], c["face"], c["pixels"], expect=["pixel(head, front, 3, 2) is black"])
    assert "ACCEPTANCE" in wb.check().text and "FAIL" not in wb.check().text
    done = wb.finish(claims=["model.height ~= 26 ± 0.5", "pixel(head, front, 5, 4) is black"]).text
    assert "CERTIFIED" in done and "NOT CERTIFIED" not in done


def test_bare_creeper_and_calc(home):
    wb = Workbench(home, protocol=False)
    wb.start_session(TID)
    wb.batch(REF)
    assert "26" in wb.calc("model.height").text and "18" in wb.calc("box.head.min_z").text
    report = wb.observe(views=["report"]).text
    assert "head" in report and "front" in report and "gkkggkkg" in report
    assert wb.finish().text.startswith("Session closed. Acceptance: 12/12 criteria pass.")


def test_the_guide_teaches_blocks():
    text = read_topic("blocks")
    for words in ("faces -Y", "top row first", "the viewer's left", "add_box", "paint_face", "pixel("):
        assert words in text, words
    assert "add_box" in read_topic("tools")
