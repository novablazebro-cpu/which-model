"""Gait checks: the mistakes models make when they animate walking."""

from __future__ import annotations

import numpy as np

from axiom3d.checks.base import CheckContext, CheckResult, frames_text, register
from axiom3d.conventions import character_axes
from axiom3d.measure import contact_windows, foot_contact, foot_xy, relation, swing_windows, track_coords

SLIDE_TOL = 0.02
FORWARD_SHARE = 0.5
BACKSWING_TOL = 0.05
ARM_RANGE = 5.0
LOOP_ANGLE_TOL = 5.0
LOOP_POS_TOL = 0.03
BACKWARD_TOL = 0.01

SIGN_HINT = (
    "Remember forward = -Y at heading 0 (rotate it with the heading). A swing foot moves forward relative "
    "to the pelvis and lands in front of where it lifted off: plant it with a larger forward value, or use "
    "positive hip flexion. +X raw rotation swings a downward bone toward +Y, which is backward."
)


def _state(ctx: CheckContext, frame: int):
    return ctx.states[frame - ctx.states[0].frame]


@register("gait.support")
def support(ctx: CheckContext) -> list[CheckResult]:
    if ctx.kind != "walk":
        return []
    bad = [s.frame for s in ctx.states if not foot_contact(s, "left") and not foot_contact(s, "right")]
    if not bad:
        return []
    return [CheckResult(
        "gait.support", "error", bad,
        f"both feet are off the ground (frames {frames_text(bad)}); that's running or jumping, not walking",
        {"frames": float(len(bad))},
        "In a walk one foot is always down. Start each swing only after the other foot is planted.",
    )]


@register("gait.foot_slide")
def foot_slide(ctx: CheckContext) -> list[CheckResult]:
    results = []
    for side in ("left", "right"):
        for a, b in contact_windows(ctx.states, side):
            start = foot_xy(_state(ctx, a), side)
            drifts = [(float(np.linalg.norm(foot_xy(_state(ctx, f), side) - start)), f) for f in range(a, b + 1)]
            drift, at = max(drifts)
            if drift <= SLIDE_TOL:
                continue
            direction = foot_xy(_state(ctx, at), side) - start
            travel = _state(ctx, b).root_position[:2] - _state(ctx, a).root_position[:2]
            moonwalk = np.linalg.norm(travel) > 1e-3 and float(direction @ travel) < 0
            frames = list(range(a, b + 1))
            if moonwalk:
                results.append(CheckResult(
                    "gait.moonwalk", "error", frames,
                    f"the {side} foot slides {drift:.3f} m BACKWARD while the body moves forward (frames {a}-{b})",
                    {"drift": drift},
                    "A foot on the ground must stay put. Use plant_foot for the contact frames; the tool then "
                    "solves the leg so the body moves over the fixed foot. If you keyed the hip by hand, check the "
                    "sign: " + SIGN_HINT,
                ))
            else:
                results.append(CheckResult(
                    "gait.foot_slide", "error", frames,
                    f"the {side} foot slides {drift:.3f} m while on the ground (frames {a}-{b})",
                    {"drift": drift},
                    "A foot on the ground must stay put. Use plant_foot for the contact frames instead of keying the leg.",
                ))
    return results


@register("gait.step_direction")
def step_direction(ctx: CheckContext) -> list[CheckResult]:
    if ctx.kind not in ("step", "walk"):
        return []
    first, last = ctx.states[0].frame, ctx.states[-1].frame
    results = []
    for side in ("left", "right"):
        for a, b in swing_windows(ctx.states, side):
            if a <= first or b >= last:
                continue
            lift, land = _state(ctx, a - 1), _state(ctx, b + 1)
            facing, _, _ = character_axes(lift.heading_deg)
            disp = foot_xy(land, side) - foot_xy(lift, side)
            horizontal = float(np.linalg.norm(disp))
            share = float(disp @ facing[:2]) / horizontal if horizontal > 0.02 else 1.0
            # A real swing moves the foot forward relative to the pelvis; the classic sign error swings it back.
            rel = [relation(_state(ctx, f), f"{side}_ankle", "pelvis")["forward"] for f in range(a - 1, b + 2)]
            backswing = rel[0] - min(rel)
            if share >= FORWARD_SHARE and backswing <= BACKSWING_TOL:
                continue
            what = "BACKWARD or sideways" if share < FORWARD_SHARE else f"BACKWARD relative to the pelvis by {backswing:.2f} m mid-swing"
            results.append(CheckResult(
                "gait.step_direction", "error", list(range(a, b + 1)),
                f"the {side} foot swings {what} (frames {a}-{b}); net {float(disp @ facing[:2]):+.2f} m along the facing",
                {"forward_share": share, "backswing": backswing, "displacement": horizontal},
                SIGN_HINT,
            ))
    return results


@register("gait.alternation")
def alternation(ctx: CheckContext) -> list[CheckResult]:
    if ctx.kind != "walk":
        return []
    swings = sorted((a, b, side) for side in ("left", "right") for a, b in swing_windows(ctx.states, side))
    results = []
    for (a0, b0, s0), (a1, b1, s1) in zip(swings, swings[1:]):
        if s0 == s1:
            results.append(CheckResult(
                "gait.alternation", "error", list(range(a0, b1 + 1)),
                f"the {s0} foot steps twice in a row (frames {a0}-{b0} and {a1}-{b1})",
                {},
                "Walking alternates: left, right, left, right. Swing the other foot between these two steps.",
            ))
    return results


@register("gait.arm_counter_swing")
def arm_counter_swing(ctx: CheckContext) -> list[CheckResult]:
    if ctx.kind != "walk":
        return []
    problems = []
    for side in ("left", "right"):
        arm = np.array([s.angles[f"{side}_shoulder.flexion"] for s in ctx.states])
        hip = np.array([s.angles[f"{side}_hip.flexion"] for s in ctx.states])
        if np.ptp(arm) < ARM_RANGE:
            problems.append(f"{side} arm is static ({np.ptp(arm):.1f} deg of swing)")
        elif np.std(hip) > 1e-6 and np.corrcoef(arm, hip)[0, 1] > 0:
            problems.append(f"{side} arm swings with its own leg (corr {np.corrcoef(arm, hip)[0, 1]:+.2f})")
    if not problems:
        return []
    return [CheckResult(
        "gait.arm_counter_swing", "warning", [], "; ".join(problems), {},
        "Arms swing opposite to the same-side leg: when the left leg is forward, the left arm is back "
        "(negative left_shoulder.flexion). Key shoulder flexion of about +/-15 deg.",
    )]


@register("gait.loop_continuity")
def loop_continuity(ctx: CheckContext) -> list[CheckResult]:
    if not ctx.clip.timeline.loop:
        return []
    a, b = ctx.states[0], ctx.states[-1]
    angle_gap = max(abs(a.angles[c] - b.angles[c]) for c in a.angles)
    pos_gap = max(
        abs(relation(a, f"{side}_ankle", "pelvis")[k] - relation(b, f"{side}_ankle", "pelvis")[k])
        for side in ("left", "right") for k in ("forward", "left")
    )
    if angle_gap <= LOOP_ANGLE_TOL and pos_gap <= LOOP_POS_TOL:
        return []
    return [CheckResult(
        "gait.loop_continuity", "error", [a.frame, b.frame],
        f"the loop doesn't close: angles differ by up to {angle_gap:.1f} deg and feet by {pos_gap:.3f} m "
        "between the first and last frame",
        {"angle_gap": angle_gap, "position_gap": pos_gap},
        "For a looping cycle the last frame must match the first (relative to the pelvis).",
    )]


@register("gait.root_progression")
def root_progression(ctx: CheckContext) -> list[CheckResult]:
    if ctx.kind not in ("step", "walk"):
        return []
    fwd = [track_coords(ctx.clip, s.root_position[:2])[0] for s in ctx.states]
    bad = [ctx.states[i + 1].frame for i in range(len(fwd) - 1) if fwd[i + 1] < fwd[i] - BACKWARD_TOL]
    if not bad:
        return []
    return [CheckResult(
        "gait.root_progression", "error", bad,
        f"the root moves backward along the track (frames {frames_text(bad)})",
        {"min_step": float(min(np.diff(fwd)))},
        "Track forward is measured along the start facing. Keep set_root forward values increasing over time.",
    )]
