import pytest

from axiom3d.rig.humanoid import build_mannequin


@pytest.fixture(scope="session")
def skel():
    return build_mannequin()


@pytest.fixture
def home(tmp_path):
    return tmp_path / ".axiom3d"
