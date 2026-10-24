import copy
import dataclasses

import numpy as np
import pytest

from axiom3d.anim.commands import apply_command
from axiom3d.anim.evaluate import evaluate_clip
from axiom3d.checks.base import CheckContext, run_checks
from axiom3d.tasks.library import TASKS, get_task, new_clip
from axiom3d.tasks.reference import reference_commands


def ctx_for(skel, tid, cmds, kind=None):
    task = get_task(tid)
    clip = new_clip(task, skel)
    for c in cmds:
        clip = apply_command(skel, clip, c)
    return CheckContext(skel, clip, evaluate_clip(skel, clip), kind or task.kind)


def ids(results, severity=None):
    return {r.id for r in results if severity is None or r.severity == severity}


def plant(side, a, b, fwd=None):
    c = {"op": "plant_foot", "side": side, "start": a, "end": b}
    if fwd is not None:
        c["forward"] = fwd
    return c


def swing(side, a, b):
    return {"op": "swing_foot", "side": side, "start": a, "end": b}


@pytest.mark.parametrize("tid", list(TASKS))
def test_references_are_clean(skel, tid):
    results = run_checks(ctx_for(skel, tid, reference_commands(tid)))
    assert not ids(results, "error"), [(r.id, r.message) for r in results]
    assert "gait.arm_counter_swing" not in ids(results)


def test_results_sorted_errors_first(skel):
    cmds = [{"op": "set_pose", "frame": 12, "angles": {"left_knee.flexion": -20}}]
    results = run_checks(ctx_for(skel, "walk_forward", cmds))
    sev = [r.severity for r in results]
    assert sev == sorted(sev, key=["error", "warning", "info"].index)


def test_joint_limits_knee_hyperextension(skel):
    cmds = reference_commands("step_forward") + [{"op": "set_pose", "frame": 12, "angles": {"left_elbow.flexion": -20}}]
    res = [r for r in run_checks(ctx_for(skel, "step_forward", cmds)) if r.id == "anatomy.joint_limits"]
    assert res and res[0].severity == "error" and 12 in res[0].frames
    assert "hyperextension" in res[0].hint and "left_elbow.flexion" in res[0].message


def test_ik_unreachable(skel):
    res = run_checks(ctx_for(skel, "step_forward", [plant("left", 0, 24, 0.6)]))
    hit = [r for r in res if r.id == "anatomy.ik_unreachable"]
    # plant 0.6 m ahead of a 0.9275 m pelvis: sqrt(0.6^2 + 0.859^2) - 0.859 = 0.189 m short
    assert hit and hit[0].evidence["shortfall"] > 0.15 and "height" in hit[0].hint


def test_support_both_feet_in_air(skel):
    cmds = [
        {"op": "set_root", "frame": 0, "height": 0.9},
        plant("left", 0, 2, 0), swing("left", 2, 12), plant("left", 12, 48, 0.1),
        plant("right", 0, 2, 0), swing("right", 2, 12), plant("right", 12, 48, 0.1),
    ]
    assert "gait.support" in ids(run_checks(ctx_for(skel, "walk_forward", cmds)), "error")


def test_ground_penetration(skel):
    cmds = [{"op": "set_root", "frame": 0, "height": 0.80}]
    assert "geometry.ground_penetration" in ids(run_checks(ctx_for(skel, "step_forward", cmds)), "error")


def test_floating_for_static_pose(skel):
    cmds = [{"op": "set_root", "frame": 0, "height": 1.0}]
    assert "geometry.floating" in ids(run_checks(ctx_for(skel, "step_forward", cmds, kind="pose")), "error")
    assert "geometry.floating" not in ids(run_checks(ctx_for(skel, "step_forward", [], kind="pose")))


def test_step_direction_catches_backward_step(skel):
    cmds = [
        {"op": "set_root", "frame": 0, "height": 0.9},
        plant("right", 0, 24, 0), plant("left", 0, 6, 0), swing("left", 6, 18), plant("left", 18, 24, -0.2),
    ]
    res = [r for r in run_checks(ctx_for(skel, "step_forward", cmds)) if r.id == "gait.step_direction"]
    assert res and res[0].severity == "error"
    assert "forward = -Y at heading 0" in res[0].hint
    assert "+X raw rotation swings a downward bone toward +Y" in res[0].hint


def test_alternation(skel):
    cmds = [
        {"op": "set_root", "frame": 0, "height": 0.9},
        plant("right", 0, 48, 0),
        plant("left", 0, 3, 0), swing("left", 3, 9), plant("left", 9, 14, 0.1),
        swing("left", 14, 20), plant("left", 20, 48, 0.2),
    ]
    assert "gait.alternation" in ids(run_checks(ctx_for(skel, "walk_forward", cmds)), "error")


def test_static_arms_warn(skel):
    cmds = [c for c in reference_commands("walk_forward") if c["op"] != "set_pose"]
    res = [r for r in run_checks(ctx_for(skel, "walk_forward", cmds)) if r.id == "gait.arm_counter_swing"]
    assert res and res[0].severity == "warning"


def test_loop_continuity(skel):
    ctx = ctx_for(skel, "step_forward", reference_commands("step_forward"))
    looped = dataclasses.replace(ctx, clip=dataclasses.replace(ctx.clip, timeline=dataclasses.replace(ctx.clip.timeline, loop=True)))
    assert "gait.loop_continuity" in ids(run_checks(looped), "error")
    assert "gait.loop_continuity" not in ids(run_checks(ctx))


def test_root_progression(skel):
    cmds = [{"op": "set_root", "frame": 12, "forward": 0.2}, {"op": "set_root", "frame": 24, "forward": 0.0}]
    assert "gait.root_progression" in ids(run_checks(ctx_for(skel, "step_forward", cmds)), "error")


def _slide_right_foot(ctx, per_frame):
    states = copy.deepcopy(ctx.states)
    for s in states:
        for name in ("right_ankle", "right_heel", "right_toe"):
            s.points[name] = s.points[name] + np.array([0.0, per_frame * s.frame, 0.0])
    return dataclasses.replace(ctx, states=states)


def test_foot_slide_with_travel(skel):
    ctx = ctx_for(skel, "step_forward", reference_commands("step_forward"))
    found = ids(run_checks(_slide_right_foot(ctx, -0.003)), "error")  # drifts toward -Y, the travel direction
    assert "gait.foot_slide" in found and "gait.moonwalk" not in found


def test_moonwalk_against_travel(skel):
    ctx = ctx_for(skel, "step_forward", reference_commands("step_forward"))
    results = run_checks(_slide_right_foot(ctx, +0.003))  # drifts backward while the root goes forward
    found = ids(results, "error")
    assert "gait.moonwalk" in found and "gait.foot_slide" not in found
    hint = next(r.hint for r in results if r.id == "gait.moonwalk")
    assert "+X raw rotation swings a downward bone toward +Y" in hint


def test_step_direction_catches_naive_backswing(skel):
    # The classic error: hip "flexion" keyed negative, so the leg swings back while the root carries it forward.
    cmds = [
        {"op": "set_root", "frame": 24, "forward": 0.3},
        {"op": "set_pose", "frame": 0, "angles": {"left_hip.flexion": 0, "left_knee.flexion": 0}},
        {"op": "set_pose", "frame": 12, "angles": {"left_hip.flexion": -25, "left_knee.flexion": 40}},
        {"op": "set_pose", "frame": 24, "angles": {"left_hip.flexion": 0, "left_knee.flexion": 0}},
    ]
    res = [r for r in run_checks(ctx_for(skel, "step_forward", cmds)) if r.id == "gait.step_direction"]
    assert res and "BACKWARD relative to the pelvis" in res[0].message
    # lift-off is at frame 8 (ankle 0.42 m behind the pelvis); mid-swing it reaches 0.57 m behind
    assert res[0].evidence["backswing"] > 0.1


def test_negative_hip_flexion_hint_names_the_backward_leg(skel):
    cmds = [{"op": "set_pose", "frame": 12, "angles": {"left_hip.flexion": -30}}]
    res = [r for r in run_checks(ctx_for(skel, "step_forward", cmds)) if r.id == "anatomy.joint_limits"]
    assert res and "BACKWARD" in res[0].hint and "positive" in res[0].hint
