import numpy as np

from axiom3d.mesh import segment_mesh
from axiom3d.rig.skeleton import forward_kinematics

H = 1.75


def pts(skel, angles, heading=0.0):
    rotations = {j: skel.angles_to_quat(j, a) for j, a in angles.items()}
    _, points = forward_kinematics(skel, np.array([0, 0, 0.530 * H]), heading, rotations)
    return points


def test_rest_pose_feet_on_ground_head_at_height(skel):
    p = pts(skel, {})
    assert abs(p["left_heel"][2]) < 1e-9 and abs(p["right_toe"][2]) < 1e-9
    assert np.isclose(p["head_top"][2], H)


def test_hip_flexion_moves_toe_forward(skel):
    assert pts(skel, {"left_hip": {"flexion": 30}})["left_toe"][1] < pts(skel, {})["left_toe"][1] - 0.2


def test_knee_flexion_moves_ankle_behind_knee(skel):
    p = pts(skel, {"left_knee": {"flexion": 45}})
    assert p["left_ankle"][1] > p["left_knee"][1] + 0.1


def test_elbow_and_knee_bend_opposite_ways(skel):
    p = pts(skel, {"left_elbow": {"flexion": 90}})
    assert p["left_wrist"][1] < p["left_elbow"][1] - 0.1


def test_abduction_mirrors(skel):
    p = pts(skel, {"left_hip": {"abduction": 20}, "right_hip": {"abduction": 20}})
    r = pts(skel, {})
    assert p["left_ankle"][0] > r["left_ankle"][0] + 0.1
    assert p["right_ankle"][0] < r["right_ankle"][0] - 0.1


def test_internal_rotation_turns_toes_to_midline(skel):
    p = pts(skel, {"left_hip": {"internal_rotation": 20}, "right_hip": {"internal_rotation": 20}})
    r = pts(skel, {})
    assert p["left_toe"][0] < r["left_toe"][0] - 0.01
    assert p["right_toe"][0] > r["right_toe"][0] + 0.01


def test_shoulder_flexion_moves_hand_forward(skel):
    assert pts(skel, {"right_shoulder": {"flexion": 40}})["right_hand"][1] < -0.2


def test_spine_flexion_and_twist(skel):
    assert pts(skel, {"spine": {"flexion": 30}})["head_top"][1] < -0.3
    assert pts(skel, {"spine": {"twist": 20}})["left_shoulder"][1] > 0.05


def test_spine_lateral_bend_left(skel):
    # Pivot is the spine joint, 0.41H below head_top: 0.7175 * sin(20) = 0.245 toward +X (left).
    assert pts(skel, {"spine": {"lateral_bend": 20}})["head_top"][0] > 0.2


def test_ankle_dorsiflexion_lifts_toes(skel):
    assert pts(skel, {"left_ankle": {"dorsiflexion": 15}})["left_toe"][2] > 0.03


def test_heading_90_faces_plus_x(skel):
    p = pts(skel, {}, heading=90)
    assert p["left_toe"][0] > p["pelvis"][0] + 0.1
    assert p["left_hip"][1] > 0.05


def test_angles_quat_roundtrip(skel):
    rng = np.random.default_rng(3)
    for name, joint in skel.joints.items():
        for _ in range(20):
            angles = {d.name: rng.uniform(max(d.min_deg, -60), min(d.max_deg, 60)) for d in joint.dofs}
            back = skel.quat_to_angles(name, skel.angles_to_quat(name, angles))
            for k, v in angles.items():
                assert abs(back[k] - v) < 1e-6, (name, k)


def test_channels_and_dims(skel):
    ch = skel.channels()
    assert "left_hip.flexion" in ch and "right_knee.flexion" in ch and "spine.twist" in ch
    assert len(skel.joints) == 14
    assert np.isclose(skel.dims["thigh"] + skel.dims["shank"] + skel.dims["ankle_height"], skel.dims["pelvis_height"])
    assert skel.dof("left_knee.flexion").min_deg == 0


def test_segment_meshes_valid(skel):
    assert skel.segments
    for seg in skel.segments:
        m = segment_mesh(seg)
        assert m.faces.max() < len(m.vertices) and np.all(np.isfinite(m.vertices))
        assert seg.side in ("left", "right", "center")
