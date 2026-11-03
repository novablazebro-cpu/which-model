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
| **test suite** | All the tests together. | 326 tests; run them with `uv run pytest -q`. |
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

## Minecraft servers (the Knell plugin plan, 2026-11-03)
| term | plain meaning | in this project |
|---|---|---|
| **chunk** | A 16 × 16 block column of a Minecraft world; the piece the game loads and generates one at a time. | The Knell's site is 12 × 12 chunks (192 × 192 blocks). |
| **biome** | A region with its own blocks, plants, colours and mobs. Its natural size comes from random noise, not a fixed number. | Tollmoor (surface) and Knell Hollow (underground). |
| **Paper** | The server software that runs your Minecraft server, with extra tools for plugin makers. | Paper 26.3, which needs Java 25. |
| **plugin** | Java code the server runs, adding behaviour: mobs, items, commands. | The Knell plugin: stamping the site, the boss, the mimic. |
| **datapack** | A folder of settings files Minecraft reads at startup: biomes, loot tables, recipes. | Packed inside the plugin, so you still install one file. |
| **tick** | One twentieth of a second, the server's heartbeat. | The stamper works a few chunks per tick so the server never freezes. |
| **seed** | A number that makes "random" choices repeatable: the same seed always gives the same result. | The same seed always digs the same caves. |
| **block display entity** | A floating block the server can move, turn and resize every tick. | About 100 of them make up the Knell's body. |
| **mannequin** | An entity shaped like a player that can wear a real player's skin. | The fake teammate at the end of a tunnel. |
| **loot table** | A file listing what a chest can contain and how likely each item is. | Common, rare, epic and boss-hoard chests. |
| **resource pack** | A download that changes textures and sounds on players' screens. | Needed later for custom item looks and the music disc. |
| **state machine** | A program that is always in exactly one state and has rules for moving between them. | The Knell's brain: asleep, waking, hunting, listening, mimicking, attacking, killed. |
| **Gradle** | A build tool: downloads the libraries a project needs and builds the final file. | Builds the plugin's `.jar`. |
| **dimension** | A whole separate world with its own rules for sky, light and terrain, like the Nether or the End. | The Knell's world: 30 × 30 chunks of rock with the Hollow inside. |
| **world border** | An invisible wall that sets how big a world can be. | 480 × 480 blocks around the Knell's dimension. |
| **noise** | Smooth randomness: nearby points get similar values. Makes cave walls look natural instead of perfectly round. | `Noise3.java` in the Knell repo. |
| **item model** | A resource-pack model shown on an item or a floating display, used to fake custom blocks. | The 13 assets in the brief for Gemini, e.g. `knell:great_bell`. |
| **flood fill** | Spreading out step by step from a start point to everything you can reach, like water filling rooms. | The test proving you can walk from the arrival chamber to the pit. |
| **mutation check** | Breaking the code on purpose to confirm a test notices. A test that stays green proves nothing. | Turning the tunnels off made the flood-fill test fail, as it should. |
