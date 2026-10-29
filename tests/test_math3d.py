import numpy as np

from axiom3d.conventions import (
    TrackFrame,
    character_axes,
    track_to_world,
    world_to_track,
    zup_to_yup,
)
from axiom3d.math3d import (
    compose_xyz,
    decompose_xyz,
    heading_quat,
    matrix_to_quat,
    quat_from_axis_angle,
    quat_rotate,
    quat_slerp,
    quat_to_matrix,
)


def test_plus_x_rotation_swings_down_bone_backward():
    # The "leg goes backward" fact: +30 deg about +X moves a downward bone toward +Y.
    tip = quat_rotate(quat_from_axis_angle((1, 0, 0), 30), np.array([0, 0, -1.0]))
    assert np.allclose(tip, [0, 0.5, -np.sqrt(3) / 2], atol=1e-9)


def test_compose_decompose_roundtrip():
    rng = np.random.default_rng(0)
    for a in rng.uniform([-170, -80, -170], [170, 80, 170], (200, 3)):
        assert np.allclose(decompose_xyz(compose_xyz(*a)), a, atol=1e-6)


def test_compose_xyz_matches_matrix_product():
    q = compose_xyz(20, -35, 50)
    rx = quat_to_matrix(quat_from_axis_angle((1, 0, 0), 20))
    ry = quat_to_matrix(quat_from_axis_angle((0, 1, 0), -35))
    rz = quat_to_matrix(quat_from_axis_angle((0, 0, 1), 50))
    assert np.allclose(quat_to_matrix(q), rx @ ry @ rz, atol=1e-12)


def test_matrix_quat_roundtrip_and_slerp_endpoints():
    rng = np.random.default_rng(1)
    for _ in range(50):
        q = rng.normal(size=4)
        q /= np.linalg.norm(q)
        back = matrix_to_quat(quat_to_matrix(q))
        assert np.allclose(back, q, atol=1e-9) or np.allclose(back, -q, atol=1e-9)
    a = quat_from_axis_angle((0, 0, 1), 10)
    b = quat_from_axis_angle((1, 0, 0), 80)
    assert np.allclose(quat_slerp(a, b, 0.0), a)
    assert np.allclose(quat_slerp(a, b, 1.0), b)


def test_heading_quat_turns_left():
    assert np.allclose(quat_rotate(heading_quat(90), np.array([0, -1.0, 0])), [1, 0, 0], atol=1e-12)


def test_character_axes_heading():
    f, l, u = character_axes(0)
    assert np.allclose(f, [0, -1, 0]) and np.allclose(l, [1, 0, 0]) and np.allclose(u, [0, 0, 1])
    f, l, u = character_axes(90)
    assert np.allclose(f, [1, 0, 0], atol=1e-12) and np.allclose(l, [0, 1, 0], atol=1e-12)


def test_track_roundtrip_and_zup_to_yup():
    t = TrackFrame((0.5, 0.2), 90)
    assert np.allclose(world_to_track(t, track_to_world(t, 0.3, -0.1)), (0.3, -0.1))
    assert np.allclose(track_to_world(TrackFrame(), 1.0, 0.0), (0, -1))
    assert np.allclose(zup_to_yup((1, 2, 3)), (1, 3, -2))
