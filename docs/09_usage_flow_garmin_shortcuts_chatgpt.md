# Usage Flow: Garmin, Shortcuts, and ChatGPT

## Decision

TrainingOS should first use Garmin's built-in Strength activity as the workout recording surface whenever possible.

The goal is:

```text
Record sets on Garmin
-> Sync to Garmin Connect
-> Import to TrainingOS cloud database
-> Trigger analysis through Shortcut or API
-> Generate next-day training design
```

## Feasibility

This is feasible, but there are two levels.

## Level 1: Semi-Automated ChatGPT App Flow

This is the most practical first version.

```text
Garmin Strength Activity
-> Garmin Connect sync
-> TrainingOS Garmin Provider import
-> Supabase stores normalized workout data
-> Apple Shortcut gathers today's summary
-> Shortcut opens ChatGPT with prepared prompt
-> ChatGPT returns analysis and next-day plan
```

Use this when:

- the goal is fast MVP testing;
- human review is acceptable;
- the user wants to read and approve next-day training;
- native app development should be delayed.

Strength:

- low implementation cost;
- uses Garmin's native set/rep/weight flow;
- works well with the current TrainingOS V4/V5 direction.

Limitation:

- ChatGPT App Shortcuts are not the best source of truth;
- background automation may require confirmation;
- output may need to be copied or saved back unless a separate API/store path is used.

## Level 2: Fully Automated TrainingOS Flow

This is the preferred long-term version.

```text
Garmin Strength Activity
-> Garmin Connect sync
-> Garmin Provider import
-> Supabase
-> Cloud Function
-> OpenAI API analysis
-> Save ai_reviews + next planned session
-> Google Calendar update
-> optional Shortcut notification
```

Use this when:

- next-day training should be generated without manual copy/paste;
- AI recommendations must be saved into the database;
- calendar updates must be reliable;
- the workflow should work even if the ChatGPT app UI changes.

## Garmin Recording Options

### Option A: Built-In Garmin Strength Activity

Recommended first.

Garmin can record strength sets, reps, weight, rest periods, and exercise details. After sync, TrainingOS imports the activity from Garmin Connect.

Best for:

- MVP;
- low friction;
- no custom watch app;
- preserving Garmin's native activity history.

### Option B: Connect IQ Data Field

Useful later if extra TrainingOS metrics are needed during an activity.

Connect IQ data fields can record custom metrics into activity files, but they are not ideal for rich set-entry UI because direct user input belongs to the activity experience itself.

Best for:

- custom readiness score;
- custom PR target display;
- extra activity metrics.

### Option C: Connect IQ Device App

Possible, but not recommended for MVP.

A custom Garmin app can create and save FIT activity sessions and can use web requests through the phone as a bridge. This gives more control, but requires Garmin app development and more testing.

Best for:

- a dedicated TrainingOS watch app;
- custom training flow;
- direct server push.

## Recommended MVP Flow

```text
1. Start Garmin Strength activity.
2. Record sets/reps/weight on Garmin.
3. Save workout.
4. Let Garmin Connect sync.
5. TrainingOS imports the activity through Garmin Provider.
6. Apple Shortcut runs "TrainingOS Review".
7. Shortcut sends today's normalized summary to ChatGPT App or API.
8. AI returns:
   - PR status;
   - estimated 1RM;
   - fatigue risk;
   - next-day plan;
   - Increase / Keep / Reduce / Deload decisions.
9. Save approved recommendation into Supabase.
10. Update Google Calendar with completed summary and next target.
```

## Shortcut Roles

### Shortcut A: TrainingOS Review

Trigger:

- manual button after Garmin sync;
- Siri phrase;
- scheduled evening reminder.

Action:

- fetch today's workout summary;
- fetch Garmin recovery context;
- prepare prompt;
- open ChatGPT App or call API.

### Shortcut B: Tomorrow Training

Trigger:

- morning;
- before leaving for gym;
- calendar event start.

Action:

- read latest `ai_reviews`;
- show today's target;
- optionally open Garmin Strength activity manually.

### Shortcut C: Quick Correction

Trigger:

- after noticing Garmin misread reps or exercise.

Action:

- open lightweight TrainingOS correction form;
- update Supabase record;
- mark Garmin raw data as corrected.

## Product Decision

For V5, use:

```text
Garmin built-in Strength activity
+ Garmin Provider import
+ Supabase
+ Shortcut-triggered ChatGPT review
```

For V6, move the analysis from the ChatGPT app UI to a backend AI workflow:

```text
Supabase
+ Cloud Function
+ OpenAI API
+ Calendar sync
+ Shortcut notification
```

This keeps the user experience simple now while preserving a reliable automation path later.

