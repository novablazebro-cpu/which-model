from axiom3d.api import Workbench
from axiom3d.eval.vase import grade_home, grade_obj
from axiom3d.model.vessel import vessel_mesh, write_obj
from axiom3d.tasks.library import MEIPING
from axiom3d.tasks.reference import reference_commands

REF = reference_commands("meiping_vase")


def test_home_grade_of_the_reference_passes_every_criterion(home):
    wb = Workbench(home, protocol=False)
    wb.start_session("meiping_vase")
    wb.batch(REF)
    row = grade_home(home)
    assert row["passed"] == len(MEIPING) == row["total"]
    assert all(ok for _, ok, _ in row["criteria"])
    assert row["phase"] == "WORKING" and row["protocol"] is False
    assert row["batches"] == 1 and row["edits"] >= 1
    assert row["spec"].wall == REF[0]["wall"]


def test_home_without_a_profile_is_an_error_row(home):
    Workbench(home, protocol=False).start_session("meiping_vase")
    assert "no profile" in grade_home(home)["error"]


def test_home_without_a_session_is_an_error_row(tmp_path):
    assert "no session" in grade_home(tmp_path / "empty")["error"]


def test_obj_grade_of_the_reference_passes_and_is_watertight(home, tmp_path):
    wb = Workbench(home, protocol=False)
    wb.start_session("meiping_vase")
    wb.batch(REF)
    spec = grade_home(home)["spec"]
    path = write_obj(*vessel_mesh(spec), tmp_path / "vase.obj")
    row = grade_obj(path)
    assert row["watertight"] is True
    assert row["passed"] == len(MEIPING), [c for c in row["criteria"] if not c[1]]


def test_missing_or_broken_obj_is_an_error_row(tmp_path):
    assert "no such file" in grade_obj(tmp_path / "nope.obj")["error"]
    bad = tmp_path / "bad.obj"
    bad.write_text("v 0 0 zero\n")
    assert "cannot read" in grade_obj(bad)["error"]
