"""Animation data: keys plus foot constraints. Interpolation is linear so values stay predictable."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from axiom3d.conventions import TrackFrame


@dataclass(frozen=True)
class Timeline:
    fps: int = 24
    start: int = 0
    end: int = 24
    loop: bool = False


@dataclass(frozen=True)
class RootKey:
    frame: int
    position: tuple[float, float, float] | None = None
    heading_deg: float | None = None


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

    def root_at(self, frame: int, rest_height: float) -> tuple[np.ndarray, float]:
        pos_keys = [(k.frame, np.asarray(k.position, dtype=float)) for k in self.root_keys if k.position is not None]
        head_keys = [(k.frame, np.asarray(k.heading_deg, dtype=float)) for k in self.root_keys if k.heading_deg is not None]
        if pos_keys:
            position = np.array(_interp(pos_keys, frame), dtype=float)
        else:
            position = np.array([*self.track.origin_xy, rest_height], dtype=float)
        heading = float(_interp(head_keys, frame)) if head_keys else float(self.track.heading_deg)
        return position, heading

    def channel_at(self, channel: str, frame: int) -> float:
        keys = [(k.frame, np.asarray(k.value_deg, dtype=float)) for k in self.pose_keys if k.channel == channel]
        return float(_interp(keys, frame)) if keys else 0.0

    def keyed_channels(self) -> set[str]:
        return {k.channel for k in self.pose_keys}
