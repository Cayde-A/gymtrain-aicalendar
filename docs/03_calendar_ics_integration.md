# Google Calendar and ICS Integration

## Role of Calendar

Google Calendar should be the scheduling and reminder layer.

It should contain:

- training day;
- session type;
- workout template;
- dynamic fields for weights and notes;
- reminder time;
- recovery and logging prompts.

It should not be the long-term source of truth for all set-level data.

## V4 ICS Design

V4 ICS should support:

- two-week training cycle;
- recurring events;
- fixed training window, initially 11:00-12:30;
- Gunyama Park Aquatic and Recreation Centre location;
- Top Set / Back-off / Accessory / Cardio structure;
- blank fields for actual training data;
- AI review field.

## Event Template

```text
TrainingOS V4 - Week A Push

Location:
Gunyama Park Aquatic and Recreation Centre

Readiness:
Morning Weight:
Sleep:
Garmin Recovery:
Body Battery:
HRV:

Primary:
Exercise:
Warm-up:
Top Set: ____ kg x ____ reps @ RPE __
Back-off: ____ kg x ____ reps x ____ sets

Accessories:
1.
2.
3.

Cardio:
Mode:
Duration:
Average HR:
Max HR:

Notes:
Pain:
Technique:
Fatigue:

AI Review:
Increase / Keep / Reduce / Deload / New PR
Next Target:
```

## Integration Levels

### Level 1: Manual ICS

Generate an `.ics` file and import it into Google Calendar.

Best for:

- immediate testing;
- stable reminders;
- confirming training flow.

### Level 2: Scripted ICS Regeneration

Maintain a structured training plan and regenerate ICS when the template changes.

Best for:

- updating blocks;
- adding deload weeks;
- changing schedule without editing events one by one.

### Level 3: Google Calendar API

TrainingOS writes completed summaries back into Google Calendar.

Example completed event:

```text
Completed
Chest Press: 95 kg x 5, new 5RM
Estimated 1RM: 111 kg
AI Review: Increase next top set by 2.5 kg
```

## Mobile Import Note

Google Calendar mobile apps generally do not directly import `.ics` files. The practical path is to import the file through Google Calendar web, then let it sync to mobile.

