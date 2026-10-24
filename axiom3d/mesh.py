"""Triangle meshes for the mannequin's rigid segments."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from axiom3d.math3d import matrix_to_quat, quat_to_matrix


@dataclass
class Mesh:
    vertices: np.ndarray  # (N, 3) float32
    faces: np.ndarray  # (M, 3) int32, counter-clockwise seen from outside

    def normals(self) -> np.ndarray:
        """Area-weighted vertex normals."""
        v = self.vertices.astype(float)
        f = self.faces
        fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
        n = np.zeros_like(v)
        for k in range(3):
            np.add.at(n, f[:, k], fn)
        lengths = np.linalg.norm(n, axis=1, keepdims=True)
        return (n / np.where(lengths < 1e-12, 1.0, lengths)).astype(np.float32)


def _round(radius: float, length: float, segments: int, rings: int) -> Mesh:
    """A sphere (length 0) or capsule along +Z from z=0 to z=length."""
    verts = [(0.0, 0.0, -radius)]
    lon = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    ring_lats = [(lat, 0.0) for lat in np.linspace(-np.pi / 2, 0, rings + 1)[1:]]
    ring_lats += [(lat, length) for lat in np.linspace(0, np.pi / 2, rings + 1)[:-1]]
    if length == 0:
        ring_lats = ring_lats[: rings] + ring_lats[rings + 1 :]
    for lat, z0 in ring_lats:
        for a in lon:
            verts.append((radius * np.cos(lat) * np.cos(a), radius * np.cos(lat) * np.sin(a), z0 + radius * np.sin(lat)))
    verts.append((0.0, 0.0, length + radius))
    n_rings = len(ring_lats)
    faces = []
    for j in range(segments):
        faces.append((0, 1 + (j + 1) % segments, 1 + j))
    for r in range(n_rings - 1):
        base, nxt = 1 + r * segments, 1 + (r + 1) * segments
        for j in range(segments):
            j2 = (j + 1) % segments
            faces.append((base + j, base + j2, nxt + j2))
            faces.append((base + j, nxt + j2, nxt + j))
    top = len(verts) - 1
    last = 1 + (n_rings - 1) * segments
    for j in range(segments):
        faces.append((last + j, last + (j + 1) % segments, top))
    return Mesh(np.asarray(verts, dtype=np.float32), np.asarray(faces, dtype=np.int32))


def sphere(radius: float, center=(0, 0, 0), segments: int = 10, rings: int = 3) -> Mesh:
    m = _round(radius, 0.0, segments, rings)
    return Mesh((m.vertices + np.asarray(center, dtype=np.float32)).astype(np.float32), m.faces)


def capsule(a, b, radius: float, segments: int = 10, rings: int = 4) -> Mesh:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    axis = b - a
    length = float(np.linalg.norm(axis))
    m = _round(radius, length, segments, rings)
    if length < 1e-12:
        return Mesh((m.vertices + a).astype(np.float32), m.faces)
    z = axis / length
    helper = np.array([1.0, 0, 0]) if abs(z[0]) < 0.9 else np.array([0, 1.0, 0])
    x = np.cross(helper, z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    rot = quat_to_matrix(matrix_to_quat(np.column_stack([x, y, z])))
    return Mesh((m.vertices.astype(float) @ rot.T + a).astype(np.float32), m.faces)


def box(size, center=(0, 0, 0)) -> Mesh:
    """Axis-aligned box with per-face vertices so normals stay flat."""
    sx, sy, sz = np.asarray(size, dtype=float) / 2
    c = np.asarray(center, dtype=float)
    quads = [
        [(-1, -1, -1), (-1, 1, -1), (1, 1, -1), (1, -1, -1)],  # -Z
        [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)],  # +Z
        [(-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)],  # -Y
        [(-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1)],  # +Y
        [(-1, -1, -1), (-1, -1, 1), (-1, 1, 1), (-1, 1, -1)],  # -X
        [(1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)],  # +X
    ]
    verts, faces = [], []
    for q in quads:
        k = len(verts)
        verts += [c + np.array(p) * (sx, sy, sz) for p in q]
        faces += [(k, k + 1, k + 2), (k, k + 2, k + 3)]
    return Mesh(np.asarray(verts, dtype=np.float32), np.asarray(faces, dtype=np.int32))


def segment_mesh(seg) -> Mesh:
    """Mesh for a Segment, in its joint's rest frame."""
    if seg.kind == "capsule":
        return capsule(seg.a, seg.b, seg.radius)
    if seg.kind == "sphere":
        return sphere(seg.radius, seg.a)
    if seg.kind == "box":
        return box(seg.size, seg.a)
    raise ValueError(f"unknown segment kind {seg.kind!r}")
