import numpy as np

from axiom3d.conventions import character_axes
from axiom3d.protocol.briefing import Q4_OPTIONS, grade_quiz, make_quiz
from axiom3d.rig.skeleton import forward_kinematics
from axiom3d.tasks.library import get_task, new_clip


def quiz(skel, seed, tid="step_forward"):
    return make_quiz(skel, new_clip(get_task(tid), skel), seed)


def test_five_questions_deterministic_per_seed(skel):
    a, b = quiz(skel, 7), quiz(skel, 7)
    assert [q.id for q in a] == ["q1", "q2", "q3", "q4", "q5"]
    assert a == b


def test_varies_across_seeds(skel):
    texts = {(quiz(skel, s)[2].text, quiz(skel, s)[4].text) for s in range(6)}
    assert len(texts) > 1


def test_facing_and_left_answers(skel):
    q = quiz(skel, 1)
    assert q[0].answer == "-Y" and q[1].answer == "+X"


def test_correct_answers_pass_and_wrong_fail(skel):
    q = quiz(skel, 3)
    assert grade_quiz(q, {x.id: x.answer for x in q}).passed
    answers = {x.id: x.answer for x in q}
    answers["q1"] = "+Y"
    res = grade_quiz(q, answers)
    assert not res.passed
    q1 = next(r for r in res.results if r[0] == "q1")
    assert q1[1] is False and q[0].explanation in q1[2]
    assert all(r[1] for r in res.results if r[0] != "q1")


def test_answer_normalisation(skel):
    q = quiz(skel, 4)
    loose = {"q1": "−y", "q2": " x ", "q3": q[2].answer.replace("_", " "),
             "q4": {"front": "forward", "back": "backward", "left": "Left", "right": "RIGHT"}[q[3].answer],
             "q5": str(round(float(q[4].answer), 2))}
    assert grade_quiz(q, loose).passed
    assert not grade_quiz(q, {}).passed


def test_q4_answers_match_independent_fk(skel):
    rest_root = np.array([0, 0, skel.dims["pelvis_height"]])
    _, rest = forward_kinematics(skel, rest_root, 0, {})
    expected = {}
    for channel, angle, point in Q4_OPTIONS:
        joint, dof = channel.split(".")
        _, moved = forward_kinematics(skel, rest_root, 0, {joint: skel.angles_to_quat(joint, {dof: angle})})
        f, l, _ = character_axes(0)
        d = moved[point] - rest[point]
        fw, lf = d @ f, d @ l
        expected[channel] = ("front" if fw > 0 else "back") if abs(fw) >= abs(lf) else ("left" if lf > 0 else "right")
    seen = set()
    for seed in range(60):
        q4 = quiz(skel, seed)[3]
        channel = next(c for c, _, _ in Q4_OPTIONS if c in q4.text)
        assert q4.answer == expected[channel], channel
        seen.add(channel)
    assert seen == {c for c, _, _ in Q4_OPTIONS}


def test_q5_is_sine(skel):
    q5 = quiz(skel, 9)[4]
    theta = float(q5.text.split("+")[1].split(" ")[0])
    assert np.isclose(float(q5.answer), np.sin(np.radians(theta)), atol=0.005)
