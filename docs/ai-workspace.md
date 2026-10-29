# A safe place for an AI to work

axiom3d writes files: session logs, screenshots, exported 3D models. If an AI model runs it from inside one
of your projects, those files land in your project, and a careless `git add .` can commit them. This page sets
up two separate, boxed-in places so the AI's work never mixes with yours.

| You want | Use | Where the AI writes |
|---|---|---|
| The AI to **make models** (vases, creepers, walks) | `axiom3d workspace init` | one dedicated folder, `~/.axiom3d-ai` |
| The AI to **change axiom3d's own code** | `axiom3d workspace dev NAME` | a separate clone, on branch `ai/NAME` |

## 1. A folder for the AI's models

```bash
axiom3d workspace init                    # makes ~/.axiom3d-ai
axiom3d workspace init --home ~/my-ai     # or pick a place
```

It prints the exact line that connects the AI, for example:

```bash
claude mcp add axiom3d -- axiom3d serve --home /home/you/.axiom3d-ai
```

(and the same thing as JSON for other MCP clients). The path is always absolute, because MCP clients start the
server without a shell and a relative path would point somewhere else each time.

**It refuses to run when:**
- the folder is inside a git repository (any parent folder holds a `.git`), because a commit could capture the
  AI's files;
- the folder already has files in it that this command did not put there, so it can never take over
  `~/Documents` by accident.

Running it again on a folder it made is safe: your sessions stay.

**The warning.** If you start `axiom3d serve`, `call` or `eval` with a `--home` that sits inside a git repository
(including the old default `./.axiom3d` when you run it inside a project), axiom3d prints a `WARNING` on stderr.
stderr is the error channel, so the warning never mixes into the output the AI reads or the MCP protocol on stdout.
It warns instead of refusing, because the repo's own evaluation scripts use a local `./home` on purpose.

**What is guaranteed.** `tests/test_containment.py` runs all 20 tools through every task type and checks that
nothing outside `--home` changes. It also attacks the tools: session ids like `../../evil`, absolute paths, a
tampered `current` pointer file, a session file that lies about its own id. Writing that test found two real
escapes, now fixed:

1. The CLI named screenshots after the contents of `current` without checking them (file written outside home).
2. `export` named the .glb after the `id` stored *inside* the session file, which a tampered file could set to
   `../../x`. A session file must now carry the id it is stored under.

**What is not guaranteed.** This protects against bugs and tampered files, not against a hostile process. A
symlink you place inside the home pointing elsewhere is followed. An AI that can run shell commands can still
write anywhere your user account can: axiom3d is not a sandbox, just a tool that keeps to its own folder.

## 2. A separate clone for code changes

```bash
cd ~/code/which-model               # any clone of the repo
axiom3d workspace dev vase-fix      # clone origin into ~/axiom3d-ai-dev/vase-fix, branch ai/vase-fix
# or:  axiom3d workspace dev vase-fix --source <url-or-path> --dest <folder>
```

Then start the AI inside the printed folder. The clone has a **pre-push hook**: a small script git runs before
every push, which exits with an error if the push would update `main` or `master` (including deleting them). The
AI pushes its branch and you open a pull request:

```bash
git push -u origin ai/vase-fix
```

Names are 1-40 lowercase letters, digits and dashes. The destination must be new or empty and outside every other
repository.

The clone also pins `core.hooksPath` to its own `.git/hooks`. Without that, a global `core.hooksPath` in your git
config (common with hook managers) makes git silently ignore the hook.

### The hook is a seat belt, not a wall

A hook lives on the AI's side. It stops mistakes, not determination:

- `git push --no-verify` skips it, and so does deleting the file.
- It does not apply to pushes that bypass the git command: GitHub connectors and APIs (for example the GitHub
  tools some AI environments expose) write to GitHub directly.

The real wall is on GitHub's side.

## 3. The one manual step: protect `main` on GitHub

This cannot be done from code here, because it is a setting on your GitHub repository, and it is the only guard
that works no matter what tool pushes.

1. Open the repository on GitHub: **Settings, then Branches** (or **Rules, then Rulesets**).
2. Add a rule for the branch `main`.
3. Turn on **Require a pull request before merging**, and block **force pushes** and **deletions** of the branch.
4. Save.
5. Check it worked: from a normal clone run `git push origin HEAD:main`. GitHub should reject it.

I could not verify from here which of these options your plan offers: branch protection on private repositories
has historically needed a paid plan, so if the options are missing, that is why. Check GitHub's current docs
(search "about protected branches").

Do this step before you let an AI near a clone that has push access.
