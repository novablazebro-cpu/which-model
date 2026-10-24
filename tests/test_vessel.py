from collections import Counter

import numpy as np
import pytest

from axiom3d.model.vessel import (
    Band,
    VesselError,
    VesselSpec,
    color_name,
    measure_obj,
    measure_spec,
    parse_color,
    sample_profile,
    vessel_mesh,
    write_obj,
)

# A meiping in the photo's proportions (0.40 m tall).
REF = ((0.000, 0.066), (0.012, 0.064), (0.040, 0.060), (0.120, 0.075), (0.200, 0.092), (0.260, 0.103),
       (0.290, 0.107), (0.330, 0.100), (0.355, 0.075), (0.370, 0.040), (0.378, 0.022), (0.392, 0.018),
       (0.400, 0.021))
BANDS = (Band(0.04, 0.37, parse_color("red")), Band(0.0, 0.04, parse_color("blue")), Band(0.37, 0.40, parse_color("blue")))


def spec():
    return VesselSpec(REF, 0.006, BANDS)


def test_measurements_match_the_photo():
    m = measure_spec(spec())
    assert abs(m.height - 0.40) < 1e-9
    assert 0.212 < m.max_diameter < 0.218 and 0.70 < m.shoulder_ratio < 0.75
    assert abs(m.mouth_diameter - 0.042) < 1e-9 and abs(m.foot_diameter - 0.132) < 1e-9
    assert m.neck_diameter <= m.mouth_diameter and m.waist_diameter < m.foot_diameter
    assert 3.0 < m.capacity_l < 9.0 and 10 < m.tip_angle_deg < 40
    assert color_name(m.color_at(0.2)) == "red" and color_name(m.color_at(0.01)) == "blue"
    assert color_name(m.color_at(0.399)) == "blue"


def test_smoothing_never_overshoots():
    h, r = sample_profile(spec())
    radii = [p[1] for p in REF]
    assert r.max() <= max(radii) + 1e-9 and r.min() >= min(radii) - 1e-9
    assert np.all(np.diff(h) > 0) and h[0] == 0 and h[-1] == 0.40


def test_mesh_is_watertight_with_colours():
    mesh, colors = vessel_mesh(spec())
    edges = Counter()
    for a, b, c in mesh.faces:
        for e in ((a, b), (b, c), (c, a)):
            edges[tuple(sorted(e))] += 1
    assert set(edges.values()) == {2}
    assert colors.shape == (len(mesh.vertices), 3) and colors.min() >= 0 and colors.max() <= 1


def test_later_band_wins_and_default_is_white():
    s = VesselSpec(REF, 0.006, (Band(0.0, 0.4, parse_color("red")), Band(0.1, 0.2, parse_color("gold"))))
    m = measure_spec(s)
    assert color_name(m.color_at(0.15)) == "gold" and color_name(m.color_at(0.3)) == "red"
    assert color_name(measure_spec(VesselSpec(REF, 0.006, ())).color_at(0.2)) == "white"


def test_obj_round_trip_measures_the_same(tmp_path):
    mesh, colors = vessel_mesh(spec())
    path = write_obj(mesh, colors, tmp_path / "vase.obj")
    m_obj, watertight = measure_obj(path)
    m = measure_spec(spec())
    assert watertight
    assert abs(m_obj.height - m.height) < 1e-6 and abs(m_obj.max_diameter - m.max_diameter) < 0.003
    assert abs(m_obj.mouth_diameter - m.mouth_diameter) < 0.004 and abs(m_obj.foot_diameter - m.foot_diameter) < 0.003
    assert color_name(m_obj.color_at(0.2)) == "red"


def test_obj_with_a_hole_is_not_watertight(tmp_path):
    mesh, colors = vessel_mesh(spec())
    mesh.faces = mesh.faces[:-1]
    _, watertight = measure_obj(write_obj(mesh, colors, tmp_path / "holed.obj"))
    assert not watertight


@pytest.mark.parametrize("bad", [((0, 0.05), (0.2, 0.05)), ((0, 0.05), (0.2, 0.06), (0.1, 0.07)),
                                 ((0, 0.05), (0.2, -0.01), (0.3, 0.02)), ((0, 0.05), (0.2, 2.0), (0.3, 0.02))])
def test_invalid_profiles_rejected(bad):
    with pytest.raises(VesselError):
        measure_spec(VesselSpec(bad, 0.006, ()))


def test_colour_parsing():
    assert parse_color("#AABBCC") == "#aabbcc" and parse_color("Blue") == parse_color("blue")
    with pytest.raises(VesselError, match="red"):
        parse_color("ultraviolet")
