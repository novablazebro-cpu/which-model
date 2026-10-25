"""Animation data: keys plus foot constraints. Interpolation is linear so values stay predictable."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from axiom3d.conventions import TrackFrame, track_to_world
from axiom3d.model.blocks import BlockModel
from axiom3d.model.vessel import VesselSpec

ROOT_CHANNELS = ("forward", "left", "height", "heading")


@dataclass(frozen=True)
class Timeline:
    fps: int = 24
    start: int = 0
    end: int = 24
    loop: bool = False


@dataclass(frozen=True)
class RootKey:
    """One root channel at one frame: forward/left are track metres, height metres, heading degrees."""

    frame: int
    channel: str
    value: float


@dataclass(frozen=True)
class PoseKey:
    frame: int
    channel: str
    value_deg: float


@dataclass(frozen=True)
class Plant:
    side: str
    start: int
    end: int
    xy: tuple[float, float]  # world position of the ankle's ground projection
    yaw_deg: float | None = None  # the foot's heading; None = the root heading at `start`, resolved live


@dataclass(frozen=True)
class Swing:
    side: str
    start: int
    end: int
    apex_m: float


def _interp(keys: list[tuple[int, np.ndarray]], frame: int):
    """Linear interpolation over (frame, value) pairs, holding at both ends."""
    keys = sorted(keys, key=lambda k: k[0])
    if frame <= keys[0][0]:
        return keys[0][1]
    if frame >= keys[-1][0]:
        return keys[-1][1]
    for (f0, v0), (f1, v1) in zip(keys, keys[1:]):
        if f0 <= frame <= f1:
            t = (frame - f0) / (f1 - f0)
            return v0 + t * (v1 - v0)
    raise AssertionError("unreachable")


@dataclass
class Clip:
    timeline: Timeline
    track: TrackFrame = field(default_factory=TrackFrame)
    root_keys: list[RootKey] = field(default_factory=list)
    pose_keys: list[PoseKey] = field(default_factory=list)
    plants: list[Plant] = field(default_factory=list)
    swings: list[Swing] = field(default_factory=list)
    vessel: VesselSpec | None = None  # vessel tasks: the lathe profile and its paint
    blocks: BlockModel | None = None  # block tasks: boxes and their painted faces

    def _channel(self, keys: list[tuple[int, float]], frame: int, default: float) -> float:
        """Linear over the keys. A channel starts at its rest value unless keyed at the start frame."""
        if not keys:
            return default
        if min(f for f, _ in keys) > self.timeline.start:
            keys = [(self.timeline.start, default)] + keys
        return float(_interp(keys, frame))

    def root_at(self, frame: int, rest_height: float) -> tuple[np.ndarray, float]:
        def channel(name: str, default: float) -> float:
            return self._channel([(k.frame, k.value) for k in self.root_keys if k.channel == name], frame, default)

        x, y = track_to_world(self.track, channel("forward", 0.0), channel("left", 0.0))
        return np.array([x, y, channel("height", rest_height)]), channel("heading", float(self.track.heading_deg))

    def channel_at(self, channel: str, frame: int) -> float:
        return self._channel([(k.frame, k.value_deg) for k in self.pose_keys if k.channel == channel], frame, 0.0)

    def keyed_channels(self) -> set[str]:
        return {k.channel for k in self.pose_keys}
