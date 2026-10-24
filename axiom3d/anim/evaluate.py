"""Evaluate a clip at a frame: keys, then foot constraints solved live with IK."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from axiom3d.anim.clip import Clip
from axiom3d.rig.ik import LegIKResult, solve_leg
from axiom3d.rig.skeleton import forward_kinematics

LEG_JOINTS = ("hip", "knee", "ankle")


@dataclass
class FrameState:
    frame: int
    root_position: np.ndarray
    heading_deg: float
    rotations: dict[str, np.ndarray]
    joint_world: dict[str, tuple[np.ndarray, np.ndarray]]
    points: dict[str, np.ndarray]
    angles: dict[str, float]
    leg_modes: dict[str, str]
    ik: dict[str, LegIKResult | None]
    notes: list[str] = field(default_factory=list)


def _leg_target(skel, clip: Clip, side: str, frame: int, notes: list[str]):
    ankle_h = skel.dims["ankle_height"]
    for p in clip.plants:
        if p.side == side and p.start <= frame <= p.end:
            return "plant", np.array([*p.xy, ankle_h])
    for s in clip.swings:
        if s.side == side and s.start <= frame <= s.end:
            before = [p for p in clip.plants if p.side == side and p.end <= s.start]
            after = [p for p in clip.plants if p.side == side and p.start >= s.end]
            if not before or not after:
                missing = "before" if not before else "after"
                notes.append(f"{side} swing {s.start}-{s.end} has no plant {missing}; using keys")
                return "keys", None
            a = max(before, key=lambda p: p.end).xy
            b = min(after, key=lambda p: p.start).xy
            t = (frame - s.start) / (s.end - s.start)
            xy = np.asarray(a) + t * (np.asarray(b) - np.asarray(a))
            return "swing", np.array([*xy, ankle_h + s.apex_m * 4 * t * (1 - t)])
    return "keys", None


def evaluate_frame(skel, clip: Clip, frame: int) -> FrameState:
    position, heading = clip.root_at(frame, skel.dims["pelvis_height"])
    keyed = clip.keyed_channels()
    rotations = {
        name: skel.angles_to_quat(name, {d.name: clip.channel_at(f"{name}.{d.name}", frame) for d in joint.dofs})
        for name, joint in skel.joints.items()
    }
    notes: list[str] = []
    modes: dict[str, str] = {}
    iks: dict[str, LegIKResult | None] = {}
    for side in ("left", "right"):
        mode, target = _leg_target(skel, clip, side, frame, notes)
        modes[side], iks[side] = mode, None
        if target is None:
            continue
        ik = solve_leg(skel, side, position, heading, target)
        iks[side] = ik
        rotations[f"{side}_hip"] = ik.hip_local
        rotations[f"{side}_knee"] = skel.angles_to_quat(f"{side}_knee", {"flexion": ik.knee_flexion_deg})
        rotations[f"{side}_ankle"] = skel.angles_to_quat(f"{side}_ankle", {"dorsiflexion": ik.ankle_dorsiflexion_deg})
        for joint in LEG_JOINTS:
            for d in skel.joints[f"{side}_{joint}"].dofs:
                channel = f"{side}_{joint}.{d.name}"
                if channel in keyed:
                    notes.append(f"{channel} keys ignored at frame {frame}: {side} leg is driven by {mode}")
    joint_world, points = forward_kinematics(skel, position, heading, rotations)
    for name, p in points.items():
        if not np.all(np.isfinite(p)):
            raise RuntimeError(f"non-finite position for {name} at frame {frame}")
    angles = {
        f"{name}.{dof}": value
        for name, joint in skel.joints.items()
        if joint.dofs
        for dof, value in skel.quat_to_angles(name, rotations[name]).items()
    }
    return FrameState(frame, position, heading, rotations, joint_world, points, angles, modes, iks, notes)


def evaluate_clip(skel, clip: Clip) -> list[FrameState]:
    tl = clip.timeline
    return [evaluate_frame(skel, clip, f) for f in range(tl.start, tl.end + 1)]
