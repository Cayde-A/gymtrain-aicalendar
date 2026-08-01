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
-> Plan is written to Supabase
-> Optional: export/send workout to Garmin or show in mobile/PWA
-> Google Calendar summary is updated
```

## Training Round Structure

A training round is a planned block of work.

Example:

```text
Round 1: Chest Press
Purpose: Top Set / PR exposure
Target: 92.5 kg x 3-5
RPE cap: 9
Decision rule:
  - If warm-up feels fast, attempt 92.5 x 5
  - If slow, keep 90 x 5

Round 2: Chest Press Back-off
Target: 80 kg x 6-7 x 3
RPE cap: 8

Round 3: Shoulder Press
Target: 45 kg x 7-8 x 3

Round 4: Cable Fly
Target: 3 x 12

Round 5: Stair Climber
Target: 20-25 min, HR 135-150
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
- exercise order;
- top-set target;
- back-off sets;
- accessory volume;
- RPE caps;
- cardio target;
- fallback rule if recovery is poor;
- short note for Garmin/Calendar;
- full note for TrainingOS.

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

