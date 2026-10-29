# AI Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give an AI a dedicated output workspace and a dedicated dev workspace so it can make 3D models and fix bugs without touching the owner's main files.

**Architecture:** One new module, `axiom3d/workspace.py`, holds all logic; `axiom3d/cli.py` gains a `workspace` subcommand (`init`, `dev`) and a stderr warning when `--home` sits inside a git repo. Containment is pinned by tests, not new enforcement code. The hard wall (container) is a later plan.

**Tech Stack:** Python ≥3.11, stdlib only (`pathlib`, `json`, `subprocess`, `shutil`, `stat`), pytest, git 2.x.

**Spec:** `docs/superpowers/specs/2026-10-29-ai-workspace-design.md`

## Global Constraints
- Runtime dependencies stay exactly `numpy`, `Pillow`, `mcp>=2.3,<3`. No new ones.
- `axiom3d serve` speaks MCP on stdout. Every warning goes to **stderr**; stdout stays clean.
- Existing tests stay green: `uv run pytest -q`.
- Any other exception reaching the CLI keeps today's behavior (`INTERNAL ERROR ...`, exit 2). Workspace failures are `WorkspaceError`, printed as `ERROR: <message>`, exit 1.
- Work on `claude/branch-merge-strategy-deh7sn`, commit per task with the session trailer, push after each task.
- New terms go in `docs/learn/glossary.md`; finish with a "What you learned" list (owner is learning to code; see `CLAUDE.md`).

## Review Focus
1. `workspace init` on an existing non-empty folder with no marker: refuse, never write into it. Pinned in Task 1.
2. `~` and relative paths: the printed MCP config must hold an absolute, expanded path, because MCP clients start in an unknown folder. Pinned in Task 1.
3. A path nested deep inside a git repo is still refused, not just the repo root. Pinned in Task 1.
4. Running `init` twice on the same folder succeeds and keeps its existing sessions. Pinned in Task 1.
5. A dev-workspace name like `../x`, `a b` or empty, or a destination that already exists: refuse before running any git command. Pinned in Task 4.

---

### Task 1: Output workspace (`workspace init`)

**Files:**
- Create: `axiom3d/workspace.py`, `tests/test_workspace.py`
- Modify: `axiom3d/cli.py` (add `workspace` subparser; `main` dispatch)

**Interfaces:**
- Produces in `axiom3d/workspace.py`:
  - `class WorkspaceError(ValueError)`
  - `MARKER = "workspace.json"`
  - `find_repo_root(path: Path) -> Path | None` — nearest ancestor of `path` (or `path` itself) containing `.git`; works for paths that don't exist yet.
  - `init_workspace(path: Path) -> Path` — returns the resolved absolute path; creates `path`, `sessions/`, `exports/`, `images/` and `workspace.json` (`{"version": 1}`).
  - `mcp_config(home: Path) -> dict` — `{"mcpServers": {"axiom3d": {"command": "axiom3d", "args": ["serve", "--home", str(home)]}}}`.
- CLI: `axiom3d workspace init [PATH]`, default `~/.axiom3d-ai`. Prints the path, the JSON from `mcp_config`, and the line `claude mcp add axiom3d -- axiom3d serve --home <path>`.

- [ ] **Step 1: Write the failing tests** in `tests/test_workspace.py`. Names and assertions:
  - `test_init_creates_layout`: after `init_workspace(tmp_path / "ws")`, `sessions`, `exports`, `images` exist and `json.loads((ws / MARKER).read_text()) == {"version": 1}`.
  - `test_init_is_idempotent_and_keeps_sessions`: create a file `ws/sessions/a.json`, call `init_workspace` again; no error, the file still exists with the same bytes.
  - `test_init_refuses_nonempty_unmarked_folder`: a folder containing `notes.txt` and no marker → `pytest.raises(WorkspaceError)`; `notes.txt` unchanged and no `sessions/` created.
  - `test_init_refuses_path_inside_git_repo`: `(tmp_path / "proj" / ".git").mkdir(parents=True)`; both `tmp_path / "proj" / "ws"` and `tmp_path / "proj" / "a" / "b" / "ws"` raise `WorkspaceError`, and neither folder is created.
  - `test_init_expands_tilde_and_relative_paths`: with `monkeypatch.setenv("HOME", str(tmp_path))`, `init_workspace(Path("~/w"))` returns `tmp_path / "w"` (absolute); with `monkeypatch.chdir(tmp_path)`, `init_workspace(Path("rel"))` returns `tmp_path / "rel"`.
  - `test_mcp_config_uses_absolute_home`: `mcp_config(ws)["mcpServers"]["axiom3d"]["args"] == ["serve", "--home", str(ws)]`.
  - `test_cli_workspace_init_prints_config`: `main(["workspace", "init", str(tmp_path / "ws")]) == 0`; output contains `"mcpServers"`, the path and `claude mcp add axiom3d`. A second test calls it on a non-empty unmarked folder and asserts exit code 1 and `ERROR` in the output.

- [ ] **Step 2: Run to verify failure**
  Run: `uv run pytest tests/test_workspace.py -q`
  Expected: collection error / FAIL (`axiom3d.workspace` missing).

- [ ] **Step 3: Implement** `axiom3d/workspace.py` per the Interfaces block. Resolve with `Path(path).expanduser().resolve()`; check the repo and non-empty rules *before* creating anything. In `cli.py`, add the `workspace` subparser with a nested `init` command, and catch `WorkspaceError` → `print(f"ERROR: {e}")`, return 1.

- [ ] **Step 4: Run to verify pass**
  Run: `uv run pytest tests/test_workspace.py -q` → all PASS; then `uv run pytest -q` → all green.

- [ ] **Step 5: Commit**
```bash
git add axiom3d/workspace.py axiom3d/cli.py tests/test_workspace.py
git commit -m "feat: axiom3d workspace init creates a dedicated output folder"
git push -u origin claude/branch-merge-strategy-deh7sn
```

---

### Task 2: Warn when `--home` is inside a git repo

**Files:**
- Modify: `axiom3d/cli.py` (`_home` callers for `serve` and `call`), `axiom3d/workspace.py`
- Test: `tests/test_workspace.py`

**Interfaces:**
- Consumes: `find_repo_root`, `MARKER` (Task 1).
- Produces: `home_warning(home: Path) -> str | None` in `workspace.py` — a one-line message naming the repo and suggesting `axiom3d workspace init`, or `None` when `home` is outside any repo or `home/workspace.json` exists.

- [ ] **Step 1: Write the failing tests**
  - `test_home_warning_inside_repo`: repo at `tmp_path/proj`, `home_warning(tmp_path/"proj"/".axiom3d")` contains `"workspace init"` and the repo path.
  - `test_home_warning_none_outside_repo_or_with_marker`: returns `None` for a plain `tmp_path/".axiom3d"`, and for a home inside a repo that already holds `workspace.json`.
  - `test_call_warns_on_stderr_only`: repo at `tmp_path/proj`; `main(["call", "start_session", "--json", '{"task": "step_forward"}', "--home", str(tmp_path/"proj"/".axiom3d")])`; `capsys.readouterr()` has `"workspace init"` in `.err` and not in `.out`; exit code 0.

- [ ] **Step 2: Run to verify failure**
  Run: `uv run pytest tests/test_workspace.py -q -k warning` → FAIL.

- [ ] **Step 3: Implement** `home_warning`; in `main`, for `serve` and `call`, print it to `sys.stderr` before doing anything else.

- [ ] **Step 4: Run to verify pass**
  Run: `uv run pytest -q` → all green (the `home` fixture lives in `tmp_path`, outside any repo, so existing tests print nothing).

- [ ] **Step 5: Commit**
```bash
git add axiom3d/workspace.py axiom3d/cli.py tests/test_workspace.py
git commit -m "feat: warn on stderr when --home is inside a git repo"
git push
```

---

### Task 3: Pin containment (tools write only under `--home`)

**Files:**
- Create: `tests/test_containment.py`
- Modify: `axiom3d/cli.py` only if a test below fails (see Step 3)

**Interfaces:**
- Consumes: `Workbench`, `main`, the `home` fixture.

- [ ] **Step 1: Write the tests** (no production code expected)
  - `test_every_task_kind_writes_only_under_home`: for one task of each kind (`step_forward` walk, one vessel task, one blocks task — take ids from `axiom3d.tasks.library.TASKS` by `task.kind`), run `start_session`, `observe`, and `export` (use the same setup helpers as `tests/test_vessel_export.py` and `tests/test_gltf.py` to reach an exportable state) with `os.chdir` set to an empty `tmp_path / "cwd"`. Then walk `tmp_path`: every file is under `home` or is nothing at all; `tmp_path / "cwd"` is still empty.
  - `test_tampered_current_pointer_cannot_escape`: write `home / "current"` containing `../../escape`; `main(["call", "observe", "--home", str(home)])` returns 1, and no file named `escape*` exists anywhere under `tmp_path`.
  - `test_hostile_session_arguments_are_rejected`: `Workbench(home).observe(session=s)` raises `AxiomError` for `s` in `"../../x"`, `"/etc/passwd"`, `"a-b/../../c"`, `""`; nothing created outside `home`.

- [ ] **Step 2: Run**
  Run: `uv run pytest tests/test_containment.py -q`
  Expected: PASS. (`load()` already validates ids with `_ID`; this task pins it.)

- [ ] **Step 3: If `test_tampered_current_pointer_cannot_escape` fails,** the CLI builds an image filename from the unvalidated `current_id(home)`. Fix in `_call` (`axiom3d/cli.py`): build `sid` only from an id matching `session_store._ID`, else `"session"`. Re-run until PASS. If it already passes, make no production change.

- [ ] **Step 4: Run the full suite** — `uv run pytest -q` → all green.

- [ ] **Step 5: Commit**
```bash
git add tests/test_containment.py axiom3d/cli.py
git commit -m "test: pin that every tool writes only under --home"
git push
```

---

### Task 4: Dev workspace (`workspace dev`)

**Files:**
- Modify: `axiom3d/workspace.py`, `axiom3d/cli.py`
- Test: `tests/test_workspace_dev.py`

**Interfaces:**
- Consumes: `WorkspaceError` (Task 1).
- Produces in `workspace.py`: `clone_dev_workspace(source: str, path: Path, name: str) -> Path` — clones `source` into `path`, checks out new branch `ai/<name>`, installs `.git/hooks/pre-push` (executable) that exits 1 with a message when any pushed ref is `refs/heads/main` or `refs/heads/master`. Returns the resolved path.
- Name rule: `^[a-z0-9][a-z0-9._-]{0,39}$`; else `WorkspaceError`, checked before any git command. `path` must not exist.
- CLI: `axiom3d workspace dev SOURCE PATH --name NAME`.

- [ ] **Step 1: Write the failing tests** in `tests/test_workspace_dev.py`. A fixture builds a local *bare* origin: `git init --bare origin.git`, seeds it from a scratch clone with one commit on `main`, using `subprocess.run([...], check=True)`.
  - `test_dev_clone_creates_ai_branch`: after `clone_dev_workspace(str(origin), tmp_path/"dev", "fix-legs")`, `git -C dev branch --show-current` prints `ai/fix-legs`.
  - `test_pre_push_hook_blocks_main`: commit a file in `dev`; `git push origin HEAD:main` exits non-zero and origin's `main` is unchanged (compare `git rev-parse main` in the bare repo before and after); same for `HEAD:master`.
  - `test_pre_push_hook_allows_ai_branch`: `git push origin HEAD:ai/fix-legs` exits 0 and the bare repo has the branch.
  - `test_dev_rejects_bad_names_and_existing_path`: names `""`, `"../x"`, `"a b"`, `"UP"`, 41 chars → `WorkspaceError`; an existing destination → `WorkspaceError`; in each case no `git` subprocess ran (monkeypatch `subprocess.run` to raise, and the error is still a `WorkspaceError`).
  - `test_cli_workspace_dev`: `main(["workspace", "dev", str(origin), str(tmp_path/"dev2"), "--name", "x"]) == 0`, and `ERROR`/exit 1 for a bad name.

- [ ] **Step 2: Run to verify failure**
  Run: `uv run pytest tests/test_workspace_dev.py -q` → FAIL.

- [ ] **Step 3: Implement** with `subprocess.run(["git", ...], check=True)` (list form, never `shell=True`; `source` is passed after `--`). Hook body: read stdin lines, reject on `refs/heads/main` / `refs/heads/master` in the remote-ref column.

- [ ] **Step 4: Run to verify pass**
  Run: `uv run pytest -q` → all green.

- [ ] **Step 5: Commit**
```bash
git add axiom3d/workspace.py axiom3d/cli.py tests/test_workspace_dev.py
git commit -m "feat: axiom3d workspace dev makes a guarded clone on an ai/ branch"
git push
```

---

### Task 5: Docs and glossary

**Files:**
- Create: `docs/ai-workspace.md`
- Modify: `README.md` (short "AI workspace" section linking to it; correct the "Connect a model" advice to use `workspace init`), `docs/learn/glossary.md`, `CLAUDE.md` (one line under "The project": agents work in `ai/*` clones, never on `main`)

- [ ] **Step 1: Write `docs/ai-workspace.md`** with: the three layers table from the spec; the exact commands for `workspace init` and `workspace dev`; the **manual GitHub step** for the owner (Settings → Branches → add a rule for `main`: require a pull request before merging), marked as *not enforced by this code and not verified by us*; and an honest "what this does not stop" section (an agent with a shell can leave its folder; only a container can, as a later plan).

- [ ] **Step 2: Add glossary rows**: workspace, sandbox vs. workspace, clone vs. worktree, pre-push hook, branch protection, read-only mount, stderr/stdout.

- [ ] **Step 3: Verify the docs' commands are real**
  Run: `uv run axiom3d workspace init /tmp/ws-check && uv run axiom3d workspace init /tmp/ws-check` → both exit 0, second changes nothing. Then `rm -r /tmp/ws-check`.

- [ ] **Step 4: Run the full suite** — `uv run pytest -q` → all green.

- [ ] **Step 5: Commit**
```bash
git add docs/ai-workspace.md README.md docs/learn/glossary.md CLAUDE.md
git commit -m "docs: AI workspace guide, README section and glossary terms"
git push
```

---

## Self-review
- **Spec coverage:** layer 1 → Tasks 1–2; containment claim → Task 3; layer 2 hook + clone → Task 4; GitHub protection, honesty about limits, layer 3 deferral → Task 5.
- **Not covered, by design:** layer 3 container, symlinks inside `--home`, automating branch protection.
- **Open question for the owner:** the default for `workspace init` is `~/.axiom3d-ai`; change it if you prefer another place.
