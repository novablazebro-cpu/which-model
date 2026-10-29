"""Joints with anatomical degrees of freedom, and forward kinematics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from axiom3d.math3d import IDENTITY, compose_xyz, decompose_xyz, heading_quat, quat_mul, quat_rotate

Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class Dof:
    """One anatomical degree of freedom.

    A positive anatomical angle is a rotation of `sign * angle` about the
    parent-frame principal `axis`.
    """

    name: str
    axis: Literal["x", "y", "z"]
    sign: int
    min_deg: float
    max_deg: float


@dataclass(frozen=True)
class Joint:
    name: str
    parent: str | None
    offset: Vec3  # rest position relative to the parent joint, in the parent's frame
    dofs: tuple[Dof, ...] = ()


@dataclass(frozen=True)
class Segment:
    """A rigid body part drawn in its joint's rest frame.

    capsule: from `a` to `b` with `radius`. sphere: centre `a`, `radius`.
    box: centre `a`, full extents `size`.
    """

    name: str
    joint: str
    kind: Literal["capsule", "box", "sphere"]
    a: Vec3
    b: Vec3
    radius: float
    size: Vec3 | None
    side: Literal["left", "right", "center"]


@dataclass
class Skeleton:
    height: float
    joints: dict[str, Joint]  # parents before children
    extra_points: dict[str, tuple[str, Vec3]]
    segments: list[Segment]
    dims: dict[str, float]

    def channels(self) -> list[str]:
        return [f"{j.name}.{d.name}" for j in self.joints.values() for d in j.dofs]

    def dof(self, channel: str) -> Dof:
        joint, _, name = channel.partition(".")
        if joint in self.joints:
            for d in self.joints[joint].dofs:
                if d.name == name:
                    return d
        raise KeyError(channel)

    def angles_to_quat(self, joint: str, angles: dict[str, float]) -> np.ndarray:
        per_axis = {"x": 0.0, "y": 0.0, "z": 0.0}
        for d in self.joints[joint].dofs:
            per_axis[d.axis] += d.sign * float(angles.get(d.name, 0.0))
        return compose_xyz(per_axis["x"], per_axis["y"], per_axis["z"])

    def quat_to_angles(self, joint: str, q) -> dict[str, float]:
        ax, ay, az = decompose_xyz(q)
        per_axis = {"x": ax, "y": ay, "z": az}
        return {d.name: d.sign * per_axis[d.axis] for d in self.joints[joint].dofs}

    def point_names(self) -> list[str]:
        return list(self.joints) + list(self.extra_points)


def forward_kinematics(
    skel: Skeleton, root_position, heading_deg: float, rotations: dict[str, np.ndarray]
) -> tuple[dict[str, tuple[np.ndarray, np.ndarray]], dict[str, np.ndarray]]:
    """World (position, rotation) per joint, and world position per named point."""
    joint_world: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for name, joint in skel.joints.items():
        local = rotations.get(name, IDENTITY)
        if joint.parent is None:
            pos = np.asarray(root_position, dtype=float)
            rot = quat_mul(heading_quat(heading_deg), local)
        else:
            ppos, prot = joint_world[joint.parent]
            pos = ppos + quat_rotate(prot, joint.offset)
            rot = quat_mul(prot, local)
        joint_world[name] = (pos, rot)
    points = {name: pos.copy() for name, (pos, _) in joint_world.items()}
    for name, (joint, offset) in skel.extra_points.items():
        pos, rot = joint_world[joint]
        points[name] = pos + quat_rotate(rot, offset)
    return joint_world, points
