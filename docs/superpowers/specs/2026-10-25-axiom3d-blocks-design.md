# axiom3d blocks mode: design

Date: 2026-10-25. Status: approved (plan mode).

## Why
The user asked Haiku to build a Minecraft creeper "with the help of tools". axiom3d could build only the walking mannequin and vessels (surfaces of revolution); a creeper is boxes. The user chose: build a blocks mode first; shape + face (green boxes in the game's proportions plus the black face pixels); and a tool vs no-tool comparison (protocol on, protocol off, plain Python).

Lessons carried from the vase test (docs/eval/2026-10-25-haiku-vase.md): a defect the tool makes is a bug; the AI's picture must match what humans see; checks must catch "the numbers pass but it looks wrong"; and fewer, better tools. Blocks mode adds three ops.

## Design

### Conventions
Follow `guide/conventions.md`:
- units are **Minecraft pixels** (16 px = 1 block = 1 m on export); Z up
- the model **faces −Y**, and **its left is +X**
- integer coordinates only, within ±64 px; at most 32 boxes

### Ops (the only new tools)
- `add_box(name, low, high, color="green", expect, dry_run)`
  - corners `low` and `high` = [x, y, z]
  - the same name replaces that box; its paint is kept only where face sizes are unchanged, and the result says so
- `remove_box(name, expect, dry_run)`
- `paint_face(box, face, pixels, key=None, expect, dry_run)`
  - `face`: front/back/left/right/top/bottom of the model (−Y/+Y/+X/−X/+Z/−Z)
  - `pixels`: one string per row, **top row first, as seen looking at that face from outside**
  - default key: `g` green, `k` black, `w` white, `r` red, `b` blue, `y` yellow, `o` gold; `.` keeps the pixel as it is
  - the grid must match the face size; the error states the expected size
- Pixel order per face is fixed and documented in a table:

  | face | top row | columns, left to right |
  |---|---|---|
  | front | +Z up | −X → +X (the viewer's left is the model's right) |
  | back | +Z up | +X → −X |
  | left | +Z up | −Y → +Y |
  | right | +Z up | +Y → −Y |
  | top | the back edge | −X → +X |
  | bottom | the front edge | −X → +X |

### Model and geometry: new `axiom3d/model/blocks.py`
- `Box(name, low, high, color, paint: dict[face, tuple[str, ...]])` and a frozen `BlockModel(boxes)`
- `validate`, `face_size(box, face)`, `pixel_color(box, face, row, col)`
- `block_mesh(model) -> (Mesh, colors)`:
  - one quad per pixel, with its own 4 vertices (flat normals, one colour per quad), so there is no shared-vertex smear
  - reuse the face quad layout of `mesh.box()` (`axiom3d/mesh.py:80`)
- `measure_blocks(model)`:
  - bounds, height/width/depth
  - per-box size and centre
  - contacts: two boxes touch when they share a face or an edge; a single corner point does not count
  - floating boxes (not connected to the ground through contacts)
  - overlaps (positive volume)
  - mirror symmetry about x = 0
- `commands_to_model(cmds)` replays a command list. It is used by the grader for all arms.

### Checks: new `axiom3d/checks/blocks.py`, dispatched in `checks/base.py`
- `blocks.empty` (error)
- `blocks.below_ground` (error)
- `blocks.floating` (error)
- `blocks.overlap` (warning)
- Each check explains the cause in plain words, as the vessel checks do.

### Task `minecraft_creeper` (kind `"blocks"`)
- The goal gives sizes and the layout in words, not coordinates. Haiku must compute them.
- The face is an 8×8 grid "as seen looking at the creeper's face": `gggggggg/gggggggg/gkkggkkg/gkkggkkg/gggkkggg/ggkkkkgg/ggkkkkgg/ggkggkgg`.
- **12 criteria.** They match boxes by size, not name, so the raw arm can name boxes freely.
  1. one 8×8×8 head
  2. one body 8 wide (X) × 4 deep (Y) × 12 tall (Z); this catches a rotated body
  3. four 4×4×6 legs
  4. the lowest point is at z = 0, and every leg stands on it
  5. the body rests at z = 6 and the head at z = 18; total height 26
  6. two legs entirely in front of the body's centre and two behind, and in each pair one leg on each side of x = 0; this catches four legs in a row
  7. the head is centred over the body
  8. mirror-symmetric about x = 0
  9. no floating or overlapping boxes
  10. ≥95% of the visible non-face pixels are green
  11. the head's **front** face equals the face grid as seen from the front; this catches a face on the back and an upside-down face
  12. no black pixels on any other face; this catches a second face painted on the back or sides
- Reference (`tasks/reference.py`), in px:
  - legs at x −4..0 / 0..4 and y −6..−2 (front) / 2..6 (back), z 0..6
  - body −4,−2,6 → 4,2,18
  - head −4,−4,18 → 4,4,26
  - the face painted on the front
- **Confidence:** the leg layout (legs reaching out front and back, the body resting on their inner edges) is from my memory of the game's model code. I'm about 80% sure of it, and the design doc says so.

### Protocol, calculator and quiz
- Prediction subjects:
  - `box.<name>.<min_x|max_x|…|size_z|center_x…>`
  - `model.<height|width|depth>`
  - `pixel(<box>, <face>, <row>, <col>) is <colour>`
  - precise = within 1 px, or any pixel colour
- `calc` reads the same names (reserve `box` and `model`).
- The relevance gate compares `clip.blocks`.
- `make_blocks_quiz(seed)`, with numbers randomised:
  1. Which axis does the front face point along? (−Y)
  2. Looking at the creeper's face, is your left on its left or its right? (right)
  3. How tall is a box from z a to z b?
  4. Which pixel row comes first? (top)
  5. At what z does a body rest on legs h tall? (h)
- `CHANGED:` diff: boxes added, removed or moved; bounds deltas; faces repainted.

### Perception and export
- `observe` views:
  - `report`: a box table, contacts, floating and overlap, symmetry, and every painted face printed back as its grid with the model side named
  - `sheet`: a 2×2 render of FRONT, RIGHT SIDE, TOP and a three-quarter view, in pixel colours, with axis and "FRONT (−Y)" labels, reusing `Camera`/`_rasterize` in `perceive/render.py`
- `export`: GLB through the existing `export_mesh_glb` (`export/gltf.py:126`), scaled to 1/16 m per px.
- `guide('blocks')`, a new topic covering:
  - the conventions and the pixel-order table
  - the classic mistakes: legs side by side, a rotated body, the face on the back, upside down or mirrored, floating parts
  - the working method: calc → dry_run → observe sheet → check
- `guide('tools')` gains the blocks ops.

### Eval
- `eval/prompts.py`: tool lists for blocks, and `raw_prompt` for blocks. The raw arm writes `creeper.json`, a list of the same `add_box`/`paint_face` commands, with Python and numpy allowed. Same conventions and grid, but no feedback, renders, checks or quiz. This isolates what the tool's feedback is worth.
- `eval/blocks.py`, following `eval/vase.py`:
  - `grade_home(home)` and `grade_json(path)`; both rebuild a `BlockModel` and grade it with the same criteria
  - a bad command becomes an error row that grades what was built up to that point
- The scripted honest agent (`eval/agents.py`) supports blocks.

## Known limits
- One run per arm.
- The creeper face is left-right symmetric, so a mirrored face cannot be told apart from the right one. Quiz q2 tests mirroring instead.
- The leg layout comes from memory (about 80% confidence).
- The "haiku" alias is assumed to be Haiku 5.5.
- Still open from the vase: the style-reference proposal. It is not in this plan.
