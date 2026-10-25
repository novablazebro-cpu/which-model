"""Block models: axis-aligned boxes measured in Minecraft pixels, with pixel paint on their faces.

The model faces -Y and its left is +X, like the mannequin. 16 px = 1 block = 1 m on export.
Every face is painted as seen looking at it from outside, top row first:

    face    top row        columns, left to right
    front   +Z up          -X -> +X   (the viewer's left is the model's right)
    back    +Z up          +X -> -X
    left    +Z up          -Y -> +Y
    right   +Z up          +Y -> -Y
    top     the back edge  -X -> +X
    bottom  the front edge -X -> +X
"""

from __future__ import annotations

import functools
import re
from collections import Counter, deque
from dataclasses import dataclass

import numpy as np

from axiom3d.mesh import Mesh
from axiom3d.model.vessel import PALETTE, parse_color

PX = 1 / 16  # metres per pixel on export
LIMIT = 64
MAX_BOXES = 32
FACES = ("front", "back", "left", "right", "top", "bottom")
FACE_ALIASES = {"-y": "front", "+y": "back", "+x": "left", "-x": "right", "+z": "top", "-z": "bottom"}
DEFAULT_KEY = {"g": "green", "k": "black", "w": "white", "r": "red", "b": "blue", "y": "yellow", "o": "gold"}
KEEP = "."
_NAME = re.compile(r"[A-Za-z0-9_\-]{1,32}")


class BlocksError(ValueError):
    """A block command that cannot be applied, with what to fix."""


@dataclass(frozen=True)
class Box:
    name: str
    low: tuple[int, int, int]
    high: tuple[int, int, int]
    color: str  # #rrggbb, the colour of every unpainted pixel
    paint: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...] = ()  # (face, rows of #rrggbb)

    def grid(self, face: str) -> tuple[tuple[str, ...], ...] | None:
        return dict(self.paint).get(face)

    @property
    def size(self) -> tuple[int, int, int]:
        return tuple(h - lo for lo, h in zip(self.low, self.high))

    @property
    def center(self) -> tuple[float, float, float]:
        return tuple((lo + h) / 2 for lo, h in zip(self.low, self.high))


@dataclass(frozen=True)
class BlockModel:
    boxes: tuple[Box, ...] = ()

    def get(self, name: str) -> Box | None:
        return next((b for b in self.boxes if b.name == name), None)


@dataclass(frozen=True)
class BlockMeasures:
    low: tuple[int, int, int]
    high: tuple[int, int, int]
    width: int  # along X
    depth: int  # along Y
    height: int  # along Z
    contacts: tuple[tuple[str, str], ...]
    floating: tuple[str, ...]
    overlaps: tuple[tuple[str, str, int], ...]  # (a, b, shared volume in px^3)
    below_ground: tuple[str, ...]
    symmetric: bool  # a mirror image of itself across x = 0


def _frame(box: Box, face: str):
    """(top-left corner, column direction, row direction, columns, rows) of a face seen from outside."""
    (x0, y0, z0), (x1, y1, z1) = box.low, box.high
    return {
        "front": ((x0, y0, z1), (1, 0, 0), (0, 0, -1), x1 - x0, z1 - z0),
        "back": ((x1, y1, z1), (-1, 0, 0), (0, 0, -1), x1 - x0, z1 - z0),
        "left": ((x1, y0, z1), (0, 1, 0), (0, 0, -1), y1 - y0, z1 - z0),
        "right": ((x0, y1, z1), (0, -1, 0), (0, 0, -1), y1 - y0, z1 - z0),
        "top": ((x0, y1, z1), (1, 0, 0), (0, -1, 0), x1 - x0, y1 - y0),
        "bottom": ((x0, y0, z0), (1, 0, 0), (0, 1, 0), x1 - x0, y1 - y0),
    }[face]


def face_size(box: Box, face: str) -> tuple[int, int]:
    """(columns, rows) of a face: its width and height as seen from outside."""
    *_, cols, rows = _frame(box, face)
    return cols, rows


def pixel_color(box: Box, face: str, row: int, col: int) -> str:
    grid = box.grid(face)
    return grid[row][col] if grid else box.color


def face_name(text) -> str:
    key = str(text).strip().lower()
    key = FACE_ALIASES.get(key, key)
    if key not in FACES:
        raise BlocksError(f"unknown face {text!r}; use {', '.join(FACES)} (front faces -Y, left is +X)")
    return key


# ---- commands --------------------------------------------------------------------------------------

def _corner(value, what: str) -> tuple[int, int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise BlocksError(f"{what} must be [x, y, z] (got {value!r})")
    out = []
    for v in value:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not float(v).is_integer():
            raise BlocksError(f"{what} must be whole pixels (integers); got {v!r}")
        if abs(v) > LIMIT:
            raise BlocksError(f"{what}: coordinates must stay within ±{LIMIT} px (got {v!r})")
        out.append(int(v))
    return tuple(out)


def _color(text) -> str:
    try:
        return parse_color(text)
    except ValueError:
        raise BlocksError(f"unknown colour {text!r}; use one of {', '.join(PALETTE)} or #rrggbb") from None


def _add_box(model: BlockModel, cmd: dict) -> BlockModel:
    name = cmd.get("name")
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise BlocksError(f"a box needs a name of 1-32 letters, digits, - or _ (got {name!r})")
    low, high = _corner(cmd.get("low"), "low"), _corner(cmd.get("high"), "high")
    for axis, a, b in zip("xyz", low, high):
        if b <= a:
            raise BlocksError(f"high must be greater than low on every axis: {axis} goes {a} -> {b}, so the box "
                              f"has no {'width' if axis == 'x' else 'depth' if axis == 'y' else 'height'}")
    new = Box(name, low, high, _color(cmd.get("color", "green")))
    old = model.get(name)
    if old is None:
        if len(model.boxes) >= MAX_BOXES:
            raise BlocksError(f"at most {MAX_BOXES} boxes; remove one first")
        return BlockModel(model.boxes + (new,))
    kept = tuple((f, g) for f, g in old.paint if face_size(old, f) == face_size(new, f))
    new = Box(name, low, high, new.color, kept)
    return BlockModel(tuple(new if b.name == name else b for b in model.boxes))


def _remove_box(model: BlockModel, cmd: dict) -> BlockModel:
    name = cmd.get("name")
    if model.get(name) is None:
        raise BlocksError(f"unknown box {name!r}; boxes: {', '.join(b.name for b in model.boxes) or 'none yet'}")
    return BlockModel(tuple(b for b in model.boxes if b.name != name))


def _paint_face(model: BlockModel, cmd: dict) -> BlockModel:
    name = cmd.get("box")
    box = model.get(name)
    if box is None:
        raise BlocksError(f"unknown box {name!r}; boxes: {', '.join(b.name for b in model.boxes) or 'none yet'}")
    face = face_name(cmd.get("face"))
    cols, rows = face_size(box, face)
    pixels = cmd.get("pixels")
    if isinstance(pixels, str):
        pixels = pixels.split("/") if "/" in pixels else pixels.split()
    if not isinstance(pixels, (list, tuple)) or not all(isinstance(r, str) for r in pixels):
        raise BlocksError("pixels must be a list of strings, one per row, top row first")
    if len(pixels) != rows or any(len(r) != cols for r in pixels):
        got = f"{len(pixels)} rows" + (f" of {sorted({len(r) for r in pixels})} characters" if pixels else "")
        raise BlocksError(f"the {face} face of {name} is {cols} wide x {rows} tall: give {rows} rows of {cols} "
                          f"characters, top row first, as seen looking at that face (got {got})")
    key = dict(DEFAULT_KEY)
    for ch, colour in (cmd.get("key") or {}).items():
        if not isinstance(ch, str) or len(ch) != 1 or ch == KEEP:
            raise BlocksError(f"key letters must be single characters other than '.' (got {ch!r})")
        key[ch] = colour
    grid = []
    for r, row in enumerate(pixels):
        out = []
        for c, ch in enumerate(row):
            if ch == KEEP:
                out.append(pixel_color(box, face, r, c))
            elif ch in key:
                out.append(_color(key[ch]))
            else:
                raise BlocksError(f"pixel {ch!r} in row {r + 1} is not in the key; use "
                                  f"{', '.join(f'{k}={v}' for k, v in key.items())}, or '.' to keep a pixel")
        grid.append(tuple(out))
    paint = tuple((f, g) for f, g in box.paint if f != face) + ((face, tuple(grid)),)
    new = Box(box.name, box.low, box.high, box.color, paint)
    return BlockModel(tuple(new if b.name == name else b for b in model.boxes))


BLOCK_OPS = {"add_box": _add_box, "remove_box": _remove_box, "paint_face": _paint_face}


def apply_blocks_command(model: BlockModel, cmd: dict) -> BlockModel:
    if not isinstance(cmd, dict) or cmd.get("op") not in BLOCK_OPS:
        op = cmd.get("op") if isinstance(cmd, dict) else cmd
        raise BlocksError(f"unknown block command {op!r}; use {', '.join(BLOCK_OPS)}")
    return BLOCK_OPS[cmd["op"]](model, cmd)


def commands_to_model(cmds) -> tuple[BlockModel, str | None]:
    """Replay commands; stop at the first that fails and say which and why."""
    model = BlockModel(())
    if not isinstance(cmds, list):
        return model, "expected a JSON list of commands"
    for i, cmd in enumerate(cmds, 1):
        try:
            model = apply_blocks_command(model, cmd)
        except BlocksError as e:
            return model, f"command #{i}: {e}"
    return model, None


# ---- geometry and measurement ----------------------------------------------------------------------

def _rgb(hex_color: str) -> tuple[float, float, float]:
    return tuple(int(hex_color[i: i + 2], 16) / 255 for i in (1, 3, 5))


def block_mesh(model: BlockModel, scale: float = 1.0) -> tuple[Mesh, np.ndarray]:
    """One quad per pixel with its own four vertices: flat normals, one colour per quad, no smear."""
    verts, cols_out, faces = [], [], []
    count = 0
    for box in model.boxes:
        for face in FACES:
            origin, right, down, cols, rows = _frame(box, face)
            o, rv, dv = (np.asarray(x, float) for x in (origin, right, down))
            i, j = np.meshgrid(np.arange(rows), np.arange(cols), indexing="ij")
            p00 = o + j[..., None] * rv + i[..., None] * dv
            quad = np.stack([p00, p00 + rv, p00 + rv + dv, p00 + dv], axis=2).reshape(-1, 3)
            verts.append(quad)
            grid = box.grid(face)
            rgb = [_rgb(grid[r][c] if grid else box.color) for r in range(rows) for c in range(cols)]
            cols_out.append(np.repeat(np.asarray(rgb, float), 4, axis=0))
            k = count + 4 * np.arange(rows * cols)[:, None]
            faces.append(np.concatenate([k + [3, 2, 1], k + [3, 1, 0]]))
            count += 4 * rows * cols
    if not verts:
        return Mesh(np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int32)), np.zeros((0, 3), np.float32)
    mesh = Mesh((np.concatenate(verts) * scale).astype(np.float32), np.concatenate(faces).astype(np.int32))
    return mesh, np.concatenate(cols_out).astype(np.float32)


def _shared(a: Box, b: Box) -> tuple[int, int, int] | None:
    """Per-axis overlap lengths of two closed boxes, or None when they are apart."""
    out = []
    for lo1, hi1, lo2, hi2 in zip(a.low, a.high, b.low, b.high):
        d = min(hi1, hi2) - max(lo1, lo2)
        if d < 0:
            return None
        out.append(d)
    return tuple(out)


def _mirror(b: Box) -> tuple:
    return ((-b.high[0], b.low[1], b.low[2]), (-b.low[0], b.high[1], b.high[2]))


@functools.lru_cache(maxsize=64)
def measure_blocks(model: BlockModel) -> BlockMeasures:
    boxes = model.boxes
    if not boxes:
        return BlockMeasures((0, 0, 0), (0, 0, 0), 0, 0, 0, (), (), (), (), True)
    low = tuple(min(b.low[k] for b in boxes) for k in range(3))
    high = tuple(max(b.high[k] for b in boxes) for k in range(3))
    contacts, overlaps = [], []
    links = {b.name: set() for b in boxes}
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            shared = _shared(a, b)
            if shared is None or sum(d > 0 for d in shared) == 0:
                continue  # apart, or touching at a single corner point
            contacts.append((a.name, b.name))
            links[a.name].add(b.name)
            links[b.name].add(a.name)
            if all(d > 0 for d in shared):
                overlaps.append((a.name, b.name, int(np.prod(shared))))
    grounded = {b.name for b in boxes if b.low[2] <= 0}
    todo = deque(grounded)
    while todo:
        for nxt in links[todo.popleft()] - grounded:
            grounded.add(nxt)
            todo.append(nxt)
    symmetric = Counter((b.low, b.high) for b in boxes) == Counter(_mirror(b) for b in boxes)
    return BlockMeasures(
        low, high, high[0] - low[0], high[1] - low[1], high[2] - low[2], tuple(contacts),
        tuple(b.name for b in boxes if b.name not in grounded), tuple(overlaps),
        tuple(b.name for b in boxes if b.low[2] < 0), symmetric,
    )
