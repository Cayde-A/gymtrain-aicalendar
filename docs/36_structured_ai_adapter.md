# Structured AI Review Adapter

TrainingOS can send a compact post-workout packet to the OpenAI Responses API and save a validated review locally. The adapter is optional: deterministic import, correction, quality checks, planning, and Garmin push remain usable without an AI call.

## Safety Model

- Dry-run is the default.
- A live request requires both `--call` and `--confirm`.
- The local trigger policy must permit `post_workout_ai`.
- `OPENAI_API_KEY` must be available in the process environment.
- A completed training anchor with at least one active set must exist on or
  before the requested training date. Otherwise the adapter returns
  `waiting_for_first_training` or `first_training_needs_data` without building
  a request or consuming API capacity.
- The request sets `store: false`.
- The response must match the strict TrainingOS JSON Schema before it is saved.
- A valid existing structured review is reused unless `--force` is supplied.
- API error output excludes credentials, packet contents, and provider response text.

The generated request contains private training context. It is written below the ignored `exports/ai/` directory and must remain local.

## Dry Run

```bash
.venv-garmin/bin/python scripts/trainingos_openai_review.py \
  --date YYYY-MM-DD
```

This writes the exact request body locally and does not call OpenAI.

## Live Call

First select `user_confirmed_api` for post-workout review on the local settings page. Then provide the key through the process environment and explicitly authorize this call:

```bash
.venv-garmin/bin/python scripts/trainingos_openai_review.py \
  --date YYYY-MM-DD \
  --call \
  --confirm
```

The adapter returns one of these primary statuses:

- `review_saved`: strict output was validated and persisted.
- `existing_review_reused`: no API call was needed.
- `manual`: the configured policy remains manual copy/paste.
- `needs_confirmation`: the policy requires confirmation.
- `blocked`: the global policy or daily cap denied the call.
- `needs_api_key`: no API key was available.
- `openai_api_failed`: the API returned a non-success response.
- `invalid_structured_output`: output could not be parsed or failed local validation.

## Output Contract

The response contains:

- a compact performance summary and direction;
- risk and data-quality flags;
- one initial next-day draft with a single primary muscle group;
- optional interstitial core placement;
- exercise rounds with load guidance and RPE cap;
- rules for deterministic next-morning recovery adjustment.

AI output is never considered the final plan. The existing morning finalizer still applies recovery, overlap, program-cycle, venue, quality, and Garmin push gates.

## Verification Boundary

Automated tests use a fake requester and cover policy denial, missing-key denial, strict-schema requests, successful persistence and reuse, invalid output rejection, and numeric type validation. A real API call is intentionally deferred until the user supplies an API key and explicitly authorizes the external request.

## Official References

- [OpenAI Responses API quickstart](https://platform.openai.com/docs/quickstart?api-mode=responses)
- [OpenAI structured outputs guide](https://platform.openai.com/docs/guides/structured-outputs)
