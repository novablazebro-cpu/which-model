"""Clean, hand-checked solutions for each task, as command lists.

The numbers come from IK reach: with the pelvis at 0.89 m a straight-ahead foot
can sit about 0.25 m in front of or behind its hip.
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


def _arms(frame, left=None, right=None):
    angles = {}
    if left is not None:
        angles["left_shoulder.flexion"] = left
    if right is not None:
        angles["right_shoulder.flexion"] = right
    return {"op": "set_pose", "frame": frame, "angles": angles}


_REFERENCE = {
    "step_forward": [
        {"op": "set_root", "frame": 0, "height": 0.89},
        {"op": "set_root", "frame": 24, "forward": 0.18, "height": 0.89},
        _plant("right", 0, 24, 0.0),
        _plant("left", 0, 6, 0.0),
        _swing("left", 6, 18),
        _plant("left", 18, 24, 0.36),
    ],
    "walk_forward": [
        {"op": "set_root", "frame": 0, "height": 0.89},
        {"op": "set_root", "frame": 48, "forward": 1.05, "height": 0.89},
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
        {"op": "set_root", "frame": 0, "heading": 0, "height": 0.89},
        {"op": "set_root", "frame": 12, "heading": 90, "height": 0.89},
        {"op": "set_root", "frame": 36, "left": 0.17, "height": 0.86},
        _plant("right", 0, 36),
        _plant("left", 0, 14),
        _swing("left", 14, 32),
        _plant("left", 32, 36, -0.0875, 0.4075),
    ],
}


def reference_commands(task_id: str) -> list[dict]:
    return [dict(c) for c in _REFERENCE[task_id]]
