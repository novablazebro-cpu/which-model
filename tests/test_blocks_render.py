import io
import json
import re
import struct

import numpy as np
from PIL import Image

from axiom3d.api import Workbench
from axiom3d.model.blocks import commands_to_model
from axiom3d.perceive.render import render_blocks_sheet
from axiom3d.tasks.reference import reference_commands

REF = reference_commands("minecraft_creeper")


def quadrant(img: Image.Image, which: int) -> np.ndarray:
    """The four views sit in a 2 x 2 grid: 0 = FRONT, 1 = RIGHT SIDE, 2 = TOP, 3 = three-quarter."""
    a = np.asarray(img.convert("RGB")).astype(int)
    h = (a.shape[0] - 24) // 2
    w = a.shape[1] // 2
    return a[(which // 2) * h:(which // 2 + 1) * h, (which % 2) * w:(which % 2 + 1) * w]


def black(a):
    return (a[..., 0] < 50) & (a[..., 1] < 50) & (a[..., 2] < 50)


def red(a):
    return (a[..., 0] > 120) & (a[..., 1] < 70) & (a[..., 2] < 70)


def test_the_front_view_shows_the_face_high_up():
    front = quadrant(render_blocks_sheet(commands_to_model(REF)[0]), 0)
    ys, _ = np.nonzero(black(front[30:-10, 10:-10]))  # skip the title and frame
    assert len(ys) > 60 and ys.mean() < 0.45 * front.shape[0]  # the head is the top third of the creeper
    on_back = [c for c in REF if c["op"] != "paint_face"] + [dict(REF[-1], face="back")]
    assert black(quadrant(render_blocks_sheet(commands_to_model(on_back)[0]), 0)[30:-10, 10:-10]).sum() < 20


def test_the_front_view_is_not_mirrored():
    # The model's LEFT is +X. Seen from the front, its left leg must appear on the viewer's RIGHT.
    marked = REF + [{"op": "paint_face", "box": "leg_front_left", "face": "front", "pixels": ["rrrr"] * 6}]
    front = quadrant(render_blocks_sheet(commands_to_model(marked)[0]), 0)
    _, xs = np.nonzero(red(front))
    assert len(xs) > 40 and xs.mean() > front.shape[1] / 2


def _accessor(data: bytes, doc: dict, index: int) -> np.ndarray:
    acc = doc["accessors"][index]
    view = doc["bufferViews"][acc["bufferView"]]
    json_len = struct.unpack_from("<I", data, 12)[0]
    start = 20 + json_len + 8 + view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    return np.frombuffer(data, np.float32, acc["count"] * 3, start).reshape(acc["count"], 3)


def test_the_creeper_exports_to_scale_with_its_pixels(home):
    wb = Workbench(home, protocol=False)
    wb.start_session("minecraft_creeper")
    wb.batch(REF)
    assert [label for label, _ in wb.observe(views=["sheet"]).images] == ["blocks"]
    path = re.search(r"EXPORTED: (\S+\.glb)", wb.export().text).group(1)
    data = open(path, "rb").read()
    doc = json.loads(data[20:20 + struct.unpack_from("<I", data, 12)[0]])
    attrs = doc["meshes"][0]["primitives"][0]["attributes"]
    assert "COLOR_0" in attrs
    pos = _accessor(data, doc, attrs["POSITION"])
    assert np.isclose(pos[:, 2].max(), 26 / 16) and np.isclose(pos[:, 2].min(), 0)  # 1.625 m tall, on the ground
    cols = _accessor(data, doc, attrs["COLOR_0"])
    assert (cols.max(axis=1) < 0.05).sum() == 4 * 20  # the face's 20 black pixels survive (4 vertices each)
