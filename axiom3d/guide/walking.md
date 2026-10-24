# Walking

## The recipe in axiom3d
1. **Root:** key `set_root` at the start and the end with the total travel (forward).
2. **Plants:** `plant_foot(side, start, end, forward=...)` pins a foot to the ground
   for those frames. The tool solves the leg every frame, so a planted foot can't slide.
3. **Swings:** `swing_foot(side, start, end, apex=0.08)` carries a foot in an arc
   from the plant that ends at `start` to the plant that begins at `end`.
4. **Alternate:** left swing, right swing, left swing... One foot is always down.
5. **Arms:** key `left_shoulder.flexion` / `right_shoulder.flexion` about ±15 deg,
   opposite to the same-side leg (left leg forward → left arm back).
6. **Check, then finish.**

## Reach: lower the pelvis
The leg is about 0.86 m long and the standing pelvis is at about 0.93 m, so a
straight leg only reaches straight down. For any step, **lower the pelvis**:
- At pelvis 0.89 m a foot can sit about 0.25 m in front of or behind its hip.
- In double support (both feet down, feet apart) use about 0.885 m.
- At mid-stance (one foot down, under the body) rise to about 0.92 m, so the
  knee is nearly straight. A constant low pelvis gives a crouched walk.
If `anatomy.ik_unreachable` fires, lower the root or put the plant nearer the hip.

## Reference angles (adult walking)
- Hip flexion: about +30 deg at heel contact, about -10 deg at push-off.
- Knee flexion: about 5-15 deg at mid-stance, about 60 deg peak in swing.
- Ankle: within about ±10-20 deg.
- Stance takes about 60% of a step cycle, swing about 40%.

## Phases of one leg
contact → loading → mid-stance → push-off → swing → contact.
While one leg is in mid-stance the other is in swing.

## Classic mistakes
- **Leg swings backward:** a sign error. Use positive hip flexion, or plant the
  next foot at a larger `forward` value.
- **Foot slides or moonwalks:** a foot on the ground was keyed instead of planted.
- **Both feet in the air:** two swings overlap. That's running, not walking.
- **Same foot twice:** walking alternates.
- **Crouch:** the pelvis is low all the time; add height keys at mid-stance.
