import numpy as np
import pytest

from axiom3d.model.blocks import (
    FACES,
    BlockModel,
    BlocksError,
    apply_blocks_command,
    block_mesh,
    commands_to_model,
    measure_blocks,
    pixel_color,
)

BLACK = "#1a1a1a"


def build(*cmds):
    model = BlockModel(())
    for c in cmds:
        model = apply_blocks_command(model, c)
    return model


def box(name, low, high, color="green"):
    return {"op": "add_box", "name": name, "low": list(low), "high": list(high), "color": color}


def corner_pixel(face, rows, cols):
    grid = ["." * cols for _ in range(rows)]
    grid[0] = "k" + "." * (cols - 1)
    return {"op": "paint_face", "box": "b", "face": face, "pixels": grid}


# A 4 (x) by 3 (y) by 2 (z) box: every face has a different shape, so a swapped axis cannot pass.
SHAPES = {"front": (2, 4), "back": (2, 4), "left": (2, 3), "right": (2, 3), "top": (3, 4), "bottom": (3, 4)}
# Where the FIRST pixel (top row, left column, as seen looking at that face from outside) must land.
FIRST_PIXEL = {
    "front": ((0.5, 0.0, 1.5), (0, -1, 0)),   # faces -Y; columns run -X to +X
    "back": ((3.5, 3.0, 1.5), (0, 1, 0)),     # faces +Y; columns run +X to -X
    "left": ((4.0, 0.5, 1.5), (1, 0, 0)),     # the model's left is +X; columns run -Y to +Y
    "right": ((0.0, 2.5, 1.5), (-1, 0, 0)),   # columns run +Y to -Y
    "top": ((0.5, 2.5, 2.0), (0, 0, 1)),      # top row is the back edge
    "bottom": ((0.5, 0.5, 0.0), (0, 0, -1)),  # top row is the front edge
}


@pytest.mark.parametrize("face", FACES)
def test_the_first_pixel_lands_where_the_table_says(face):
    rows, cols = SHAPES[face]
    model = build(box("b", (0, 0, 0), (4, 3, 2)), corner_pixel(face, rows, cols))
    mesh, colors = block_mesh(model)
    black = np.all(np.abs(colors - np.array([0x1a, 0x1a, 0x1a]) / 255) < 1e-3, axis=1)
    tris = mesh.faces[black[mesh.faces].all(axis=1)]
    assert len(tris) == 2  # exactly one pixel quad
    centre = mesh.vertices[np.unique(tris)].astype(float).mean(axis=0)
    want, normal = FIRST_PIXEL[face]
    assert np.allclose(centre, want), (face, centre)
    v = mesh.vertices.astype(float)
    n = np.cross(v[tris[0, 1]] - v[tris[0, 0]], v[tris[0, 2]] - v[tris[0, 0]])
    assert np.allclose(n / np.linalg.norm(n), normal)  # counter-clockwise seen from outside
    assert pixel_color(model.boxes[0], face, 0, 0) == BLACK


def test_a_grid_of_the_wrong_size_is_refused_with_the_size_it_needs():
    with pytest.raises(BlocksError, match=r"4 wide x 2 tall"):
        build(box("b", (0, 0, 0), (4, 3, 2)), {"op": "paint_face", "box": "b", "face": "front", "pixels": ["kkkk"] * 3})
    with pytest.raises(BlocksError, match="unknown box 'head'"):
        build(box("b", (0, 0, 0), (4, 3, 2)), {"op": "paint_face", "box": "head", "face": "front", "pixels": ["k"]})
    with pytest.raises(BlocksError, match="'q'"):
        build(box("b", (0, 0, 0), (1, 1, 1)), {"op": "paint_face", "box": "b", "face": "top", "pixels": ["q"]})


def test_add_box_explains_bad_input():
    for bad, words in [
        (box("b", (0, 0, 0), (4.5, 1, 1)), "whole pixels"),
        (box("b", (0, 0, 0), (0, 1, 1)), "greater than low"),
        (box("b", (0, 0, 0), (100, 1, 1)), "64"),
        (box("", (0, 0, 0), (1, 1, 1)), "name"),
        (box("b", (0, 0, 0), (1, 1, 1), color="mauve"), "colour"),
    ]:
        with pytest.raises(BlocksError, match=words):
            build(bad)
    many = [box(f"b{i}", (i, 0, 0), (i + 1, 1, 1)) for i in range(33)]
    with pytest.raises(BlocksError, match="32"):
        build(*many)


def test_replacing_a_box_keeps_paint_only_where_the_face_size_holds():
    model = build(box("b", (0, 0, 0), (2, 2, 2)),
                  {"op": "paint_face", "box": "b", "face": "front", "pixels": ["kk", "kk"]},
                  {"op": "paint_face", "box": "b", "face": "top", "pixels": ["kk", "kk"]},
                  box("b", (0, 0, 0), (2, 3, 2)))  # deeper: front stays 2x2, top becomes 2x3
    b = model.boxes[0]
    assert pixel_color(b, "front", 1, 1) == BLACK
    assert pixel_color(b, "top", 0, 0) != BLACK
    assert len(build(box("b", (0, 0, 0), (1, 1, 1)), {"op": "remove_box", "name": "b"}).boxes) == 0


def test_one_colour_and_one_flat_normal_per_pixel_quad():
    model = build(box("b", (0, 0, 0), (3, 2, 4)),
                  {"op": "paint_face", "box": "b", "face": "front", "pixels": ["kgk", "gkg", "kgk", "gkg"]})
    mesh, colors = block_mesh(model)
    c = colors[mesh.faces]
    assert np.allclose(c[:, 0], c[:, 1]) and np.allclose(c[:, 0], c[:, 2])
    v = mesh.vertices.astype(float)
    fn = np.cross(v[mesh.faces[:, 1]] - v[mesh.faces[:, 0]], v[mesh.faces[:, 2]] - v[mesh.faces[:, 0]])
    fn /= np.linalg.norm(fn, axis=1, keepdims=True)
    assert np.allclose(mesh.normals()[mesh.faces[:, 0]], fn, atol=1e-6)  # no smoothing across edges
    assert len(mesh.faces) == 2 * 2 * (3 * 2 + 3 * 4 + 2 * 4)  # one quad per pixel on every face


def test_contacts_floating_overlap_and_symmetry():
    stacked = measure_blocks(build(box("leg", (0, 0, 0), (2, 2, 3)), box("top", (0, 0, 3), (2, 2, 5))))
    assert stacked.contacts == (("leg", "top"),) and stacked.floating == ()
    # Touching along an edge holds a box up (the creeper's body sits on its legs' inner edges).
    edge = measure_blocks(build(box("leg", (0, -4, 0), (2, 0, 3)), box("body", (0, 0, 3), (2, 2, 6))))
    assert edge.floating == ()
    corner = measure_blocks(build(box("a", (0, 0, 0), (1, 1, 1)), box("b", (1, 1, 1), (2, 2, 2))))
    assert corner.floating == ("b",)
    hover = measure_blocks(build(box("a", (0, 0, 0), (1, 1, 1)), box("b", (0, 0, 5), (1, 1, 6))))
    assert hover.floating == ("b",)
    over = measure_blocks(build(box("a", (0, 0, 0), (2, 2, 2)), box("b", (1, 1, 0), (3, 3, 2))))
    assert over.overlaps == (("a", "b", 2),)  # 1 x 1 x 2 px shared
    pair = build(box("l", (-3, 0, 0), (-1, 1, 1)), box("r", (1, 0, 0), (3, 1, 1)))
    assert measure_blocks(pair).symmetric
    assert not measure_blocks(apply_blocks_command(pair, box("r", (1, 0, 0), (4, 1, 1)))).symmetric
    m = measure_blocks(pair)
    assert (m.width, m.depth, m.height) == (6, 1, 1)


def test_commands_replay_until_the_first_bad_one():
    model, error = commands_to_model([box("a", (0, 0, 0), (1, 1, 1)), box("b", (0, 0, 0), (0, 1, 1)),
                                      box("c", (2, 0, 0), (3, 1, 1))])
    assert [b.name for b in model.boxes] == ["a"]
    assert error.startswith("command #2") and "greater than low" in error
    assert commands_to_model("not a list")[1] is not None
