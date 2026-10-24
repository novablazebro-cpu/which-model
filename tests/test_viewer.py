import base64
import re

import pytest

from axiom3d.anim.commands import apply_command
from axiom3d.anim.evaluate import evaluate_clip
from axiom3d.export.viewer import THREE_ADDONS, THREE_MODULE, export_html, viewer_html
from axiom3d.tasks.library import get_task, new_clip
from axiom3d.tasks.reference import reference_commands


@pytest.fixture(scope="module")
def walk(skel):
    clip = new_clip(get_task("walk_forward"), skel)
    for c in reference_commands("walk_forward"):
        clip = apply_command(skel, clip, c)
    return clip, evaluate_clip(skel, clip)


def test_pinned_three_urls(skel, walk):
    html = viewer_html(skel, *walk, title="Walk Forward Viewer", task="walk_forward")
    assert THREE_MODULE == "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js"
    assert THREE_ADDONS == "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
    assert THREE_MODULE in html and THREE_ADDONS in html


def test_embedded_glb_decodes(skel, walk):
    html = viewer_html(skel, *walk, title="Walk Forward Viewer", task="walk_forward")
    blob = re.search(r'<script type="application/octet-stream" id="glb">([A-Za-z0-9+/=\s]+)</script>', html).group(1)
    assert base64.b64decode("".join(blob.split())).startswith(b"glTF")


def test_controls_title_and_themes(skel, walk):
    html = viewer_html(skel, *walk, title="Walk Forward Viewer", task="walk_forward")
    assert 'id="frame"' in html and 'id="play"' in html and 'id="scrub"' in html
    assert "<title>Walk Forward Viewer</title>" in html[:8192]
    assert "prefers-color-scheme: dark" in html and ':root[data-theme="dark"]' in html


def test_fragment_and_standalone(skel, walk):
    fragment = viewer_html(skel, *walk, title="Walk Forward Viewer", task="walk_forward", standalone=False)
    assert "<html" not in fragment.lower() and "<!doctype" not in fragment.lower() and "<body" not in fragment.lower()
    full = viewer_html(skel, *walk, title="Walk Forward Viewer", task="walk_forward")
    assert full.lower().startswith("<!doctype html>")


def test_export_html_writes_file(skel, walk, tmp_path):
    path = export_html(skel, *walk, tmp_path / "walk.html", title="Walk Forward Viewer", task="walk_forward")
    assert path.exists() and path.read_text().lower().startswith("<!doctype html>")


def test_hidden_rule_and_motion_framing(skel, walk):
    # The loading notice must actually disappear, and the camera must frame the whole motion, not frame 0.
    html = viewer_html(skel, *walk, title="Walk Forward Viewer", task="walk_forward")
    assert "[hidden] { display: none !important; }" in html
    m = re.search(r"const FRAME_CENTER = \[([-\d.]+), ([-\d.]+), ([-\d.]+)\], FRAME_RADIUS = ([\d.]+);", html)
    assert m, "motion bounds missing"
    cx, cy, cz, r = (float(v) for v in m.groups())
    assert 0.9 < r < 2.0 and cz > 0.3   # Y-up: the walk travels toward +Z (glTF front), so the centre sits ahead of the start
