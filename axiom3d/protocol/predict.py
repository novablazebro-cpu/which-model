"""A small, safe prediction language. The model states what it expects; the tool measures.

Grammar (case-insensitive):
  <subject> (< | > | <= | >=) <number | subject>
  <subject> ~= <number> ± <tolerance>          (also +- or +/-)
  <subject> in [<low>, <high>]
  <point> (in_front_of | behind | left_of | right_of | above | below) <point>
  <point> on_ground
  color(<height>) is <name | #rrggbb>           (vessels)
  pixel(<box>, <face>, <row>, <col>) is <name | #rrggbb>   (blocks; row 1 = top, col 1 = left, as seen)
  subjects: <point>.(x|y|z|height|forward|left), root.(x|y|z|height|forward|left|heading),
            <channel> such as left_hip.flexion, (slide|min_height|max_height)(<point>),
            vessel.(height|max_diameter|shoulder_ratio|...|capacity|tip_angle),
            box.<name>.(min_x|max_x|...|size_z|center_x|...), model.(width|depth|height|min_z|max_z)
  frames:   optional @N, @A..B or @all (after the subject or at the end)
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

import numpy as np

from axiom3d.conventions import CONTACT_EPS
from axiom3d.measure import relation, track_coords
from axiom3d.model.blocks import BlocksError, face_name, face_size, measure_blocks, pixel_color
from axiom3d.model.vessel import ATTRS as VESSEL_ATTRS
from axiom3d.model.vessel import VesselError, color_name, measure_cached, parse_color

POINT_ATTRS = ("x", "y", "z", "height", "forward", "left")
ROOT_ATTRS = POINT_ATTRS + ("heading",)
RELATIONS = ("in_front_of", "behind", "left_of", "right_of", "above", "below")
METRICS = ("slide", "min_height", "max_height")
PRECISE_M = 0.15
PRECISE_DEG = 20.0
PRECISE_SLIDE = 0.05
# Vessels are small: a length is precise within 2 cm.
PRECISE_VESSEL = {"shoulder_ratio": 0.05, "capacity": 0.5, "tip_angle": 5.0}
PRECISE_VESSEL_M = 0.02
# Blocks are whole pixels: a length is precise within 1 px.
PRECISE_PX = 1.0
BOX_ATTRS = tuple(f"{k}_{a}" for k in ("min", "max", "size", "center") for a in "xyz")
MODEL_ATTRS = ("width", "depth", "height", "min_z", "max_z")

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?"
_NAME = r"[a-z_]+(?:\.[a-z_]+)?"
_METRIC = r"(?:slide|min_height|max_height)\(\s*[a-z_]+\s*\)"
_BOX = r"box\.[a-z0-9_]+\.[a-z_]+"
_SUBJ = rf"(?:{_METRIC}|{_BOX}|{_NAME})"
_FRAMES = re.compile(r"@\s*(all|\d+\s*\.\.\s*\d+|\d+)")


class PredictionError(ValueError):
    pass


@dataclass(frozen=True)
class Subject:
    kind: str  # "point" | "root" | "channel" | "metric" | "vessel" | "box" | "model"
    name: str
    attr: str | None = None


@dataclass(frozen=True)
class Frames:
    kind: str = "default"  # "default" | "one" | "range" | "all"
    a: int | None = None
    b: int | None = None


@dataclass(frozen=True)
class Prediction:
    kind: str  # "compare" | "relation" | "metric" | "color" | "pixel"
    op: str
    subject: Subject | None = None
    other: Subject | None = None
    value: float | None = None
    tol: float | None = None
    low: float | None = None
    high: float | None = None
    point: str | None = None
    other_point: str | None = None
    color: str | None = None  # a palette name or #rrggbb
    box: str | None = None  # pixel predictions: which box, face, row and column (1-based, as seen)
    face: str | None = None
    row: int | None = None
    col: int | None = None
    frames: Frames = Frames()
    text: str = field(default="", compare=False)


@dataclass
class Outcome:
    passed: bool
    measured: str


def _normalize(text: str) -> str:
    t = text.replace("−", "-").replace("+/-", "±").replace("+-", "±").lower()
    return re.sub(r"\s+", " ", t).strip()


def _suggest(bad: str, candidates: list[str]) -> str:
    close = difflib.get_close_matches(bad, candidates, n=10, cutoff=0.3)
    return ", ".join(close or candidates[:10])


def _point(name: str, skel) -> str:
    if name not in skel.point_names():
        raise PredictionError(f"unknown point {name!r}; closest: {_suggest(name, skel.point_names())}")
    return name


def _subject(token: str, skel) -> Subject:
    m = re.fullmatch(r"(slide|min_height|max_height)\(\s*([a-z_]+)\s*\)", token)
    if m:
        return Subject("metric", m.group(1), _point(m.group(2), skel))
    head, _, attr = token.partition(".")
    if head == "box":
        name, _, battr = attr.partition(".")
        if battr not in BOX_ATTRS:
            raise PredictionError(f"unknown box measurement {token!r}; use box.<name>.<one of "
                                  f"{', '.join(BOX_ATTRS)}>, e.g. box.head.min_z")
        return Subject("box", name, battr)
    if head == "model":
        if attr not in MODEL_ATTRS:
            raise PredictionError(f"unknown model measurement {token!r}; use one of: "
                                  f"{', '.join('model.' + a for a in MODEL_ATTRS)}")
        return Subject("model", "model", attr)
    if head == "vessel":
        if attr not in VESSEL_ATTRS:
            raise PredictionError(f"unknown vessel measurement {token!r}; use one of: "
                                  f"{', '.join('vessel.' + a for a in VESSEL_ATTRS)}")
        return Subject("vessel", "vessel", attr)
    if not attr:
        raise PredictionError(f"{token!r} needs an attribute, e.g. {token}.z or {token}.forward")
    if head == "root" and attr in ROOT_ATTRS:
        return Subject("root", "root", attr)
    if token in skel.channels():
        return Subject("channel", token)
    if head in skel.point_names() and attr in POINT_ATTRS:
        return Subject("point", head, attr)
    candidates = skel.channels() + [f"root.{a}" for a in ROOT_ATTRS] + [
        f"{p}.{a}" for p in skel.point_names() for a in POINT_ATTRS
    ]
    raise PredictionError(f"unknown subject {token!r}; closest: {_suggest(token, candidates)}")


def _frames(text: str) -> tuple[str, Frames]:
    found = _FRAMES.findall(text)
    if len(found) > 1:
        raise PredictionError("use at most one frame selector (@N, @A..B or @all)")
    if not found:
        return text, Frames()
    sel = found[0].replace(" ", "")
    text = _FRAMES.sub(" ", text, count=1)
    text = re.sub(r"\s+", " ", text).strip()
    if sel == "all":
        return text, Frames("all")
    if ".." in sel:
        a, b = (int(x) for x in sel.split(".."))
        if a > b:
            raise PredictionError(f"frame range @{a}..{b} runs backward")
        return text, Frames("range", a, b)
    return text, Frames("one", int(sel))


def _substitute(body: str, variables: dict | None) -> str:
    """Replace $name with the calculator variable's value."""
    def value(m):
        name = m.group(1)
        if not variables or name not in variables:
            raise PredictionError(f"unknown variable ${name}; set it with calc, e.g. calc('{name} = 0.36')")
        v = variables[name]
        if isinstance(v, (list, tuple)):
            raise PredictionError(f"${name} is a vector; use a number, e.g. calc('{name}_x = {name}.x')")
        return f"{float(v):.10g}"
    return re.sub(r"\$([a-z_][a-z0-9_]*)", value, body)


def parse_prediction(text: str, skel, variables: dict | None = None) -> Prediction:
    if not isinstance(text, str) or not text.strip():
        raise PredictionError("empty prediction")
    body, frames = _frames(_substitute(_normalize(text), variables))
    m = re.fullmatch(rf"colou?r\( ?({_NUM}) ?\) is (#?[a-z0-9]+)", body)
    if m:
        try:
            parse_color(m.group(2))
        except VesselError as e:
            raise PredictionError(str(e)) from None
        return Prediction("color", "is", value=float(m.group(1)), color=m.group(2), frames=frames, text=text)
    m = re.fullmatch(r"pixel\( ?([a-z0-9_]+) ?, ?([a-z+\-]+) ?, ?(\d+) ?, ?(\d+) ?\) is (#?[a-z0-9]+)", body)
    if m:
        try:
            face = face_name(m.group(2))
            parse_color(m.group(5))
        except (BlocksError, VesselError) as e:
            raise PredictionError(str(e)) from None
        row, col = int(m.group(3)), int(m.group(4))
        if row < 1 or col < 1:
            raise PredictionError("pixel rows and columns count from 1: row 1 is the top row, column 1 the left one")
        return Prediction("pixel", "is", box=m.group(1), face=face, row=row, col=col, color=m.group(5),
                          frames=frames, text=text)
    m = re.fullmatch(r"([a-z_]+) on_ground", body)
    if m:
        return Prediction("relation", "on_ground", point=_point(m.group(1), skel), frames=frames, text=text)
    m = re.fullmatch(rf"([a-z_]+) ({'|'.join(RELATIONS)}) ([a-z_]+)", body)
    if m:
        if m.group(1) == m.group(3):
            raise PredictionError(f"{text!r} compares {m.group(1)} with itself; predict something the edit changes")
        return Prediction("relation", m.group(2), point=_point(m.group(1), skel),
                          other_point=_point(m.group(3), skel), frames=frames, text=text)
    m = re.fullmatch(rf"({_SUBJ}) in \[\s*({_NUM})\s*,\s*({_NUM})\s*\]", body)
    if m:
        subj, low, high = _subject(m.group(1), skel), float(m.group(2)), float(m.group(3))
        if low > high:
            raise PredictionError(f"range [{low}, {high}] is backward")
        return Prediction(_kind(subj), "in", subj, low=low, high=high, frames=frames, text=text)
    m = re.fullmatch(rf"({_SUBJ}) ?~= ?({_NUM}) ?± ?({_NUM})", body)
    if m:
        subj = _subject(m.group(1), skel)
        tol = abs(float(m.group(3)))
        return Prediction(_kind(subj), "~=", subj, value=float(m.group(2)), tol=tol, frames=frames, text=text)
    m = re.fullmatch(rf"({_SUBJ}) ?(<=|>=|<|>) ?({_NUM})", body)
    if m:
        subj = _subject(m.group(1), skel)
        return Prediction(_kind(subj), m.group(2), subj, value=float(m.group(3)), frames=frames, text=text)
    m = re.fullmatch(rf"({_SUBJ}) ?(<=|>=|<|>) ?({_SUBJ})", body)
    if m:
        subj, other = _subject(m.group(1), skel), _subject(m.group(3), skel)
        if subj == other:
            raise PredictionError(f"{text!r} compares {m.group(1)} with itself; predict something the edit changes")
        return Prediction("compare", m.group(2), subj, other=other, frames=frames, text=text)
    raise PredictionError(
        f"can't parse {text!r}. Examples: 'left_toe.forward ~= 0.36 ± 0.05', 'left_toe in_front_of pelvis @24', "
        "'slide(right_heel) < 0.02', 'left_knee.flexion in [10, 40] @12'"
    )


def _kind(subj: Subject) -> str:
    return "metric" if subj.kind == "metric" else "compare"


def _is_angle(subj: Subject) -> bool:
    return subj.kind == "channel" or (subj.kind == "root" and subj.attr == "heading")


def is_precise(p: Prediction) -> bool:
    if p.kind in ("relation", "color", "pixel") or p.other is not None:
        return True
    if p.subject.kind in ("box", "model"):
        limit = PRECISE_PX
    elif p.subject.kind == "vessel":
        limit = PRECISE_VESSEL.get(p.subject.attr, PRECISE_VESSEL_M)
    else:
        limit = PRECISE_DEG if _is_angle(p.subject) else PRECISE_M
    if p.op == "~=":
        return p.tol <= limit
    if p.op == "in":
        return p.high - p.low <= limit
    if p.kind == "metric" and p.subject.name == "slide" and p.op in ("<", "<="):
        return p.value <= PRECISE_SLIDE
    return False


def _select(frames: Frames, states, default_frame: int, metric: bool) -> list:
    first, last = states[0].frame, states[-1].frame
    if frames.kind == "default":
        wanted = list(range(first, last + 1)) if metric else [default_frame]
    elif frames.kind == "all":
        wanted = list(range(first, last + 1))
    elif frames.kind == "one":
        wanted = [frames.a]
    else:
        wanted = list(range(frames.a, frames.b + 1))
    if wanted[0] < first or wanted[-1] > last:
        raise PredictionError(f"frames must be within {first}..{last}")
    return [states[f - first] for f in wanted]


def _value(subj: Subject, state, clip) -> float:
    if subj.kind in ("box", "model"):
        return _blocks_value(subj, clip)
    if subj.kind == "vessel":
        if clip.vessel is None:
            return float("nan")  # nothing measured yet: never equal to a prediction
        return float(getattr(measure_cached(clip.vessel), VESSEL_ATTRS[subj.attr]))
    if subj.kind == "channel":
        return float(state.angles[subj.name])
    p = state.root_position if subj.kind == "root" else state.points[subj.name]
    if subj.attr == "heading":
        return float(state.heading_deg)
    if subj.attr in ("forward", "left"):
        f, l = track_coords(clip, p[:2])
        return f if subj.attr == "forward" else l
    return float(p["xyz".index(subj.attr)] if subj.attr in ("x", "y", "z") else p[2])


def _blocks_value(subj: Subject, clip) -> float:
    model = clip.blocks
    if subj.kind == "model":
        if model is None or not model.boxes:
            return float("nan")
        m = measure_blocks(model)
        return float({"width": m.width, "depth": m.depth, "height": m.height, "min_z": m.low[2],
                      "max_z": m.high[2]}[subj.attr])
    box = model.get(subj.name) if model else None
    if box is None:
        return float("nan")  # no such box (yet): never equal to a prediction
    kind, axis = subj.attr.split("_")
    k = "xyz".index(axis)
    return float({"min": box.low[k], "max": box.high[k], "size": box.size[k], "center": box.center[k]}[kind])


def _pixel(p: Prediction, clip) -> Outcome:
    box = clip.blocks.get(p.box) if clip.blocks else None
    where = f"pixel({p.box}, {p.face}, {p.row}, {p.col})"
    if box is None:
        return Outcome(False, f"{where} = none (no box {p.box!r})")
    cols, rows = face_size(box, p.face)
    if p.row > rows or p.col > cols:
        return Outcome(False, f"{where} = none (the {p.face} face of {p.box} is {cols} wide x {rows} tall)")
    found = pixel_color(box, p.face, p.row - 1, p.col - 1)
    target = parse_color(p.color)
    ok = found == target if p.color.startswith("#") else color_name(found) == p.color
    return Outcome(ok, f"{where} = {found} ({color_name(found)})")


def _metric(subj: Subject, chosen) -> float:
    pts = np.array([s.points[subj.attr] for s in chosen])
    if subj.name == "slide":
        return float(np.max(np.linalg.norm(pts[:, :2] - pts[0, :2], axis=1)))
    return float(pts[:, 2].min() if subj.name == "min_height" else pts[:, 2].max())


def _label(subj: Subject) -> str:
    if subj.kind == "metric":
        return f"{subj.name}({subj.attr})"
    if subj.kind == "box":
        return f"box.{subj.name}.{subj.attr}"
    return subj.name if subj.kind == "channel" else f"{subj.name}.{subj.attr}"


def _holds(op: str, v: float, p: Prediction, other: float | None = None) -> bool:
    target = other if other is not None else p.value
    if op == "~=":
        return abs(v - p.value) <= p.tol
    if op == "in":
        return p.low <= v <= p.high
    return {"<": v < target, ">": v > target, "<=": v <= target, ">=": v >= target}[op]


_REL_TEXT = {
    "in_front_of": ("forward", 1, "in front of", "behind"),
    "behind": ("forward", -1, "in front of", "behind"),
    "left_of": ("left", 1, "left of", "right of"),
    "right_of": ("left", -1, "left of", "right of"),
    "above": ("up", 1, "above", "below"),
    "below": ("up", -1, "above", "below"),
}


def _color(p: Prediction, clip) -> Outcome:
    if clip.vessel is None:
        return Outcome(False, f"color({p.value:.3f}) = none (no profile yet)")
    found = measure_cached(clip.vessel).color_at(p.value)
    target = parse_color(p.color)
    ok = found == target if p.color.startswith("#") else color_name(found) == p.color
    return Outcome(ok, f"color({p.value:.3f}) = {found} ({color_name(found)})")


def evaluate_prediction(p: Prediction, skel, clip, states, default_frame: int) -> Outcome:
    if p.kind == "color":
        return _color(p, clip)
    if p.kind == "pixel":
        return _pixel(p, clip)
    chosen = _select(p.frames, states, default_frame, metric=p.kind == "metric")
    if p.kind == "metric":
        v = _metric(p.subject, chosen)
        span = f"{chosen[0].frame}..{chosen[-1].frame}"
        return Outcome(_holds(p.op, v, p), f"{_label(p.subject)} = {v:.3f} over frames {span}")
    for s in chosen:
        if p.kind == "relation":
            if p.op == "on_ground":
                z = float(s.points[p.point][2])
                ok, measured = z <= CONTACT_EPS, f"{p.point} is {z:.3f} m above the ground @{s.frame}"
            else:
                key, sign, pos, neg = _REL_TEXT[p.op]
                d = relation(s, p.point, p.other_point)[key]
                ok = sign * d > 0
                measured = f"{p.point} is {abs(d):.3f} m {pos if d >= 0 else neg} {p.other_point} @{s.frame}"
        else:
            v = _value(p.subject, s, clip)
            other = _value(p.other, s, clip) if p.other is not None else None
            ok = _holds(p.op, v, p, other)
            measured = f"{_label(p.subject)} = {v:.3f} @{s.frame}"
            if other is not None:
                measured += f", {_label(p.other)} = {other:.3f}"
        if not ok:
            return Outcome(False, measured)
    return Outcome(True, measured)
