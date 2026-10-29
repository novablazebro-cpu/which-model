"""The axioms: one source of truth for frames, units and axis conventions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

UP = np.array([0.0, 0.0, 1.0])
FORWARD0 = np.array([0.0, -1.0, 0.0])
LEFT0 = np.array([1.0, 0.0, 0.0])

# A foot point at or below this height counts as touching the ground (metres).
CONTACT_EPS = 0.02

# glTF is Y-up with +Z as the asset's front: rotate the Z-up scene -90 deg about X.
GLTF_ROOT_ROTATION_XYZW = (-0.70710678, 0.0, 0.0, 0.70710678)

CONVENTIONS_TEXT = """\
Frame: right-handed, Z up, metres, degrees. Ground is z = 0.
Heading 0: the mannequin faces -Y and its LEFT is +X. Positive heading turns it left.
Track coordinates (forward, left): measured from the task's start point along its start facing.
Anatomy: positive angle = the anatomical motion (flexion bends the joint the way it naturally bends).
Raw +X rotation swings a downward-pointing bone toward +Y, which is BACKWARD at heading 0."""


@dataclass(frozen=True)
class TrackFrame:
    origin_xy: tuple[float, float] = (0.0, 0.0)
    heading_deg: float = 0.0


def character_axes(heading_deg: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """World (forward, left, up) vectors for a character at this heading."""
    h = np.radians(heading_deg)
    c, s = np.cos(h), np.sin(h)
    forward = np.array([s, -c, 0.0])
    left = np.array([c, s, 0.0])
    return forward, left, UP.copy()


def track_to_world(track: TrackFrame, forward: float, left: float) -> np.ndarray:
    f, l, _ = character_axes(track.heading_deg)
    return np.asarray(track.origin_xy, dtype=float) + forward * f[:2] + left * l[:2]


def world_to_track(track: TrackFrame, xy) -> tuple[float, float]:
    f, l, _ = character_axes(track.heading_deg)
    d = np.asarray(xy, dtype=float)[:2] - np.asarray(track.origin_xy, dtype=float)
    return float(d @ f[:2]), float(d @ l[:2])


def zup_to_yup(p) -> np.ndarray:
    x, y, z = p
    return np.array([x, z, -y], dtype=float)
