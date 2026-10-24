# Tools and workflow

1. `start_session(task)`: returns the goal, the acceptance criteria, the conventions and the quiz.
2. `answer_quiz(answers)`: editing unlocks when every answer is right.
3. `observe(frames, views)`: views are `report`, `timeline`, `sheet`, `filmstrip` and `footprints`.
   Trust the numbers in `report` and `timeline` over your reading of the images.
4. Edit. Every edit takes `expect=[...]`:
   - `set_root(frame, forward, left, height, heading)`: pelvis position (track coordinates) and facing
   - `set_pose(frame, angles)`: anatomical angles, e.g. {"left_shoulder.flexion": 15}
   - `plant_foot(side, start, end, forward, left)`: pin a foot; the tool solves the leg
   - `swing_foot(side, start, end, apex)`: arc a foot between two plants
5. `check()`: lists every failed check with a hint, and the acceptance status.
6. `undo()` or `accept_discrepancy(reason)` after a failed prediction.
7. `finish(claims)`: at least 2 claims about the final result, at least one precise.
   The tool certifies only when every check, criterion and claim passes.
   If it says NOT CERTIFIED, the task is not done: fix it and call finish again.
8. `export()`: writes a .glb file that Blender opens.
9. `guide(topic)`: conventions, walking, predictions, tools.
