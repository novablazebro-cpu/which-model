import json
import subprocess

import pytest

from axiom3d.cli import main
from axiom3d.workspace import MARKER, WorkspaceError, in_git_repo, init_workspace


def make_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


# ---- task 1: workspace init --------------------------------------------------------------------

def test_init_creates_owned_folder_and_returns_config(tmp_path):
    home = tmp_path / "ai-home"
    info = init_workspace(home)
    assert home.is_dir() and (home / MARKER).is_file()
    assert info.home == home.resolve()
    # The exact line to paste into Claude Code, with an absolute path (MCP clients start servers without a shell).
    assert info.claude_command == f"claude mcp add axiom3d -- axiom3d serve --home {home.resolve()}"
    assert json.loads(info.mcp_json) == {
        "mcpServers": {"axiom3d": {"command": "axiom3d", "args": ["serve", "--home", str(home.resolve())]}}}


def test_init_refuses_inside_a_git_repo(tmp_path):
    repo = make_repo(tmp_path / "project")
    with pytest.raises(WorkspaceError, match="git repository"):
        init_workspace(repo / "ai-home")
    assert not (repo / "ai-home").exists()  # refused before creating anything


def test_init_refuses_the_repo_root_itself(tmp_path):
    repo = make_repo(tmp_path / "project")
    with pytest.raises(WorkspaceError, match="git repository"):
        init_workspace(repo)


def test_init_refuses_nonempty_folder_it_does_not_own(tmp_path):
    home = tmp_path / "Documents"
    home.mkdir()
    (home / "taxes.txt").write_text("private")
    with pytest.raises(WorkspaceError, match="not empty"):
        init_workspace(home)
    assert not (home / MARKER).exists() and (home / "taxes.txt").read_text() == "private"


def test_init_accepts_an_existing_empty_folder(tmp_path):
    home = tmp_path / "empty"
    home.mkdir()
    init_workspace(home)
    assert (home / MARKER).is_file()


def test_init_again_on_own_workspace_keeps_the_work(tmp_path):
    home = tmp_path / "ai-home"
    init_workspace(home)
    (home / "sessions").mkdir()
    (home / "sessions" / "keep-1.json").write_text("{}")
    init_workspace(home)
    assert (home / "sessions" / "keep-1.json").read_text() == "{}"


def test_init_refuses_a_file(tmp_path):
    f = tmp_path / "afile"
    f.write_text("x")
    with pytest.raises(WorkspaceError, match="not a folder"):
        init_workspace(f)


def test_in_git_repo_sees_parents_and_worktree_files(tmp_path):
    repo = make_repo(tmp_path / "project")
    assert in_git_repo(repo / "a" / "b" / "not-yet-created")
    assert not in_git_repo(tmp_path / "elsewhere")
    # A linked worktree or submodule has a .git *file*, not a folder.
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: /somewhere")
    assert in_git_repo(wt / "x")


def test_cli_workspace_init(tmp_path, capsys):
    home = tmp_path / "ai-home"
    assert main(["workspace", "init", "--home", str(home)]) == 0
    out = capsys.readouterr().out
    assert f"claude mcp add axiom3d -- axiom3d serve --home {home.resolve()}" in out
    assert (home / MARKER).is_file()


def test_cli_workspace_init_refusal_exit_code(tmp_path, capsys):
    repo = make_repo(tmp_path / "project")
    assert main(["workspace", "init", "--home", str(repo / "ai")]) == 1
    assert "git repository" in capsys.readouterr().out


def test_cli_workspace_init_default_is_dot_axiom3d_ai(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("AXIOM3D_HOME", raising=False)
    assert main(["workspace", "init"]) == 0
    assert (tmp_path / ".axiom3d-ai" / MARKER).is_file()


# ---- task 2: warn when --home sits inside a repo ----------------------------------------------

def test_call_inside_repo_warns_on_stderr_not_stdout(tmp_path, capsys):
    repo = make_repo(tmp_path / "project")
    home = repo / ".axiom3d"
    assert main(["call", "start_session", "--json", '{"task": "step_forward"}', "--home", str(home)]) == 0
    cap = capsys.readouterr()
    assert "WARNING" in cap.err and str(repo) in cap.err and "axiom3d workspace init" in cap.err
    assert "WARNING" not in cap.out  # stdout stays clean: it is the MCP channel and what models read


def test_call_outside_repo_is_silent(tmp_path, capsys):
    home = tmp_path / "ai-home"
    assert main(["call", "start_session", "--json", '{"task": "step_forward"}', "--home", str(home)]) == 0
    assert capsys.readouterr().err == ""


def test_relative_default_home_inside_repo_warns(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path / "project")
    monkeypatch.chdir(repo)
    monkeypatch.delenv("AXIOM3D_HOME", raising=False)
    main(["eval", "report"])
    assert "WARNING" in capsys.readouterr().err


def test_serve_warns_before_starting(tmp_path, monkeypatch, capsys):
    repo = make_repo(tmp_path / "project")
    started = []

    class FakeServer:
        def run(self, transport):
            started.append(transport)

    monkeypatch.setattr("axiom3d.mcp_server.build_server", lambda *a, **k: FakeServer())
    assert main(["serve", "--home", str(repo / "h")]) == 0
    assert started == ["stdio"] and "WARNING" in capsys.readouterr().err


# ---- task 4: workspace dev ---------------------------------------------------------------------

import os  # noqa: E402

from axiom3d.workspace import dev_workspace  # noqa: E402


def git(cwd, *args, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


@pytest.fixture
def remote(tmp_path, monkeypatch):
    """A bare 'GitHub' with one commit on main, and git set up so tests ignore the machine's own git config."""
    cfg = tmp_path / "gitconfig"
    cfg.write_text("[user]\n\tname = Tester\n\temail = t@example.com\n[init]\n\tdefaultBranch = main\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    bare = tmp_path / "github.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", "-q", str(bare), str(seed))
    (seed / "README.md").write_text("hello\n")
    git(seed, "add", ".")
    git(seed, "commit", "-q", "-m", "first")
    git(seed, "push", "-q", "origin", "HEAD:main")
    return bare


def test_dev_makes_a_separate_clone_on_an_ai_branch(tmp_path, remote):
    info = dev_workspace("fix-vase", source=str(remote), dest=tmp_path / "dev")
    assert info.path == (tmp_path / "dev").resolve() and info.branch == "ai/fix-vase"
    assert git(info.path, "branch", "--show-current").stdout.strip() == "ai/fix-vase"
    assert (info.path / "README.md").read_text() == "hello\n"


def test_dev_hook_lets_the_ai_branch_through_and_refuses_main_and_master(tmp_path, remote):
    info = dev_workspace("fix-vase", source=str(remote), dest=tmp_path / "dev")
    (info.path / "work.txt").write_text("ai work\n")
    git(info.path, "add", ".")
    git(info.path, "commit", "-q", "-m", "ai work")
    main_before = git(remote, "rev-parse", "main").stdout

    git(info.path, "push", "-q", "-u", "origin", "ai/fix-vase")  # allowed
    assert git(remote, "rev-parse", "ai/fix-vase").stdout == git(info.path, "rev-parse", "HEAD").stdout

    for target in ("main", "master"):
        refused = git(info.path, "push", "origin", f"HEAD:refs/heads/{target}", check=False)
        assert refused.returncode != 0 and "refusing" in refused.stderr.lower(), target
    deleted = git(info.path, "push", "origin", "--delete", "main", check=False)  # deleting main is also a push to it
    assert deleted.returncode != 0
    assert git(remote, "rev-parse", "main").stdout == main_before
    assert git(remote, "rev-parse", "--verify", "master", check=False).returncode != 0


def test_dev_hook_survives_a_global_hooks_path(tmp_path, remote, monkeypatch):
    """A user's global core.hooksPath would silently disable .git/hooks, so the clone pins its own."""
    cfg = tmp_path / "gitconfig"
    cfg.write_text(cfg.read_text() + f"[core]\n\thooksPath = {tmp_path / 'elsewhere'}\n")
    info = dev_workspace("x1", source=str(remote), dest=tmp_path / "dev")
    (info.path / "f").write_text("f")
    git(info.path, "add", ".")
    git(info.path, "commit", "-q", "-m", "f")
    assert git(info.path, "push", "origin", "HEAD:main", check=False).returncode != 0


@pytest.mark.parametrize("name", ["", "../x", "a/b", "Main", "has space", "-rf", ".hidden", "x" * 60, "ai/x", "main\n"])
def test_dev_refuses_bad_names(tmp_path, remote, name):
    with pytest.raises(WorkspaceError, match="name"):
        dev_workspace(name, source=str(remote), dest=tmp_path / "dev")
    assert not (tmp_path / "dev").exists()


def test_dev_refuses_nonempty_dest_and_dest_inside_a_repo(tmp_path, remote):
    full = tmp_path / "full"
    full.mkdir()
    (full / "x").write_text("x")
    with pytest.raises(WorkspaceError, match="not empty"):
        dev_workspace("a1", source=str(remote), dest=full)
    repo = make_repo(tmp_path / "project")
    with pytest.raises(WorkspaceError, match="git repository"):
        dev_workspace("a1", source=str(remote), dest=repo / "dev")
    assert not (repo / "dev").exists()


def test_dev_reports_a_failed_clone_cleanly(tmp_path):
    with pytest.raises(WorkspaceError, match="clone"):
        dev_workspace("a1", source=str(tmp_path / "no-such-repo"), dest=tmp_path / "dev")
    assert not (tmp_path / "dev").exists()


def test_dev_default_source_is_the_origin_of_the_repo_you_are_in(tmp_path, remote, monkeypatch):
    mine = tmp_path / "mine"
    git(tmp_path, "clone", "-q", str(remote), str(mine))
    monkeypatch.chdir(mine)
    info = dev_workspace("a1", dest=tmp_path / "dev")
    assert git(info.path, "remote", "get-url", "origin").stdout.strip() == str(remote)


def test_cli_workspace_dev(tmp_path, remote, capsys):
    assert main(["workspace", "dev", "fix-vase", "--source", str(remote), "--dest", str(tmp_path / "dev")]) == 0
    out = capsys.readouterr().out
    assert "ai/fix-vase" in out and str((tmp_path / "dev").resolve()) in out
    assert main(["workspace", "dev", "Bad Name", "--source", str(remote), "--dest", str(tmp_path / "d2")]) == 1
