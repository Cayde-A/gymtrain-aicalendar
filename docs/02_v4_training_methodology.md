# V4 PR Training Methodology

## Summary

TrainingOS V4 is centered on PR-based progression. It combines heavy top sets, back-off volume, accessory work, cardio, recovery tracking, and AI review.

The plan should avoid fixed long-term weights. Instead, each session uses a stable structure with dynamic weight selection.

## Muscle-Group Rotation

Each session should have one primary large muscle group target.

Default rule:

- Choose one primary target: legs, chest, back, shoulders, arms, core, or recovery.
- Keep secondary work small and clearly supportive.
- Adjacent training days should minimize overlapping muscles, joints, and stabilizers.
- After a chest/shoulder day, prioritize legs next.
- Do not make back or arms the primary next-day target after chest/shoulder work, because pressing fatigue often overlaps with triceps, front delts, scapular stabilizers, upper back, biceps, and grip.
- If recovery is poor, reduce the selected day's volume before switching to a nearby overlapping upper-body target.

This rule takes priority over convenience-based exercise selection. The goal is to preserve PR quality by reducing interference between adjacent sessions.

## Interstitial Core Work

Abdominal training can be inserted between chest, legs, and pull days, but it should not become hidden fatigue for the next primary session.

Default rotation:

```text
Chest
-> Core A
-> Legs
-> Core B
-> Pull
-> Rest or low-intensity cardio
```

Core A sits between chest and legs:

- Use kneeling cable crunch, dead bug, side plank, or controlled crunch variations.
- Keep intensity at RPE 7-8.
- Avoid high-volume hanging leg raises, toes-to-bar, and hard hip-flexor work before legs.
- Avoid maximal bracing work that could reduce squat, leg press, or hinge quality.

Core B sits between legs and pull:

- Use weighted crunch, Russian twist, McGill curl-up, or non-hanging anti-rotation work.
- Keep intensity at RPE 7-8.
- Avoid hanging or grip-heavy core before pull day.
- Avoid exercises that heavily tax lats, grip, or lower back.

Core sessions should usually be 15-25 minutes, 6-9 total work sets, and never trained to failure during PR-focused blocks.

## Session Structure

```text
Warm-up
-> Movement Skill
-> Top Set
-> Back-off Sets
-> Accessories
-> Cardio
-> Recovery Notes
-> AI Review
```

## Top Set

The top set is the main performance signal.

Typical targets:

- Week 1: 5RM focus
- Week 2: 4RM focus
- Week 3: 3RM focus
- Week 4: Recovery week, no PR attempt

Target effort:

- Normal day: RPE 8-9
- Low recovery day: RPE 6-7 or skip PR
- High readiness day: attempt small PR if warm-ups move well

## Eight-Week Program Cycle

V4 runs two four-week waves as one persisted 56-day block:

| Week | Phase | Top-set focus | Volume | PR allowed |
|---|---|---:|---:|---|
| 1 | Accumulation | 5 reps | 100% | Yes |
| 2 | Accumulation | 5 reps | 100% | Yes |
| 3 | Intensification | 4 reps | 90% ceiling | Yes |
| 4 | Deload | None | 55% ceiling | No |
| 5 | Accumulation | 5 reps | 100% | Yes |
| 6 | Intensification | 4 reps | 90% ceiling | Yes |
| 7 | Realization | 3 reps | 80% ceiling | Yes |
| 8 | Deload | None | 55% ceiling | No |

Recovery reduction and the scheduled volume ceiling are both evaluated; the
stricter set count wins. The cycle supplies guidance rather than fixed weights,
so equipment increments and warm-up performance remain user-controlled.

## Estimated 1RM

Use estimated 1RM to compare different rep ranges.

```text
Estimated 1RM = Weight x (1 + Reps / 30)
```

Example:

```text
120 kg x 8 = 152 kg estimated 1RM
140 kg x 2 = 149 kg estimated 1RM
```

This allows the system to detect progress even when the session does not include a true max single.

## Back-off Sets

Back-off work builds and maintains muscle while controlling fatigue.

Default rule:

- Back-off load: 80-88% of today's top set
- Sets: 2-4
- Reps: 5-8 for compound lifts, 8-12 for machine compounds
- RPE: 7-8

If top set performance is poor, reduce back-off volume before changing the whole plan.

## Accessories

Accessory work supports hypertrophy, weak points, joint health, and movement balance.

Default rule:

- 2-4 accessory exercises per session
- 2-4 sets each
- 8-15 reps
- RPE 7-9
- No frequent PR requirement

## Progression Rules

Use a simple decision model after each session.

| Result | Next Action |
|---|---|
| New PR, RPE <= 9, recovery acceptable | Increase next target slightly |
| Completed target reps, no PR, RPE 7-8 | Keep or small increase |
| Missed reps, RPE 9-10 | Keep weight |
| Two consecutive declines | Reduce load 5% or reduce volume |
| Poor Garmin recovery plus poor performance | Deload or back-off only |

The deterministic implementation also returns `establish_baseline` when an
exercise has no history. It never increases after an RPE 9+ result, and two
consecutive estimated-1RM declines produce a 5% reduction recommendation.

## Recovery Week

Every fourth week should reduce fatigue.

Default recovery week:

- No PR attempts
- 50-60% normal volume
- 80-85% normal working load
- No failure
- More Zone 2 cardio or swimming if recovery supports it

## Data Required After Each Workout

- Date
- Body weight
- Sleep or Garmin sleep score
- Recovery notes or Garmin readiness context
- Exercise
- Top set weight, reps, RPE
- Back-off sets
- Accessory sets
- Cardio duration and heart rate
- Pain, technique, fatigue, notes
- AI decision: Increase, Keep, Reduce, Deload, or New PR
