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
from axiom3d.model.vessel import Band, VesselSpec, display_mesh, load_obj, measure_obj, parse_color, vessel_mesh, write_obj
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


def _at(mesh, normals, h, r, tol=1e-4):
    v = mesh.vertices.astype(float)
    on = (np.abs(v[:, 2] - h) < tol) & (np.abs(np.hypot(v[:, 0], v[:, 1]) - r) < tol)
    return normals[on]


def test_display_mesh_keeps_the_base_edge_and_the_lip_crisp():
    # One shared ring at the base averaged "down" and "out" into normals ~84 deg below horizontal,
    # which every viewer (and Blender) shades as a dark smeared rim.
    s = spec()
    mesh, _ = display_mesh(s)
    n = mesh.normals()
    base = _at(mesh, n, 0.0, s.profile[0][1])
    assert (base[:, 2] < -0.99).any()  # the base disk faces straight down
    wall = base[base[:, 2] >= -0.99]
    assert len(wall) and (np.abs(wall[:, 2]) < 0.35).all()  # the wall's lowest ring faces outward
    lip = _at(mesh, n, s.profile[-1][0], s.profile[-1][1])
    assert (lip[:, 2] > 0.99).any() and (np.abs(lip[:, 2]) < 0.5).any()  # lip faces up, wall faces out


def test_display_mesh_paints_each_triangle_one_colour():
    # Band edges blended over one sample (~4 mm): a painted edge should be a line, not a gradient.
    mesh, colors = display_mesh(spec())
    c = colors[mesh.faces]
    assert np.allclose(c[:, 0], c[:, 1]) and np.allclose(c[:, 0], c[:, 2])
    assert len({tuple(np.round(x, 3)) for x in colors}) >= 3  # red, blue, porcelain inside


def test_display_mesh_is_the_same_closed_shape(tmp_path):
    # Splitting vertices must not open gaps: welded back by position it is still watertight.
    m, watertight = measure_obj(write_obj(*display_mesh(spec()), tmp_path / "d.obj"))
    assert watertight and abs(m.max_diameter - measure_obj(write_obj(*vessel_mesh(spec()), tmp_path / "w.obj"))[0].max_diameter) < 1e-6


def _accessor(data: bytes, doc: dict, index: int) -> np.ndarray:
    acc = doc["accessors"][index]
    view = doc["bufferViews"][acc["bufferView"]]
    json_len = struct.unpack_from("<I", data, 12)[0]
    start = 20 + json_len + 8 + view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    width = {"VEC3": 3, "VEC2": 2, "SCALAR": 1}[acc["type"]]
    return np.frombuffer(data, np.float32, acc["count"] * width, start).reshape(acc["count"], width)


def test_exported_glb_has_the_crisp_base_edge(home):
    data = open(re.search(r"EXPORTED: (\S+\.glb)", finished_vase(home).export().text).group(1), "rb").read()
    doc = gltf_json(data)
    attrs = doc["meshes"][0]["primitives"][0]["attributes"]
    pos, nrm = _accessor(data, doc, attrs["POSITION"]), _accessor(data, doc, attrs["NORMAL"])
    foot = REF[0]["points"][0][1]
    rim = (np.abs(pos[:, 2]) < 1e-4) & (np.abs(np.hypot(pos[:, 0], pos[:, 1]) - foot) < 1e-4)
    assert (nrm[rim, 2] < -0.99).any() and (np.abs(nrm[rim, 2]) < 0.35).any()
