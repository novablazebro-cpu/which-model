import numpy as np

from axiom3d.rig.ik import solve_leg
from axiom3d.rig.skeleton import forward_kinematics


def fk_leg(skel, side, res, pelvis, heading):
    rotations = {
        f"{side}_hip": res.hip_local,
        f"{side}_knee": skel.angles_to_quat(f"{side}_knee", {"flexion": res.knee_flexion_deg}),
        f"{side}_ankle": skel.angles_to_quat(f"{side}_ankle", {"dorsiflexion": res.ankle_dorsiflexion_deg}),
    }
    return forward_kinematics(skel, pelvis, heading, rotations)[1]


def test_reaches_target_in_front(skel):
    pel = np.array([0, 0, 0.89])
    tgt = np.array([0.0875, -0.2, skel.dims["ankle_height"]])
    r = solve_leg(skel, "left", pel, 0, tgt)
    p = fk_leg(skel, "left", r, pel, 0)
    assert r.reached and r.shortfall_m == 0
    assert np.allclose(p["left_ankle"], tgt, atol=1e-6)
    assert abs(p["left_heel"][2]) < 0.005 and abs(p["left_toe"][2]) < 0.005
    assert p["left_knee"][1] < p["left_hip"][1]
    assert r.knee_flexion_deg > 5


def test_reaches_target_behind(skel):
    pel = np.array([0, 0, 0.89])
    tgt = np.array([-0.0875, 0.2, skel.dims["ankle_height"]])
    r = solve_leg(skel, "right", pel, 0, tgt)
    p = fk_leg(skel, "right", r, pel, 0)
    assert r.reached and np.allclose(p["right_ankle"], tgt, atol=1e-6)
    assert abs(p["right_toe"][2]) < 0.005


def test_knee_points_along_heading_90(skel):
    pel = np.array([0, 0, 0.85])
    tgt = np.array([0.0, 0.0875, skel.dims["ankle_height"]])
    r = solve_leg(skel, "left", pel, 90, tgt)
    p = fk_leg(skel, "left", r, pel, 90)
    assert r.reached and np.allclose(p["left_ankle"], tgt, atol=1e-6)
    assert p["left_knee"][0] > p["left_hip"][0] + 0.02


def test_unreachable_reports_shortfall(skel):
    r = solve_leg(skel, "left", np.array([0, 0, 0.89]), 0, np.array([0.0875, -2.0, 0.07]))
    assert not r.reached and r.shortfall_m > 1.0
    assert np.all(np.isfinite(r.hip_local)) and np.isfinite(r.knee_flexion_deg)


def test_target_at_hip_is_finite(skel):
    pel = np.array([0, 0, 0.89])
    hip = pel + np.array([skel.dims["hip_half_width"], 0, 0])
    r = solve_leg(skel, "left", pel, 0, hip)
    assert not r.reached
    assert np.all(np.isfinite(r.hip_local)) and np.isfinite(r.knee_flexion_deg) and np.isfinite(r.ankle_dorsiflexion_deg)


def test_straight_down_rest_is_reached(skel):
    pel = np.array([0, 0, skel.dims["pelvis_height"]])
    tgt = np.array([skel.dims["hip_half_width"], 0, skel.dims["ankle_height"]])
    r = solve_leg(skel, "left", pel, 0, tgt)
    assert r.reached and abs(r.knee_flexion_deg) < 0.1
    assert abs(skel.quat_to_angles("left_hip", r.hip_local)["flexion"]) < 0.1
