# Usage Flow Test v0.1

## Objective

Test the current TrainingOS MVP flow before building deeper automation.

This test checks whether the system can support the real-world experience:

```text
Plan workout
-> record workout
-> attach Garmin recovery context
-> analyze with AI
-> produce next-session plan
-> optionally update calendar
```

## Test Scope

Included:

- Google Calendar / ICS planning flow;
- Garmin Strength activity as the preferred recording surface;
- manual fallback workout log;
- PR and estimated 1RM calculation;
- AI post-workout review;
- next-session target generation.

Excluded:

- real Garmin API sync;
- Supabase production setup;
- Google Calendar API write-back;
- Apple Shortcut automation;
- native app behavior.

## Test Participants

- Athlete: primary TrainingOS user.
- AI Coach: ChatGPT or API review layer.
- Data Store: simulated Supabase record.

## Test Preconditions

- TrainingOS project documents are available.
- Workout log template is available.
- AI review prompt is available.
- At least one planned workout exists in calendar or test notes.
- Garmin watch can record a Strength activity, or manual log fallback is ready.

## End-to-End Test Steps

### Step 1: Planned Session

Create or select a planned session.

Expected result:

- Session type is clear.
- Main lift is clear.
- Top Set target rep range is clear.
- Back-off rule is clear.
- Notes fields are available.

Status:

```text
Pass / Fail:
Notes:
```

### Step 2: Garmin Recording

Use Garmin Strength activity during the workout.

Record:

- exercise;
- sets;
- reps;
- weight;
- rest if available.

Expected result:

- Workout can be saved on Garmin.
- Garmin Connect receives the activity.
- If exercise names are imperfect, the set data is still usable.

Status:

```text
Pass / Fail:
Notes:
```

### Step 3: Manual Fallback Log

If Garmin data is incomplete, fill the workout log template manually.

Expected result:

- Top Set and back-off work are captured.
- RPE and notes are captured.
- Cardio summary is captured.

Status:

```text
Pass / Fail:
Notes:
```

### Step 4: Recovery Context

Attach Garmin recovery context.

Minimum fields:

- sleep;
- sleep score;
- HRV status;
- Body Battery;
- training readiness;
- stress;
- recovery time.

Expected result:

- Recovery data can be tied to the same calendar date as the workout.

Status:

```text
Pass / Fail:
Notes:
```

### Step 5: AI Review

Send the completed workout and recovery context to the AI review prompt.

Expected result:

- AI identifies PR status.
- AI calculates or confirms estimated 1RM.
- AI returns fatigue risk.
- AI returns next target.
- AI gives one clear next-session decision.

Status:

```text
Pass / Fail:
Notes:
```

### Step 6: Next-Day Plan

Convert the AI result into a next-day training plan.

Expected result:

- Main lift target is clear.
- Back-off rule is clear.
- Recovery adjustment is clear.
- The plan can be copied into calendar, Supabase, or workout notes.

Status:

```text
Pass / Fail:
Notes:
```

### Step 7: Calendar Summary

Prepare a short completed-session calendar summary.

Expected result:

```text
Completed
Main lift:
Top Set:
Estimated 1RM:
Decision:
Next target:
```

Status:

```text
Pass / Fail:
Notes:
```

## Sample Test Data

```text
Date: 2026-07-31
Session Type: Push
Location: Gunyama

Readiness
- Morning Weight: 94.2 kg
- Sleep: 7h 42m
- Garmin Sleep Score: 82
- HRV: Balanced
- Body Battery: 71
- Training Readiness: 76
- Recovery Time: 14h
- Stress: 32

Main Exercise
- Exercise: Chest Press
- Warm-up: 40 x 10, 60 x 6, 75 x 3
- Top Set: 90 kg x 5 @ RPE 8.5
- Back-off 1: 77.5 kg x 7 @ RPE 8
- Back-off 2: 77.5 kg x 7 @ RPE 8
- Back-off 3: 77.5 kg x 6 @ RPE 8.5

Secondary Exercise
- Exercise: Shoulder Press
- Sets: 45 kg x 8, 45 kg x 7, 42.5 kg x 8
- RPE: 8

Accessories
1. Cable Fly: 3 x 12
2. Triceps Pressdown: 3 x 10
3. Lateral Raise: 3 x 15

Cardio
- Mode: Stair Climber
- Duration: 22 min
- Average HR: 142
- Max HR: 154

Notes
- Pain: none
- Technique: stable
- Fatigue: moderate
- Pump: good
- General Notes: top set moved well, final back-off rep speed slowed.
```

## Expected AI Review for Sample

```text
Session score: Good
Estimated 1RM: 105.0 kg
PR status: Check against history; if prior 5RM < 90 kg, mark New 5RM.
Fatigue risk: Low to moderate
Decision: Small Increase or Keep
Next target: 92.5 kg x 3-5 if recovery remains acceptable
Back-off target: 80 kg x 6-7 x 3
Practical recommendation: attempt small top-set increase only if warm-ups feel fast.
```

## Pass Criteria

The flow passes if:

- workout can be recorded with either Garmin or manual fallback;
- recovery context can be attached;
- AI can produce a next-session target;
- user can understand tomorrow's plan in less than 30 seconds;
- no private Garmin credential or raw export is committed.

## Findings

```text
Date:
Tester:
Result:
Main friction:
Data missing:
Decision:
Next iteration:
```

