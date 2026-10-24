"""glTF 2.0 binary (.glb) export: joint hierarchy, rigid segment meshes, baked animation."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

from axiom3d.conventions import GLTF_ROOT_ROTATION_XYZW
from axiom3d.mesh import segment_mesh
from axiom3d.perceive.render import CENTER_COLOR, LEFT_COLOR, RIGHT_COLOR

FLOAT, UINT = 5126, 5125
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963
_MATERIALS = {"left": 0, "right": 1, "center": 2}


class _Buffer:
    def __init__(self):
        self.data = bytearray()
        self.views: list[dict] = []
        self.accessors: list[dict] = []

    def add(self, array: np.ndarray, kind: str, target: int | None = None, bounds: bool = False) -> int:
        array = np.ascontiguousarray(array)
        component = UINT if array.dtype == np.uint32 else FLOAT
        while len(self.data) % 4:
            self.data.append(0)
        view = {"buffer": 0, "byteOffset": len(self.data), "byteLength": array.nbytes}
        if target is not None:
            view["target"] = target
        self.data += array.tobytes()
        self.views.append(view)
        acc = {"bufferView": len(self.views) - 1, "componentType": component, "count": int(array.shape[0]), "type": kind}
        if bounds:
            flat = array.reshape(array.shape[0], -1)
            acc["min"] = [float(v) for v in flat.min(0)]
            acc["max"] = [float(v) for v in flat.max(0)]
        self.accessors.append(acc)
        return len(self.accessors) - 1


def _xyzw(q) -> list[float]:
    w, x, y, z = q
    return [float(x), float(y), float(z), float(w)]


def _continuous(quats: np.ndarray) -> np.ndarray:
    """Flip signs so consecutive quaternions stay on one hemisphere (no interpolation spins)."""
    out = quats.copy()
    for i in range(1, len(out)):
        if np.dot(out[i], out[i - 1]) < 0:
            out[i] = -out[i]
    return out


def export_glb(skel, clip, states, path: Path) -> Path:
    buf = _Buffer()
    meshes = []
    for seg in skel.segments:
        mesh = segment_mesh(seg)
        pos = buf.add(mesh.vertices.astype(np.float32), "VEC3", ARRAY_BUFFER, bounds=True)
        nrm = buf.add(mesh.normals().astype(np.float32), "VEC3", ARRAY_BUFFER)
        idx = buf.add(mesh.faces.astype(np.uint32).reshape(-1), "SCALAR", ELEMENT_ARRAY_BUFFER)
        meshes.append({"name": seg.name, "primitives": [
            {"attributes": {"POSITION": pos, "NORMAL": nrm}, "indices": idx, "material": _MATERIALS[seg.side]}
        ]})

    first = states[0]
    joint_names = list(skel.joints)
    node_of = {name: 1 + i for i, name in enumerate(joint_names)}
    nodes = [{"name": "axiom3d_root", "rotation": list(GLTF_ROOT_ROTATION_XYZW), "children": [node_of["pelvis"]]}]
    for name in joint_names:
        joint = skel.joints[name]
        if joint.parent is None:
            translation, rotation = first.root_position, first.joint_world[name][1]
        else:
            translation, rotation = np.asarray(joint.offset), first.rotations[name]
        nodes.append({"name": name, "translation": [float(v) for v in translation], "rotation": _xyzw(rotation)})
    for name in joint_names:
        children = [node_of[c] for c, j in skel.joints.items() if j.parent == name]
        if children:
            nodes[node_of[name]]["children"] = children
    for i, seg in enumerate(skel.segments):
        nodes.append({"name": f"{seg.name}_mesh", "mesh": i})
        nodes[node_of[seg.joint]].setdefault("children", []).append(len(nodes) - 1)

    times = np.array([(s.frame - first.frame) / clip.timeline.fps for s in states], dtype=np.float32)
    time_acc = buf.add(times, "SCALAR", bounds=True)
    samplers, channels = [], []

    def animate(node: int, path_name: str, values: np.ndarray, kind: str) -> None:
        samplers.append({"input": time_acc, "output": buf.add(values.astype(np.float32), kind), "interpolation": "LINEAR"})
        channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": path_name}})

    animate(node_of["pelvis"], "translation", np.array([s.root_position for s in states]), "VEC3")
    for name in joint_names:
        quats = [s.joint_world[name][1] if skel.joints[name].parent is None else s.rotations[name] for s in states]
        animate(node_of[name], "rotation", _continuous(np.array([_xyzw(q) for q in quats])), "VEC4")

    colors = {"left": LEFT_COLOR, "right": RIGHT_COLOR, "center": CENTER_COLOR}
    gltf = {
        "asset": {"version": "2.0", "generator": "axiom3d"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": [
            {"name": side, "pbrMetallicRoughness": {"baseColorFactor": [c / 255 for c in colors[side]] + [1.0],
                                                    "metallicFactor": 0.0, "roughnessFactor": 0.8}}
            for side in ("left", "right", "center")
        ],
        "animations": [{"name": "clip", "samplers": samplers, "channels": channels}],
        "accessors": buf.accessors,
        "bufferViews": buf.views,
        "buffers": [{"byteLength": len(buf.data)}],
    }
    while len(buf.data) % 4:
        buf.data.append(0)
    gltf["buffers"][0]["byteLength"] = len(buf.data)
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(buf.data), 0x004E4942) + bytes(buf.data)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body)
    return path
