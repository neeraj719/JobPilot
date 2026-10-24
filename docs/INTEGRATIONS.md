# Integrations

Third-party accounts JobPilot connects to, what each one yields and how to set it up. Every
integration uses the provider's **official** API with the user's consent. JobPilot never
scrapes a site, never automates a browser against a provider to read a profile, and never
asks for a provider password.

* Gmail (read-only, recruiter replies) — see `docs/CONTRACTS.md` §13 and `.env.example`.
* LinkedIn (profile auto-fill for Create Resume) — this page.

## LinkedIn

"Connect LinkedIn" in **Create Resume** (`/resume/new?source=linkedin`) and in **Settings ›
Connected accounts** fills the master profile from LinkedIn, lets the user review every change
before it is written, creates a resume from it, and keeps it in sync (manual *Sync now*, plus an
opt-in scheduled check that notifies and never overwrites).

### What each path yields

| Path | How | Yields |
|---|---|---|
| **Sign In with LinkedIn using OpenID Connect** (generally available) | OAuth 2.0 authorization code + PKCE, scopes `openid profile email`, `GET /v2/userinfo` | `sub`, name, given / family name, profile photo URL, email (+ verified flag), locale. **No positions, education or skills.** |
| **Member Data Portability (3rd party)** (needs LinkedIn approval; EU/EEA members only) | extra scope `r_dma_portability_3rd_party`, `GET /rest/memberSnapshotData?q=criteria&domain=…` | Domains `PROFILE`, `POSITIONS`, `EDUCATION`, `SKILLS`, `CERTIFICATIONS`, `LANGUAGES` — the same fields as the export CSVs, mapped by the same normaliser (`resumes.importers.parse_linkedin_rows`). |
| **LinkedIn export ZIP** ("Get a copy of your data") | uploaded by the user, read in memory | Profile, positions, education, skills, certifications, projects, languages, honors. While connected, the normalised details are kept on the connection and `export_imported_at` drives the "export is N days old" hint. |

The UI says exactly this: connecting gives the basics instantly; the full history needs the
export (or the portability API where LinkedIn grants it). When the portability scope is
requested but not granted, the card explains that only the basics were filled and offers the
export upload.

### Create the LinkedIn app (owner, once)

1. Sign in at <https://www.linkedin.com/developers/apps> and **Create app** (a LinkedIn Page
   for the company is required; verify it when asked).
2. **Products** tab → request **Sign In with LinkedIn using OpenID Connect** (approved
   instantly). Optional: request **Member Data Portability API (3rd party)** — LinkedIn
   reviews it, and it only ever returns data for EU/EEA members.
3. **Auth** tab → *Authorized redirect URLs for your app*: add the callback exactly, e.g.
   `https://<your-api-host>/api/v1/integrations/linkedin/callback` (dev:
   `http://localhost:8000/api/v1/integrations/linkedin/callback`).
4. Copy the **Client ID** and **Primary Client Secret** into the backend environment.

### Environment

| Variable | Default | Meaning |
|---|---|---|
| `LINKEDIN_CLIENT_ID` / `LINKEDIN_CLIENT_SECRET` | empty | The app credentials. Empty = the card says "not configured" and offers the export. The secret is never logged or returned. |
| `LINKEDIN_REDIRECT_URI` | `http://localhost:8000/api/v1/integrations/linkedin/callback` | Must match the app's authorized redirect URL. |
| `LINKEDIN_AUTH_BASE` | `https://www.linkedin.com/oauth/v2` | `authorization`, `accessToken`, `revoke` live under it. The expected ID-token issuer is derived from it (`…/oauth`). |
| `LINKEDIN_API_BASE` | `https://api.linkedin.com` | `v2/userinfo`, `rest/memberSnapshotData`. |
| `LINKEDIN_DMA_ENABLED` | `false` | Request `r_dma_portability_3rd_party`. Turn on only after LinkedIn approved the product. |
| `LINKEDIN_PKCE_ENABLED` | `false` | Send an S256 challenge / the verifier. **Leave off**: on a standard web app the real token endpoint answered `401 invalid_request: Unable to retrieve access token: authorization code not found` for every code requested with a `code_challenge`, and succeeded once PKCE was off (owner's app, 2026-10-24). LinkedIn documents PKCE only for its separately approved native-client flow. |
| `LINKEDIN_AUTO_SYNC_HOURS` | `24` | The scheduled check re-reads a connection once its last sync is this old (the job ticks hourly). |
| `LINKEDIN_EXPORT_STALE_DAYS` | `90` | An export older than this is flagged on the card. |

`FRONTEND_URL` must point at the SPA: the callback redirects to
`FRONTEND_URL/resume/new?source=linkedin&connected=1` (or `&error=<code>`).

### Security

* `state` = JWT signed with `SECRET_KEY`: names the user, expires after 10 minutes, carries a
  random `jti` stored on the connection row and cleared when spent (single use); the state is
  also mirrored into an `HttpOnly` cookie scoped to `/api/v1/integrations/linkedin` that must
  come back with the callback (the browser that finishes the flow started it).
* PKCE: off (see the table). The flow is a confidential-client code flow: the client secret
  authenticates the exchange, and the signed single-use `state` + cookie binds the response to
  the browser and the user. A new connect start overwrites the previous flow's state (one live
  row per user), so only the newest consent tab can finish; an older tab gets `invalid_state`.
  The callback locks the row (`SELECT … FOR UPDATE`) before spending the state, so one code is
  redeemed at most once even if the browser repeats the GET.
* ID token: signature verified (RS256) against LinkedIn's JWKS
  (`https://www.linkedin.com/oauth/openid/jwks`, cached 1 h, refetched once on an unknown `kid`;
  `HS*` / `none` headers are refused), `aud` = our client id, `exp` in the future, `iss` =
  `https://www.linkedin.com/oauth`. LinkedIn's ID token carries **no `nonce`** (its discovery
  document lists `iss, aud, iat, exp, sub, name, given_name, family_name, picture, email,
  email_verified, locale`); a missing nonce is accepted because the state already matched, a
  present but different one is refused. If the JWKS cannot be fetched, the ID token's claims are
  ignored and the identity comes only from `/v2/userinfo`, which is always the source of
  `sub` / name / email anyway.
* Token-endpoint errors log LinkedIn's `error` / `error_description` (values we sent are
  redacted) and are audited as `integration.linkedin.connect_failed`; "authorization code not
  found" surfaces as `?error=linkedin_code_rejected` ("start again from Create Resume; do not
  reuse an old tab").
* Access / refresh tokens are Fernet-encrypted (`encrypt_str`) in
  `master.linkedin_connections`; `GET /integrations/linkedin` returns identity, scopes,
  timestamps and counts only. Audit rows carry field names and counts, never values.
* LinkedIn member tokens last 60 days. With a refresh token (only some partner apps get one)
  the backend refreshes; otherwise the connection becomes `expired` and the UI asks to reconnect.
  A `401` from LinkedIn marks it `revoked` and wipes the tokens.
* Disconnect revokes at LinkedIn (best effort), wipes tokens and the stored snapshot, and
  soft-deletes the row. The profile and any resumes stay as they are.

### The no-scraping rule

LinkedIn's User Agreement forbids scraping and automated access to profiles, and so does this
project. Nothing in JobPilot reads linkedin.com pages, drives a browser against LinkedIn, or
stores a LinkedIn password — and there are no hooks for it. The only LinkedIn data sources are
the two official APIs above and the export file the user downloads and uploads themselves.
