"""Analytic two-bone leg IK: the tool computes the angles so the model doesn't have to."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from axiom3d.conventions import character_axes
from axiom3d.math3d import heading_quat, matrix_to_quat, quat_conj, quat_mul, quat_rotate


@dataclass
class LegIKResult:
    hip_local: np.ndarray
    knee_flexion_deg: float
    ankle_dorsiflexion_deg: float
    reached: bool
    shortfall_m: float


def _unit(v) -> np.ndarray:
    return v / np.linalg.norm(v)


def solve_leg(skel, side: str, pelvis_position, heading_deg: float, ankle_target) -> LegIKResult:
    """Place the ankle at `ankle_target` with the knee aimed along the facing and the foot flat."""
    a, b = skel.dims["thigh"], skel.dims["shank"]
    knee = skel.dof(f"{side}_knee.flexion")
    ankle = skel.dof(f"{side}_ankle.dorsiflexion")
    heading = heading_quat(heading_deg)
    forward, left, _ = character_axes(heading_deg)

    hip = np.asarray(pelvis_position, dtype=float) + quat_rotate(heading, skel.joints[f"{side}_hip"].offset)
    d = np.asarray(ankle_target, dtype=float) - hip
    dist = float(np.linalg.norm(d))
    direction = d / dist if dist > 1e-9 else np.array([0.0, 0.0, -1.0])

    # The knee flexion limit sets the closest reachable target; full extension the farthest.
    min_dist = float(np.sqrt(a * a + b * b - 2 * a * b * np.cos(np.radians(180 - knee.max_deg))))
    max_dist = a + b
    reached = min_dist - 1e-6 <= dist <= max_dist + 1e-6
    shortfall = max(0.0, dist - max_dist, min_dist - dist)
    length = float(np.clip(dist, min_dist, max_dist))

    pole = forward - (forward @ direction) * direction
    if np.linalg.norm(pole) < 1e-6:
        pole = np.cross(direction, left)
    pole = _unit(pole)

    alpha = np.arccos(np.clip((a * a + length * length - b * b) / (2 * a * length), -1.0, 1.0))
    thigh_dir = np.cos(alpha) * direction + np.sin(alpha) * pole
    knee_forward = -np.sin(alpha) * direction + np.cos(alpha) * pole
    x_axis = np.cross(knee_forward, thigh_dir)
    hip_world = matrix_to_quat(np.column_stack([x_axis, -knee_forward, -thigh_dir]))
    hip_local = quat_mul(quat_conj(heading), hip_world)

    interior = np.arccos(np.clip((a * a + b * b - length * length) / (2 * a * b), -1.0, 1.0))
    knee_flexion = float(np.clip(180.0 - np.degrees(interior), knee.min_deg, knee.max_deg))

    knee_world = quat_mul(hip_world, skel.angles_to_quat(f"{side}_knee", {"flexion": knee_flexion}))
    q = quat_mul(quat_conj(knee_world), heading)
    twist_about_x = np.degrees(2.0 * np.arctan2(q[1], q[0]))
    twist_about_x = (twist_about_x + 180.0) % 360.0 - 180.0
    dorsiflexion = float(np.clip(ankle.sign * twist_about_x, ankle.min_deg, ankle.max_deg))

    return LegIKResult(hip_local, knee_flexion, dorsiflexion, bool(reached), float(shortfall))
