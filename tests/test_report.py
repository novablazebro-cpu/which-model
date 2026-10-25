import pytest

from axiom3d.anim.commands import apply_command
from axiom3d.anim.evaluate import evaluate_clip
from axiom3d.perceive.report import describe_frame, describe_timeline
from axiom3d.tasks.library import get_task, new_clip
from axiom3d.tasks.reference import reference_commands


def solve(skel, tid, cmds):
    clip = new_clip(get_task(tid), skel)
    for c in cmds:
        clip = apply_command(skel, clip, c)
    return clip, evaluate_clip(skel, clip)


@pytest.fixture(scope="module")
def step(skel):
    return solve(skel, "step_forward", reference_commands("step_forward"))


def line_for(text, name):
    return next(l for l in text.splitlines() if l.startswith(name + " "))


def test_report_semantics(skel, step):
    clip, states = step
    text = describe_frame(skel, clip, states[24])
    toe = line_for(text, "left_toe")
    assert "IN FRONT of pelvis" in toe and "ON ground" in toe and "LEFT by" in toe
    assert "Heading 0" in text and "frame 24" in text


def test_report_behind(skel):
    clip, states = solve(skel, "step_forward", [{"op": "set_pose", "frame": 0, "angles": {"left_knee.flexion": 60}}])
    heel = line_for(describe_frame(skel, clip, states[0]), "left_heel")
    assert "BEHIND pelvis" in heel and "ON ground" not in heel


def test_report_angles_and_limits(skel):
    clip, states = solve(skel, "step_forward", [{"op": "set_pose", "frame": 0, "angles": {"left_hip.flexion": 60}}])
    hip = line_for(describe_frame(skel, clip, states[0]), "left_hip.flexion")
    assert "+60.0" in hip and "limit -20..120" in hip and "50%" in hip


def test_timeline_support_column(skel, step):
    clip, states = step
    rows = {int(l.split()[0]): l.split() for l in describe_timeline(skel, clip, states, stride=1).splitlines()[1:]}
    assert rows[12][-1] == "R" and rows[0][-1] == "LR"
