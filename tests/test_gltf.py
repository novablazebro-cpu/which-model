import json
import struct

import numpy as np
import pytest

from axiom3d.anim.commands import apply_command
from axiom3d.anim.evaluate import evaluate_clip
from axiom3d.api import Workbench
from axiom3d.conventions import GLTF_ROOT_ROTATION_XYZW, zup_to_yup
from axiom3d.export.gltf import export_glb
from axiom3d.math3d import quat_rotate
from axiom3d.tasks.library import get_task, new_clip
from axiom3d.tasks.reference import reference_commands

COMPONENTS = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}
DTYPES = {5126: np.float32, 5125: np.uint32}


def parse(path):
    data = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF" and version == 2 and length == len(data)
    jlen, jtype = struct.unpack_from("<II", data, 12)
    assert jtype == 0x4E4F534A and jlen % 4 == 0
    gltf = json.loads(data[20 : 20 + jlen])
    blen, btype = struct.unpack_from("<II", data, 20 + jlen)
    assert btype == 0x004E4942 and blen % 4 == 0
    return gltf, data[28 + jlen : 28 + jlen + blen]


def read(gltf, binary, index):
    acc = gltf["accessors"][index]
    view = gltf["bufferViews"][acc["bufferView"]]
    n = COMPONENTS[acc["type"]]
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    arr = np.frombuffer(binary, DTYPES[acc["componentType"]], acc["count"] * n, start)
    return arr.reshape(acc["count"], n) if n > 1 else arr


@pytest.fixture(scope="module")
def exported(skel, tmp_path_factory):
    clip = new_clip(get_task("step_forward"), skel)
    for c in reference_commands("step_forward"):
        clip = apply_command(skel, clip, c)
    states = evaluate_clip(skel, clip)
    path = export_glb(skel, clip, states, tmp_path_factory.mktemp("glb") / "step.glb")
    return states, *parse(path)


def test_accessors_consistent(exported):
    _, gltf, binary = exported
    assert gltf["asset"]["version"] == "2.0"
    for i, acc in enumerate(gltf["accessors"]):
        view = gltf["bufferViews"][acc["bufferView"]]
        size = acc["count"] * COMPONENTS[acc["type"]] * 4
        assert view.get("byteOffset", 0) % 4 == 0 and size <= view["byteLength"]
        assert view.get("byteOffset", 0) + view["byteLength"] <= len(binary)
        if "min" in acc:
            data = read(gltf, binary, i).reshape(acc["count"], -1)
            assert np.allclose(data.min(0), acc["min"], atol=1e-5) and np.allclose(data.max(0), acc["max"], atol=1e-5)
    for mesh in gltf["meshes"]:
        prim = mesh["primitives"][0]
        assert "min" in gltf["accessors"][prim["attributes"]["POSITION"]]
        n_verts = gltf["accessors"][prim["attributes"]["POSITION"]]["count"]
        assert read(gltf, binary, prim["indices"]).max() < n_verts


def test_nodes_and_root_rotation(skel, exported):
    _, gltf, _ = exported
    names = [n.get("name") for n in gltf["nodes"]]
    assert set(skel.joints) <= set(names)
    assert gltf["scenes"][gltf["scene"]]["nodes"] == [0]
    assert names[0] == "axiom3d_root" and np.allclose(gltf["nodes"][0]["rotation"], GLTF_ROOT_ROTATION_XYZW)
    assert len(gltf["meshes"]) == len(skel.segments) and len(gltf["materials"]) == 3


def test_animation_shape(skel, exported):
    _, gltf, binary = exported
    anim = gltf["animations"][0]
    times = read(gltf, binary, anim["samplers"][0]["input"])
    assert len(times) == 25 and np.isclose(times[-1], 1.0)
    paths = [(gltf["nodes"][c["target"]["node"]]["name"], c["target"]["path"]) for c in anim["channels"]]
    assert ("pelvis", "translation") in paths
    assert {n for n, p in paths if p == "rotation"} == set(skel.joints)


def test_pelvis_translation_maps_to_y_up(exported):
    states, gltf, binary = exported
    anim = gltf["animations"][0]
    chan = next(c for c in anim["channels"] if c["target"]["path"] == "translation")
    t24 = read(gltf, binary, anim["samplers"][chan["sampler"]]["output"])[24]
    x, y, z, w = GLTF_ROOT_ROTATION_XYZW
    world_yup = quat_rotate(np.array([w, x, y, z]), t24)
    assert np.allclose(world_yup, zup_to_yup(states[24].root_position), atol=1e-6)


def test_rotation_values_match_states(exported):
    states, gltf, binary = exported
    anim = gltf["animations"][0]
    names = [n.get("name") for n in gltf["nodes"]]
    chan = next(c for c in anim["channels"] if c["target"]["path"] == "rotation" and names[c["target"]["node"]] == "left_knee")
    q12 = read(gltf, binary, anim["samplers"][chan["sampler"]]["output"])[12]
    w, x, y, z = states[12].rotations["left_knee"]
    assert np.allclose(q12, [x, y, z, w], atol=1e-6) or np.allclose(q12, [-x, -y, -z, -w], atol=1e-6)


def test_workbench_export(home):
    wb = Workbench(home, protocol=False)
    wb.start_session("step_forward")
    text = wb.export().text
    path = home / "exports" / f"{(home / 'current').read_text()}.glb"
    assert "EXPORTED" in text and path.exists()
    parse(path)
