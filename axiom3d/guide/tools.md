# Tools and workflow

1. `start_session(task)`: returns the goal, the acceptance criteria and the conventions. With the protocol on,
   it also returns a short quiz.
2. `answer_quiz(answers)`: only with the protocol on (the default). Editing unlocks when every answer is right.
   With the protocol off there is no quiz: start editing straight away.
3. `observe(views)`: look at the result.
   - Vessels: `report` (measurements as text) and `sheet` (a side view beside the profile plot).
   - Blocks: `report` (boxes, contacts, painted faces) and `sheet` (front, side, top, three-quarter).
   - Figures: `report`, `timeline`, `sheet`, `filmstrip` and `footprints`, at chosen `frames`.
   Trust the numbers over your reading of the images, but do look: the criteria do not judge everything.
4. Edit. With the protocol on, every edit takes `expect=[...]`, predictions the tool checks after the edit.
   - Vessels: `shape_profile(points, wall)` sets the side profile, [height, radius] pairs from the base up;
     `paint_band(start, end, color)` paints heights start to end, both included. See guide('vessels').
   - Figures: `set_root(frame, forward, left, height, heading)` places the pelvis; `set_pose(frame, angles)`
     sets anatomical angles, e.g. {"left_shoulder.flexion": 15}; `plant_foot(side, start, end, forward, left,
     facing)` pins a foot and the tool solves the leg; `swing_foot(side, start, end, apex)` arcs a foot
     between two plants. See guide('walking').
   - Blocks: `add_box(name, low, high, color)` places a box with whole-pixel corners; `remove_box(name)`;
     `paint_face(box, face, pixels)` paints a face pixel by pixel, top row first as seen. See guide('blocks').
   - `batch(edits)`: several edits at once under one set of predictions; one `undo()` reverts them all.
   - Every edit takes `dry_run=true`: the tool evaluates it and shows what would change, but applies nothing.
   - Every edit result ends with `CHANGED:`, a numeric before/after diff. Trust it over images.
5. `calc(expr)`: exact math on the scene (see guide('calculator')). Save numbers and use them as `$name`.
6. `check()`: lists every failed check with a hint, and the acceptance status.
7. `undo()`, or with the protocol on `accept_discrepancy(reason)`, after a failed prediction.
8. `finish(claims)`: with the protocol on, claims are a LIST of short statements in the prediction syntax,
   e.g. ["vessel.foot_diameter ~= 0.10 ± 0.01", "color(0.05) is gold"]: at least 2, at least one precise.
   The tool certifies only when every check, criterion and claim passes; NOT CERTIFIED means the task is not
   done. With the protocol off, `finish` closes the session and reports the acceptance result.
9. `export()`: writes a .glb file that Blender opens.
10. `guide(topic)`: conventions, walking, vessels, blocks, predictions, calculator, tools.
