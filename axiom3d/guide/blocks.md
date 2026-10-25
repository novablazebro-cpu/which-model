# Blocks

A block model is built from boxes, measured in Minecraft pixels (px): 16 px = 1 block = 1 m when exported.
Every corner is a whole pixel. Z is up and the model stands on z = 0.

## Which way is which
- The model **faces -Y**. Its own **left is +X**, its right is -X.
- Standing in front of it, looking at its face, **the viewer's left is the model's right**.
  This is the most common mistake: picture yourself inside the model, not looking at it.

## Boxes
- `add_box(name, low=[x, y, z], high=[x, y, z], color="green")`: every high value is greater than the low
  one; size = high - low. Names are lowercase letters, digits and `_`, e.g. `leg_front_left`.
- The same name again replaces that box (its paint stays on faces whose size did not change).
- `remove_box(name)`.
- A box **rests on** another when its low z equals the other's high z and they share some x and y.
  Touching along an edge counts. Touching at a single corner does not: that box floats.
- Width is along X, depth along Y, height along Z. "8 wide, 4 deep, 12 tall" is size [8, 4, 12].

## Faces and pixels
`paint_face(box, face, pixels)` paints one face. `pixels` is a list of strings: one string per row,
**top row first, as seen looking at that face from outside**. One letter per pixel:
g green, k black, w white, r red, b blue, y yellow, o gold, and `.` keeps the pixel as it is.
Your own letters: `key={"d": "#0b6e0b"}`. The grid must match the face: as many rows as the face is tall,
as many letters per row as it is wide (the error says the size it needs).

| face | points | its rows | its columns, left to right |
|---|---|---|---|
| front | -Y | top row = highest | -X to +X (from the model's right to its left: the viewer's left is the model's right) |
| back | +Y | top row = highest | +X to -X |
| left | +X | top row = highest | -Y to +Y (front to back) |
| right | -X | top row = highest | +Y to -Y (back to front) |
| top | +Z | top row = the back edge | -X to +X |
| bottom | -Z | top row = the front edge | -X to +X |

Painting the front face is like painting a picture of the model's face as you see it: copy the picture
row by row, top row first. Do not mirror it.

## Measurements and predictions
- `box.<name>.min_x`, `max_z`, `size_y`, `center_x`, ... (min, max, size, center of x, y or z).
- `model.width`, `model.depth`, `model.height`, `model.min_z`, `model.max_z`.
- `pixel(<box>, <face>, <row>, <col>) is <colour>`: row 1 is the top row, column 1 the left one, as seen.
- `calc` reads all of these: `calc('box.head.min_z - box.body.max_z')`.

## Common mistakes (the criteria and checks catch them)
1. **Legs side by side.** "Two legs in front and two behind" means two different y ranges, not four in a row.
2. **A box turned 90 degrees.** 8 wide and 4 deep is [8, 4, ...], not [4, 8, ...].
3. **The face on the back.** The front is -Y: the face goes on `front`, not `back`.
4. **An upside-down face.** Row 1 is the top row.
5. **A mirrored face.** On the front face, column 1 is at -X: the model's right, your left.
6. **Floating parts** (`blocks.floating`): a gap of 1 px or a corner-only touch leaves a box in the air.
7. **Overlaps** (`blocks.overlap`): boxes should meet at faces, not pass into each other.

## Working method
1. Write down every box's low and high corner first. Use `calc` for sums such as the z where a box rests.
2. Add boxes from the ground up, with `dry_run=true` when unsure, and read the CHANGED block.
3. Paint, then `observe(views=['sheet'])`: look at the front view and check the face is the right way up.
4. `check`, fix what fails, then `finish`.
