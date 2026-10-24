# linkedin-connect — progress

Brief: `notes/linkedin-connect-prompt.md`. Migration `d2e4f6a8b0c1` (down `f6b8d0c2e4a7`), two heads on purpose
(other head = ai-model-choice `e6f8a0b2c4d7`). Never `alembic upgrade head`.

## Checklist
- ✅ config + model + migration (applied to `jobpilot`; `alembic current` = e6f8a0b2c4d7 + d2e4f6a8b0c1)
- ✅ OAuth (signed user-bound state JWT + jti single use + HttpOnly cookie, PKCE S256, nonce/aud/exp/iss) — `integrations/linkedin_oauth.py`
- ✅ endpoints — `integrations/linkedin_router.py` (+ `resumes/router_linkedin.py`), one import + one include in `app/main.py`
- ✅ sync / diff / apply / export / disconnect / resume — `integrations/linkedin_service.py`
- ✅ scheduler job `sync_linkedin` (hourly tick; due after LINKEDIN_AUTO_SYNC_HOURS; notify only)
- ✅ backend tests `tests/test_linkedin.py` (40 passed after the live fixes)
- ✅ frontend: `features/linkedin/**` (types, api, copy, LinkedInParts, LinkedInReviewDialog, LinkedInConnectPanel)
- ✅ Settings card `LinkedInAccountCard`
- ✅ docs: `docs/INTEGRATIONS.md` (new), CONTRACTS §20, DATABASE (39 tables, row, encryption), `.env.example`
- ✅ verification: tsc 0, build green (main 350.15 kB), contrast failures 0, Playwright phases A + B green (34 screenshots)
- ✅ DONE: full suite junit tests=1405 failures=0 errors=0 skipped=3 (exit 0); Playwright phase A re-run green against an RS256, nonce-less, PKCE-less fake; throwaway user soft-deleted; 8103/8104/5233 stopped

## Live fixes (owner's real LinkedIn app, 2026-10-24)
- **live fix: PKCE** — real token endpoint answered `401 invalid_request: authorization code not found` for codes issued with a `code_challenge`; with PKCE off the exchange succeeds. `LINKEDIN_PKCE_ENABLED` default → False; verifier not stored/sent unless enabled.
- **live fix: nonce** — LinkedIn's ID token carries no `nonce` (its discovery doc `claims_supported` = iss, aud, iat, exp, sub, name, given_name, family_name, picture, email, email_verified, locale). `verify_id_token` now accepts a missing nonce (state already matched; INFO log), still rejects a wrong one, keeps aud/exp/iss, and verifies the RS256 signature against `https://www.linkedin.com/oauth/openid/jwks` (1 h cache, one refetch on unknown kid); JWKS unreachable → claims ignored, identity from `/v2/userinfo` only.
- Diagnosability: token-endpoint errors log LinkedIn's `error` / `error_description` (sent values redacted); code-not-found → `linkedin_code_rejected` ("start again from Create Resume; do not reuse an old tab"); `connect_failed` audit row + `last_error`.
- Single redemption: callback locks the row (`SELECT … FOR UPDATE`) before comparing the jti.

## Shared-file edits
- `frontend/src/pages/resume/CreateResume.tsx`: import panel; `Mode` + `'connect'`; MODES entry before `linkedin`; linkedin description; `source=linkedin` → mode connect; grid `lg:grid-cols-3`; render branch; export alert sentence.
- `frontend/src/lib/queryClient.ts`: `qk.linkedin`.
- `frontend/src/pages/Settings.tsx`: import + `<LinkedInAccountCard />` above `ConnectedAccountsCard` in `accounts`.
- `frontend/src/types/api.ts`: not touched (types in `features/linkedin/types.ts`).
- backend shared: `app/main.py` (include), `app/models/__init__.py` (import), `app/core/config.py` (LINKEDIN_*), `app/worker/scheduler.py` (job), `importers.py` (parse_linkedin_rows split + record_export hook), tests: test_migrations (`heads`, 39), test_db_conventions (39), test_automation (job set).

## Decisions
- Status values lowercase strings per brief + `pending` (flow started, not completed).
- Snapshot stores normalised data (identity + ParsedResume dict from DMA / export), never raw export files.
- Connect does not require recent auth (same as Gmail); consent happens at LinkedIn.
- Extra settings: LINKEDIN_PKCE_ENABLED (default false — see live fix), LINKEDIN_EXPORT_STALE_DAYS (90).
- Notification type SYSTEM (no enum change); link `/resume/new?source=linkedin&review=1`.
- `components/ui/switch.tsx` dark checked fill is lost (tailwind-merge drops bg-primary next to bg-gradient-brand); worked around locally with `SWITCH_DARK_FIX`; reported, not fixed (theme-owned file).

