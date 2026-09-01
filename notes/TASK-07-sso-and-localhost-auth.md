# Task 7: SSO (Google, Apple) and passwordless localhost

## Context and intent

Two login friction points, one requirement behind both: the right amount of
authentication for each environment, provably not less.

- **Staging/preproduction** (`oivus.pnr.iki.fi`): the student should log in
  with an existing identity — at least Sign in with Google and Sign in with
  Apple — instead of a site-local password.
- **Localhost** (the `tools/start.sh` instance): a single-user development
  machine should not demand passwords at all, *provided* the instance
  demonstrably listens only on the loopback interfaces (127.0.0.1 and ::1).

## Starting points

File-level facts verified 2026-09-01; container-level claims to re-verify
against the running 5.1 image at implementation time.

1. Compose publishes Moodle on `127.0.0.1:8000` only
   (`docker-compose.yml`); there is **no ::1 binding**, so IPv6 localhost
   does not reach Moodle at all today. Adding `[::1]` is a usability fix;
   the security property (no wildcard listener) already holds and must be
   preserved. Same applies to the Mailpit port.
2. Accounts are created manually (DEPLOY.md §7); `registerauth` is empty and
   the guest login button hidden. SSO must not loosen either.
3. Secrets policy: service credentials (Anthropic API key, SMTP password)
   live in the Moodle database via the admin UI only — never in the repo or
   `.env`. OAuth client secrets follow the same policy.
4. Moodle core `auth_oauth2` ships preconfigured issuer templates including
   Google (confirm the template list in 5.1). Apple is **not** a core
   template.
5. The idempotent-init pattern for site config is established:
   `lang-init.sh`, `mail-init.sh`, run both locally and by
   `server-update.sh`.

## Known obstacles: Apple

Sign in with Apple is materially harder than Google; a survey step in the
style of `notes/aiprovider-survey.md` is required before committing:

1. **Cost and registration.** Apple Developer Program membership
   (99 USD/year), a Services ID with registered return URLs, and domain
   association for the email relay service.
2. **Rotating client secret.** Apple's "client secret" is a self-issued
   ES256 JWT valid at most 6 months. Moodle assumes a static secret, so the
   secret must be regenerated and re-pasted twice a year — a recurring
   manual chore that must be documented and calendared, or automated by a
   plugin that signs the JWT itself.
3. **No userinfo endpoint.** Claims arrive in the `id_token` (the name only
   in the *first* authorisation response). Moodle core's issuer model maps
   user fields from a userinfo endpoint; whether a custom issuer can work
   from the id_token alone in 5.1, or whether a contributed plugin is
   needed, is the survey's central question.
4. **Hide My Email.** The relay address Apple may issue is the address that
   must be on the pre-created account for mapping (R2), or the student must
   share the real address at first sign-in.

Decision gate: adopt a workable route, or record the deferral and go
Google-only for now. Google alone already removes the site-local password.

**Gate outcome (2026-09-01): deferred.** Survey in
`notes/sso-apple-survey.md`: Moodle 5.1 core cannot complete an Apple login
(no id_token claim path — verified in source), no contributed plugin
exists, the MDL-70109 core patch is unlanded, and an OIDC broker is not
worth the dependency here. Google-only; revisit triggers in the survey.

## Requirements

**R1. No secrets in the repo or `.env`.** OAuth client IDs/secrets are
entered in the admin UI only; the manual steps are documented in DEPLOY.md
(same treatment as the SMTP credentials).

**R2. SSO must not open account creation.** `authpreventaccountcreation`
is set; an IdP login succeeds only when it maps (by email) to a pre-created
account. Self-registration stays off; the guest button stays hidden. The
posture checks in DEPLOY.md §7 grow assertions for these.

**R3. Passwordless login must be impossible off-loopback — fail closed in
both directions.** The enabling path refuses unless `$CFG->wwwroot` is a
loopback/localhost URL, and the server-side convergence
(`server-update.sh` posture check) asserts the mechanism is disabled.
A misconfigured staging deploy must fail the deploy, not fall back to open.

**R4. Loopback-only listening, v4 and v6.** Published ports bind
`127.0.0.1` and `[::1]` explicitly; a smoke check asserts no wildcard
listener exists for the published ports (e.g. via `ss` on the host or
inspecting `docker port` output).

**R5. Convergence, not hand-applied state.** Deterministic parts land in an
idempotent `auth-init.sh` (pattern of `lang-init.sh`/`mail-init.sh`), run
by `tools/start.sh` locally and `server-update.sh` on the server. Manual
admin-UI parts are documented as numbered DEPLOY.md steps.

**R6. Role parity.** SSO changes authentication only: the student account
keeps the same role and enrolments whichever way it logs in.

## Sketch of a satisfying design

- **Google (staging):** core `auth_oauth2` issuer from the Google template.
  Google Cloud OAuth client with redirect URI
  `https://oivus.pnr.iki.fi/admin/oauth2callback.php` (confirm path);
  client ID/secret pasted in the admin UI; login page then shows the IdP
  button. DEPLOY.md gains the setup steps, including linking the student's
  existing account by email.
- **Apple (staging):** surveyed (`notes/sso-apple-survey.md`) → deferred,
  per the gate above.
- **Localhost:** the core-shipped `auth_none` plugin (any username, no
  password) is the candidate mechanism, acceptable only under R3+R4;
  `auth-init.sh` enables it when the wwwroot is loopback and
  disables/asserts-disabled otherwise. Alternatives to weigh in
  implementation: keeping password auth with browser autofill (zero code,
  rejected by the task premise) or a token-URL auto-login plugin (more
  moving parts than `auth_none` for no gain on a loopback-only site).
- **Compose:** add `[::1]` published-port entries for `moodle` and
  `mailpit`; verify Docker's IPv6 loopback publishing behaves on both
  macOS and the Ubuntu server (it must not widen the listener).

## Implementation status (2026-09-01)

Implemented in `init/scripts/auth-init.sh` (run by `tools/start.sh`,
`tools/clean-rebuild.sh` and `server-update.sh`), with the posture assertions
in `smoke-tests.sh` and the `[::1]` port bindings in `docker-compose.yml`
(verified to publish loopback-only on macOS). Google issuer setup is
DEPLOY.md §8; the admin-UI steps there remain manual by design (R1).

One deviation from the sketch: `auth_none` alone is *not* passwordless for
existing accounts — core validates the stored hash and is only
password-free for accounts it would create, a path `authpreventaccountcreation`
closes (verified in `public/auth/none/auth.php` on `MOODLE_501_STABLE`). So
on a loopback wwwroot, `auth-init.sh` both switches local accounts to
`auth=none` and blanks their passwords (login = username + empty password
field; the core login form submits empty passwords). R3 still holds twice
over off-loopback: a disabled `auth_none` refuses those accounts outright in
`authenticate_user_login()`, and `auth-init.sh`/`smoke-tests.sh` fail the
deploy if any active account accepts an empty password.

## Sequencing

After the M6 hardening leftovers (this is convenience; those are
protection), and before M7 "access for other families" — R2 is a
precondition for that anyway. Google first; Apple behind its survey.

## Out of scope

- MFA, additional IdPs, self-registration.
- Production domain (`oivus.fi`) — redirect URIs will need re-registration
  at that move; noted, not handled here.
- Removing `divertallemailsto` (M7).
