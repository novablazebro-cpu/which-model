import base64
import io
import json
import re
import struct

import numpy as np
from PIL import Image

from axiom3d.api import Workbench
from axiom3d.export.gltf import export_mesh_glb
from axiom3d.export.viewer import mesh_viewer_html
from axiom3d.model.vessel import VesselSpec, load_obj, parse_color, vessel_mesh, write_obj, Band
from axiom3d.tasks.reference import reference_commands

REF = reference_commands("meiping_vase")


def spec():
    bands = tuple(Band(c["start"], c["end"], parse_color(c["color"])) for c in REF[1:])
    return VesselSpec(tuple(map(tuple, REF[0]["points"])), REF[0]["wall"], bands)


def gltf_json(data: bytes) -> dict:
    magic, version, _ = struct.unpack_from("<4sII", data)
    assert magic == b"glTF" and version == 2
    length, kind = struct.unpack_from("<II", data, 12)
    assert kind == 0x4E4F534A
    return json.loads(data[20:20 + length])


def test_static_glb_has_vertex_colours_and_no_animation(tmp_path):
    mesh, colors = vessel_mesh(spec())
    doc = gltf_json(export_mesh_glb(mesh, colors, tmp_path / "vase.glb").read_bytes())
    prim = doc["meshes"][0]["primitives"][0]
    assert {"POSITION", "NORMAL", "COLOR_0"} <= set(prim["attributes"])
    assert "animations" not in doc
    acc = doc["accessors"][prim["attributes"]["COLOR_0"]]
    assert acc["count"] == len(mesh.vertices) and acc["type"] == "VEC3"
    assert doc["nodes"][0]["rotation"] == [-0.70710678, 0.0, 0.0, 0.70710678]  # Z-up to glTF's Y-up


def test_static_viewer_has_no_transport(tmp_path):
    mesh, colors = vessel_mesh(spec())
    html = mesh_viewer_html(mesh, colors, title="Meiping Vase", task="meiping_vase",
                            facts=["height 0.400 m", "max Ø 0.214 m"])
    assert '<div class="transport" hidden>' in html and "LEFT" not in html
    assert "<title>Meiping Vase</title>" in html[:8192] and "height 0.400 m" in html
    blob = re.search(r'id="glb">([A-Za-z0-9+/=\s]+)</script>', html).group(1)
    assert base64.b64decode("".join(blob.split())).startswith(b"glTF")


def test_obj_loads_back_into_a_mesh(tmp_path):
    mesh, colors = vessel_mesh(spec())
    loaded, loaded_colors = load_obj(write_obj(mesh, colors, tmp_path / "v.obj"))
    assert loaded.faces.shape == mesh.faces.shape and np.allclose(loaded.vertices, mesh.vertices, atol=1e-5)
    assert np.allclose(loaded_colors, colors, atol=1e-3)


def finished_vase(home):
    wb = Workbench(home, protocol=False)
    wb.start_session("meiping_vase")
    wb.batch(REF)
    return wb


def test_workbench_exports_the_vase(home):
    text = finished_vase(home).export().text
    assert "vertex colours" in text
    path = re.search(r"EXPORTED: (\S+\.glb)", text).group(1)
    assert gltf_json(open(path, "rb").read())["meshes"][0]["primitives"][0]["attributes"]["COLOR_0"] is not None


def test_sheet_shows_the_red_body(home):
    res = finished_vase(home).observe(views=["sheet"])
    (label, png), = res.images
    img = np.asarray(Image.open(io.BytesIO(png)).convert("RGB")).astype(int)
    assert img.shape[1] > img.shape[0]  # side view + profile plot, side by side
    left = img[:, : img.shape[1] // 2]
    reddish = (left[..., 0] > 120) & (left[..., 0] > left[..., 1] + 50) & (left[..., 0] > left[..., 2] + 50)
    bluish = (left[..., 2] > left[..., 0] + 40) & (left[..., 2] > 90)
    assert reddish.sum() > 2000 and bluish.sum() > 100
