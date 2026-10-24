"""Vessel perception: the measurements as text, and a numeric diff between two versions."""

from __future__ import annotations

import numpy as np

from axiom3d.model.vessel import ATTRS, PALETTE, VesselSpec, color_name, measure_cached, radius_at

PROFILE_ROWS = 10
DIFF_TOL = {"shoulder_ratio": 0.002, "capacity": 0.01, "tip_angle": 0.1}
DIFF_TOL_M = 0.0005


def color_zones(spec: VesselSpec) -> list[tuple[float, float, str]]:
    """(start, end, #rrggbb) runs from the base to the top, adjacent equal colours merged."""
    top = spec.profile[-1][0]
    cuts = sorted({0.0, top} | {e for b in spec.bands for e in (b.start, b.end) if 0 < e < top})
    zones: list[tuple[float, float, str]] = []
    for a, b in zip(cuts, cuts[1:]):
        c = spec.color_at((a + b) / 2)
        if zones and zones[-1][2] == c:
            zones[-1] = (zones[-1][0], b, c)
        else:
            zones.append((a, b, c))
    return zones


def _label(color: str) -> str:
    name = color_name(color)
    return name if PALETTE[name] == color else f"{color} (≈{name})"


def _zones_text(spec: VesselSpec) -> str:
    return " · ".join(f"{a:.3f}–{b:.3f} {_label(c)}" for a, b, c in color_zones(spec))


def describe_vessel(spec: VesselSpec | None) -> str:
    if spec is None:
        return "VESSEL: no profile yet. Call shape_profile(points=[[0, foot_radius], ..., [height, mouth_radius]])."
    m = measure_cached(spec)
    lines = [
        "VESSEL (Z up, metres; diameters are 2 × radius):",
        f"  height {m.height:.3f} · max diameter {m.max_diameter:.3f} at h {m.shoulder_height:.3f} "
        f"(shoulder ratio {m.shoulder_ratio:.3f})",
        f"  mouth {m.mouth_diameter:.3f} · neck {m.neck_diameter:.3f} · waist {m.waist_diameter:.3f} · "
        f"foot {m.foot_diameter:.3f}",
        f"  max diameter/height {m.max_diameter / m.height:.3f} · mouth/height {m.mouth_diameter / m.height:.3f} · "
        f"foot/height {m.foot_diameter / m.height:.3f}",
        f"  wall {spec.wall:.3f} · capacity {m.capacity_l:.2f} L · tip angle {m.tip_angle_deg:.1f}° "
        f"(tips below 8°) · sharpest turn {m.max_turn_deg:.0f}°",
        "PROFILE (smoothed outer radius; h, radius, diameter):",
    ]
    for h in np.linspace(0, m.height, PROFILE_ROWS + 1):
        r = radius_at(spec, h)
        lines.append(f"  h {h:.3f}  r {r:.3f}  d {2 * r:.3f}")
    lines.append(f"  (widest: r {m.max_diameter / 2:.3f} at h {m.shoulder_height:.3f}; narrowest above it: "
                 f"d {m.neck_diameter:.3f}; narrowest below it: d {m.waist_diameter:.3f})")
    lines.append(f"COLOUR ZONES (bottom to top): {_zones_text(spec)}")
    return "\n".join(lines)


def _value(spec: VesselSpec | None, attr: str) -> float | None:
    return None if spec is None else float(getattr(measure_cached(spec), ATTRS[attr]))


def vessel_diff(before: VesselSpec | None, after: VesselSpec | None) -> list[str]:
    lines = []
    for attr in ATTRS:
        a, b = _value(before, attr), _value(after, attr)
        if a is None and b is None:
            continue
        if a is None or b is None or abs(b - a) > DIFF_TOL.get(attr, DIFF_TOL_M):
            fa = "none" if a is None else f"{a:.3f}"
            fb = "none" if b is None else f"{b:.3f}"
            lines.append(f"  vessel.{attr} {fa} → {fb}")
    za = _zones_text(before) if before is not None else None
    zb = _zones_text(after) if after is not None else None
    if za != zb and zb is not None:
        lines.append(f"  colour zones {za or 'none'} → {zb}")
    return lines
