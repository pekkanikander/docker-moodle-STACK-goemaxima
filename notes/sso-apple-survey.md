# Survey: Sign in with Apple for Moodle 5.1

Survey date: 2026-09-01. Decision gate for the SSO work: Google was
straightforward, Apple was not, and this records why Apple was deferred and
what would reopen it.

## Target Moodle version

`versions.yml` pins `moodle-5.1.6` (stable501 tarball). Source-tree claims
below verified against `MOODLE_501_STABLE` on GitHub (paths under `public/`
per the 5.x layout); also checked on `MOODLE_502_STABLE` and `main`.

## Core support status: MDL-70109, not landed

Tracker issue [MDL-70109 "Support Sign in with Apple"]
(https://moodle.atlassian.net/browse/MDL-70109), opened 2020-11. Status at
survey date: **Reopened** (To Do), last field update 2026-06-19. No Apple
service class exists on any branch: `public/lib/classes/oauth2/service/`
contains `google`, `microsoft`, `facebook`, `clever`, `linkedin`,
`nextcloud`, `imsobv2p1`, `moodlenet`, `custom` — no `apple` — on 5.1, 5.2
and `main` alike.

History in brief: a community patch (Pramod / eAbyas Info Solutions) has been
iterating since 2022; HQ reviewers (Jake Dallimore, David Woloszyn) reshaped
it repeatedly; it reached integration review for the 5.1 cycle (2025-08:
"get this across the line for 5.1"), was held through the on-sync period,
and was pushed back by the integrator on 2026-01-21 with a request to rework
the `oauth2callback.php` changes onto the Hook API. Auto-reopened
2026-01-28; no substantive activity since. Four "PR only" companion issues
(MDL-80389, MDL-81917, MDL-83482, MDL-86421 — the last from June 2026) show
the patch is still being carried forward. Close, but with a 5-year history
of near-misses; landing version unknowable.

## Why stock 5.1 cannot do it (the survey's central question)

The task brief asked whether a custom issuer can work from the `id_token`
alone in 5.1. **No — verified in source:**

1. **Userinfo endpoint is mandatory.**
   `core\oauth2\client::get_raw_userinfo()`
   (`public/lib/classes/oauth2/client.php` ~line 508) returns `false` when
   the issuer has no `userinfo` endpoint, and `get_userinfo()` only maps
   fields from that response. `auth_oauth2\auth::complete_login()`
   (`public/auth/oauth2/classes/auth.php` ~line 415) then fails hard with
   `loginerror_nouserinfo`. There is no `id_token` claim-extraction path
   anywhere in the 5.1 client. Apple has no userinfo endpoint, so a custom
   issuer pointed at Apple can authenticate but never log anyone in.
2. **Client secret field rejects Apple's secret.** The issuer form
   (`public/admin/tool/oauth2/classes/form/issuer.php` line 107) enforces
   `maxlength 255` on `clientsecret`; Apple's "secret" is an ES256 JWT,
   typically ~300+ characters. (Form-side rule only — bypassable by CLI
   writes to the DB — but it marks the boundary of supported territory.)
3. **`response_mode=form_post`** (required by Apple when the `name`/`email`
   scopes are requested) is *not* a blocker: extra `loginparams` are a
   supported issuer property, and Moodle reads the callback params from
   POST as well as GET. Confirmed working in the tracker discussion.
4. **Name arrives only once, outside the token.** Apple sends the user's
   name as a `user` POST field in the *first* authorisation response only;
   core drops it. Cosmetic here (accounts are pre-created with names),
   fatal for general deployments.

So blocker 1 is fatal on its own; the rest grade from chore to cosmetic.

## Contributed plugin candidates: none

- Moodle plugins directory / marketplace: no Apple authentication plugin
  exists (searched "apple", authentication category, 2026-09-01). The
  MDL-70109 work is a **core patch**, not an installable plugin — the
  repositories (`kaitapupramod/moodleapple`,
  `davewoloszyn/moodle` branch `MDL-70109-main`) are Moodle forks.
- `auth_oidc` (Microsoft): reads claims from the id_token, but is a
  single-IdP plugin, Entra-centric, and handles neither the rotating
  ES256 secret nor the first-response `user` field. Not a route.

## Routes considered

### A. Carry the MDL-70109 patch in our image build — rejected

We build the Moodle image ourselves, so applying the patch is mechanically
possible. But the patch targets `main`, not stable501; it is still changing
shape (Hook API rework outstanding); and we would own a fork of core auth
code for a convenience feature. Against the repo's pinned-and-reproducible
policy for no protective gain.

### B. Direct custom issuer against Apple — impossible

Per the source verification above. No configuration reaches a login.

### C. OIDC broker in front of Apple — workable, not worth it here

An identity broker (Amazon Cognito, Auth0, or self-hosted Keycloak with the
community Apple provider extension) speaks Sign in with Apple upstream and
presents Moodle with a fully standard OIDC issuer: static client secret,
real userinfo endpoint, no form_post quirk. Brokers generate and rotate
Apple's ES256 client secret themselves from the uploaded `.p8` key, which
also dissolves the six-month re-paste chore.

What a broker does **not** remove: the Apple Developer Program fee
(99 USD/year + VAT), the Services ID / key registration, the Hide My Email
mapping problem (below), and it *adds* a third-party auth dependency for a
single-student site — the same reasoning that rejected Bedrock in
`aiprovider-survey.md`. Recorded as the fallback if Apple ever becomes a
hard requirement before core support lands.

## Apple-side obligations (any route)

- **Cost/registration:** Apple Developer Program membership (99 USD/year),
  a Services ID with registered domain + return URL. Return URLs must be
  re-registered at the `oivus.fi` move (already noted in the task brief).
- **Secret rotation:** self-issued ES256 JWT, `exp` at most ~6 months
  (15777000 s). Manual re-paste twice a year unless a broker signs it.
- **Hide My Email vs R2:** if the student picks "Hide My Email", Apple
  issues a relay address unknowable in advance; with
  `authpreventaccountcreation` set, the login then fails closed (correct
  per R2, but a trap: Apple only re-sends the choice after the student
  revokes the app under Settings → Apple ID → Sign in with Apple).
  Mitigations: instruct "Share My Email" at first sign-in, or link the
  issuer to the existing account from a logged-in session (auth_oauth2
  linked logins) before first use.
- **Private email relay:** sending mail *to* a relay address requires
  registering sender domains/addresses (SPF-verified) in the Apple
  developer console. Moot while `divertallemailsto` is set, and moot if
  the real address is shared.

## Decision gate

**No workable route exists at acceptable cost: defer.** Core Moodle 5.1
cannot complete an Apple login (verified in source, not just folklore); no
contributed plugin exists; the core patch is unlanded and still moving; a
broker works but buys a cloud dependency plus 99 USD/year to duplicate what
Google sign-in already provides for this student.

**Recommendation:** go Google-only, per the gate's fallback.
Revisit triggers, checked at each Moodle version bump:

1. MDL-70109 gains a fix version (then Apple arrives as a core issuer
   template — cost and Hide My Email caveats above still apply).
2. Apple sign-in becomes a hard requirement (e.g. M7 families without
   Google accounts) — then route C (broker), Cognito or Keycloak first.
