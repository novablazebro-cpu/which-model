# Glossary

Every professional term we use, in plain words. New terms are added as they come up.

## Saving and sharing work (git and GitHub)
| term | plain meaning | in this project |
|---|---|---|
| **repository (repo)** | A project folder plus the full history of every change. | `which-model` is your repo. |
| **git** | The program that records that history on your computer. | Every save below is a git action. |
| **GitHub** | A website that stores repos online so people can share them. | Your repo lives at github.com/novablazebro-cpu/which-model. |
| **commit** | A saved snapshot of the project, with a short note saying what changed and why. Like saving a game with a label. | 79 so far (as of 2026-10-25), e.g. "fix: crisp base edge, crisp band edges…". |
| **branch** | Your own copy of the project's timeline, where you can work without disturbing the main one. | The work is on `claude/vigilant-goodall-y4x0bf`. |
| **main** | The official branch: what everyone treats as the real version. | Your branch has not been added to it yet. |
| **push** | Upload your commits from your computer to GitHub. | Done after each finished step, so nothing is lost. |
| **pull / fetch** | Download other people's commits from GitHub to your computer. | |
| **pull request (PR)** | A request to merge your branch into main. Others review the changes, comment, ask for fixes, then approve. | None yet; you decide when to open one. |
| **merge** | Combining one branch's changes into another. | Happens when a PR is approved. |
| **worktree** | A second working folder for the same repo, so two branches can be open at once. | The code sits in `.worktrees/v2`. |

## Writing code safely
| term | plain meaning | in this project |
|---|---|---|
| **bug** | Code that does something other than what was intended. | The vase's dark smeared base edge was a bug. |
| **test** | A small program that checks another program: green = passes, red = fails. | `tests/test_vessel.py` checks the vase code. |
| **test suite** | All the tests together. | 392 tests; run them with `uv run pytest -q`. |
| **TDD (test-driven development)** | Write the test first, watch it fail (red), then write code until it passes (green). It proves the test can catch the bug. | Every fix here, e.g. the vase foot slope: 31.45° (red) became 20.56° (green). |
| **CI (continuous integration)** | A service that runs the test suite automatically on every push. | Not set up for this repo yet. |
| **refactor** | Reorganising code without changing what it does, to make it cleaner. | Replacing scattered `if vessel` checks with one per-kind table. |
| **spec (specification)** | A written description of what a program must do, before building it. | `docs/superpowers/specs/`. |
| **plan** | The step-by-step build order for a spec. | `docs/superpowers/plans/`. |

## How programs talk
| term | plain meaning | in this project |
|---|---|---|
| **API** | The set of commands a program offers to other programs. | The Workbench's tools, e.g. `add_box`, `paint_face`. |
| **tool** | One command an AI model can call. | axiom3d has 20 tools. |
| **CLI (command-line interface)** | Using a program by typing commands in a terminal. | `axiom3d call add_box ...` |
| **MCP (Model Context Protocol)** | A standard way for AI models to connect to tools. | `axiom3d serve` lets Claude use axiom3d. |

## 3D
| term | plain meaning | in this project |
|---|---|---|
| **mesh** | A 3D shape made of many small triangles. | Every vase, creeper and dragon. |
| **vertex** | A corner point of those triangles. | The dragon has about 70,000 triangles. |
| **normal** | The direction a surface faces; lighting uses it. | Wrong normals caused the vase's dark smear. |
| **GLB / glTF** | A standard 3D file format that Blender and browsers open. | `storm_dragon.glb`. |

## Keeping an AI in a box (workspaces)
| term | plain meaning | in this project |
|---|---|---|
| **workspace** | A folder set aside for one job so its files never mix with your other work. | `axiom3d workspace init` makes `~/.axiom3d-ai` for the AI's models. |
| **marker file** | A tiny file whose presence says "this folder is mine". | `.axiom3d-workspace`: init refuses a non-empty folder without it, so it can't take over `~/Documents`. |
| **clone** | A full, separate copy of a repo, with its own history, made from another copy. | `axiom3d workspace dev` clones the repo so the AI edits a copy, not your working folder. |
| **git hook** | A script git runs automatically at a certain moment (before a commit, before a push). | `pre-push` in the dev clone refuses pushes to `main` and `master`. |
| **branch protection** | A GitHub setting that makes a branch refuse direct pushes, force-pushes and deletion. | The one manual step in `docs/ai-workspace.md`. The only guard that works whatever tool pushes. |
| **stdout / stderr** | A program's two output channels: stdout is the normal result, stderr is for warnings and errors. | The "--home is inside a repo" warning goes to stderr so it never mixes into what the AI reads. |
| **path traversal** | Tricking a program into touching files elsewhere by using `..` ("go up one folder") in a name. | A session id of `../../evil` would reach outside the home folder; `tests/test_containment.py` tries it. |
| **containment** | A guarantee that a program only touches the places it is allowed to. | Every tool writes only under `--home`, and tests prove it. |
| **environment variable** | A named setting that lives outside a program and is read by it. | `AXIOM3D_HOME` sets the default home. |
| **mutation check** | Deliberately breaking the code to confirm a test fails. A test that can't fail proves nothing. | Removing the hook's `core.hooksPath` line made `test_dev_hook_survives_a_global_hooks_path` go red. |
