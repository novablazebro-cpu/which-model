import numpy as np
import pytest

from axiom3d.anim.commands import apply_command
from axiom3d.anim.evaluate import evaluate_clip
from axiom3d.perceive.render import LEFT_COLOR, render_filmstrip, render_footprints, render_sheet, to_png
from axiom3d.tasks.library import get_task, new_clip
from axiom3d.tasks.reference import reference_commands

TILE = 384


@pytest.fixture(scope="module")
def step(skel):
    clip = new_clip(get_task("step_forward"), skel)
    for c in reference_commands("step_forward"):
        clip = apply_command(skel, clip, c)
    return clip, evaluate_clip(skel, clip)


def blue_mask(img):
    a = np.asarray(img.convert("RGB")).astype(int)
    target = np.array(LEFT_COLOR)
    # Shaded blue keeps its hue: blue channel dominant, red low.
    return (a[..., 2] > a[..., 0] + 60) & (a[..., 2] > a[..., 1] + 20) & (np.abs(a - target).sum(-1) < 400)


def test_sheet_size_and_png(skel, step):
    _, states = step
    sheet = render_sheet(skel, states[0], size=TILE)
    assert sheet.size == (2 * TILE, 2 * TILE)
    assert to_png(sheet).startswith(b"\x89PNG")


def test_front_view_left_is_screen_right(skel, step):
    _, states = step
    front = blue_mask(render_sheet(skel, states[0], size=TILE).crop((0, 0, TILE, TILE)))
    assert front[:, TILE // 2 :].sum() > 5 * front[:, : TILE // 2].sum()
    assert front.sum() > 200


def test_side_view_step_toe_right_of_pelvis(skel, step):
    _, states = step
    side = blue_mask(render_sheet(skel, states[24], size=TILE).crop((TILE, 0, 2 * TILE, TILE)))
    ys, xs = np.nonzero(side[int(TILE * 0.75) :, :])
    assert xs.size > 20 and xs.mean() > TILE / 2


def test_filmstrip_width(skel, step):
    _, states = step
    strip = render_filmstrip(skel, states[::5], size=256)
    assert strip.size == (len(states[::5]) * 256, 256)


def test_footprints_render(skel, step):
    clip, states = step
    img = render_footprints(skel, clip, states, size=TILE)
    assert img.size == (TILE, TILE) and blue_mask(img).sum() > 10
