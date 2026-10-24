"""Measurements shared by reports, checks, criteria and predictions."""

from __future__ import annotations

import numpy as np

from axiom3d.conventions import CONTACT_EPS, character_axes, world_to_track


def foot_contact(state, side: str) -> bool:
    return min(state.points[f"{side}_heel"][2], state.points[f"{side}_toe"][2]) <= CONTACT_EPS


def _runs(flags: list[bool], frames: list[int]) -> list[tuple[int, int]]:
    runs, start = [], None
    for f, on in zip(frames, flags):
        if on and start is None:
            start = f
        if not on and start is not None:
            runs.append((start, prev))
            start = None
        prev = f
    if start is not None:
        runs.append((start, frames[-1]))
    return runs


def contact_windows(states, side: str) -> list[tuple[int, int]]:
    return _runs([foot_contact(s, side) for s in states], [s.frame for s in states])


def swing_windows(states, side: str) -> list[tuple[int, int]]:
    return _runs([not foot_contact(s, side) for s in states], [s.frame for s in states])


def foot_xy(state, side: str) -> np.ndarray:
    return state.points[f"{side}_ankle"][:2].copy()


def relation(state, a: str, b: str) -> dict[str, float]:
    """Point `a` relative to point `b` in the character frame at this state's heading."""
    forward, left, up = character_axes(state.heading_deg)
    d = state.points[a] - state.points[b]
    return {"forward": float(d @ forward), "left": float(d @ left), "up": float(d @ up)}


def track_coords(clip, xy) -> tuple[float, float]:
    return world_to_track(clip.track, xy)


def root_travel(clip, states) -> float:
    first = track_coords(clip, states[0].root_position[:2])[0]
    last = track_coords(clip, states[-1].root_position[:2])[0]
    return last - first


def support_label(state) -> str:
    left, right = foot_contact(state, "left"), foot_contact(state, "right")
    return {(True, True): "LR", (True, False): "L", (False, True): "R"}.get((left, right), "-")
