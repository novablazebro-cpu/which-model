# Tools and workflow

1. `start_session(task)`: returns the goal, the acceptance criteria, the conventions and the quiz.
2. `answer_quiz(answers)`: editing unlocks when every answer is right.
3. `observe(frames, views)`: views are `report`, `timeline`, `sheet`, `filmstrip` and `footprints`.
   Trust the numbers in `report` and `timeline` over your reading of the images.
4. Edit. Every edit takes `expect=[...]`:
   - `set_root(frame, forward, left, height, heading)`: pelvis position (track coordinates) and facing
   - `set_pose(frame, angles)`: anatomical angles, e.g. {"left_shoulder.flexion": 15}
   - `plant_foot(side, start, end, forward, left, facing)`: pin a foot; `facing` sets where its toes point
     (default: the body heading at the plant's first frame). The tool solves the leg.
   - `swing_foot(side, start, end, apex)`: arc a foot between two plants
   - `batch(edits)`: several edits at once under one set of predictions; one `undo()` reverts them all
   - Every edit takes `dry_run=true`: the tool evaluates it, grades your predictions and shows what would
     change, but applies nothing. Use it to try ideas safely.
   - Every edit result ends with `CHANGED:`, a numeric before/after diff. Trust it over images.
5. `calc(expr)`: exact math on the scene (see guide('calculator')). Save numbers and use them as `$name`.
6. `check()`: lists every failed check with a hint, and the acceptance status.
7. `undo()` or `accept_discrepancy(reason)` after a failed prediction.
8. `finish(claims)`: at least 2 claims about the final result, at least one precise.
   The tool certifies only when every check, criterion and claim passes.
   If it says NOT CERTIFIED, the task is not done: fix it and call finish again.
9. `export()`: writes a .glb file that Blender opens.
10. `guide(topic)`: conventions, walking, predictions, calculator, tools.
