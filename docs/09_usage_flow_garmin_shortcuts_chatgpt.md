# Usage Flow: Garmin, Shortcuts, and ChatGPT

## Decision

TrainingOS should first use Garmin's built-in Strength activity as the workout recording surface whenever possible.

The goal is:

```text
TrainingOS generates planned training rounds
-> User executes with Garmin Strength Activity
-> Sync to Garmin Connect
-> Import to local TrainingOS database
-> User corrects workout record
-> Trigger post-workout analysis manually through Shortcut or API
-> Generate initial next-day training draft
-> Adjust the draft after next-day recovery import
```

## Feasibility

This is feasible, but there are two levels.

## Level 1: Semi-Automated ChatGPT App Flow

This is the most practical first version.

```text
Garmin Strength Activity
-> TrainingOS morning plan shown in PWA/Shortcut/Calendar
-> Garmin Connect sync
-> TrainingOS Garmin Provider import
-> Local SQLite stores normalized workout data
-> User corrects workout record
-> User manually opens AI post-workout analysis and initial-plan draft
-> ChatGPT returns post-workout review and initial next-day plan
-> Next-day Garmin recovery metrics refine the draft before final push
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
-> TrainingOS planned rounds
-> Garmin Connect sync
-> Garmin Provider import
-> Local SQLite
-> User correction or auto-validation
-> Cloud Function
-> OpenAI API post-workout analysis
-> Save ai_reviews and initial next-day draft
-> Next-day recovery import
-> Adjust next planned session
-> Optional monthly minimized Supabase sync
-> Google Calendar update
-> optional Shortcut notification
```

Use this when:

- post-workout analysis should be saved without manual copy/paste;
- next-day training should have an initial draft before sleep data and a final adjustment after sleep data;
- AI recommendations must be saved into the database;
- calendar updates must be reliable;
- the workflow should work even if the ChatGPT app UI changes.

## Garmin Recording Options

### Option A: Built-In Garmin Strength Activity

Recommended first.

Garmin can record strength sets, reps, weight, and rest periods. TrainingOS should provide the planned exercise order and target rounds before the session, because exact exercise/equipment correction is more reliable in TrainingOS or Garmin Connect after sync.

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
1. Morning Garmin recovery metrics are imported.
2. TrainingOS reads recent PR and workout history.
3. TrainingOS generates today's training rounds.
4. User reviews the plan in PWA, Shortcut, or Calendar.
5. User starts Garmin Strength activity and follows the TrainingOS plan.
6. User records sets/reps/weight on Garmin.
7. Save workout and let Garmin Connect sync.
8. TrainingOS imports the activity through Garmin Provider.
9. User adds corrections, RPE, pain, and notes.
10. User manually enters AI post-workout analysis and initial-plan draft.
11. AI returns:
   - PR status;
   - estimated 1RM;
   - fatigue risk;
   - data quality issues;
   - initial next-day training draft;
   - next-morning adjustment rules;
   - Increase / Keep / Reduce / Deload decisions.
12. Save approved analysis and initial draft into local SQLite.
13. Next morning Garmin sleep and recovery metrics are imported.
14. TrainingOS adjusts the draft after recovery sync.
15. User approves the plan before Garmin push.
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

Important:

- This review should analyze the completed session and create an initial next-day draft.
- The draft should not become the final Garmin workout until next-day recovery metrics are imported and applied.

### Shortcut B: Tomorrow Training

Trigger:

- morning;
- before leaving for gym;
- calendar event start.

Action:

- import next-day Garmin sleep and recovery metrics;
- read latest `ai_reviews`;
- show today's target;
- show TrainingOS-generated training rounds;
- optionally open Garmin Strength activity manually.

### Shortcut C: Quick Correction

Trigger:

- after noticing Garmin misread reps or exercise.

Action:

- open lightweight TrainingOS correction form;
- update local SQLite record;
- mark Garmin raw data as corrected.

## Product Decision

For V5, use:

```text
Garmin built-in Strength activity
+ Garmin Provider import
+ Local SQLite
+ Shortcut-triggered ChatGPT review
```

For V6, move the analysis from the ChatGPT app UI to a backend AI workflow:

```text
Local SQLite
+ Cloud Function
+ OpenAI API
+ Monthly minimized Supabase sync
+ Calendar sync
+ Shortcut notification
```

This keeps the user experience simple now while preserving a reliable automation path later.
