# axiom3d vessel slice: modeling a Ming meiping vase

## Why
The user asked to test whether axiom3d helps a cheap model (Haiku 5.5) model a real object: the Chinese
meiping vase in their reference photo. axiom3d could only animate a mannequin, so this slice adds object
modeling. It follows the same principles: the AI states intent, the tool does the geometry and the
measurement, and the tool grades.

**User decisions:** build it now (pausing v2 after its Task 6), shape plus colour zones (no dragon
painting), and a three-way comparison: axiom3d with the protocol, axiom3d bare, and no axiom3d at all
(raw mesh code). Haiku runs at high effort.

**Process:** the user approved this design in chat, through the option questions. This document is the
written record; work proceeds without a separate spec-review round, by the user's direction.

## The object
A meiping (梅瓶) is a surface of revolution. Proportions measured from the reference photo:
- widest point: about 0.54 × the height, at about 72% of the height
- mouth: about 0.10 × the height, on a short narrow neck
- foot: about 0.33 × the height, slightly flared below a waist
- colours: a red body, a blue-and-white wave band at the foot, a blue rim

## Design
- **`axiom3d/model/vessel.py`**
  - **Data:** `VesselSpec(profile: tuple[(h, r)], wall: float, bands: tuple[Band(start, end, color)])`.
  - **Profile:** points are (height, radius) in metres, Z up, base at 0, axis through the origin. The profile is smoothed with monotone cubic (PCHIP-style) interpolation, so radii never overshoot, then sampled at 96 heights.
  - **Mesh:** `vessel_mesh(spec) -> (Mesh, colors)`. A watertight shell: outer surface, inner surface offset radially by `wall`, a lip ring, an outer base disk and an inner floor at `h = wall`. Per-vertex colours come from the bands; the default is porcelain white.
  - **Measurements:** `measure_profile(h, r, wall, color_at) -> VesselMeasures`:
    - height; max, mouth, neck, waist and foot diameters
    - shoulder height and ratio
    - capacity in litres
    - tip angle: `atan(foot_radius / centre-of-mass height)` of the shell
    - max profile turn in degrees
    - colour at any height
  - **No-tool runs:** `measure_obj(path)` parses `v x y z [r g b]` / `f`. It slices by height to derive the outer profile, checks it is watertight (every edge has exactly 2 faces), and returns the same `VesselMeasures`. Both arms are graded by identical criteria.
- **Commands (in `apply_command`):**
  - `shape_profile(points, wall=0.006)`: 3–64 points with strictly increasing heights, 0 < radius ≤ 1 m, 0.002 ≤ wall ≤ 0.03. It replaces the profile.
  - `paint_band(start, end, color)`: color is a name (`red`, `blue`, `white`, `green`, `yellow`, `black`, `gold`) or `#rrggbb`. Later bands paint over earlier ones.
  - Both are stored in `Clip.vessel`.
- **Task `meiping_vase`** (kind `vessel`). Criteria, all from the photo:
  - height in 0.35–0.45 m
  - max diameter / height in 0.48–0.60
  - shoulder ratio in 0.62–0.82
  - mouth / height in 0.07–0.14
  - foot / height in 0.26–0.40
  - neck diameter ≤ 1.05 × mouth
  - foot − waist diameter ≥ 0.005 m (the foot flares)
  - colour red at half height; blue somewhere in the lowest 20%; blue at the top
- **Checks (kind `vessel`):**
  - errors:
    - `vessel.no_profile`
    - `vessel.too_thin`: radius < wall + 2 mm above the floor
    - `vessel.mouth_closed`: mouth radius < 2 × wall
    - `vessel.unstable`: tip angle < 8°
  - warnings:
    - `vessel.kink`: profile turn > 45°
    - `vessel.band_outside`
- **Predictions and calc:**
  - New subjects `vessel.height|max_diameter|shoulder_height|shoulder_ratio|mouth_diameter|neck_diameter|waist_diameter|foot_diameter|capacity|tip_angle`.
  - Precise means a tolerance ≤ 0.02 m (≤ 0.05 for a ratio, ≤ 0.5 L for capacity, ≤ 5° for an angle).
  - `calc` gets the same `vessel.*` names plus `radius_at(h)`.
- **Workbench:** for vessel tasks:
  - `observe` reports the measurements, a profile table and colour zones; the `sheet` view renders the vase
  - `check`, `finish` and the diff use vessel measurements
  - two new tools, `shape_profile` and `paint_band`, for 17 in total
- **Export and viewer:** a static GLB with `COLOR_0` vertex colours; the HTML viewer hides the transport bar when there's no animation.

## Tasks (each test-first, then commit)
- **VT1:** vessel core (profile, mesh, measurements, OBJ measurement)
- **VT2:** commands, task, checks, and a reference solution that certifies
- **VT3:** Workbench, MCP, CLI, predictions and calc for vessels
- **VT4:** vessel GLB, static viewer, sheet render
- **VT5:** three Haiku runs (high effort), the comparison report, viewer pages for the user
