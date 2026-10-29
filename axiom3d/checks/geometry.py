"""Geometry checks: nothing under the ground, nothing hovering."""

from __future__ import annotations

from axiom3d.checks.base import CheckContext, CheckResult, frames_text, register

PENETRATION_TOL = 0.01
FLOAT_TOL = 0.05


@register("geometry.ground_penetration")
def ground_penetration(ctx: CheckContext) -> list[CheckResult]:
    bad, worst, worst_name = [], 0.0, ""
    for s in ctx.states:
        name, p = min(s.points.items(), key=lambda kv: kv[1][2])
        if p[2] < -PENETRATION_TOL:
            bad.append(s.frame)
            if p[2] < worst:
                worst, worst_name = float(p[2]), name
    if not bad:
        return []
    return [CheckResult(
        "geometry.ground_penetration", "error", bad,
        f"{worst_name} goes {-worst:.3f} m below the ground (frames {frames_text(bad)})",
        {"min_z": worst},
        "Nothing may go below z = 0. Raise the root height, or use plant_foot so the tool keeps the foot on the ground.",
    )]


@register("geometry.floating")
def floating(ctx: CheckContext) -> list[CheckResult]:
    if ctx.kind != "pose":
        return []
    bad, lowest = [], []
    for s in ctx.states:
        low = min(p[2] for p in s.points.values())
        if low > FLOAT_TOL:
            bad.append(s.frame)
            lowest.append(low)
    if not bad:
        return []
    return [CheckResult(
        "geometry.floating", "error", bad,
        f"the body hovers {min(lowest):.3f} m above the ground (frames {frames_text(bad)})",
        {"gap": min(lowest)},
        "A standing body touches the ground. Lower the root height until the feet reach z = 0.",
    )]
