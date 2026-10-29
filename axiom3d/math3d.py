"""Quaternion and rotation helpers.

Quaternions are numpy arrays (w, x, y, z). Angles are degrees.
"""

from __future__ import annotations

import numpy as np

_AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}
IDENTITY = np.array([1.0, 0.0, 0.0, 0.0])


def quat_normalize(q) -> np.ndarray:
    q = np.asarray(q, dtype=float)
    n = np.linalg.norm(q)
    return IDENTITY.copy() if n < 1e-15 else q / n


def quat_from_axis_angle(axis, deg: float) -> np.ndarray:
    if isinstance(axis, str):
        axis = _AXES[axis]
    a = np.asarray(axis, dtype=float)
    a = a / np.linalg.norm(a)
    half = np.radians(deg) / 2.0
    return np.concatenate(([np.cos(half)], np.sin(half) * a))


def quat_mul(a, b) -> np.ndarray:
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return quat_normalize(
        [
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        ]
    )


def quat_conj(q) -> np.ndarray:
    return np.array([q[0], -q[1], -q[2], -q[3]], dtype=float)


def quat_to_matrix(q) -> np.ndarray:
    w, x, y, z = quat_normalize(q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
        ]
    )


def quat_rotate(q, v) -> np.ndarray:
    return quat_to_matrix(q) @ np.asarray(v, dtype=float)


def matrix_to_quat(m) -> np.ndarray:
    m = np.asarray(m, dtype=float)
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = 2.0 * np.sqrt(tr + 1.0)
        q = [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = 2.0 * np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2])
        q = [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
    elif m[1, 1] > m[2, 2]:
        s = 2.0 * np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2])
        q = [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
    else:
        s = 2.0 * np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1])
        q = [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]
    q = quat_normalize(q)
    return q if q[0] >= 0 else -q


def quat_slerp(a, b, t: float) -> np.ndarray:
    a = quat_normalize(a)
    b = quat_normalize(b)
    dot = float(np.dot(a, b))
    if dot < 0:
        b, dot = -b, -dot
    if dot > 0.9995:
        return quat_normalize(a + t * (b - a))
    theta = np.arccos(dot)
    return quat_normalize((np.sin((1 - t) * theta) * a + np.sin(t * theta) * b) / np.sin(theta))


def compose_xyz(ax: float, ay: float, az: float) -> np.ndarray:
    """Rotation R = Rx(ax) @ Ry(ay) @ Rz(az)."""
    return quat_mul(
        quat_mul(quat_from_axis_angle("x", ax), quat_from_axis_angle("y", ay)),
        quat_from_axis_angle("z", az),
    )


def decompose_xyz(q) -> tuple[float, float, float]:
    """Inverse of compose_xyz."""
    r = quat_to_matrix(q)
    ay = np.arcsin(np.clip(r[0, 2], -1.0, 1.0))
    ax = np.arctan2(-r[1, 2], r[2, 2])
    az = np.arctan2(-r[0, 1], r[0, 0])
    return float(np.degrees(ax)), float(np.degrees(ay)), float(np.degrees(az))


def heading_quat(deg: float) -> np.ndarray:
    """Rotation about +Z; positive turns the character left."""
    return quat_from_axis_angle("z", deg)
