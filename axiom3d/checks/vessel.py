"""Vessel checks: the mistakes that make a profile unbuildable or unusable, and why."""

from __future__ import annotations

import numpy as np

from axiom3d.checks.base import CheckContext, CheckResult
from axiom3d.model.vessel import measure_cached

MIN_OPENING = 0.002
MIN_TIP_DEG = 8.0
MAX_TURN_DEG = 45.0


def vessel_checks(ctx: CheckContext) -> list[CheckResult]:
    spec = ctx.clip.vessel
    if spec is None:
        return [CheckResult("vessel.no_profile", "error", [], "the vessel has no profile yet",
                            hint="call shape_profile(points=[[0, foot_radius], ..., [height, mouth_radius]]): "
                                 "[height, RADIUS] pairs from the base up")]
    m = measure_cached(spec)
    out = []
    inner = m.r - spec.wall
    low = int(np.argmin(inner))
    if inner[low] < MIN_OPENING:
        out.append(CheckResult(
            "vessel.too_thin", "error", [],
            f"at h={m.h[low]:.3f} m the radius is {m.r[low]:.3f} m but the wall is {spec.wall:.3f} m: "
            f"the inside is only {max(inner[low], 0) * 1000:.1f} mm wide",
            {"height": float(m.h[low]), "radius": float(m.r[low]), "wall": spec.wall},
            "the inner radius is radius - wall and must stay >= 2 mm. Widen the profile there or use a thinner wall. "
            "Profile values are RADII: half the diameter."))
    mouth_r = m.mouth_diameter / 2
    if mouth_r < 2 * spec.wall:
        out.append(CheckResult(
            "vessel.mouth_closed", "error", [],
            f"the mouth radius {mouth_r:.3f} m is under 2 x wall ({2 * spec.wall:.3f} m): the opening nearly closes",
            {"mouth_radius": mouth_r, "wall": spec.wall},
            "a mouth needs an opening wider than its wall; make the last point's radius at least 2 x wall."))
    if m.tip_angle_deg < MIN_TIP_DEG:
        out.append(CheckResult(
            "vessel.unstable", "error", [],
            f"tip angle {m.tip_angle_deg:.1f} deg: the vessel tips over if tilted more than that",
            {"tip_angle_deg": m.tip_angle_deg, "foot_radius": m.foot_diameter / 2},
            "tip angle = atan(foot radius / centre-of-mass height). Widen the foot (the first point's radius) "
            f"or lower the mass; it must be >= {MIN_TIP_DEG:g} deg."))
    if m.max_turn_deg > MAX_TURN_DEG:
        ang = np.degrees(np.arctan2(np.diff(m.r), np.diff(m.h)))
        k = int(np.argmax(np.abs(np.diff(ang)))) + 1
        out.append(CheckResult(
            "vessel.kink", "warning", [],
            f"the profile turns {m.max_turn_deg:.0f} deg at h={m.h[k]:.3f} m: a crease, not a curve",
            {"height": float(m.h[k]), "turn_deg": m.max_turn_deg},
            "two points very close in height with very different radii make a step; spread the change over "
            "more height or add points between them."))
    for i, band in enumerate(spec.bands):
        if band.end > m.height + 1e-9:
            out.append(CheckResult(
                "vessel.band_outside", "warning", [],
                f"band #{i + 1} ({band.start:.3f}-{band.end:.3f} m) reaches above the top ({m.height:.3f} m)",
                {"band": i + 1, "top": m.height},
                "bands are heights from the base (0) to the top; this paint partly misses the vessel."))
    return out
