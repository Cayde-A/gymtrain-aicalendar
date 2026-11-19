# TrainingOS Preset Training Rounds

## Decision

TrainingOS should generate the planned training rounds before the workout.

Garmin should execute and record the workout. It should not be responsible for deciding the training structure.

## Why This Is Better

Garmin watches are good at:

- timing the session;
- recording sets;
- recording reps;
- recording weight;
- recording heart rate;
- syncing the completed activity.

TrainingOS is better suited for:

- selecting today's exercises;
- choosing one primary large muscle group for the session;
- reducing muscle overlap across adjacent training days;
- choosing top-set target;
- choosing back-off volume;
- using Garmin recovery data;
- using historical PR data;
- adjusting for fatigue;
- designing the next training day.

## Morning Planning Flow

Recommended daily flow:

```text
06:30 Garmin recovery import
-> TrainingOS reads sleep, HRV, Body Battery, readiness, stress
-> TrainingOS reads recent training performance and PR history
-> AI Coach generates today's training rounds
-> User reviews and approves
-> Plan is written to local SQLite
-> Optional: export/send workout to Garmin or show in mobile/PWA
-> Google Calendar summary is updated
```

## Training Round Structure

A training round is a planned block of work.

TrainingOS should first select the primary large muscle group for the day. The plan should then build rounds around that target and keep secondary work limited.

Hard constraints:

- One session has one primary large muscle group.
- Adjacent days should avoid close overlap in prime movers, stabilizers, joints, and grip demands.
- Chest/shoulder training should usually be followed by legs, not back or arms.
- Back and arm work can return after the pressing chain has had more distance, unless recovery data and user notes show unusually low fatigue.
- If the prior day was chest/shoulders and recovery is moderate or low, the default next plan is leg priority with limited upper-body involvement.
- Medium/high-intensity core sessions can be inserted between the main split days only if they do not impair the next day's prime movers, bracing, or grip.

Default split with core inserted:

```text
Chest -> Core A -> Legs -> Core B -> Pull -> Rest
```

Current Garmin-compatible Pull preset:

- lat pull-down: 4 x 8;
- seated cable row: 3 x 10;
- face pull: 3 x 12;
- cable biceps curl: 2 x 12.

The exercise category/name pairs are checked against the installed `python-garminconnect` exercise catalog in automated tests.

Core A between chest and legs:

- kneeling cable crunch;
- weighted dead bug;
- side plank;
- no hanging leg raise or toes-to-bar;
- no high-volume hip-flexor work.

Core B between legs and pull:

- weighted crunch;
- Russian twist;
- McGill curl-up;
- no hanging or grip-heavy core;
- no heavy lower-back fatigue.

Example:

```text
Primary target: Legs

Round 1: Leg Press
Purpose: main lower-body work
Target: 4 x 10
RPE cap: 8
Decision rule:
  - If warm-up feels fast, keep planned load
  - If slow, reduce load or remove one set

Round 2: Romanian Deadlift
Target: 3 x 8
RPE cap: 8

Round 3: Goblet Squat
Target: 3 x 12

Round 4: Standing Calf Raise
Target: 2 x 15

Round 5: Plank
Target: 2 easy sets
```

## Data Inputs

Morning plan should use:

- today's Garmin recovery metrics;
- last 7-14 days of sleep and HRV;
- last 2-4 sessions for the target muscle group;
- PR history;
- missed reps;
- pain and technique notes;
- training phase, such as accumulation, intensification, or deload;
- upcoming calendar constraints.

## Output Targets

TrainingOS should produce:

- session type;
- primary large muscle group;
- avoided overlap from the previous training day;
- exercise order;
- short movement cues for each exercise;
- top-set target;
- back-off sets;
- accessory volume;
- RPE caps;
- cardio target;
- fallback rule if recovery is poor;
- short note for Garmin/Calendar;
- full note for TrainingOS.

## Movement Cues

TrainingOS should maintain its own text cues instead of copying Garmin animation or instruction content.

Each planned exercise can include one short cue:

```text
Bench Press:
Shoulder blades set, feet planted, controlled touch, press without bouncing.
```

Rules:

- Keep cues short enough for watch and phone display.
- Describe one to four form priorities, not a full coaching article.
- Avoid private, copyrighted, or scraped Garmin animation text.
- Prefer safety and repeatability: setup, range, tempo, stop condition.
- If Garmin accepts step descriptions, include the cue in the workout payload.
- If Garmin does not display the cue on a device, TrainingOS Web/App/Shortcut remains the source of truth.

## Garmin Execution Options

### Option A: Display Plan Outside Garmin

MVP recommendation.

```text
TrainingOS PWA / Shortcut / Calendar shows the plan
Garmin records Strength activity
User follows the plan manually
Garmin syncs completed data
TrainingOS imports and reconciles
```

This is easiest and avoids Garmin workout creation complexity.

### Option B: Create Garmin Connect Workout

Later option.

```text
TrainingOS generates workout structure
-> Garmin Connect workout format/API/manual creation
-> Send workout to watch
-> Watch guides each step
```

This gives a better watch experience, but Garmin workout creation and device sync are more complex.

### Option C: Custom Connect IQ App

Long-term option only.

Use only if TrainingOS needs a dedicated watch experience that Garmin's native Strength workflow cannot support.

## TrainingOS Feedback Loop

```text
Morning plan
-> Garmin execution
-> Garmin import
-> User correction/RPE notes
-> AI post-workout review
-> Next morning plan
```

This turns TrainingOS into the planning engine while preserving Garmin as the capture device.

## MVP Acceptance Criteria

The first preset-round MVP is successful when:

- TrainingOS can generate a clear morning plan from recovery + history.
- The user can follow it without editing Garmin exercise names during training.
- Garmin activity can be imported afterward.
- User can add RPE, pain, and corrections in under 60 seconds.
- The next plan uses the completed workout.
