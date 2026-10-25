from axiom3d.anim.commands import apply_command
from axiom3d.anim.evaluate import evaluate_clip
from axiom3d.perceive.diff import describe_diff
from axiom3d.tasks.library import get_task, new_clip


def build(skel, cmds, tid="step_forward"):
    clip = new_clip(get_task(tid), skel)
    for c in cmds:
        clip = apply_command(skel, clip, c)
    return clip, evaluate_clip(skel, clip)


def diff(skel, before_cmds, extra, frame=24, limit=12):
    return describe_diff(skel, "step", build(skel, before_cmds), build(skel, before_cmds + extra), frame, limit)


def test_plant_reports_moved_ankle_and_new_error(skel):
    lines = diff(skel, [], [{"op": "plant_foot", "side": "left", "start": 0, "end": 24, "forward": 0.36}])
    assert lines[0] == "CHANGED:"
    # The plant is out of reach from the standing pelvis: the diff shows where the foot really got to.
    assert any("left_ankle forward +0.000 → +0.332" in l for l in lines)
    assert any(l.strip().startswith("checks:") and "NEW anatomy.ik_unreachable" in l for l in lines)


def test_noop_is_nothing_measurable(skel):
    assert diff(skel, [], [{"op": "set_pose", "frame": 0, "angles": {"left_shoulder.flexion": 0}}]) == [
        "CHANGED: nothing measurable"]


def test_channel_change_and_fixed_error(skel):
    bad = [{"op": "set_pose", "frame": 24, "angles": {"left_knee.flexion": -20}}]
    lines = diff(skel, [], bad)
    assert any("left_knee.flexion -0.0 → -20.0" in l or "left_knee.flexion +0.0 → -20.0" in l for l in lines)
    assert any("NEW anatomy.joint_limits" in l for l in lines)
    fixed = describe_diff(skel, "step", build(skel, bad), build(skel, []), 24, 12)
    assert any("FIXED anatomy.joint_limits" in l for l in fixed)


def test_largest_change_elsewhere(skel):
    lines = diff(skel, [], [{"op": "set_pose", "frame": 12, "angles": {"left_shoulder.flexion": 60}}], frame=0)
    assert any(l.strip().startswith("largest change at frame 12: left_hand") for l in lines)


def test_limit_truncates(skel):
    lines = diff(skel, [], [{"op": "set_root", "frame": 24, "heading": 90}], limit=3)
    assert len(lines) == 5 and lines[-1].strip().startswith("(+") and lines[-1].strip().endswith("more)")
