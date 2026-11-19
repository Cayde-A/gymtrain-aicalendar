# Local Voice Input

TrainingOS provides a local voice-assisted entry path for new workouts and imported-session correction. The transcript is parsed into ordinary editable fields and is never written to SQLite.

## Entry Points

- `/entry`: create a local strength session from structured fields or short voice phrases.
- `/session?id=...`: fill one selected set in an imported session before saving the correction.

The browser microphone uses the Web Speech API when the current browser supports it. Typed text uses the same parser and remains the fallback. Browser speech recognition may be implemented by the browser or operating-system vendor and is not guaranteed to process audio entirely on-device; users requiring fully local audio processing should type the phrase instead.

## Supported Phrases

Examples:

```text
杠铃卧推 八十公斤 八次 RPE八
Leg Press 120 kg 10 reps 3 sets
再来一组
再来一组 减十公斤
```

Each accepted set requires an exercise, weight, and repetitions. RPE is optional. `再来一组` copies the preceding set and can apply a weight increase or reduction. A phrase may expand to at most 12 sets.

## Persistence Rules

- Parsing alone does not save anything.
- All parsed values remain editable before submission.
- New sessions use provider `local` and source `local_manual_entry`.
- Existing-session voice correction is a temporary form fill until the user presses the normal save button.
- Raw transcript and audio are not stored in TrainingOS.
- Saved sets use the existing normalized SQLite and PR processing path.

## Validation

The parser rejects missing exercise, weight, or repetitions; invalid RPE; impossible set counts; and out-of-range values. It accepts Arabic numbers and common Chinese numbers through hundreds, including decimals.

Automated tests cover Chinese and English phrases, multi-set expansion, repeat and weight adjustment, missing fields, manual session persistence, and non-persistent correction previews.
