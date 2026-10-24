"""Anatomy checks: joint limits and legs that can't reach their targets."""

from __future__ import annotations

from axiom3d.checks.base import CheckContext, CheckResult, frames_text, register

LIMIT_TOL = 0.5


def _limit_hint(channel: str, dof, worst: float) -> str:
    if dof.name == "flexion" and dof.min_deg == 0 and worst < 0:
        joint = channel.split(".")[0].split("_", 1)[1]
        moves = "the foot backward" if joint == "knee" else "the hand forward and up"
        return (f"The {joint} only bends one way: positive flexion moves {moves}; "
                "a negative value is hyperextension. Use a positive angle.")
    if dof.name == "flexion" and worst < dof.min_deg:
        return (f"Negative {channel} is extension: it swings the limb BACKWARD. To move it forward use a "
                f"positive angle (limit {dof.min_deg:g}..{dof.max_deg:g}).")
    return f"Keep {channel} within {dof.min_deg:g}..{dof.max_deg:g} degrees."


@register("anatomy.joint_limits")
def joint_limits(ctx: CheckContext) -> list[CheckResult]:
    results = []
    for channel in ctx.skel.channels():
        dof = ctx.skel.dof(channel)
        bad = [s.frame for s in ctx.states
               if not dof.min_deg - LIMIT_TOL <= s.angles[channel] <= dof.max_deg + LIMIT_TOL]
        if not bad:
            continue
        values = [ctx.states[f - ctx.states[0].frame].angles[channel] for f in bad]
        worst = max(values, key=lambda v: max(dof.min_deg - v, v - dof.max_deg))
        results.append(CheckResult(
            "anatomy.joint_limits", "error", bad,
            f"{channel} reaches {worst:+.1f} deg, outside its limit {dof.min_deg:g}..{dof.max_deg:g} "
            f"(frames {frames_text(bad)})",
            {"worst": worst, "min": dof.min_deg, "max": dof.max_deg},
            _limit_hint(channel, dof, worst),
        ))
    return results


@register("anatomy.ik_unreachable")
def ik_unreachable(ctx: CheckContext) -> list[CheckResult]:
    leg = ctx.skel.dims["thigh"] + ctx.skel.dims["shank"]
    results = []
    for side in ("left", "right"):
        bad = [s for s in ctx.states if s.ik[side] is not None and not s.ik[side].reached]
        if not bad:
            continue
        shortfall = max(s.ik[side].shortfall_m for s in bad)
        frames = [s.frame for s in bad]
        results.append(CheckResult(
            "anatomy.ik_unreachable", "error", frames,
            f"the {side} leg can't reach its target by up to {shortfall:.3f} m (frames {frames_text(frames)})",
            {"shortfall": shortfall, "leg_length": leg},
            f"The leg is {leg:.2f} m long. Lower the root (height) or plant the foot nearer the hip; "
            "with the pelvis at 0.89 m a foot can sit about 0.25 m in front of or behind its hip.",
        ))
    return results
