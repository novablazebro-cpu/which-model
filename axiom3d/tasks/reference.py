"""Clean, hand-checked solutions for each task, as command lists.

The numbers come from IK reach. The pelvis bobs like a real gait: high
(0.92 m) at mid-stance so the stance knee stays near-straight, low (0.885 m)
in double support so both feet can reach the ground about 0.25 m from the hip.
"""

from __future__ import annotations


def _plant(side, start, end, forward=None, left=None):
    cmd = {"op": "plant_foot", "side": side, "start": start, "end": end}
    if forward is not None:
        cmd["forward"] = forward
    if left is not None:
        cmd["left"] = left
    return cmd


def _swing(side, start, end, apex=0.08):
    return {"op": "swing_foot", "side": side, "start": start, "end": end, "apex": apex}


def _bob(frame, height):
    """Pelvis height key; forward/left stay on the line between the neighbouring keys."""
    return {"op": "set_root", "frame": frame, "height": height}


def _arms(frame, left=None, right=None):
    angles = {}
    if left is not None:
        angles["left_shoulder.flexion"] = left
    if right is not None:
        angles["right_shoulder.flexion"] = right
    return {"op": "set_pose", "frame": frame, "angles": angles}


_REFERENCE = {
    "step_forward": [
        {"op": "set_root", "frame": 0, "height": 0.92},
        {"op": "set_root", "frame": 24, "forward": 0.18, "height": 0.885},
        _bob(12, 0.92),
        _bob(18, 0.89),
        _plant("right", 0, 24, 0.0),
        _plant("left", 0, 6, 0.0),
        _swing("left", 6, 18),
        _plant("left", 18, 24, 0.36),
    ],
    "walk_forward": [
        {"op": "set_root", "frame": 0, "height": 0.92},
        {"op": "set_root", "frame": 48, "forward": 1.05, "height": 0.92},
        _bob(6, 0.915),
        _bob(10, 0.885),
        _bob(16, 0.92),
        _bob(23, 0.885),
        _bob(31, 0.92),
        _bob(39, 0.885),
        _bob(43, 0.915),
        _plant("left", 0, 3, 0.0),
        _plant("right", 0, 10, 0.0),
        _swing("left", 3, 9),
        _plant("left", 9, 24, 0.35),
        _swing("right", 10, 22),
        _plant("right", 22, 40, 0.70),
        _swing("left", 24, 38),
        _plant("left", 38, 48, 1.05),
        _swing("right", 40, 46),
        _plant("right", 46, 48, 1.05),
        _arms(0, left=0, right=0),
        _arms(9, left=-15),
        _arms(10, right=15),
        _arms(22, right=-15),
        _arms(24, left=15),
        _arms(38, left=-15),
        _arms(40, right=15),
        _arms(48, left=0, right=0),
    ],
    "turn_then_step": [
        # A step-turn: planted feet keep their heading, so the body never turns more than 35 deg over a
        # planted foot. The left foot opens to 70 deg, the right steps to 90 deg, then the left steps along +X.
        {"op": "set_root", "frame": 0, "heading": 0, "height": 0.92},
        {"op": "set_root", "frame": 8, "heading": 35},
        {"op": "set_root", "frame": 14, "heading": 35},
        {"op": "set_root", "frame": 20, "heading": 75},
        {"op": "set_root", "frame": 24, "heading": 90, "height": 0.92, "left": 0.0},
        _bob(28, 0.92),
        _bob(32, 0.885),
        {"op": "set_root", "frame": 36, "left": 0.18, "height": 0.885},
        _plant("right", 0, 14),
        _plant("left", 0, 8),
        _swing("left", 8, 14),
        dict(_plant("left", 14, 24, -0.0822, 0.0299), facing=70),
        _swing("right", 14, 20),
        dict(_plant("right", 20, 36, 0.0875, 0.0), facing=90),
        _swing("left", 24, 32),
        dict(_plant("left", 32, 36, -0.0875, 0.36), facing=90),
    ],
    "meiping_vase": [
        # Measured from the reference photo: shoulder at 72% of the height, mouth 0.10 x the height.
        {"op": "shape_profile", "wall": 0.006, "points": [
            [0.000, 0.066], [0.012, 0.064], [0.040, 0.060], [0.120, 0.075], [0.200, 0.092], [0.260, 0.103],
            [0.290, 0.107], [0.330, 0.100], [0.355, 0.075], [0.370, 0.040], [0.378, 0.022], [0.392, 0.018],
            [0.400, 0.021]]},
        {"op": "paint_band", "start": 0.04, "end": 0.37, "color": "red"},
        {"op": "paint_band", "start": 0.0, "end": 0.04, "color": "blue"},
        {"op": "paint_band", "start": 0.37, "end": 0.40, "color": "blue"},
    ],
}


def reference_commands(task_id: str) -> list[dict]:
    return [dict(c) for c in _REFERENCE[task_id]]
