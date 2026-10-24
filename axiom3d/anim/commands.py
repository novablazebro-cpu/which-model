"""Commands: the only way a clip changes. Each returns a new clip or raises CommandError."""

from __future__ import annotations

import copy
import dataclasses
import math

from axiom3d.anim.clip import ROOT_CHANNELS, Clip, Plant, PoseKey, RootKey, Swing
from axiom3d.conventions import track_to_world
from axiom3d.model.vessel import MAX_HEIGHT, Band, VesselError, VesselSpec, parse_color, validate

SIDES = ("left", "right")
VESSEL_OPS = ("shape_profile", "paint_band")
OPS = ("set_root", "set_pose", "plant_foot", "swing_foot") + VESSEL_OPS
MAX_BANDS = 32
DEFAULT_WALL = 0.006
MIN_APEX = 0.03
MAX_ANGLE = 720.0
MAX_DISTANCE = 50.0


class CommandError(ValueError):
    pass


def _num(value, what: str) -> float:
    if isinstance(value, bool):
        raise CommandError(f"{what} must be a number, got {value!r}")
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise CommandError(f"{what} must be a number, got {value!r}") from None
    if not math.isfinite(x):
        raise CommandError(f"{what} must be a finite number, got {value!r}")
    return x


def _bounded(value, what: str, limit: float, unit: str) -> float:
    x = _num(value, what)
    if abs(x) > limit:
        raise CommandError(f"{what} must be within -{limit:g}..{limit:g} {unit}, got {value!r}")
    return x


def _frame(clip: Clip, value, what: str = "frame") -> int:
    x = _num(value, what)
    tl = clip.timeline
    if x != int(x) or not tl.start <= x <= tl.end:
        raise CommandError(f"{what} must be a whole frame in {tl.start}..{tl.end}, got {value!r}")
    return int(x)


def _side(value) -> str:
    if value not in SIDES:
        raise CommandError(f"side must be 'left' or 'right', got {value!r}")
    return value


def _span(clip: Clip, cmd: dict) -> tuple[int, int]:
    start, end = _frame(clip, cmd.get("start"), "start"), _frame(clip, cmd.get("end"), "end")
    if start >= end:
        raise CommandError(f"start must be before end, got {start}..{end}")
    return start, end


def _overlaps(a0, a1, b0, b1, touching: bool) -> bool:
    return (a0 <= b1 and b0 <= a1) if touching else (a0 < b1 and b0 < a1)


MAX_BATCH = 40


def _apply_batch(skel, clip: Clip, edits) -> Clip:
    if not isinstance(edits, list) or not 1 <= len(edits) <= MAX_BATCH:
        raise CommandError(f"a batch needs a list of 1..{MAX_BATCH} edits")
    for i, edit in enumerate(edits):
        op = edit.get("op") if isinstance(edit, dict) else None
        if op == "batch":
            raise CommandError(f"batch edit #{i + 1}: a batch can't contain another batch")
        try:
            clip = apply_command(skel, clip, edit)
        except CommandError as e:
            raise CommandError(f"batch edit #{i + 1} ({op}): {e}") from None
    return clip


def apply_command(skel, clip: Clip, cmd: dict) -> Clip:
    if isinstance(cmd, dict) and cmd.get("op") == "batch":
        return _apply_batch(skel, clip, cmd.get("edits"))
    if not isinstance(cmd, dict) or cmd.get("op") not in OPS:
        raise CommandError(f"op must be one of {', '.join(OPS)}, got {cmd.get('op') if isinstance(cmd, dict) else cmd!r}")
    clip = copy.deepcopy(clip)
    op = cmd["op"]
    if op == "set_root":
        _set_root(skel, clip, cmd)
    elif op == "set_pose":
        _set_pose(skel, clip, cmd)
    elif op == "plant_foot":
        _plant(skel, clip, cmd)
    elif op == "swing_foot":
        _swing(clip, cmd)
    elif op == "shape_profile":
        _shape(clip, cmd)
    else:
        _paint(clip, cmd)
    return clip


def _set_root(skel, clip: Clip, cmd: dict) -> None:
    frame = _frame(clip, cmd.get("frame"))
    values = {name: _bounded(cmd[name], name, MAX_ANGLE if name == "heading" else MAX_DISTANCE,
                             "degrees" if name == "heading" else "m")
              for name in ROOT_CHANNELS if cmd.get(name) is not None}
    if not values:
        raise CommandError("set_root needs at least one of forward, left, height, heading")
    height = values.get("height")
    if height is not None and not 0.3 <= height <= 1.2 * skel.height:
        raise CommandError(f"height must be within 0.3..{1.2 * skel.height:.2f} m, got {height}")
    for name, value in values.items():
        clip.root_keys = [k for k in clip.root_keys if not (k.frame == frame and k.channel == name)]
        clip.root_keys.append(RootKey(frame, name, value))


def _set_pose(skel, clip: Clip, cmd: dict) -> None:
    frame = _frame(clip, cmd.get("frame"))
    angles = cmd.get("angles")
    if not isinstance(angles, dict) or not angles:
        raise CommandError("set_pose needs angles, e.g. {\"left_hip.flexion\": 30}")
    valid = skel.channels()
    for channel, value in angles.items():
        if channel not in valid:
            raise CommandError(f"unknown channel {channel!r}; valid channels: {', '.join(valid)}")
        deg = _bounded(value, channel, MAX_ANGLE, "degrees")
        clip.pose_keys = [k for k in clip.pose_keys if not (k.frame == frame and k.channel == channel)]
        clip.pose_keys.append(PoseKey(frame, channel, deg))


def _plant(skel, clip: Clip, cmd: dict) -> None:
    side = _side(cmd.get("side"))
    start, end = _span(clip, cmd)
    for p in clip.plants:
        if p.side == side and _overlaps(start, end, p.start, p.end, touching=True):
            raise CommandError(f"{side} plant {start}..{end} would overlap the {side} plant {p.start}..{p.end}")
    for s in clip.swings:
        if s.side == side and _overlaps(start, end, s.start, s.end, touching=False):
            raise CommandError(f"{side} plant {start}..{end} would overlap the {side} swing {s.start}..{s.end}")
    sign = 1.0 if side == "left" else -1.0
    forward = _bounded(cmd["forward"], "forward", MAX_DISTANCE, "m") if cmd.get("forward") is not None else 0.0
    left = (_bounded(cmd["left"], "left", MAX_DISTANCE, "m") if cmd.get("left") is not None
            else sign * skel.dims["hip_half_width"])
    yaw = None
    if cmd.get("facing") is not None:
        yaw = _num(cmd["facing"], "facing")
        if abs(yaw) > MAX_ANGLE:
            raise CommandError(f"facing must be within -{MAX_ANGLE:g}..{MAX_ANGLE:g} degrees, got {yaw}")
    x, y = track_to_world(clip.track, forward, left)
    clip.plants.append(Plant(side, start, end, (float(x), float(y)), yaw))


def _swing(clip: Clip, cmd: dict) -> None:
    side = _side(cmd.get("side"))
    start, end = _span(clip, cmd)
    apex = _num(cmd.get("apex", 0.08), "apex")
    if not MIN_APEX <= apex <= 0.3:
        raise CommandError(f"apex must be within {MIN_APEX}..0.3 m (a swing lifts the foot), got {apex}")
    for s in clip.swings:
        # Swings can't share an endpoint: the foot must land (a plant) between two swings.
        if s.side == side and _overlaps(start, end, s.start, s.end, touching=True):
            raise CommandError(f"{side} swing {start}..{end} would overlap the {side} swing {s.start}..{s.end}; "
                               "plant the foot between two swings")
    for p in clip.plants:
        if p.side == side and _overlaps(start, end, p.start, p.end, touching=False):
            raise CommandError(f"{side} swing {start}..{end} would overlap the {side} plant {p.start}..{p.end}")
    clip.swings.append(Swing(side, start, end, apex))


def _shape(clip: Clip, cmd: dict) -> None:
    points = cmd.get("points")
    if not isinstance(points, (list, tuple)):
        raise CommandError("points must be a list of [height, radius] pairs, e.g. [[0, 0.06], [0.2, 0.1], [0.4, 0.02]]")
    if any(not isinstance(p, (list, tuple)) or len(p) != 2 for p in points):
        raise CommandError("each point must be [height, radius] in metres (radius, not diameter)")
    profile = tuple((_num(h, "height"), _num(r, "radius")) for h, r in points)
    wall = _num(cmd.get("wall", DEFAULT_WALL), "wall")
    spec = VesselSpec(profile, wall, clip.vessel.bands if clip.vessel else ())
    try:
        validate(spec)
    except VesselError as e:
        raise CommandError(str(e)) from None
    clip.vessel = spec


def _paint(clip: Clip, cmd: dict) -> None:
    if clip.vessel is None:
        raise CommandError("there is nothing to paint yet: call shape_profile first")
    start, end = _num(cmd.get("start"), "start"), _num(cmd.get("end"), "end")
    if not 0 <= start < end <= MAX_HEIGHT:
        raise CommandError(f"start must be below end, both within 0..{MAX_HEIGHT:g} m (heights), got {start:g}..{end:g}")
    if len(clip.vessel.bands) >= MAX_BANDS:
        raise CommandError(f"at most {MAX_BANDS} bands; undo some first")
    try:
        color = parse_color(cmd.get("color"))
    except VesselError as e:
        raise CommandError(str(e)) from None
    clip.vessel = dataclasses.replace(clip.vessel, bands=clip.vessel.bands + (Band(start, end, color),))
