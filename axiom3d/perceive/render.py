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


def _rasterize(tris: np.ndarray, colors: np.ndarray, camera: Camera, size: int, base: np.ndarray,
               light: np.ndarray = LIGHT, ids: np.ndarray | None = None):
    """Shaded z-buffer render. With `ids` (one int per triangle), also returns which id each pixel shows (-1 = none)."""
    img = base.astype(float).copy()
    depth = np.full((size, size), np.inf)
    idbuf = np.full((size, size), -1)
    want_ids = ids is not None
    ids = np.full(len(tris), -1) if ids is None else ids
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    shade = 0.45 + 0.55 * np.abs(normals @ light) / np.where(lengths < 1e-12, 1.0, lengths)
    proj = camera.project(tris.reshape(-1, 3), size).reshape(-1, 3, 3)
    for (a, b, c), color, s, tid in zip(proj, colors, shade, ids):
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
        idbuf[y0 : y1 + 1, x0 : x1 + 1][hit] = tid
    return (img, idbuf) if want_ids else img


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


VESSEL_LIGHT = np.array([-0.4, -0.8, 0.45]) / np.linalg.norm([-0.4, -0.8, 0.45])
INK = (35, 40, 46)
FAINT = (150, 156, 162)
OUTLINE = (128, 134, 142)


def _tag(draw: ImageDraw.ImageDraw, xy, text: str, font, fill=INK) -> None:
    """Text on a background box, readable over any paint."""
    x0, y0, x1, y1 = draw.textbbox(xy, text, font=font)
    draw.rectangle([x0 - 2, y0 - 1, x1 + 2, y1 + 1], fill=BACKGROUND)
    draw.text(xy, text, fill=fill, font=font)


def _vessel_side(spec, m, size: int) -> Image.Image:
    from axiom3d.model.vessel import display_mesh

    height, rmax = m.height, m.max_diameter / 2
    half = max(0.62 * height, 1.45 * rmax)
    centre = 0.47 * height  # a little headroom for the title
    cam = Camera("SIDE (looking +Y; up = +Z)", np.array([0.0, -3.0, centre]), np.array([0.0, 0.0, centre]),
                 np.array([0.0, 0.0, 1.0]), ortho_half_height=half)
    mesh, vcol = display_mesh(spec, segments=32)  # one colour per triangle: band edges stay sharp
    v = mesh.vertices.astype(float)
    tris = v[mesh.faces]
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    keep = normals[:, 1] < 0  # facing the camera
    colors = vcol[mesh.faces].mean(axis=1)[keep] * 255
    base = Image.new("RGB", (size, size), BACKGROUND)
    img = Image.fromarray(_rasterize(tris[keep], colors, cam, size, np.asarray(base), VESSEL_LIGHT).astype(np.uint8))
    draw = ImageDraw.Draw(img)
    font = _font(max(10, size // 30))

    def px(x, z):
        q = cam.project(np.array([[x, 0.0, z]]), size)[0]
        return float(q[0]), float(q[1])

    ground = px(-half, 0)[1]
    draw.line([(0, ground), (size, ground)], fill=GRID_COLOR, width=1)
    # Height bracket on the right.
    xr = 1.18 * rmax
    (bx, by0), (_, by1) = px(xr, 0), px(xr, height)
    draw.line([(bx, by0), (bx, by1)], fill=INK, width=1)
    for y in (by0, by1):
        draw.line([(bx - 4, y), (bx + 4, y)], fill=INK, width=1)
    _tag(draw, (bx + 6, (by0 + by1) / 2 - 6), f"H {height:.3f}", font)
    (x0, y), (x1, _) = px(-rmax, m.shoulder_height), px(rmax, m.shoulder_height)
    draw.line([(x0, y), (x1, y)], fill=INK, width=1)
    _tag(draw, (x0, y - 17), f"max D {m.max_diameter:.3f} at h {m.shoulder_height:.3f}", font)
    mx, my = px(m.mouth_diameter / 2, height)
    _tag(draw, (mx + 8, my - 2), f"mouth D {m.mouth_diameter:.3f}", font)
    fx, fy = px(m.foot_diameter / 2, 0)
    _tag(draw, (fx + 8, fy - 16), f"foot D {m.foot_diameter:.3f}", font)
    _tag(draw, (6, 4), cam.title, font, fill=(20, 20, 20))
    draw.rectangle([0, 0, size - 1, size - 1], outline=(180, 180, 180))
    return img


def _vessel_profile(spec, m, size: int) -> Image.Image:
    from axiom3d.model.vessel import _rgb
    from axiom3d.perceive.vessel import color_zones

    img = Image.new("RGB", (size, size), BACKGROUND)
    draw = ImageDraw.Draw(img)
    font = _font(max(10, size // 30))
    left, right, top, bottom = 52, size - 14, 28, size - 34
    height, rmax = m.height, max(m.max_diameter / 2, 1e-3)
    rspan = 1.15 * rmax

    def px(r, h):
        return left + (r / rspan) * (right - left), bottom - (h / height) * (bottom - top)

    for h in np.arange(0, height + 1e-9, 0.05 if height > 0.2 else 0.02):
        y = px(0, h)[1]
        draw.line([(left, y), (right, y)], fill=GRID_COLOR, width=1)
        draw.text((6, y - 6), f"{h:.2f}", fill=FAINT, font=font)
    for r in np.arange(0, rspan + 1e-9, 0.02 if rspan > 0.06 else 0.01):
        x = px(r, 0)[0]
        draw.line([(x, top), (x, bottom)], fill=GRID_COLOR, width=1)
        draw.text((x - 10, bottom + 4), f"{r:.2f}", fill=FAINT, font=font)
    for a, b, c in color_zones(spec):  # the paint, as a strip along the axis
        (_, y0), (_, y1) = px(0, a), px(0, b)
        draw.rectangle([left - 10, y1, left - 3, y0], fill=tuple(int(v * 255) for v in _rgb(c)))
    inner = m.h >= spec.wall
    draw.line([px(r - spec.wall, h) for h, r in zip(m.h[inner], m.r[inner]) if r > spec.wall],
              fill=FAINT, width=1)
    draw.line([px(r, h) for h, r in zip(m.h, m.r)], fill=INK, width=3)
    for h, r in spec.profile:
        x, y = px(r, h)
        draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(66, 133, 244))
    sx, sy = px(m.max_diameter / 2, m.shoulder_height)
    _tag(draw, (min(sx + 8, right - 100), sy - 6), f"widest r {m.max_diameter / 2:.3f}", font)
    draw.text((left + 4, top - 22), "PROFILE: radius across, height up (dots = your points)", fill=(20, 20, 20),
              font=font)
    draw.text((right - 120, bottom + 16), "radius (m)", fill=FAINT, font=font)
    draw.rectangle([0, 0, size - 1, size - 1], outline=(180, 180, 180))
    return img


def render_vessel_sheet(spec, size: int = 384) -> Image.Image:
    """Side view with dimensions, beside the profile plot (radius against height)."""
    from axiom3d.model.vessel import measure_cached

    m = measure_cached(spec)
    sheet = Image.new("RGB", (2 * size, size + 24), BACKGROUND)
    sheet.paste(_vessel_side(spec, m, size), (0, 0))
    sheet.paste(_vessel_profile(spec, m, size), (size, 0))
    ImageDraw.Draw(sheet).text(
        (8, size + 5),
        f"height {m.height:.3f} m | max D {m.max_diameter:.3f} | shoulder ratio {m.shoulder_ratio:.2f} | mouth D "
        f"{m.mouth_diameter:.3f} | foot D {m.foot_diameter:.3f} | {m.capacity_l:.1f} L | tip {m.tip_angle_deg:.0f} deg"
        "   (D = diameter, r = radius, metres)",
        fill=(60, 60, 60), font=_font(max(10, size // 34)))
    return sheet


def _blocks_view(tris, colors, normals, box_ids, cam: Camera, size: int, title: str, notes: list[str]) -> Image.Image:
    _, _, forward = cam.basis()
    keep = normals @ forward < 0  # faces turned toward the camera; hides the touching faces between boxes
    base = Image.new("RGB", (size, size), BACKGROUND)
    shaded, ids = _rasterize(tris[keep], colors[keep], cam, size, np.asarray(base), ids=box_ids[keep])
    # Outline every box where the visible box changes, so same-coloured parts stay apart (no hidden lines).
    edge = np.zeros(ids.shape, bool)
    edge[:, 1:] |= ids[:, 1:] != ids[:, :-1]
    edge[1:, :] |= ids[1:, :] != ids[:-1, :]
    shaded[edge] = OUTLINE  # mid grey: never mistaken for black paint or any palette colour
    img = Image.fromarray(shaded.astype(np.uint8))
    draw = ImageDraw.Draw(img)
    font = _font(max(10, size // 28))
    _tag(draw, (6, 4), title, font, fill=(20, 20, 20))
    for i, note in enumerate(notes):
        draw.text((6, size - 16 * (len(notes) - i) - 2), note, fill=FAINT, font=font)
    draw.rectangle([0, 0, size - 1, size - 1], outline=(180, 180, 180))
    return img


def render_blocks_sheet(model, size: int = 320) -> Image.Image:
    """FRONT, RIGHT SIDE, TOP and a three-quarter view of a block model, each labelled with which side is which."""
    from axiom3d.model.blocks import FACES, block_mesh, face_size, measure_blocks

    m = measure_blocks(model)
    mesh, vcol = block_mesh(model)
    v = mesh.vertices.astype(float)
    tris = v[mesh.faces]
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    colors = vcol[mesh.faces].mean(axis=1) * 255
    per_box = [2 * sum(c * r for c, r in (face_size(b, f) for f in FACES)) for b in model.boxes]
    box_ids = np.repeat(np.arange(len(model.boxes)), per_box)  # block_mesh emits boxes in order
    c = (np.array(m.low, float) + np.array(m.high, float)) / 2
    reach = max(m.width, m.depth, m.height, 1)
    half, far = 0.62 * reach, 4.0 * reach
    up, back = np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.0])
    iso = np.array([1.0, -1.4, 0.9]) / np.linalg.norm([1.0, -1.4, 0.9])
    views = [
        (Camera("FRONT (looking at -Y face)", c + [0, -far, 0], c, up, half),
         ["your left = its RIGHT (-X)", "your right = its LEFT (+X)"]),
        (Camera("RIGHT SIDE (its -X side)", c + [-far, 0, 0], c, up, half),
         ["its front (-Y) is on your right"]),
        (Camera("TOP (looking down)", c + [0, 0, far], c, back, half),
         ["its back (+Y) at the top, front at the bottom"]),
        (Camera("3/4 VIEW (front, its left, above)", c + far * iso, c, up, half * 1.1), []),
    ]
    sheet = Image.new("RGB", (2 * size, 2 * size + 24), BACKGROUND)
    for i, (cam, notes) in enumerate(views):
        sheet.paste(_blocks_view(tris, colors, normals, box_ids, cam, size, cam.title, notes),
                    ((i % 2) * size, (i // 2) * size))
    ImageDraw.Draw(sheet).text(
        (8, 2 * size + 5),
        f"width {m.width} px (x {m.low[0]}..{m.high[0]}) | depth {m.depth} (y {m.low[1]}..{m.high[1]}) | "
        f"height {m.height} (z {m.low[2]}..{m.high[2]}) | {len(model.boxes)} boxes | faces -Y, its left is +X",
        fill=(60, 60, 60), font=_font(max(10, size // 30)))
    return sheet


def to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
