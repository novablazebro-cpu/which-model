"""Vessels: surfaces of revolution (vases, bottles, jars) built from a side profile.

The AI states the profile as (height, radius) points; the tool smooths it, builds a watertight
shell and measures it. Z is up, metres, the axis runs through the origin, the base sits at z = 0.
"""

from __future__ import annotations

import functools
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from axiom3d.mesh import Mesh

SAMPLES = 96
SEGMENTS = 48
MAX_POINTS = 64
MAX_HEIGHT = 2.0
MAX_RADIUS = 1.0
WALL_RANGE = (0.002, 0.03)
MIN_INNER = 1e-4
MAX_OBJ_BYTES = 20_000_000
WELD = 1e-5
PALETTE = {
    "red": "#b3261e",
    "blue": "#1f3f8f",
    "white": "#f4f1e8",
    "green": "#2e7d32",
    "yellow": "#e8c547",
    "black": "#1a1a1a",
    "gold": "#b8892b",
}
DEFAULT_COLOR = PALETTE["white"]
_HEX = re.compile(r"#[0-9a-f]{6}")
# Prediction and calculator names -> VesselMeasures fields.
ATTRS = {
    "height": "height",
    "max_diameter": "max_diameter",
    "shoulder_height": "shoulder_height",
    "shoulder_ratio": "shoulder_ratio",
    "mouth_diameter": "mouth_diameter",
    "neck_diameter": "neck_diameter",
    "waist_diameter": "waist_diameter",
    "foot_diameter": "foot_diameter",
    "capacity": "capacity_l",
    "tip_angle": "tip_angle_deg",
}


class VesselError(ValueError):
    """A vessel spec or file that cannot be built or measured."""


@dataclass(frozen=True)
class Band:
    start: float
    end: float
    color: str  # "#rrggbb"


@dataclass(frozen=True)
class VesselSpec:
    profile: tuple  # ((height, radius), ...) in metres, base first
    wall: float
    bands: tuple = ()  # Band, ...; later bands paint over earlier ones

    def color_at(self, height: float) -> str:
        for band in reversed(self.bands):
            if band.start <= height <= band.end:
                return band.color
        return DEFAULT_COLOR


@dataclass
class VesselMeasures:
    height: float
    max_diameter: float
    shoulder_height: float
    shoulder_ratio: float
    mouth_diameter: float
    neck_diameter: float
    waist_diameter: float
    foot_diameter: float
    capacity_l: float
    tip_angle_deg: float
    max_turn_deg: float
    h: np.ndarray = field(repr=False)
    r: np.ndarray = field(repr=False)
    _color: Callable[[float], str] = field(repr=False, compare=False)

    def color_at(self, height: float) -> str:
        return self._color(height)


def parse_color(text: str) -> str:
    """A palette name or #rrggbb, returned as lowercase #rrggbb."""
    key = str(text).strip().lower()
    if key in PALETTE:
        return PALETTE[key]
    if _HEX.fullmatch(key):
        return key
    raise VesselError(f"unknown colour {text!r}; use one of {', '.join(PALETTE)} or #rrggbb")


def _rgb(hex_color: str) -> np.ndarray:
    return np.array([int(hex_color[i : i + 2], 16) for i in (1, 3, 5)], dtype=float) / 255


def _hex(rgb) -> str:
    return "#" + "".join(f"{int(round(min(max(c, 0.0), 1.0) * 255)):02x}" for c in rgb)


def color_name(hex_color: str) -> str:
    """The palette name nearest to a colour."""
    rgb = _rgb(hex_color)
    return min(PALETTE, key=lambda name: float(np.sum((_rgb(PALETTE[name]) - rgb) ** 2)))


def validate(spec: VesselSpec) -> tuple[np.ndarray, np.ndarray]:
    """The profile as arrays, or a VesselError that says what to fix."""
    pts = spec.profile
    if not 3 <= len(pts) <= MAX_POINTS:
        raise VesselError(f"a profile needs 3..{MAX_POINTS} points [height, radius]; got {len(pts)}")
    try:
        arr = np.array([[float(p[0]), float(p[1])] for p in pts])
    except (TypeError, ValueError, IndexError):
        raise VesselError("each profile point must be [height, radius] in metres") from None
    if not np.all(np.isfinite(arr)):
        raise VesselError("profile values must be finite numbers")
    h, r = arr[:, 0], arr[:, 1]
    if abs(h[0]) > 1e-9:
        raise VesselError(f"the first point is the base: its height must be 0 (got {h[0]:g})")
    for i in range(1, len(h)):
        if h[i] <= h[i - 1]:
            raise VesselError(f"heights must strictly increase: point #{i + 1} (h={h[i]:g}) is not above point #{i} (h={h[i - 1]:g})")
    if h[-1] > MAX_HEIGHT:
        raise VesselError(f"a vessel can be at most {MAX_HEIGHT:g} m tall (got {h[-1]:g})")
    for i, radius in enumerate(r):
        if not 0 < radius <= MAX_RADIUS:
            raise VesselError(f"point #{i + 1}: radius must be in (0, {MAX_RADIUS:g}] m (got {radius:g})")
    lo, hi = WALL_RANGE
    if not lo <= spec.wall <= hi:
        raise VesselError(f"wall must be {lo:g}..{hi:g} m (got {spec.wall:g})")
    if h[-1] <= 3 * spec.wall:
        raise VesselError(f"the vessel must be taller than 3 × wall ({3 * spec.wall:g} m)")
    h[0] = 0.0
    return h, r


def _edge_slope(h0: float, h1: float, d0: float, d1: float) -> float:
    m = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
    if np.sign(m) != np.sign(d0):
        return 0.0
    if np.sign(d0) != np.sign(d1) and abs(m) > 3 * abs(d0):
        return 3 * d0
    return m


def _pchip(x: np.ndarray, y: np.ndarray) -> Callable[[np.ndarray], np.ndarray]:
    """Monotone cubic interpolation (Fritsch-Carlson): never overshoots the points."""
    hk = np.diff(x)
    d = np.diff(y) / hk
    m = np.zeros(len(x))
    for k in range(1, len(x) - 1):
        if d[k - 1] * d[k] > 0:
            w1, w2 = 2 * hk[k] + hk[k - 1], hk[k] + 2 * hk[k - 1]
            m[k] = (w1 + w2) / (w1 / d[k - 1] + w2 / d[k])
    m[0] = _edge_slope(hk[0], hk[1], d[0], d[1])
    m[-1] = _edge_slope(hk[-1], hk[-2], d[-1], d[-2])

    def f(q):
        q = np.clip(np.asarray(q, dtype=float), x[0], x[-1])
        k = np.clip(np.searchsorted(x, q, side="right") - 1, 0, len(x) - 2)
        t = (q - x[k]) / hk[k]
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * y[k] + (t3 - 2 * t2 + t) * hk[k] * m[k]
                + (-2 * t3 + 3 * t2) * y[k + 1] + (t3 - t2) * hk[k] * m[k + 1])

    return f


def _dedupe(values: np.ndarray, tol: float) -> np.ndarray:
    values = np.unique(values)
    keep = np.concatenate([[True], np.diff(values) > tol])
    return values[keep]


def sample_profile(spec: VesselSpec) -> tuple[np.ndarray, np.ndarray]:
    """The smoothed outer profile: every point and band edge, plus SAMPLES even heights."""
    h, r = validate(spec)
    edges = [e for b in spec.bands for e in (b.start, b.end) if 0 < e < h[-1]]
    must = _dedupe(np.concatenate([h, edges]), 1e-6)
    even = np.linspace(0, h[-1], SAMPLES)
    even = even[np.min(np.abs(even[:, None] - must[None, :]), axis=1) > 1e-4]
    hs = np.sort(np.concatenate([must, even]))
    return hs, _pchip(h, r)(hs)


def _rings(radii: np.ndarray, heights: np.ndarray, segments: int) -> np.ndarray:
    a = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    return np.stack([radii[:, None] * np.cos(a), radii[:, None] * np.sin(a),
                     np.broadcast_to(heights[:, None], (len(heights), segments))], axis=-1).reshape(-1, 3)


def vessel_mesh(spec: VesselSpec, segments: int = SEGMENTS) -> tuple[Mesh, np.ndarray]:
    """A watertight shell and per-vertex RGB colours (0..1).

    The meridian runs from the base centre, up the outside, across the lip, down the inside to the
    floor centre at h = wall; revolving it gives one closed surface.
    """
    h, r = sample_profile(spec)
    radius = _pchip(*validate(spec))
    wall = spec.wall
    inner_h = np.concatenate([[wall], h[h > wall + 1e-6]])
    inner_r = np.maximum(radius(inner_h) - wall, MIN_INNER)
    mer_h = np.concatenate([h, inner_h[::-1]])
    mer_r = np.concatenate([r, inner_r[::-1]])
    n_rings, s = len(mer_h), segments
    verts = np.concatenate([[[0.0, 0.0, 0.0]], _rings(mer_r, mer_h, s), [[0.0, 0.0, wall]]])
    j = np.arange(s)
    j2 = (j + 1) % s
    faces = [np.stack([np.zeros(s, int), 1 + j2, 1 + j], axis=1)]
    for i in range(n_rings - 1):
        a, b = 1 + i * s + j, 1 + i * s + j2
        c, d = 1 + (i + 1) * s + j2, 1 + (i + 1) * s + j
        faces += [np.stack([a, b, c], axis=1), np.stack([a, c, d], axis=1)]
    last, pole = 1 + (n_rings - 1) * s, 1 + n_rings * s
    faces.append(np.stack([last + j, last + j2, np.full(s, pole)], axis=1))
    white = _rgb(DEFAULT_COLOR)
    ring_rgb = [_rgb(spec.color_at(z)) for z in h] + [white] * len(inner_h)
    colors = np.concatenate([[_rgb(spec.color_at(0.0))], np.repeat(ring_rgb, s, axis=0), [white]])
    mesh = Mesh(verts.astype(np.float32), np.concatenate(faces).astype(np.int32))
    return mesh, colors.astype(np.float32)


def _com_height(verts: np.ndarray, faces: np.ndarray) -> float:
    """Centre-of-mass height of the surface (a thin shell of even thickness)."""
    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
    total = float(area.sum())
    return float((area * (a[:, 2] + b[:, 2] + c[:, 2]) / 3).sum() / total) if total > 0 else 0.0


def _max_turn(h: np.ndarray, r: np.ndarray) -> float:
    ang = np.arctan2(np.diff(r), np.diff(h))
    return float(np.degrees(np.max(np.abs(np.diff(ang))))) if len(ang) > 1 else 0.0


def _measures(h, r, capacity_l, com_h, color) -> VesselMeasures:
    height = float(h[-1] - h[0])
    top = np.where(r >= r.max() - 1e-9)[0]
    shoulder = float((h[top[0]] + h[top[-1]]) / 2)
    above, below = r[h >= shoulder - 1e-12], r[h <= shoulder + 1e-12]
    foot = float(r[0])
    return VesselMeasures(
        height=height,
        max_diameter=2 * float(r.max()),
        shoulder_height=shoulder,
        shoulder_ratio=shoulder / height if height > 0 else 0.0,
        mouth_diameter=2 * float(r[-1]),
        neck_diameter=2 * float(above.min() if len(above) else r[-1]),
        waist_diameter=2 * float(below.min() if len(below) else r[0]),
        foot_diameter=2 * foot,
        capacity_l=capacity_l,
        tip_angle_deg=math.degrees(math.atan2(foot, com_h)) if com_h > 0 else 90.0,
        max_turn_deg=_max_turn(h, r),
        h=h,
        r=r,
        _color=color,
    )


def measure_spec(spec: VesselSpec) -> VesselMeasures:
    h, r = sample_profile(spec)
    mesh, _ = vessel_mesh(spec)
    inner = h >= spec.wall
    q = np.maximum(r[inner] - spec.wall, 0.0)
    capacity = float(np.trapezoid(np.pi * q * q, h[inner])) * 1000 if inner.sum() > 1 else 0.0
    com = _com_height(mesh.vertices.astype(float), mesh.faces)
    return _measures(h, r, capacity, com, spec.color_at)


@functools.lru_cache(maxsize=64)
def measure_cached(spec: VesselSpec) -> VesselMeasures:
    """measure_spec, memoised: specs are frozen, and edits re-measure the same scene often."""
    return measure_spec(spec)


def radius_at(spec: VesselSpec, height: float) -> float:
    """The smoothed outer radius at a height (clamped to the vessel)."""
    return float(_pchip(*validate(spec))(height))


def write_obj(mesh: Mesh, colors: np.ndarray, path) -> Path:
    path = Path(path)
    lines = [f"v {x:.6f} {y:.6f} {z:.6f} {cr:.4f} {cg:.4f} {cb:.4f}"
             for (x, y, z), (cr, cg, cb) in zip(mesh.vertices.tolist(), colors.tolist())]
    lines += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in mesh.faces.tolist()]
    path.write_text("\n".join(lines) + "\n")
    return path


def _parse_obj(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if not path.is_file():
        raise VesselError(f"no such file: {path}")
    if path.stat().st_size > MAX_OBJ_BYTES:
        raise VesselError(f"{path.name} is larger than {MAX_OBJ_BYTES // 1_000_000} MB")
    verts, cols, faces = [], [], []
    for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        parts = line.split()
        if not parts:
            continue
        try:
            if parts[0] == "v":
                nums = [float(x) for x in parts[1:]]
                verts.append(nums[:3])
                cols.append(nums[3:6] if len(nums) >= 6 else [1.0, 1.0, 1.0])
            elif parts[0] == "f":
                idx = [int(p.split("/")[0]) for p in parts[1:]]
                idx = [i - 1 if i > 0 else len(verts) + i for i in idx]
                faces += [(idx[0], idx[k], idx[k + 1]) for k in range(1, len(idx) - 1)]
        except (ValueError, IndexError):
            raise VesselError(f"{path.name} line {n}: cannot read {line.strip()[:60]!r}") from None
    if len(verts) < 3 or not faces:
        raise VesselError(f"{path.name} has no mesh (needs v and f lines)")
    v = np.array(verts, dtype=float)
    f = np.array(faces, dtype=np.int64)
    if f.min() < 0 or f.max() >= len(v) or v.shape[1] != 3:
        raise VesselError(f"{path.name}: a face uses a vertex that does not exist")
    c = np.array(cols, dtype=float)
    if c.max() > 1.0:
        c = c / 255
    return v, c, f


def measure_obj(path) -> tuple[VesselMeasures, bool]:
    """Measure any OBJ by slicing it like a vessel (Z up). Returns (measures, watertight)."""
    v, c, f = _parse_obj(Path(path))
    keys = np.round(v / WELD).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    v, c, f = v[first], c[first], inverse.reshape(-1)[f]
    f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
    if not len(f):
        raise VesselError("every face is degenerate")
    edges = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
    uniq, counts = np.unique(edges, axis=0, return_counts=True)
    watertight = bool(np.all(counts == 2))
    v = v - [(v[:, 0].min() + v[:, 0].max()) / 2, (v[:, 1].min() + v[:, 1].max()) / 2, v[:, 2].min()]
    top = float(v[:, 2].max())
    rad = np.hypot(v[:, 0], v[:, 1])
    tol = 1e-6 + 1e-6 * top
    hs, rs, colors = [], [], []
    for level in (0.0, top):
        on = np.where(np.abs(v[:, 2] - level) < tol)[0]
        k = on[np.argmax(rad[on])]
        hs.append(level), rs.append(float(rad[k])), colors.append(_hex(c[k]))
    p0, p1 = v[uniq[:, 0]], v[uniq[:, 1]]
    c0, c1 = c[uniq[:, 0]], c[uniq[:, 1]]
    for level in np.linspace(0, top, SAMPLES + 1)[1:-1]:
        cross = np.where((p0[:, 2] - level) * (p1[:, 2] - level) < 0)[0]
        if not len(cross):
            continue
        t = (level - p0[cross, 2]) / (p1[cross, 2] - p0[cross, 2])
        pts = p0[cross] + t[:, None] * (p1[cross] - p0[cross])
        k = int(np.argmax(np.hypot(pts[:, 0], pts[:, 1])))
        hs.insert(-1, float(level)), rs.insert(-1, float(np.hypot(*pts[k, :2])))
        colors.insert(-1, _hex(c0[cross[k]] + t[k] * (c1[cross[k]] - c0[cross[k]])))
    h, r = np.array(hs), np.array(rs)
    if top <= 0:
        raise VesselError("the mesh is flat (zero height)")
    a, b, cc = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    volume = abs(float(np.einsum("ij,ij->i", a, np.cross(b, cc)).sum()) / 6)
    outer = float(np.trapezoid(np.pi * r * r, h))
    capacity = (outer - volume) * 1000 if watertight else float("nan")

    def color(height: float) -> str:
        return colors[int(np.argmin(np.abs(h - height)))]

    return _measures(h, r, capacity, _com_height(v, f), color), watertight
