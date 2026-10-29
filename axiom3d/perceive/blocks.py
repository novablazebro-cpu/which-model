"""Block perception: the model as text (boxes, contacts, painted faces) and a numeric diff between versions."""

from __future__ import annotations

from collections import Counter

from axiom3d.model.blocks import DEFAULT_KEY, FACES, BlockModel, face_size, measure_blocks, pixel_color
from axiom3d.model.vessel import color_name

AXIS = {"front": "-Y", "back": "+Y", "left": "+X", "right": "-X", "top": "+Z", "bottom": "-Z"}
LETTER = {name: letter for letter, name in DEFAULT_KEY.items()}


def _corner(c) -> str:
    return "[" + ", ".join(str(v) for v in c) + "]"


def face_letters(box, face) -> list[str]:
    cols, rows = face_size(box, face)
    return ["".join(LETTER[color_name(pixel_color(box, face, r, c))] for c in range(cols)) for r in range(rows)]


def describe_blocks(model: BlockModel | None) -> str:
    if model is None or not model.boxes:
        return "BLOCKS: no boxes yet. Call add_box(name, low=[x, y, z], high=[x, y, z]) in whole pixels."
    m = measure_blocks(model)
    lines = [
        "BLOCKS (Z up, pixels; the model faces -Y, its left is +X):",
        f"  width {m.width} (x {m.low[0]}..{m.high[0]}) · depth {m.depth} (y {m.low[1]}..{m.high[1]}) · "
        f"height {m.height} (z {m.low[2]}..{m.high[2]})",
        "BOXES (low -> high; size wide x deep x tall; colour):",
    ]
    width = max(len(b.name) for b in model.boxes)
    for b in model.boxes:
        lines.append(f"  {b.name:<{width}}  {_corner(b.low)} -> {_corner(b.high)}  "
                     f"{b.size[0]} x {b.size[1]} x {b.size[2]}  {color_name(b.color)}")
    kinds = []
    for a, b in m.contacts:
        shared = [min(x1, y1) - max(x0, y0) for x0, x1, y0, y1 in
                  zip(model.get(a).low, model.get(a).high, model.get(b).low, model.get(b).high)]
        kinds.append(f"{a}-{b} ({'overlap' if all(d > 0 for d in shared) else 'face' if sum(d > 0 for d in shared) == 2 else 'edge'})")
    lines.append(f"CONTACTS: {', '.join(kinds) or 'none'}")
    lines.append(f"  floating: {', '.join(m.floating) or 'none'} · overlapping: "
                 f"{', '.join(f'{a}+{b}' for a, b, _ in m.overlaps) or 'none'} · "
                 f"mirror image across x = 0: {'yes' if m.symmetric else 'no'}")
    painted = [(b, f) for b in model.boxes for f in FACES if b.grid(f)]
    if painted:
        lines.append("PAINTED FACES (as seen looking at each face from outside, top row first; "
                     + " ".join(f"{k}={v}" for k, v in DEFAULT_KEY.items()) + "):")
        for b, f in painted:
            cols, rows = face_size(b, f)
            lines.append(f"  {b.name} {f} ({AXIS[f]}), {cols} wide x {rows} tall:")
            lines += [f"    {row}" for row in face_letters(b, f)]
    return "\n".join(lines)


def _counts(box, face) -> str:
    c = Counter(color_name(pixel_color(box, face, r, k)) for r in range(face_size(box, face)[1])
                for k in range(face_size(box, face)[0]))
    return ", ".join(f"{n} {name}" for name, n in c.most_common())


def blocks_diff(before: BlockModel | None, after: BlockModel | None) -> list[str]:
    before, after = before or BlockModel(()), after or BlockModel(())
    lines = []
    for b in after.boxes:
        old = before.get(b.name)
        if old is None:
            lines.append(f"  + box {b.name} {_corner(b.low)} -> {_corner(b.high)} "
                         f"({b.size[0]} x {b.size[1]} x {b.size[2]}, {color_name(b.color)})")
            continue
        if (old.low, old.high) != (b.low, b.high):
            lines.append(f"  box {b.name} {_corner(old.low)} -> {_corner(old.high)}  became  "
                         f"{_corner(b.low)} -> {_corner(b.high)}")
        if old.color != b.color:
            lines.append(f"  box {b.name} colour {color_name(old.color)} -> {color_name(b.color)}")
        for f in FACES:
            if old.grid(f) != b.grid(f):
                lines.append(f"  painted {b.name} {f} ({AXIS[f]}): {_counts(b, f)}" if b.grid(f)
                             else f"  paint removed from {b.name} {f} (its size changed)")
    lines += [f"  - box {b.name}" for b in before.boxes if after.get(b.name) is None]
    ma, mb = measure_blocks(before), measure_blocks(after)
    for key in ("width", "depth", "height"):
        if getattr(ma, key) != getattr(mb, key):
            lines.append(f"  model {key} {getattr(ma, key)} -> {getattr(mb, key)}")
    return lines
