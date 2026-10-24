"""Diagnostic renders: labelled multi-view sheets, filmstrips and footprint maps.

A small numpy z-buffer rasterizer, so it runs headless with no GPU. Left parts
are blue, right parts orange, so laterality is visible at a glance.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from axiom3d.conventions import character_axes
from axiom3d.measure import foot_contact
from axiom3d.math3d import quat_to_matrix
from axiom3d.mesh import segment_mesh

LEFT_COLOR = (66, 133, 244)
RIGHT_COLOR = (244, 140, 40)
CENTER_COLOR = (170, 170, 170)
BACKGROUND = (250, 250, 250)
GRID_COLOR = (205, 205, 205)
AXIS_COLORS = {"+X": (220, 50, 50), "+Y": (40, 160, 40), "+Z": (40, 40, 40)}
LIGHT = np.array([0.3, -0.5, 0.8]) / np.linalg.norm([0.3, -0.5, 0.8])
_SIDE_COLORS = {"left": LEFT_COLOR, "right": RIGHT_COLOR, "center": CENTER_COLOR}


@dataclass(frozen=True)
class Camera:
    title: str
    eye: np.ndarray
    target: np.ndarray
    up: np.ndarray
    ortho_half_height: float | None = 1.1
    fov_deg: float = 40.0

    def basis(self):
        f = self.target - self.eye
        f = f / np.linalg.norm(f)
        r = np.cross(f, self.up)
        r = r / np.linalg.norm(r)
        return r, np.cross(r, f), f

    def project(self, pts: np.ndarray, size: int) -> np.ndarray:
        """(N,3) world -> (N,3) of (screen x, screen y, depth)."""
        r, u, f = self.basis()
        d = pts - self.eye
        x, y, z = d @ r, d @ u, d @ f
        if self.ortho_half_height is not None:
            scale = (size / 2) / self.ortho_half_height
            return np.column_stack([size / 2 + x * scale, size / 2 - y * scale, z])
        t = np.tan(np.radians(self.fov_deg) / 2)
        zc = np.maximum(z, 1e-3)
        return np.column_stack([size / 2 + (x / (zc * t)) * size / 2, size / 2 - (y / (zc * t)) * size / 2, z])


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # older Pillow
        return ImageFont.load_default()


def world_triangles(skel, state) -> tuple[np.ndarray, np.ndarray]:
    """All segment triangles in world space (M,3,3) and their base colours (M,3)."""
    tris, colors = [], []
    for seg in skel.segments:
        mesh = segment_mesh(seg)
        pos, rot = state.joint_world[seg.joint]
        v = mesh.vertices.astype(float) @ quat_to_matrix(rot).T + pos
        tris.append(v[mesh.faces])
        colors.append(np.tile(_SIDE_COLORS[seg.side], (len(mesh.faces), 1)))
    return np.concatenate(tris), np.concatenate(colors).astype(float)


def _rasterize(tris: np.ndarray, colors: np.ndarray, camera: Camera, size: int, base: np.ndarray) -> np.ndarray:
    img = base.astype(float).copy()
    depth = np.full((size, size), np.inf)
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    shade = 0.45 + 0.55 * np.abs(normals @ LIGHT) / np.where(lengths < 1e-12, 1.0, lengths)
    proj = camera.project(tris.reshape(-1, 3), size).reshape(-1, 3, 3)
    for (a, b, c), color, s in zip(proj, colors, shade):
        x0, x1 = int(max(0, np.floor(min(a[0], b[0], c[0])))), int(min(size - 1, np.ceil(max(a[0], b[0], c[0]))))
        y0, y1 = int(max(0, np.floor(min(a[1], b[1], c[1])))), int(min(size - 1, np.ceil(max(a[1], b[1], c[1]))))
        if x0 > x1 or y0 > y1 or min(a[2], b[2], c[2]) <= 0:
            continue
        area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        if abs(area) < 1e-9:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((b[0] - xs) * (c[1] - ys) - (b[1] - ys) * (c[0] - xs)) / area
        w1 = ((c[0] - xs) * (a[1] - ys) - (c[1] - ys) * (a[0] - xs)) / area
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        z = w0 * a[2] + w1 * b[2] + w2 * c[2]
        region = depth[y0 : y1 + 1, x0 : x1 + 1]
        hit = inside & (z < region)
        region[hit] = z[hit]
        img[y0 : y1 + 1, x0 : x1 + 1][hit] = color * s
    return img


def _cameras(state) -> list[Camera]:
    p = state.points["pelvis"]
    target = np.array([p[0], p[1], 0.9])
    up = np.array([0.0, 0.0, 1.0])
    return [
        Camera("FRONT (looking +Y; screen-right = +X)", target + [0, -4, 0], target, up),
        Camera("SIDE (looking +X; screen-right = -Y)", target + [-4, 0, 0], target, up),
        Camera("TOP (looking down; screen-up = -Y)", target + [0, 0, 4], target, np.array([0.0, -1.0, 0.0])),
        Camera("PERSP (from front-left, above)", target + [2.2, -2.6, 1.6], target, up, ortho_half_height=None),
    ]


def _draw_ground(draw: ImageDraw.ImageDraw, camera: Camera, target: np.ndarray, size: int) -> None:
    span = np.arange(-2.0, 2.01, 0.5)
    for k in span:
        for a, b in (
            ((target[0] + k, target[1] - 2, 0), (target[0] + k, target[1] + 2, 0)),
            ((target[0] - 2, target[1] + k, 0), (target[0] + 2, target[1] + k, 0)),
        ):
            pa, pb = camera.project(np.array([a, b], dtype=float), size)
            if pa[2] > 0 and pb[2] > 0:
                draw.line([(pa[0], pa[1]), (pb[0], pb[1])], fill=GRID_COLOR, width=1)


def _draw_gizmo(draw: ImageDraw.ImageDraw, camera: Camera, size: int, font) -> None:
    r, u, _ = camera.basis()
    origin = np.array([size * 0.12, size * 0.88])
    for label, axis in (("+X", (1, 0, 0)), ("+Y", (0, 1, 0)), ("+Z", (0, 0, 1))):
        a = np.asarray(axis, dtype=float)
        d = np.array([a @ r, -(a @ u)])
        if np.linalg.norm(d) < 0.2:
            draw.text(tuple(origin + [4, -14]), f"{label} (toward you or away)", fill=AXIS_COLORS[label], font=font)
            continue
        tip = origin + d * size * 0.08
        draw.line([tuple(origin), tuple(tip)], fill=AXIS_COLORS[label], width=2)
        draw.text(tuple(tip + d * 6 - [6, 6]), label, fill=AXIS_COLORS[label], font=font)


def render_view(skel, state, camera: Camera, size: int = 384, label: str | None = None) -> Image.Image:
    base = Image.new("RGB", (size, size), BACKGROUND)
    draw = ImageDraw.Draw(base)
    p = state.points["pelvis"]
    _draw_ground(draw, camera, np.array([p[0], p[1], 0.0]), size)
    tris, colors = world_triangles(skel, state)
    img = Image.fromarray(_rasterize(tris, colors, camera, size, np.asarray(base)).astype(np.uint8))
    draw = ImageDraw.Draw(img)
    font = _font(max(10, size // 32))
    draw.text((6, 4), label or camera.title, fill=(20, 20, 20), font=font)
    _draw_gizmo(draw, camera, size, font)
    draw.rectangle([0, 0, size - 1, size - 1], outline=(180, 180, 180))
    return img


def render_sheet(skel, state, size: int = 384) -> Image.Image:
    sheet = Image.new("RGB", (2 * size, 2 * size), BACKGROUND)
    for i, cam in enumerate(_cameras(state)):
        sheet.paste(render_view(skel, state, cam, size), ((i % 2) * size, (i // 2) * size))
    ImageDraw.Draw(sheet).text((2 * size - 150, 2 * size - 16), f"frame {state.frame}  blue=LEFT orange=RIGHT",
                               fill=(60, 60, 60), font=_font(max(10, size // 36)))
    return sheet


def render_filmstrip(skel, states, size: int = 256) -> Image.Image:
    strip = Image.new("RGB", (len(states) * size, size), BACKGROUND)
    for i, st in enumerate(states):
        cam = _cameras(st)[1]
        strip.paste(render_view(skel, st, cam, size, label=f"SIDE frame {st.frame}"), (i * size, 0))
    return strip


def render_footprints(skel, clip, states, size: int = 384) -> Image.Image:
    """Top-down map: root path, feet in contact, facing arrows. Track forward points up."""
    forward0, left0, _ = character_axes(clip.track.heading_deg)

    def to_track(xy):
        d = np.asarray(xy)[:2] - np.asarray(clip.track.origin_xy)
        return np.array([d @ left0[:2], d @ forward0[:2]])

    pts = [to_track(st.points[n]) for st in states for n in ("left_heel", "left_toe", "right_heel", "right_toe", "pelvis")]
    lo, hi = np.min(pts, axis=0) - 0.3, np.max(pts, axis=0) + 0.3
    scale = (size - 40) / max(hi - lo)
    centre = (lo + hi) / 2

    def px(t):
        return (size / 2 + (t[0] - centre[0]) * scale, size / 2 - (t[1] - centre[1]) * scale)

    img = Image.new("RGB", (size, size), BACKGROUND)
    draw = ImageDraw.Draw(img)
    font = _font(max(10, size // 32))
    draw.line([px(to_track(st.root_position)) for st in states], fill=(120, 120, 120), width=2)
    for st in states:
        for side, color in (("left", LEFT_COLOR), ("right", RIGHT_COLOR)):
            if foot_contact(st, side):
                draw.line([px(to_track(st.points[f"{side}_heel"])), px(to_track(st.points[f"{side}_toe"]))],
                          fill=color, width=4)
    for st in states[:: max(1, len(states) // 4)] + [states[-1]]:
        f, _, _ = character_axes(st.heading_deg)
        a = to_track(st.root_position)
        b = a + 0.25 * np.array([f @ left0, f @ forward0])
        draw.line([px(a), px(b)], fill=(30, 30, 30), width=2)
        draw.text(px(b), f"f{st.frame}", fill=(30, 30, 30), font=font)
    draw.text((6, 4), "FOOTPRINTS (top-down, track forward = up)", fill=(20, 20, 20), font=font)
    return img


def to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
