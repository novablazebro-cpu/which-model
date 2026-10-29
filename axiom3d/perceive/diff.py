"""Numeric before/after diff of an edit. Models misread image differences; numbers don't lie."""

from __future__ import annotations

import numpy as np

from axiom3d.checks.base import CheckContext, run_checks
from axiom3d.measure import track_coords

KEY_POINTS = ("pelvis", "head_top", "left_ankle", "right_ankle", "left_toe", "right_toe", "left_hand", "right_hand")
POS_TOL = 0.005
ANGLE_TOL = 0.5


def _root(clip, state) -> dict[str, float]:
    f, l = track_coords(clip, state.root_position[:2])
    return {"forward": f, "left": l, "height": float(state.root_position[2]), "heading": state.heading_deg}


def _point(clip, state, name) -> dict[str, float]:
    p = state.points[name]
    f, l = track_coords(clip, p[:2])
    return {"forward": f, "left": l, "z": float(p[2])}


def _errors(skel, kind, clip, states) -> set[str]:
    return {r.id for r in run_checks(CheckContext(skel, clip, states, kind)) if r.severity == "error"}


def _check_delta(skel, kind, before, after) -> list[str]:
    (clip_a, states_a), (clip_b, states_b) = before, after
    errs_a, errs_b = _errors(skel, kind, clip_a, states_a), _errors(skel, kind, clip_b, states_b)
    fixed, new = sorted(errs_a - errs_b), sorted(errs_b - errs_a)
    if not (fixed or new):
        return []
    parts = ([f"FIXED {', '.join(fixed)}"] if fixed else []) + ([f"NEW {', '.join(new)}"] if new else [])
    return ["  checks: " + "; ".join(parts)]


def describe_diff(skel, kind, before, after, frame: int, limit: int = 12) -> list[str]:
    (clip_a, states_a), (clip_b, states_b) = before, after
    if kind in ("vessel", "blocks"):
        if kind == "vessel":
            from axiom3d.perceive.vessel import vessel_diff

            lines = vessel_diff(clip_a.vessel, clip_b.vessel)
        else:
            from axiom3d.perceive.blocks import blocks_diff

            lines = blocks_diff(clip_a.blocks, clip_b.blocks)
        lines += _check_delta(skel, kind, before, after)
        return ["CHANGED:"] + lines if lines else ["CHANGED: nothing measurable"]
    i = frame - states_a[0].frame
    a, b = states_a[i], states_b[i]
    lines = []

    ra, rb = _root(clip_a, a), _root(clip_b, b)
    for key in ("forward", "left", "height", "heading"):
        tol = ANGLE_TOL if key == "heading" else POS_TOL
        if abs(rb[key] - ra[key]) > tol:
            lines.append(f"  root {key} {ra[key]:+.3f} → {rb[key]:+.3f} @{frame}")
    for name in KEY_POINTS:
        pa, pb = _point(clip_a, a, name), _point(clip_b, b, name)
        for key in ("forward", "left", "z"):
            if abs(pb[key] - pa[key]) > POS_TOL:
                lines.append(f"  {name} {key} {pa[key]:+.3f} → {pb[key]:+.3f} @{frame}")

    moves = [(float(np.linalg.norm(sb.points[n] - sa.points[n])), sa.frame, n)
             for sa, sb in zip(states_a, states_b) for n in KEY_POINTS]
    biggest, at, name = max(moves, key=lambda m: (round(m[0], 6), -m[1]))  # ties: earliest frame
    if biggest > POS_TOL and at != frame:
        lines.append(f"  largest change at frame {at}: {name} moved {biggest:.3f} m")

    for channel, va in a.angles.items():
        vb = b.angles[channel]
        if abs(vb - va) > ANGLE_TOL:
            lines.append(f"  {channel} {va:+.1f} → {vb:+.1f} @{frame}")

    lines += _check_delta(skel, kind, before, after)

    if not lines:
        return ["CHANGED: nothing measurable"]
    if len(lines) > limit:
        lines = lines[:limit] + [f"  (+{len(lines) - limit} more)"]
    return ["CHANGED:"] + lines
