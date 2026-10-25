import numpy as np
import pytest

from axiom3d.anim.clip import Clip, Timeline
from axiom3d.anim.commands import apply_command
from axiom3d.anim.evaluate import evaluate_clip
from axiom3d.conventions import TrackFrame
from axiom3d.measure import (
    contact_windows,
    foot_contact,
    foot_xy,
    relation,
    root_travel,
    support_label,
    swing_windows,
    track_coords,
)
from axiom3d.tasks.reference import reference_commands


@pytest.fixture(scope="module")
def step(skel):
    clip = Clip(Timeline(end=24), TrackFrame())
    for c in reference_commands("step_forward"):
        clip = apply_command(skel, clip, c)
    return clip, evaluate_clip(skel, clip)


def test_windows_for_step(step):
    _, states = step
    assert contact_windows(states, "left") == [(0, 6), (18, 24)]
    assert swing_windows(states, "left") == [(7, 17)]
    assert contact_windows(states, "right") == [(0, 24)]
    assert swing_windows(states, "right") == []


def test_relation_in_front(step):
    _, states = step
    rel = relation(states[24], "left_toe", "pelvis")
    assert rel["forward"] > 0.2 and abs(rel["left"]) < 0.1


def test_support_labels(step):
    _, states = step
    assert support_label(states[12]) == "R"
    assert support_label(states[0]) == "LR"
    assert foot_contact(states[0], "left") and not foot_contact(states[12], "left")


def test_root_travel_and_track_coords(step):
    clip, states = step
    assert np.isclose(root_travel(clip, states), 0.18)
    f, l = track_coords(clip, foot_xy(states[24], "left"))
    assert np.isclose(f, 0.36) and np.isclose(l, 0.0875)
