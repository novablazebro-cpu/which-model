"""The mannequin: a 14-joint humanoid with Winter's anthropometric proportions."""

from __future__ import annotations

from axiom3d.rig.skeleton import Dof, Joint, Segment, Skeleton

# Positive angle = the anatomical motion; signs follow the spec's anatomy table.
_SIDE_SIGN = {"left": -1, "right": +1}


def _hip_dofs(side: str) -> tuple[Dof, ...]:
    s = _SIDE_SIGN[side]
    return (
        Dof("flexion", "x", -1, -20, 120),
        Dof("abduction", "y", s, -30, 45),
        Dof("internal_rotation", "z", s, -40, 40),
    )


def _shoulder_dofs(side: str) -> tuple[Dof, ...]:
    s = _SIDE_SIGN[side]
    return (
        Dof("flexion", "x", -1, -50, 180),
        Dof("abduction", "y", s, -30, 180),
        Dof("internal_rotation", "z", s, -70, 90),
    )


def _trunk_dofs(flex: tuple[float, float], bend: float, twist: float) -> tuple[Dof, ...]:
    return (
        Dof("flexion", "x", +1, *flex),
        Dof("lateral_bend", "y", +1, -bend, bend),
        Dof("twist", "z", +1, -twist, twist),
    )


def build_mannequin(height: float = 1.75) -> Skeleton:
    h = height
    joints = [
        Joint("pelvis", None, (0.0, 0.0, 0.530 * h)),
        Joint("spine", "pelvis", (0.0, 0.0, 0.06 * h), _trunk_dofs((-30, 80), 35, 45)),
        Joint("neck", "spine", (0.0, 0.0, 0.228 * h), _trunk_dofs((-60, 70), 45, 70)),
        Joint("head", "neck", (0.0, 0.0, 0.052 * h)),
    ]
    for side, sx in (("left", 1.0), ("right", -1.0)):
        joints += [
            Joint(f"{side}_shoulder", "spine", (sx * 0.1295 * h, 0.0, 0.228 * h), _shoulder_dofs(side)),
            Joint(f"{side}_elbow", f"{side}_shoulder", (0.0, 0.0, -0.186 * h), (Dof("flexion", "x", -1, 0, 150),)),
        ]
    for side, sx in (("left", 1.0), ("right", -1.0)):
        joints += [
            Joint(f"{side}_hip", "pelvis", (sx * 0.05 * h, 0.0, 0.0), _hip_dofs(side)),
            Joint(f"{side}_knee", f"{side}_hip", (0.0, 0.0, -0.245 * h), (Dof("flexion", "x", +1, 0, 150),)),
            Joint(f"{side}_ankle", f"{side}_knee", (0.0, 0.0, -0.246 * h), (Dof("dorsiflexion", "x", -1, -50, 30),)),
        ]

    extra: dict[str, tuple[str, tuple[float, float, float]]] = {"head_top": ("head", (0.0, 0.0, 0.13 * h))}
    for side in ("left", "right"):
        extra[f"{side}_heel"] = (f"{side}_ankle", (0.0, 0.035 * h, -0.039 * h))
        extra[f"{side}_toe"] = (f"{side}_ankle", (0.0, -0.117 * h, -0.039 * h))
        extra[f"{side}_wrist"] = (f"{side}_elbow", (0.0, 0.0, -0.146 * h))
        extra[f"{side}_hand"] = (f"{side}_elbow", (0.0, 0.0, -0.254 * h))

    o = (0.0, 0.0, 0.0)
    segments = [
        Segment("pelvis", "pelvis", "box", (0.0, 0.0, 0.02 * h), o, 0.0, (0.19 * h, 0.1 * h, 0.06 * h), "center"),
        Segment("torso", "spine", "box", (0.0, 0.0, 0.114 * h), o, 0.0, (0.2 * h, 0.1 * h, 0.228 * h), "center"),
        Segment("neck", "neck", "capsule", o, (0.0, 0.0, 0.052 * h), 0.025 * h, None, "center"),
        Segment("head", "head", "sphere", (0.0, 0.0, 0.065 * h), o, 0.065 * h, None, "center"),
    ]
    for side in ("left", "right"):
        segments += [
            Segment(f"{side}_upper_arm", f"{side}_shoulder", "capsule", o, (0.0, 0.0, -0.186 * h), 0.025 * h, None, side),
            Segment(f"{side}_forearm", f"{side}_elbow", "capsule", o, (0.0, 0.0, -0.146 * h), 0.02 * h, None, side),
            Segment(f"{side}_hand", f"{side}_elbow", "sphere", (0.0, 0.0, -0.2 * h), o, 0.02 * h, None, side),
            Segment(f"{side}_thigh", f"{side}_hip", "capsule", o, (0.0, 0.0, -0.245 * h), 0.035 * h, None, side),
            Segment(f"{side}_shank", f"{side}_knee", "capsule", o, (0.0, 0.0, -0.246 * h), 0.028 * h, None, side),
            Segment(
                f"{side}_foot", f"{side}_ankle", "box", (0.0, -0.041 * h, -0.0195 * h), o, 0.0,
                (0.05 * h, 0.152 * h, 0.039 * h), side,
            ),
        ]

    dims = {
        "thigh": 0.245 * h,
        "shank": 0.246 * h,
        "ankle_height": 0.039 * h,
        "pelvis_height": 0.530 * h,
        "hip_half_width": 0.05 * h,
        "foot_length": 0.152 * h,
    }
    return Skeleton(h, {j.name: j for j in joints}, extra, segments, dims)
