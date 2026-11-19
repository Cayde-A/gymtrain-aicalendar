# Mobile Customer Information Architecture

## Product Constraint

The customer app has exactly four primary destinations in a persistent bottom
tab bar:

1. Today
2. Training
3. Nutrition
4. Progress

New customer features must fit one of these destinations. A focused task may
open a sheet, camera, editor, or detail view, but it must return to its owning
tab and must not become a fifth primary destination.

Developer diagnostics, provider credentials, raw payloads, trigger internals,
and integration test controls are excluded from customer builds.

## 1. Today

Purpose: answer "What should I do now?" without requiring navigation.

Contents:

- recovery summary: sleep, HRV, Body Battery, and readiness when available;
- today's final training plan and a Start Workout command;
- calories, protein, hydration, and eating-window progress summaries;
- the next scheduled action, such as train, drink, eat, or close the eating window;
- Garmin and health-sync status with a user-readable retry action;
- first-training waiting state when no completed-workout anchor exists.

Today shows compact summaries. Editing a workout belongs to Training; editing a
meal or water entry belongs to Nutrition.

## 2. Training

Purpose: execute, review, and correct training.

Contents:

- today's workout rounds, movement cues, rest state, and completion progress;
- Garmin-imported sessions and local/manual session entry;
- set-level correction for exercise, order, weight, reps, RPE, pain, and notes;
- workout history grouped by day;
- post-workout AI review and next-day initial draft;
- PR and estimated 1RM details relevant to the selected exercise.

Garmin watch execution remains supported. The app is the correction and review
surface when watch-side exercise selection is insufficient.

## 3. Nutrition

Purpose: capture intake and manage the daily nutrition schedule.

Contents:

- camera-based food capture with an editable recognition result;
- barcode, search, favorites, and manual entry fallbacks;
- serving size, calories, protein, carbohydrate, and fat correction before save;
- meal history and daily macro totals;
- quick water logging and hydration progress;
- nutrition-plan selection, including maintenance, fat loss, muscle gain, and
  time-restricted eating such as 16:8;
- eating-window, meal, and hydration reminders with quiet-hours controls.

Photo recognition is an estimate, not an authoritative nutrition measurement.
The user must be able to correct food identity, ingredients, serving amount,
and cooking oil before the record affects daily totals.

## 4. Progress

Purpose: explain longer-term change and hold low-frequency account controls.

Contents:

- training volume, PR, estimated 1RM, and muscle-group frequency trends;
- recovery, sleep, body weight, measurements, calories, macros, and hydration trends;
- eight-week cycle position and adherence summaries;
- weekly and monthly reviews;
- goal editing and plan history.

The top-right settings control opens a sheet or nested settings state owned by
Progress. It contains:

- account and profile;
- Garmin, Apple Health, and Health Connect connections;
- notification categories, eating window, hydration cadence, and quiet hours;
- units, language, accessibility, and privacy controls;
- data export, cloud-sync choice, retention, and account/data deletion.

## Navigation Rules

- Use a four-item bottom tab bar on phone layouts.
- Preserve each tab's navigation state when switching tabs.
- Put the most common command at the top of each tab: Start Workout, Add Food,
  Add Water, or Review Progress.
- Use sheets for quick add, correction, filters, and settings.
- Use the operating-system camera and notification permission flows rather than
  recreating them as app pages.
- Deep links and notifications open the owning tab and focused task state.
- Do not expose Debug, API keys, raw Garmin data, provider switching, or manual
  trigger-policy internals to customers.

## Feature Placement

| Capability | Primary owner | Secondary summary |
| --- | --- | --- |
| Garmin recovery | Today | Progress |
| Today's workout | Training | Today |
| Training import and correction | Training | Today sync state |
| AI review and next plan | Training | Today next action |
| PR and training trends | Progress | Training exercise detail |
| Food photo/barcode/manual entry | Nutrition | Today nutrition progress |
| Calories and macros | Nutrition | Today progress |
| Water logging | Nutrition | Today hydration progress |
| 16:8 eating window and reminders | Nutrition | Today next action |
| Body and recovery trends | Progress | Today status |
| Devices, notifications, privacy | Progress settings sheet | Relevant error/action only |

## Customer And Operator Separation

The current local Web application remains an operator and UX-validation tool.
The native customer app consumes the same normalized domain data and planning
rules but presents only the four destinations above. Operator-only routes may
remain available in local development builds behind a separate developer mode;
they are not linked or shipped in the customer navigation.

## Initial Mobile Delivery Order

1. Four-tab app shell, local database, Today, and Training correction flow.
2. Nutrition manual entry, water logging, local notifications, and 16:8 window.
3. Barcode/search nutrition sources and editable food-photo recognition.
4. Progress trends, account/device settings, privacy lifecycle, and optional cloud sync.

