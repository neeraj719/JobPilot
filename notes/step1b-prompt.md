# Step 1b — Runner ordering fix and standing answers

You are a senior developer on JobPilot AI. This step closes two gaps found while verifying
Step 1. Work only inside `C:\Users\Neera\projects\job application`. Read
`docs/ARCHITECTURE.md` §3.2 and `docs/CONTRACTS.md` §11–12 first. Do not commit.

## Gap A — the runner pauses before it answers, so counters and the run log are wrong

**Observed.** `tests/test_runner_demo_ats.py::test_pipeline_auto_applies_to_the_demo_ats_end_to_end`
fails with `assert 0 == 1` on `steps["autofill"]["data"]["filled"]`. The pipeline log for
that run reads:

```
autofill: SUCCESS - 0 forms filled, 1 need a human, 0 failed
approval_queue: SUCCESS - 0 ready for review, 1 need your input
auto_submit: SUCCESS - 1 applications submitted automatically
finish: ... 1 queued, 0 ready for review, 1 need your input
```

The application was in fact filled and submitted, but the autofill and approval counters
say otherwise and the user-facing summary tells the user they have work to do when they do
not.

**Cause.** `ApplicationRunner` (`backend/app/modules/browser/runner.py`) lets
`fill_application` run before the questions it just detected on the page have answers.
When the form has a question with no stored answer the adapter returns `REQUIRES_USER`
(`UNKNOWN_QUESTION`), the runner pauses, `record_snapshot_questions` creates the answer
rows, and only later does the answer engine fill them, after which the pipeline's submit
step approves and submits. The pause was never needed.

**Fix.** In the runner, after `start_application` succeeds and before `fill_application`:

1. Detect the form (`browser.detector.detect_form`) and map fields
   (`browser.mapper.FieldMapper`) to get the full question list for this page.
2. Record any questions not yet present as `ApplicationAnswer` rows
   (`applications.service.record_snapshot_questions` or a sibling that works from the
   detected fields rather than a snapshot).
3. Run the answer engine (`applications.answers.generate_answers`) for the unanswered rows
   so profile facts and permitted AI answers are in place.
4. Only then call `fill_application`. If a **required** answer is still
   `NEEDS_USER_INPUT`, pause with `UNKNOWN_QUESTION` as today; optional unanswered
   questions never pause (same rule as `approve()`).

Avoid detecting the form twice when the adapter's `fill_application` also detects it: pass
the detected form through `ApplyContext` (add an optional `detected_form` attribute) and
let `GenericAtsFormAdapter.fill_application` reuse it when present.

The autofill step counters in `pipeline.py` must then read `1 forms filled, 0 need a human`
for the demo run, and `requires_user` in the final stats must be 0 when nothing is waiting
on the user. Make the failing end-to-end test pass without changing its assertions.

## Gap B — standing answers

**Observed.** The demo form asks two things the answer engine deliberately never decides
for a human: a data-processing consent checkbox and a preferred start date. Real ATS forms
ask the same kind of thing on every application (consent, notice period, start date,
willingness to relocate, salary expectation, work authorisation, how did you hear about
us). Today each one pauses the first application at every company, so unattended apply
never completes for a new user.

**Fix.** Add "standing answers": answers the user gives once and the engine reuses.

- Model: `StandingAnswer` in `backend/app/models/profile.py`, table
  `master.standing_answers`, `StandardColumnsMixin`, columns `user_id` (FK), `question_key`
  (the canonical key from `browser/mapper.py` / `applications/questions.py`, e.g.
  `custom:consent`, `std:notice_period_days`, `std:earliest_start_date`), `question_text`
  (what the user saw), `field_type`, `answer`, `applies_to` (`ALL` or a list of
  `JobSourceType`), `expires_at` (nullable), `is_active`. Unique on
  `(user_id, question_key) WHERE deleted_at IS NULL`. One Alembic migration.
- Answer engine (`applications/answers.py`): lookup order becomes
  user-typed answer on this application → **standing answer** → profile/resume/preference
  facts → AI (free text only) → `NEEDS_USER_INPUT`. A standing answer is recorded with
  `AnswerSource.USER` and rationale "Standing answer you saved".
- Consent and legal declarations: a standing answer may satisfy them **only** if the stored
  `question_text` matches the detected question text closely (normalised, ≥ 0.9 similarity
  using the existing fuzzy helper in `jobs/dedupe.py` or `difflib`). A consent box with
  different wording still pauses. Demographic questions never use standing answers.
- Capture: when the user answers a `NEEDS_USER_INPUT` question in the UI
  (`PUT /applications/{id}/answers`), accept an optional `save_as_standing: bool`. When
  true, upsert the standing answer.
- API: `GET/PUT/DELETE /profiles/standing-answers` for the Profile page. Service logic in
  `profiles/service.py`, router thin.
- Frontend: a "Standing answers" card on `Profile.tsx` listing saved answers with edit and
  delete, and a "Remember this answer" checkbox in the Approval Center's answer form.
- Seed: give the demo user standing answers for consent (matching the demo form's wording
  exactly) and start date, so the seeded account's first unattended run completes.

## Tests

- Runner: a unit test with a stubbed adapter asserting the call order
  `start → detect → record questions → generate answers → fill`, and that an optional
  unanswered question does not pause.
- The existing end-to-end demo test passes unchanged. Add a second variant that stores
  **no** per-application answers but has the two standing answers and still ends `APPLIED`.
- Standing answers: lookup order, consent wording match and mismatch, demographic exclusion,
  `applies_to` filtering, expiry, `save_as_standing` upsert, and the three endpoints.
- Run the full suite with `TEST_DATABASE_URL` pointing at your own database name.

## Constraints

- Nothing bypasses CAPTCHA, OTP, 2FA, login or bot detection. Blockers still pause.
- Auto-submit stays off by default and per-source opt-in.
- Follow `docs/DATABASE.md` conventions; one additive migration.
- Do not touch the adapters package beyond the `detected_form` reuse in
  `GenericAtsFormAdapter`; another developer is working there.

## Report

1. Files changed, one line each. 2. Migration id. 3. Final pytest summary and any failures
in full. 4. The demo run's steps JSON showing the corrected autofill and approval counters.
5. Decisions not covered here. 6. Anything unfinished and why.

## Addendum (after Step 2 landed)

Step 2 changed two behaviours that three Step 1 tests in `tests/test_automation.py` still
assume. Fix the tests, not the behaviour:

- `test_browser_backed_source_is_prepared_when_the_browser_is_available` and
  `test_browser_backed_source_is_deferred_without_a_browser` use the `greenhouse_catalogue`
  fixture, which patches `GreenhouseAdapter.search_jobs` but configures no company with a
  Greenhouse board. Board sources are now searched only when a company has a board, so
  nothing is queued. Give one `Company` in the fixture `ats_type="GREENHOUSE"` and an
  `ats_board_token`.
- `test_auto_submit_refuses_an_application_with_a_required_unanswered_question` picks
  `sorted(auto_apply_sources() - DEMO_ATS)[0]`, which is now `ASHBY`. Use a fixed mock
  source such as `"LINKEDIN"`.

Also note from Step 2's live run: every vendor's hosted form (Greenhouse, Lever, Ashby,
SmartRecruiters) shows a CAPTCHA or bot check, so board applications pause with
`REQUIRES_USER / CAPTCHA` before anything is typed. Your runner change must keep that
behaviour: detect, record questions, generate answers, then fill, and if a blocker is
present at any point, pause with the mapped fields in the snapshot and nothing typed.
