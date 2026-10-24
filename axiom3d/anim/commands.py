"""Commands: the only way a clip changes. Each returns a new clip or raises CommandError."""

from __future__ import annotations

import copy
import math

from axiom3d.anim.clip import Clip, Plant, PoseKey, RootKey, Swing
from axiom3d.conventions import track_to_world, world_to_track

SIDES = ("left", "right")
OPS = ("set_root", "set_pose", "plant_foot", "swing_foot")


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


def apply_command(skel, clip: Clip, cmd: dict) -> Clip:
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
    else:
        _swing(clip, cmd)
    return clip


def _set_root(skel, clip: Clip, cmd: dict) -> None:
    frame = _frame(clip, cmd.get("frame"))
    fields = [k for k in ("forward", "left", "height", "heading") if cmd.get(k) is not None]
    if not fields:
        raise CommandError("set_root needs at least one of forward, left, height, heading")
    position, _ = clip.root_at(frame, skel.dims["pelvis_height"])
    forward, left = world_to_track(clip.track, position[:2])
    if cmd.get("forward") is not None:
        forward = _num(cmd["forward"], "forward")
    if cmd.get("left") is not None:
        left = _num(cmd["left"], "left")
    height = _num(cmd["height"], "height") if cmd.get("height") is not None else float(position[2])
    if not 0.3 <= height <= 1.2 * skel.height:
        raise CommandError(f"height must be within 0.3..{1.2 * skel.height:.2f} m, got {height}")
    x, y = track_to_world(clip.track, forward, left)
    heading = _num(cmd["heading"], "heading") if cmd.get("heading") is not None else None
    old = next((k for k in clip.root_keys if k.frame == frame), None)
    if heading is None and old is not None:
        heading = old.heading_deg
    clip.root_keys = [k for k in clip.root_keys if k.frame != frame]
    clip.root_keys.append(RootKey(frame, (float(x), float(y), height), heading))


def _set_pose(skel, clip: Clip, cmd: dict) -> None:
    frame = _frame(clip, cmd.get("frame"))
    angles = cmd.get("angles")
    if not isinstance(angles, dict) or not angles:
        raise CommandError("set_pose needs angles, e.g. {\"left_hip.flexion\": 30}")
    valid = skel.channels()
    for channel, value in angles.items():
        if channel not in valid:
            raise CommandError(f"unknown channel {channel!r}; valid channels: {', '.join(valid)}")
        deg = _num(value, channel)
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
    forward = _num(cmd["forward"], "forward") if cmd.get("forward") is not None else 0.0
    left = _num(cmd["left"], "left") if cmd.get("left") is not None else sign * skel.dims["hip_half_width"]
    x, y = track_to_world(clip.track, forward, left)
    clip.plants.append(Plant(side, start, end, (float(x), float(y))))


def _swing(clip: Clip, cmd: dict) -> None:
    side = _side(cmd.get("side"))
    start, end = _span(clip, cmd)
    apex = _num(cmd.get("apex", 0.08), "apex")
    if not 0.0 <= apex <= 0.3:
        raise CommandError(f"apex must be within 0..0.3 m, got {apex}")
    for s in clip.swings:
        if s.side == side and _overlaps(start, end, s.start, s.end, touching=False):
            raise CommandError(f"{side} swing {start}..{end} would overlap the {side} swing {s.start}..{s.end}")
    for p in clip.plants:
        if p.side == side and _overlaps(start, end, p.start, p.end, touching=False):
            raise CommandError(f"{side} swing {start}..{end} would overlap the {side} plant {p.start}..{p.end}")
    clip.swings.append(Swing(side, start, end, apex))
