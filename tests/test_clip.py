import numpy as np
import pytest

from axiom3d.anim.clip import Clip, Timeline
from axiom3d.anim.commands import CommandError, apply_command
from axiom3d.anim.evaluate import evaluate_clip, evaluate_frame
from axiom3d.conventions import TrackFrame
from axiom3d.rig.skeleton import forward_kinematics
from axiom3d.tasks.reference import reference_commands


def make(skel, cmds, end=24):
    clip = Clip(Timeline(end=end), TrackFrame())
    for c in cmds:
        clip = apply_command(skel, clip, c)
    return clip


def test_no_keys_is_rest_pose(skel):
    _, rest = forward_kinematics(skel, np.array([0, 0, skel.dims["pelvis_height"]]), 0, {})
    for st in evaluate_clip(skel, make(skel, [])):
        for name, p in rest.items():
            assert np.allclose(st.points[name], p, atol=1e-9)
        assert set(st.leg_modes.values()) == {"keys"}


def test_root_linear_and_hold(skel):
    clip = make(skel, [{"op": "set_root", "frame": 0, "forward": 0}, {"op": "set_root", "frame": 24, "forward": 1}])
    assert np.isclose(evaluate_frame(skel, clip, 12).root_position[1], -0.5)
    assert np.isclose(evaluate_frame(skel, clip, 24).root_position[1], -1.0)
    with pytest.raises(CommandError, match="0..24"):
        apply_command(skel, clip, {"op": "set_root", "frame": 30, "forward": 1})


def test_channels_start_from_rest(skel):
    # A key after the start ramps from the rest value instead of holding backward.
    clip = make(skel, [{"op": "set_root", "frame": 12, "heading": 90},
                       {"op": "set_pose", "frame": 12, "angles": {"left_hip.flexion": 30}}])
    assert evaluate_frame(skel, clip, 0).heading_deg == 0
    assert np.isclose(evaluate_frame(skel, clip, 6).heading_deg, 45)
    assert np.isclose(evaluate_frame(skel, clip, 6).angles["left_hip.flexion"], 15)
    assert np.isclose(evaluate_frame(skel, clip, 20).heading_deg, 90)


def test_root_keys_are_order_independent(skel):
    # Height-only keys must not pin forward/left (review I7): order of set_root calls can't change the motion.
    cmds = reference_commands("step_forward")
    roots = [c for c in cmds if c["op"] == "set_root"]
    bob_first = [c for c in roots if "forward" not in c] + [c for c in roots if "forward" in c]
    reordered = bob_first + [c for c in cmds if c["op"] != "set_root"]
    a, b = evaluate_clip(skel, make(skel, cmds)), evaluate_clip(skel, make(skel, reordered))
    for sa, sb in zip(a, b):
        assert np.allclose(sa.root_position, sb.root_position, atol=1e-9), sa.frame


def test_set_root_keeps_unspecified_fields(skel):
    clip = make(skel, [{"op": "set_root", "frame": 24, "forward": 0.5}, {"op": "set_root", "frame": 24, "height": 0.8}])
    st = evaluate_frame(skel, clip, 24)
    assert np.allclose(st.root_position, [0, -0.5, 0.8])


def test_channel_linear(skel):
    clip = make(skel, [
        {"op": "set_pose", "frame": 0, "angles": {"left_hip.flexion": 0}},
        {"op": "set_pose", "frame": 10, "angles": {"left_hip.flexion": "30"}},
    ])
    assert np.isclose(evaluate_frame(skel, clip, 5).angles["left_hip.flexion"], 15)
    assert np.isclose(evaluate_frame(skel, clip, 20).angles["left_hip.flexion"], 30)


def test_plant_never_slides(skel):
    clip = make(skel, [
        {"op": "set_root", "frame": 0, "height": 0.89},
        {"op": "set_root", "frame": 24, "forward": 0.2, "height": 0.89},
        {"op": "plant_foot", "side": "left", "start": 0, "end": 24},
    ])
    states = evaluate_clip(skel, clip)
    xy = np.array([s.points["left_ankle"][:2] for s in states])
    assert np.allclose(xy, xy[0], atol=1e-9)
    assert np.allclose(xy[0], [skel.dims["hip_half_width"], 0])
    assert all(s.leg_modes["left"] == "plant" and s.ik["left"].reached for s in states)


def test_swing_arc(skel):
    clip = make(skel, reference_commands("step_forward"))
    ah = skel.dims["ankle_height"]
    mid = evaluate_frame(skel, clip, 12)
    assert mid.leg_modes["left"] == "swing"
    assert np.isclose(mid.points["left_ankle"][2], ah + 0.08, atol=1e-6)
    assert np.allclose(evaluate_frame(skel, clip, 6).points["left_ankle"][:2], [0.0875, 0], atol=1e-6)
    assert np.allclose(evaluate_frame(skel, clip, 18).points["left_ankle"][:2], [0.0875, -0.36], atol=1e-6)


def test_swing_without_plant_notes_and_uses_keys(skel):
    clip = make(skel, [{"op": "swing_foot", "side": "left", "start": 6, "end": 18}])
    st = evaluate_frame(skel, clip, 12)
    assert st.leg_modes["left"] == "keys"
    assert any("no plant" in n for n in st.notes)


def test_plant_overrides_leg_keys_with_note(skel):
    clip = make(skel, [
        {"op": "set_pose", "frame": 0, "angles": {"left_knee.flexion": 40}},
        {"op": "plant_foot", "side": "left", "start": 0, "end": 24},
    ])
    st = evaluate_frame(skel, clip, 0)
    assert abs(st.angles["left_knee.flexion"]) < 0.5
    assert any("left_knee.flexion" in n for n in st.notes)


def test_overlapping_plants_rejected(skel):
    clip = make(skel, [{"op": "plant_foot", "side": "left", "start": 0, "end": 10}])
    with pytest.raises(CommandError, match="overlap"):
        apply_command(skel, clip, {"op": "plant_foot", "side": "left", "start": 10, "end": 20, "forward": 0.3})


def test_plant_and_swing_may_share_endpoint(skel):
    make(skel, [
        {"op": "plant_foot", "side": "left", "start": 0, "end": 6},
        {"op": "swing_foot", "side": "left", "start": 6, "end": 18},
    ])


def test_zero_length_swing_rejected(skel):
    with pytest.raises(CommandError):
        make(skel, [{"op": "swing_foot", "side": "left", "start": 6, "end": 6}])


def test_bad_values_rejected(skel):
    with pytest.raises(CommandError, match="number"):
        make(skel, [{"op": "set_pose", "frame": 0, "angles": {"left_hip.flexion": "abc"}}])
    with pytest.raises(CommandError, match="side"):
        make(skel, [{"op": "plant_foot", "side": "middle", "start": 0, "end": 4}])
    with pytest.raises(CommandError, match="op"):
        make(skel, [{"op": "teleport"}])
    with pytest.raises(CommandError, match="apex"):
        make(skel, [{"op": "swing_foot", "side": "left", "start": 0, "end": 4, "apex": 2}])


def test_unknown_channel_lists_valid(skel):
    with pytest.raises(CommandError, match="left_hip.flexion"):
        make(skel, [{"op": "set_pose", "frame": 0, "angles": {"hip_left": 10}}])


@pytest.mark.parametrize("tid,end", [("step_forward", 24), ("walk_forward", 48), ("turn_then_step", 36)])
def test_reference_commands_apply_and_evaluate(skel, tid, end):
    states = evaluate_clip(skel, make(skel, reference_commands(tid), end=end))
    assert len(states) == end + 1
    for s in states:
        assert all(np.all(np.isfinite(p)) for p in s.points.values())


def test_keyed_angles_reported_as_keyed_past_gimbal(skel):
    # Review I6: abduction is the middle Euler axis; past 90 deg a decomposition flips to an equivalent triple.
    clip = make(skel, [{"op": "set_pose", "frame": 0, "angles": {"left_shoulder.abduction": 120}}])
    st = evaluate_frame(skel, clip, 0)
    assert np.isclose(st.angles["left_shoulder.abduction"], 120)
    assert np.isclose(st.angles["left_shoulder.flexion"], 0) and np.isclose(st.angles["left_shoulder.internal_rotation"], 0)
    assert st.points["left_hand"][2] > st.points["left_shoulder"][2]  # the arm really is raised above shoulder height
