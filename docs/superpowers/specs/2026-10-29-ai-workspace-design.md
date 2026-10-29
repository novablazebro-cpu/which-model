# AI workspace (design)

## Problem
Nova wants an AI to generate 3D models and fix bugs without touching the project's own files. Two different jobs hide in that sentence:

1. **Using** axiom3d to make models. Already mostly walled off: every tool writes only under `--home` (`sessions/`, `exports/`, `images/`, `current`). The gap is that the default `--home` is `./.axiom3d`, relative to wherever the client starts, so it can land inside the repo.
2. **Fixing** axiom3d's source. That is editing source, so the wall has to be "work on a copy, a human promotes it", not "never touch files".

## Layers
| layer | what | enforced by |
|---|---|---|
| 1. Output workspace | a fixed folder outside any git repo, made by `axiom3d workspace init`; a warning when `--home` is inside a repo | the program (soft) |
| 2. Dev workspace | a separate clone on an `ai/<name>` branch with a pre-push hook that refuses `main`/`master`; GitHub branch protection on `main` (manual, by the owner) | hook (soft), GitHub (hard) |
| 3. Hard wall | container with the real source mounted read-only | the operating system. **Out of scope here**; a later plan |

## Decisions
- No new dependencies. `workspace` is a subcommand of the existing CLI.
- `serve` speaks MCP on stdout, so every warning goes to stderr.
- `workspace init` refuses a path inside a git repo, and refuses a non-empty folder that has no `workspace.json` marker. Running it twice on its own folder is a no-op.
- The dev workspace is a clone, not a worktree: a worktree shares the main checkout's `.git`, so an agent in it can rewrite refs the owner cares about.
- Nothing here stops an agent with a shell from leaving its workspace. Only layer 3 can; the docs say so plainly.

## Non-goals
Symlink attacks inside `--home`, network isolation, and automating GitHub branch protection (no tool for it in this environment; the docs give the owner the clicks).
