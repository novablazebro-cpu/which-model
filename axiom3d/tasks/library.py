"""Tasks: a goal the model can read, and numeric criteria the tool grades."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

import numpy as np

from axiom3d.anim.clip import Clip, Timeline
from axiom3d.anim.commands import apply_command
from axiom3d.conventions import TrackFrame, character_axes
from axiom3d.measure import foot_contact, foot_xy, root_travel, swing_windows
from axiom3d.model.blocks import FACES, BlockModel, face_size, measure_blocks, pixel_color
from axiom3d.model.vessel import VesselMeasures, color_name, measure_cached


@dataclass(frozen=True)
class Criterion:
    id: str
    description: str
    fn: Callable  # (skel, clip, states) -> (passed: bool, measured: str)


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    goal: str
    kind: Literal["step", "walk", "pose", "vessel", "blocks"]
    timeline: Timeline
    start_heading_deg: float
    setup: tuple[dict, ...]
    criteria: tuple[Criterion, ...]


def _step_length(side: str, low: float, high: float) -> Criterion:
    def fn(skel, clip, states):
        swings = swing_windows(states, side)
        if not swings:
            return False, f"{side} foot never left the ground (step length 0.00 m)"
        last = swings[-1]  # the final step (earlier ones may be turning steps)
        lift = states[last[0] - states[0].frame - 1] if last[0] > states[0].frame else states[0]
        forward, _, _ = character_axes(lift.heading_deg)
        length = float((foot_xy(states[-1], side) - foot_xy(lift, side)) @ forward[:2])
        return low <= length <= high, f"{side} step {length:+.2f} m along the facing at lift-off"

    return Criterion(f"{side}_step_length", f"{side} foot ends {low}-{high} m forward of where it lifted off", fn)


def _foot_still(side: str, tol: float = 0.02) -> Criterion:
    def fn(skel, clip, states):
        start = foot_xy(states[0], side)
        drift = max(float(np.linalg.norm(foot_xy(s, side) - start)) for s in states)
        return drift <= tol, f"{side} foot drifted {drift:.3f} m"

    return Criterion(f"{side}_foot_still", f"{side} foot stays put (drift <= {tol} m)", fn)


def _feet_down(which: tuple[str, ...]) -> Criterion:
    def fn(skel, clip, states):
        picks = {"start": states[0], "end": states[-1]}
        bad = [f"{w}:{side}" for w in which for side in ("left", "right") if not foot_contact(picks[w], side)]
        return not bad, "both feet down" if not bad else "off the ground: " + ", ".join(bad)

    label = " and ".join(which)
    return Criterion(f"both_feet_down_at_{'_and_'.join(which)}", f"both feet on the ground at the {label}", fn)


def _travel(low: float, high: float) -> Criterion:
    def fn(skel, clip, states):
        t = root_travel(clip, states)
        return low <= t <= high, f"root travelled {t:+.2f} m forward"

    return Criterion("travel", f"root travels {low}-{high} m forward", fn)


def _steps(minimum: int) -> Criterion:
    def fn(skel, clip, states):
        n = len(swing_windows(states, "left")) + len(swing_windows(states, "right"))
        return n >= minimum, f"{n} steps"

    return Criterion("steps", f"at least {minimum} steps", fn)


def _final_heading(target: float, tol: float) -> Criterion:
    def fn(skel, clip, states):
        h = states[-1].heading_deg
        return abs(h - target) <= tol, f"final heading {h:.1f} deg"

    return Criterion("final_heading", f"final heading {target} +/- {tol} deg", fn)


# The meiping in the user's photo: (id, description, test on the measurements).
MEIPING = (
    ("height", "height 0.35-0.45 m", lambda m: (0.35 <= m.height <= 0.45, f"height {m.height:.3f} m")),
    ("width", "max diameter / height 0.48-0.60",
     lambda m: (0.48 <= m.max_diameter / m.height <= 0.60, f"max diameter / height {m.max_diameter / m.height:.3f}")),
    ("shoulder", "widest point at 0.62-0.82 of the height (a high shoulder)",
     lambda m: (0.62 <= m.shoulder_ratio <= 0.82, f"shoulder ratio {m.shoulder_ratio:.3f}")),
    ("mouth", "mouth diameter / height 0.07-0.14 (a small mouth)",
     lambda m: (0.07 <= m.mouth_diameter / m.height <= 0.14, f"mouth / height {m.mouth_diameter / m.height:.3f}")),
    ("foot", "foot diameter / height 0.26-0.40",
     lambda m: (0.26 <= m.foot_diameter / m.height <= 0.40, f"foot / height {m.foot_diameter / m.height:.3f}")),
    ("neck", "a neck: narrowest point above the shoulder <= 1.05 x the mouth",
     lambda m: (m.neck_diameter <= 1.05 * m.mouth_diameter,
                f"neck {m.neck_diameter:.3f} m vs mouth {m.mouth_diameter:.3f} m")),
    ("foot_flare", "the foot flares: foot diameter >= waist diameter + 0.005 m",
     lambda m: (m.foot_diameter - m.waist_diameter >= 0.005,
                f"foot {m.foot_diameter:.3f} m vs waist {m.waist_diameter:.3f} m")),
    ("waist_low", "the waist sits just above the foot: the narrowest point below the shoulder is in the lowest 15% "
     "of the height (higher up, the body pinches into an hourglass)",
     lambda m: (m.waist_height <= 0.15 * m.height,
                f"waist at h {m.waist_height:.3f} m = {m.waist_height / m.height:.3f} x height")),
    ("red_body", "red at half height",
     lambda m: (color_name(m.color_at(m.height / 2)) == "red", f"colour at half height: {_named(m, m.height / 2)}")),
    ("blue_foot", "blue somewhere in the lowest 20% (the wave band)", lambda m: _blue_low(m)),
    ("blue_rim", "blue at the rim (98% of the height)",
     lambda m: (color_name(m.color_at(0.98 * m.height)) == "blue", f"colour at the rim: {_named(m, 0.98 * m.height)}")),
)


def _named(m: VesselMeasures, h: float) -> str:
    c = m.color_at(h)
    return f"{color_name(c)} ({c})"


def _blue_low(m: VesselMeasures):
    heights = [h for h in m.h if h <= 0.2 * m.height]
    blue = [h for h in heights if color_name(m.color_at(h)) == "blue"]
    return bool(blue), (f"blue from {min(blue):.3f} to {max(blue):.3f} m" if blue else "no blue in the lowest 20%")


def grade_vessel(m: VesselMeasures, criteria=MEIPING) -> list[tuple[str, bool, str]]:
    """Grade measurements directly. The same function grades OBJ files made without axiom3d."""
    return [(cid, *fn(m)) for cid, _, fn in criteria]


def _vessel_criterion(cid: str, description: str, fn) -> Criterion:
    def check(skel, clip, states):
        if clip.vessel is None:
            return False, "no profile yet (call shape_profile)"
        return fn(measure_cached(clip.vessel))

    return Criterion(cid, description, check)


# The creeper's face, as seen looking at it: top row first, g = green, k = black.
CREEPER_FACE = ("gggggggg", "gggggggg", "gkkggkkg", "gkkggkkg", "gggkkggg", "ggkkkkgg", "ggkkkkgg", "ggkggkgg")
_LETTER = {"g": "green", "k": "black"}


def _sized(model: BlockModel, size) -> list:
    return [b for b in model.boxes if b.size == tuple(size)]


def _one(model: BlockModel, size, what: str):
    found = _sized(model, size)
    return found[0] if len(found) == 1 else None, f"{len(found)} {what} box{'es' if len(found) != 1 else ''}"


def _parts(model: BlockModel):
    head, _ = _one(model, (8, 8, 8), "head")
    body, _ = _one(model, (8, 4, 12), "body")
    legs = _sized(model, (4, 4, 6))
    return head, body, legs


def _c_head(m):
    head, n = _one(m, (8, 8, 8), "8x8x8")
    return head is not None, f"{n} (the head)"


def _c_body(m):
    body, n = _one(m, (8, 4, 12), "8 wide x 4 deep x 12 tall")
    turned = len(_sized(m, (4, 8, 12)))
    return body is not None, f"{n}" + (f"; {turned} turned 90 deg (4 wide x 8 deep)" if turned else "")


def _c_legs(m):
    legs = _sized(m, (4, 4, 6))
    return len(legs) == 4, f"{len(legs)} legs of 4 x 4 x 6"


def _c_ground(m):
    _, _, legs = _parts(m)
    lowest = measure_blocks(m).low[2]
    ok = bool(m.boxes) and lowest == 0 and len(legs) == 4 and all(b.low[2] == 0 for b in legs)
    return ok, f"lowest z {lowest}; legs standing on z = 0: {sum(b.low[2] == 0 for b in legs)} of {len(legs)}"


def _c_stack(m):
    head, body, legs = _parts(m)
    if head is None or body is None:
        return False, "needs one head and one body"
    ok = body.low[2] == 6 and head.low[2] == body.high[2] == 18 and measure_blocks(m).height == 26
    return ok, (f"body z {body.low[2]}..{body.high[2]}, head z {head.low[2]}..{head.high[2]}, "
                f"height {measure_blocks(m).height}")


def _c_stance(m):
    _, body, legs = _parts(m)
    if body is None or len(legs) != 4:
        return False, "needs one body and four legs"
    cy, cx = body.center[1], body.center[0]
    front = [b for b in legs if b.high[1] <= cy]
    back = [b for b in legs if b.low[1] >= cy]
    pairs_ok = all(sorted(b.center[0] < cx for b in pair) == [False, True] for pair in (front, back))
    ok = len(front) == 2 and len(back) == 2 and pairs_ok
    return ok, f"{len(front)} legs in front of the body's centre, {len(back)} behind" + (
        "" if pairs_ok or not (len(front) == 2 and len(back) == 2) else "; a pair is on one side")


def _c_centred(m):
    head, body, _ = _parts(m)
    if head is None or body is None:
        return False, "needs one head and one body"
    dx, dy = head.center[0] - body.center[0], head.center[1] - body.center[1]
    return dx == 0 and dy == 0, f"head centre is {dx:+g}, {dy:+g} px from the body's"


def _c_symmetric(m):
    sym = measure_blocks(m).symmetric
    return bool(m.boxes) and sym, "a mirror image across x = 0" if sym else "not a mirror image across x = 0"


def _c_connected(m):
    ms = measure_blocks(m)
    ok = bool(m.boxes) and not ms.floating and not ms.overlaps
    return ok, (f"floating: {', '.join(ms.floating) or 'none'}; "
                f"overlapping: {', '.join(f'{a}+{b}' for a, b, _ in ms.overlaps) or 'none'}")


def _pixels(m, skip_head_front: bool):
    head, _, _ = _parts(m)
    for b in m.boxes:
        for f in FACES:
            if skip_head_front and b is head and f == "front":
                continue
            cols, rows = face_size(b, f)
            for r in range(rows):
                for c in range(cols):
                    yield b, f, color_name(pixel_color(b, f, r, c))


def _c_green(m):
    names = [n for _, _, n in _pixels(m, True)]
    share = sum(n == "green" for n in names) / len(names) if names else 0.0
    return share >= 0.95, f"{share:.0%} of the pixels outside the face are green"


def _c_face(m):
    head, _, _ = _parts(m)
    if head is None:
        return False, "no head to paint"
    wrong = [(r, c) for r in range(8) for c in range(8)
             if color_name(pixel_color(head, "front", r, c)) != _LETTER[CREEPER_FACE[r][c]]]
    return not wrong, ("the front of the head shows the face" if not wrong else
                       f"{len(wrong)} of 64 pixels differ from the face (first at row {wrong[0][0] + 1}, "
                       f"column {wrong[0][1] + 1}, as seen from the front)")


def _c_face_only(m):
    black = sorted({f"{b.name} {f}" for b, f, n in _pixels(m, True) if n == "black"})
    return bool(m.boxes) and not black, f"black pixels elsewhere: {', '.join(black) or 'none'}"


CREEPER = (
    ("head", "one head: an 8 x 8 x 8 px box", _c_head),
    ("body", "one body: 8 px wide (X), 4 px deep (Y), 12 px tall (Z)", _c_body),
    ("legs", "four legs: 4 x 4 x 6 px boxes", _c_legs),
    ("ground", "it stands on the ground: the lowest point is z = 0 and every leg reaches it", _c_ground),
    ("stack", "the body rests on the legs at z = 6 and the head on the body at z = 18; 26 px tall", _c_stack),
    ("stance", "two legs in front of the body's centre and two behind, one on each side in each pair", _c_stance),
    ("centred", "the head is centred over the body", _c_centred),
    ("symmetric", "a mirror image of itself across x = 0", _c_symmetric),
    ("connected", "no floating and no overlapping boxes", _c_connected),
    ("green", "green all over: at least 95% of the pixels outside the face", _c_green),
    ("face_front", "the face is on the FRONT of the head (-Y), right way up, as given", _c_face),
    ("face_only_front", "no black pixels anywhere else", _c_face_only),
)


def grade_blocks(model: BlockModel | None, criteria=CREEPER) -> list[tuple[str, bool, str]]:
    """Grade a block model directly. The same function grades models built without axiom3d."""
    model = model or BlockModel(())
    return [(cid, *fn(model)) for cid, _, fn in criteria]


def _blocks_criterion(cid: str, description: str, fn) -> Criterion:
    def check(skel, clip, states):
        return fn(clip.blocks or BlockModel(()))

    return Criterion(cid, description, check)


TASKS: dict[str, Task] = {
    t.id: t
    for t in (
        Task(
            "step_forward",
            "Step forward",
            "Step the LEFT foot forward 0.3-0.5 m and end standing on both feet. Frames 0..24 at 24 fps.",
            "step",
            Timeline(fps=24, start=0, end=24),
            0.0,
            (),
            (_step_length("left", 0.3, 0.5), _foot_still("right"), _feet_down(("end",))),
        ),
        Task(
            "walk_forward",
            "Walk forward",
            "Walk forward 1.0-1.6 m, starting and ending standing. Frames 0..48 at 24 fps.",
            "walk",
            Timeline(fps=24, start=0, end=48),
            0.0,
            (),
            (_travel(1.0, 1.6), _steps(3), _feet_down(("start", "end"))),
        ),
        Task(
            "turn_then_step",
            "Turn, then step",
            "Turn left to heading 90 (face world +X), then step the LEFT foot forward 0.3-0.5 m "
            "along the NEW facing. Frames 0..36 at 24 fps.",
            "step",
            Timeline(fps=24, start=0, end=36),
            0.0,
            (),
            (_final_heading(90.0, 5.0), _step_length("left", 0.3, 0.5), _feet_down(("end",))),
        ),
        Task(
            "meiping_vase",
            "Ming meiping vase",
            "Model a Ming-dynasty meiping (plum vase) as a lathe profile. From the bottom up: a slightly flared "
            "FOOT, a narrower WAIST just above it, a body that swells to a broad, high SHOULDER (the widest point, "
            "about 70% of the way up), then curves in sharply to a short, narrow NECK and a small MOUTH with a "
            "slight lip. Paint the body red, a blue band at the foot and a blue rim at the mouth.",
            "vessel",
            Timeline(fps=24, start=0, end=0),
            0.0,
            (),
            tuple(_vessel_criterion(cid, desc, fn) for cid, desc, fn in MEIPING),
        ),
        Task(
            "minecraft_creeper",
            "Minecraft creeper",
            "Model a Minecraft creeper from boxes, measured in Minecraft pixels (px; 16 px = 1 block). It stands "
            "on four legs, each 4 px wide, 4 px deep and 6 px tall: two legs in front of the body and two behind "
            "it, and in each pair one leg on the creeper's left and one on its right, so seen from the side the "
            "legs reach out in front of and behind the body. The body is 8 px wide, 4 px deep and 12 px tall and "
            "rests on the tops of the legs. The head is an 8 px cube resting on the body, centred over it. The "
            "creeper faces -Y. Paint it green all over, and paint its face on the front of the head. Looking at "
            "the creeper's face, top row first (g = green, k = black): " + " / ".join(CREEPER_FACE) + ".",
            "blocks",
            Timeline(fps=24, start=0, end=0),
            0.0,
            (),
            tuple(_blocks_criterion(cid, desc, fn) for cid, desc, fn in CREEPER),
        ),
    )
}


def get_task(task_id: str) -> Task:
    if task_id not in TASKS:
        raise KeyError(f"unknown task {task_id!r}; tasks: {', '.join(TASKS)}")
    return TASKS[task_id]


def new_clip(task: Task, skel) -> Clip:
    clip = Clip(task.timeline, TrackFrame((0.0, 0.0), task.start_heading_deg))
    for cmd in task.setup:
        clip = apply_command(skel, clip, cmd)
    return clip
