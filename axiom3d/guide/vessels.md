# Vessels

A vessel (vase, bottle, jar) is a surface of revolution: one side profile spun
around the Z axis. You give the profile; the tool smooths it, builds a closed
shell with a wall, and measures everything.

## The profile
- `shape_profile(points=[[height, radius], ...], wall=0.006)`: 3 to 64 points.
- The first point is the base: height 0. Heights strictly increase up to the mouth.
- The second number is the **radius**: the distance from the axis, half the diameter.
- Z is up. The vessel stands on z = 0.
- A new `shape_profile` replaces the whole profile and keeps the paint.

## How the curve follows your points
The tool joins your points with a smooth monotone curve:
- The curve passes through every point exactly.
- It never bulges past your points. The widest point of the vessel is your
  point with the largest radius, at exactly that height. The narrowest is your
  point with the smallest radius.
- So put a point exactly where you want the widest point, the waist and the
  neck, and use a few points in between to shape the curves.

## Anatomy, from the bottom up
| part | what it is | how to make it |
|---|---|---|
| foot | the ring the vessel stands on | the first point's radius |
| waist | the narrowest point below the widest | a point narrower than the foot, just above it (a meiping's waist sits in the lowest ~10%) |
| body | the swelling part | radii growing toward the shoulder |
| shoulder | the widest point | your largest radius |
| neck | the narrowest point above the shoulder | a small radius just below the top |
| mouth | the opening at the top | the last point's radius (a lip: slightly wider than the neck) |

## Measurements (all diameters = 2 × radius)
- `vessel.height`: the last point's height.
- `vessel.max_diameter`, at `vessel.shoulder_height`; `vessel.shoulder_ratio` = shoulder height / height.
- `vessel.mouth_diameter` (last point), `vessel.foot_diameter` (first point).
- `vessel.neck_diameter`: the narrowest above the shoulder. `vessel.waist_diameter`: the narrowest below it,
  at `vessel.waist_height`.
- `vessel.capacity`: litres inside (radius − wall, from the floor at h = wall to the mouth).
- `vessel.tip_angle`: degrees it can tilt before it falls; atan(foot radius / centre-of-mass height).

`calc` reads all of these, plus `radius_at(h)`, the smoothed radius at any height.

## Paint
- `paint_band(start, end, color)`: start and end are heights in metres, not fractions, both included:
  a band from 0 to 0.05 also paints h = 0.05.
- Colours: red, blue, white, green, yellow, black, gold, or `#rrggbb`. Unpainted is porcelain white.
- Later bands paint over earlier ones (where two bands touch, the later one wins), so paint the big area
  first, then the details.
- Predict paint with `color(h) is red`.

## Common mistakes (the checks catch them)
1. **Diameter typed as radius.** The vessel comes out twice as wide. Divide every diameter by 2.
2. **Wrong axis.** Height is the first number of each point, along +Z.
3. **Shoulder too low.** The widest point at mid-height makes a jar, not a high-shouldered vase. Check `vessel.shoulder_ratio`.
4. **No neck.** If the mouth is the narrowest point, there is no neck. Add a point narrower than the mouth just below the top.
5. **Wall vs neck** (`vessel.too_thin`): the inside is radius − wall. It must stay at least 2 mm wide.
6. **Steps** (`vessel.kink`): two points close in height with very different radii make a ledge.
7. **Closed mouth** (`vessel.mouth_closed`): the mouth radius must be at least 2 × wall.
8. **Tipping** (`vessel.unstable`): a tiny foot under a heavy body falls over below 8°.
9. **Hourglass.** A waist placed high up (say a fifth of the way up) pinches the lower body into a stem.
   Keep the narrowest point just above the foot; `vessel.waist_height` tells you where it is.

## Working method
1. Turn every ratio in the task into a radius with calc first, e.g. `r = 0.54 * 0.40 / 2`.
2. Try the profile with `dry_run=true` and read the CHANGED block.
3. Apply it, then `observe(views=['sheet'])` and `check`; fix what fails; then paint.
4. Look at the sheet before `finish`: the criteria measure proportions, not whether the vase looks right.

## Example (a simple bottle, not any task's answer)
`[[0, 0.040], [0.02, 0.042], [0.15, 0.045], [0.20, 0.030], [0.25, 0.012], [0.28, 0.013]]`
