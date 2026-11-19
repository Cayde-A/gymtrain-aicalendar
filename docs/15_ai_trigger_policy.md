# AI Trigger Policy

TrainingOS should not call AI or external APIs every time data changes.

The system uses a local trigger policy so the user can choose when compute is spent and when automation is allowed.

## Default Policy

The MVP default is conservative:

- Post-workout AI review: manual copy/paste.
- Next-morning recovery adjustment: user-confirmed API call.
- Garmin workout push: user-confirmed push.
- Automatic API calls: disabled.
- Daily AI call cap: 2.

This keeps the workflow observable and avoids accidental model calls while import and correction are still being tested.

## Trigger Types

### Post-Workout AI Review

This happens after Garmin activity import and user correction.

Supported modes:

- `manual_copy_paste`: TrainingOS builds the compact packet and prompt; the user sends it manually to ChatGPT.
- `user_confirmed_api`: TrainingOS can call the AI API only after the user clicks a confirmation button.
- `auto_api_after_correction`: TrainingOS may call the AI API after correction is saved, but only if automatic API calls are enabled.

### Next-Morning Recovery Adjustment

This happens after Garmin sleep, HRV, Body Battery, readiness, and recovery data are synced.

Supported modes:

- `manual_copy_paste`: user manually sends the recovery-adjustment packet.
- `user_confirmed_api`: user confirms before TrainingOS calls the AI API.
- `auto_api_after_recovery_sync`: TrainingOS may call the AI API after recovery sync, but only if automatic API calls are enabled.

### Garmin Push

This controls when a generated workout is pushed to Garmin.

Supported modes:

- `manual_only`: user recreates or pushes the workout manually.
- `user_confirmed`: user confirms before TrainingOS pushes the workout.
- `auto_after_final_plan`: TrainingOS may push after the final plan is generated.

## Global Safety Switch

`auto_api_enabled` is the global switch for automatic API calls.

If it is off, automatic trigger modes do not execute automatically. The UI should show a manual or confirmation step instead.

## Daily Cap

`max_ai_calls_per_day` limits model calls for a local user.

TrainingOS enforces this through the API trigger gate before any future model request is made.

## Trigger Gate

The local trigger gate returns one of these statuses:

- `manual`: the selected mode is manual copy/paste or manual-only.
- `needs_confirmation`: the mode allows API use, but the user has not confirmed this specific action.
- `allowed`: the action may proceed.
- `blocked`: the action must not proceed.

The gate checks:

1. the selected mode for the trigger;
2. whether the user explicitly confirmed the action;
3. whether automatic API calls are globally enabled;
4. whether the daily AI call cap has already been reached.

Each gate decision can be recorded in `api_trigger_logs` for observability.

## Current MVP Behavior

The local review UI exposes the policy at:

```text
http://127.0.0.1:8787/settings
```

The AI review packet includes the active `trigger_policy` so each analysis can be audited later.

AI review still defaults to the manual copy/paste path. An optional Responses API adapter now supports `user_confirmed_api`, strict structured output, `store: false`, daily-cap enforcement, and reuse of an existing valid review. It never runs under the default manual policy and never treats its initial draft as a final plan. See [Structured AI Review Adapter](36_structured_ai_adapter.md).

The daily pipeline can consume the saved structured response, apply deterministic recovery and overlap rules, and generate a final Garmin payload.

The settings page provides standalone trigger checks. The daily pipeline uses the same gate before a Garmin write. Under the default `user_confirmed` mode, `--push --confirm-push` is required; denied decisions do not execute the Garmin command.
