# Go-live runbook: Hetzner VM for oivus.pnr.iki.fi

Concrete steps for provisioning, DNS, TLS and first deploy. Run the macOS
steps from the repo root. Cloud-init automates everything up to (but
excluding) the `.env` secrets and the init scripts.

## 1. One-time macOS preparation

```sh
brew install hcloud
hcloud context create moodle-stack     # prompts for the API token, stores it in ~/.config/hcloud
```

Get the API token from the Hetzner Cloud Console (https://console.hetzner.cloud):
select (or create) the project, then *Security → API tokens → Generate API token*,
with **Read & Write** permission. It is shown only once.

Generate the admin SSH key and a `~/.ssh/config` entry (`Host moodle-hetzner`):

```sh
HOSTNAME=oivus.pnr.iki.fi ./infra/hetzner/scripts/ssh-keygen.sh
```

## 2. Provision the VM

```sh
export ADMIN_SSH_PUBKEY="$(cat ~/.ssh/to_moodle_hetzner_admin_ed25519.pub)"
./infra/hetzner/scripts/hcloud-create.sh
```

This creates firewall `moodle` (inbound TCP 80/443/33101 only), server `moodle`
(CX23, Ubuntu 24.04, cloud-init user-data) and volume `moodle` (10 GB, automount),
then prints the IPv4/IPv6 addresses.

Notes:
- Port 22 is blocked by the Hetzner firewall; SSH becomes reachable on **33101
  only after cloud-init finishes** (several minutes). If locked out, use the
  Console's web terminal (">_" icon on the server page).
- Cloud-init creates user `admin` (key-only, passwordless sudo; auto-login on
  the Hetzner web console), disables root SSH login and password auth, installs
  Docker + compose v2 + Caddy + yq, bind-mounts the volume to
  `/srv/moodle-persistent`, clones this repo to `/opt/moodle-stack`, and runs
  `server-bootstrap.sh` (Caddy vhost, the sshd hardening drop-in from
  `infra/hetzner/sshd/`, the systemd timers, image build/pull). This takes a while; `cloud-init status --wait` on
  the VM tells when it is done.
- The create script also drops stale `~/.ssh/known_hosts` entries for the
  server's DNS name and IPs (a recreated server has new host keys).

## 3. DNS at easyDNS

In the `pnr.iki.fi` zone, add (values printed by the create script):
- `A` record, host `oivus` → VM IPv4
- `AAAA` record, host `oivus` → VM IPv6
- TTL 300 s for now

Verify: `dig A oivus.pnr.iki.fi +short` and `dig AAAA oivus.pnr.iki.fi +short`.
DNS must resolve before Caddy can obtain a certificate.

## 4. First login and checks

```sh
ssh moodle-hetzner              # alias from step 1; admin@oivus.pnr.iki.fi port 33101
cloud-init status --wait        # must end with "status: done"
sudo cloud-init status --long   # on errors: see /var/log/cloud-init-output.log
df -h /srv/moodle-persistent    # must show the ~10 GB volume, not the root disk
ls -l /srv/moodle-persistent    # moodledata/ mariadb/ backups/
```

If `/srv/moodle-persistent` is missing (volume attach raced cloud-init), run
`sudo /usr/local/sbin/bind-hetzner-volume` and re-check.

## 5. Verify Caddy

Cloud-init installed the vhost; Caddy fetches the certificate on first
request. Verify from macOS:

```sh
curl -I http://oivus.pnr.iki.fi     # 308 redirect to https
curl -I https://oivus.pnr.iki.fi   # 502 until Moodle is up; no certificate warning
```

## 6. Deploy the stack

Cloud-init cloned the repo to `/opt/moodle-stack`, generated `.env.versions`,
seeded `.env` from `.env.example` (site URL preset) and built the images.

On the VM (`ssh moodle-hetzner`), edit `/opt/moodle-stack/.env` (nano or vi):
- `MOODLE_ADMIN_EMAIL`, `MOODLE_ADMIN_PASSWORD` (real values; the password is
  the actual admin login)
- `MOODLE_SITE_FULLNAME`, `MOODLE_SITE_SHORTNAME`, `MOODLE_NOREPLY_EMAIL`
- Outgoing mail (see "Outgoing mail via smtp.iki.fi" below): the
  `.env.example` defaults send to the bundled Mailpit capture, which real
  recipients never see; on the server set `MOODLE_SMTPHOSTS` to a real
  relay, `MOODLE_SMTPSECURE` accordingly, and `COMPOSE_PROFILES=` (empty,
  so Mailpit does not run)
- `MOODLE_LANGPACKS` (e.g. `fi`) and `MOODLE_LANG` (fallback, `en`); `.env.example`
  installs no packs, so this must be set here to get anything but English
- `MOODLE_ENV_LABEL` and `MOODLE_ENV_COLOUR` (page tint and corner badge
  marking the environment; `STAGING` and `#b26a00` on this server, empty
  label on production)
- optionally `MOODLE_GOOGLE_OAUTH_CLIENT_ID` and
  `MOODLE_GOOGLE_OAUTH_CLIENT_SECRET` for Google sign-in (§8; can be added
  later, then applied with `./init/scripts/auth-init.sh`)

Then:

```sh
cd /opt/moodle-stack
docker compose --env-file .env.versions --env-file .env up -d
./init/scripts/moodle-init.sh      # also sets $CFG->sslproxy for the https wwwroot
./init/scripts/lang-init.sh        # language packs + default language
./init/scripts/mail-init.sh        # noreply address + SMTP target from .env
./init/scripts/stack-init.sh
./init/scripts/auth-init.sh        # SSO posture: no account creation, OAuth 2 on
./init/scripts/appearance-init.sh  # environment tint and badge from .env
MOODLE_HTTP_PORT=8000 ./init/scripts/smoke-tests.sh
```

Notes:
- `admin` is in the `docker` group (no sudo needed for docker), but the group
  membership takes effect only on a fresh login after cloud-init.
- When recreating the server on the existing volume (data present), do NOT
  rerun `moodle-init.sh`; just `up -d`. The container entrypoint restores
  `config.php` from `moodledata`, so a recreated container comes back installed.
- `lang-init.sh`, unlike `moodle-init.sh`, is safe to rerun at any time. That is
  how an already-installed site gets a language pack: add the code to
  `MOODLE_LANGPACKS` and run it again.
- `mail-init.sh` is likewise safe to rerun: it applies the mail settings in
  `.env` (noreply address, SMTP target, transport security) to an installed
  site.

### Outgoing mail via smtp.iki.fi

The server relays through IKI's authenticated SMTP submission service
(https://ikiwiki.iki.fi/faq/smtp): DKIM/ARC signing and deliverability are
IKI's problem, and no MTA runs on the VM. Constraints: the sender must be an
@iki.fi address owned by the authenticating member (enforced; whether
`user@member.iki.fi` subdomain forms are accepted is untested), and rate
limits are 15 messages/minute — far above this site's volume.

1. In the IKI member registry, generate the service-specific SMTP password
   (*Change Password → Auth SMTP-palvelusalasana*). This is separate from the
   main member password. Changes activate within an hour.

2. In `/opt/moodle-stack/.env`:

   ```
   MOODLE_NOREPLY_EMAIL=<member>@iki.fi   # must be IKI-accepted as yours
   MOODLE_SMTPHOSTS=smtp.iki.fi:587
   MOODLE_SMTPSECURE=tls
   COMPOSE_PROFILES=
   ```

   Then apply: `./init/scripts/mail-init.sh` (and, if Mailpit was running
   before the profile change,
   `docker compose --env-file .env.versions --env-file .env up -d
   --remove-orphans` removes its now-orphaned container).

3. In the Moodle admin UI (*Site administration → Server → Email → Outgoing
   mail configuration*, `/admin/settings.php?section=outgoingmailconfig`):
   set *SMTP username* to the IKI member name and *SMTP password* to the
   service-specific password from step 1. These live in the Moodle database
   only — never in the repo or `.env` (same policy as the Anthropic API key).

4. Verify with *Site administration → Server → Email → Test outgoing mail
   configuration* (`/admin/testoutgoingmailconf.php`), sending to a real
   mailbox. IKI rejections ("Sender address rejected: not owned by user")
   indicate a noreply/username mismatch with step 2.

Replies to the noreply address land in the member's normal IKI-forwarded
mailbox; for this site that is a feature, not a bug.

## 7. Site posture checks (go-live policy)

`smoke-tests.sh` asserts all of these on every run (and additionally that
`auth_none` is disabled and no active account accepts an empty password on a
non-loopback wwwroot, and that no published port has a wildcard listener).
To verify by hand (`moodle-init.sh` hides the guest login button;
self-registration is off by Moodle default, not set explicitly;
`auth-init.sh` prevents account creation at login):

```sh
docker compose --env-file .env.versions --env-file .env exec -T moodle \
  php /var/www/html/admin/cli/cfg.php --name=registerauth        # must be empty (no self-registration)
docker compose --env-file .env.versions --env-file .env exec -T moodle \
  php /var/www/html/admin/cli/cfg.php --name=guestloginbutton    # 0 = hidden
docker compose --env-file .env.versions --env-file .env exec -T moodle \
  php /var/www/html/admin/cli/cfg.php --name=authpreventaccountcreation  # 1 = logins never create accounts
```

`lang-init.sh` sets these:

```sh
docker compose --env-file .env.versions --env-file .env exec -T moodle \
  php /var/www/html/admin/cli/cfg.php --name=lang                # fallback language
docker compose --env-file .env.versions --env-file .env exec -T moodle \
  php /var/www/html/admin/cli/cfg.php --name=autolang            # 1 = browser language wins
```

Accounts are created manually in the admin UI (*Site administration → Users*).

## 8. Enable Google sign-in (SSO)

`auth-init.sh` enables the OAuth 2 auth plugin and sets
`authpreventaccountcreation`, so a Google login succeeds only when its email
matches a pre-created account; anything else is refused. The OAuth client
ID/secret go into `/opt/moodle-stack/.env` (never in the repo; the Moodle
admin UI is the manual fallback).

1. In the [Google Cloud console](https://console.cloud.google.com/), create
   (or reuse) a project, configure the OAuth consent screen, and create an
   OAuth client ID of type *Web application* with authorised redirect URI
   `https://oivus.pnr.iki.fi/admin/oauth2callback.php`. (Re-register at the
   `oivus.fi` move.)

2. In `/opt/moodle-stack/.env`:

   ```
   MOODLE_GOOGLE_OAUTH_CLIENT_ID=<client id>
   MOODLE_GOOGLE_OAUTH_CLIENT_SECRET=<client secret>
   ```

   Then apply: `./init/scripts/auth-init.sh`. It creates or updates the
   Google issuer (*Site administration → Server → OAuth 2 services*) with
   email verification off: with `divertallemailsto` set, a link-confirmation
   mail would never reach the student, and it is redundant here — Google only
   asserts addresses it has verified, and unknown addresses are refused by
   `authpreventaccountcreation`. `smoke-tests.sh` asserts the issuer matches
   `.env` whenever the client ID is set.

3. Create the student's account (*Site administration → Users → Add a new
   user*) with *Choose an authentication method* set to **OAuth 2** and the
   email exactly their Google address. No password is needed — the form does
   not require one for OAuth 2 accounts — and password login is refused for
   the account outright; it can sign in only via Google. The first Google
   login auto-links by email; the account keeps its role and enrolments.
   (An existing password account with the matching email auto-links too, but
   keeps its password; switch its authentication method to *OAuth 2* on the
   user's edit page to retire the password.)

4. Test: log out; the login page shows a Google button; sign in as the
   student. Also confirm a password login attempt for that account fails.

A local instance mirrors this by setting the same two variables in its
`.env` from an OAuth client with redirect URI
`http://localhost:8000/admin/oauth2callback.php` (Google accepts plain-http
localhost) and rerunning `./init/scripts/auth-init.sh`.

## 9. Enable the AI provider (Anthropic Claude)

In the admin UI (*Site administration → AI → AI providers*), add a
"Claude API Provider" instance, paste the Anthropic API key, set an explicit
`max_tokens` per action, and enable the provider. Use a dedicated production
key (own Anthropic Console workspace, spend limit set), not the key used in
local testing environments.

The key is stored in the Moodle database only — never in the repo or `.env`.
It survives updates and container rebuilds, and it is contained in the
database dumps (see `infra/BACKUP.md`); treat those accordingly.

Done on oivus.pnr.iki.fi 2026-08-26.

## 10. Verify end-to-end

- https://oivus.pnr.iki.fi loads the login page with a valid certificate.
- Log in as admin; *Site administration → Plugins → Question types → STACK*
  health check passes (Maxima connection).

## 11. Monitoring: dead-man health check

`moodle-health.timer` (installed and enabled by `server-bootstrap.sh`) runs
`infra/hetzner/scripts/server-health.sh` daily at 07:00 UTC. The script
checks disk usage on `/` and `/srv/moodle-persistent` (< 85%), that the
newest DB dump is younger than 26 h (the backup runs at 03:30), and that
`https://oivus.pnr.iki.fi/login/index.php` answers through Caddy (which also
catches an expiring certificate). Only when everything passes does it ping a
healthchecks.io URL; a missed ping — a failed check, a dead VM, a broken
timer — triggers healthchecks.io's alert email. There is deliberately no
mail path on the VM itself.

One-time setup:

1. Sign up at https://healthchecks.io (free tier) and create a check, e.g.
   "oivus health": *Simple* schedule, period **1 day**, grace **6 h** (absorbs
   timer jitter and `Persistent=true` catch-up runs). Ensure the email
   integration is on.

2. On the VM, add the check's ping URL to `/opt/moodle-stack/.env` (the file
   is already chmod 600; the URL stays out of the repo — anyone holding it
   can fake "healthy" pings):

   ```
   HEALTHCHECKS_PING_URL=https://hc-ping.com/<uuid>
   ```

   Until it is set, the timer runs but the unit fails visibly — intended.

3. Verify the first ping: `sudo systemctl start moodle-health.service`, then
   confirm the check shows a fresh ping in the healthchecks.io UI.

4. Verify the failure path once:

   ```sh
   sudo DISK_LIMIT_PCT=0 /opt/moodle-stack/infra/hetzner/scripts/server-health.sh
   ```

   must exit non-zero without pinging; then use healthchecks.io's *Send test
   notification* to confirm email delivery end to end.

Hardening spot-checks (after any deploy that touches these):

```sh
curl -sI https://oivus.pnr.iki.fi | grep -i strict-transport-security  # max-age=15552000
ssh moodle-hetzner sudo sshd -T | grep -iE 'maxauthtries|logingracetime'  # 3 / 20
```

## Updating later

An installed server is updated by checking out the new commit and running
`infra/hetzner/scripts/server-update.sh`. Both the automated and the manual
update path (below) use that same script; it performs a database backup,
re-runs `server-bootstrap.sh` (as root: Caddyfile, sshd drop-in, backup and
health units, `.env.versions`, image build), then `up -d`, `upgrade.php`, the idempotent
`lang-init.sh`, `mail-init.sh`, `stack-init.sh`, `auth-init.sh` and
`appearance-init.sh` (the same convergence `tools/start.sh` runs locally), the
smoke tests, and an external check of the public site URL. It fails fast and
leaves state in place for manual investigation.

Do NOT run `moodle-init.sh` on an installed site. It deletes `config.php` from
both the container and `moodledata` before running the installer, so it destroys
the durable copy the entrypoint restores from. There is no need for it here: a
rebuilt container picks `config.php` up again on start, and `upgrade.php` does
the rest. Likewise never `docker compose down -v`: it destroys the `secrets`
volume holding the generated DB credentials. `server-update.sh` contains
neither.

### Automated update (GitHub Actions)

The `Deploy staging` workflow deploys a CI-validated commit over SSH:

```sh
gh workflow run deploy-staging.yml -f ref=main
```

(or *Actions → Deploy to staging environment → Run workflow*). It resolves
the ref to a
commit SHA, refuses to deploy unless that exact SHA has a successful `CI`
run, then SSHes in with a restricted deploy key. On the server the key is
forced to run `infra/hetzner/scripts/deploy-cmd.sh`, which accepts only a full
SHA of a commit already on origin, checks it out, and runs
`server-update.sh` from the new checkout. Finally the workflow curls
`https://oivus.pnr.iki.fi/login/index.php` from outside, covering Caddy and
TLS.

Rollback: re-run the workflow with the previous SHA (each deploy log prints
it as `previous:`); restore the database per `infra/BACKUP.md` if
`upgrade.php` migrated the schema. Commits from before the push-to-main CI
trigger have no CI run and are blocked — run CI on them first
(`gh workflow run ci.yml --ref <ref>`) or update manually.

One-time setup:

1. Generate a dedicated deploy key (do not reuse the admin key):

   ```sh
   ssh-keygen -t ed25519 -a 64 -f ~/.ssh/to_moodle_hetzner_deploy_ed25519 \
     -C moodle-hetzner-deploy-gha -N ""
   ```

2. Register it on the server — append to `/home/admin/.ssh/authorized_keys`,
   as one line:

   ```
   restrict,command="/opt/moodle-stack/infra/hetzner/scripts/deploy-cmd.sh" ssh-ed25519 <pubkey> moodle-hetzner-deploy-gha
   ```

3. Create the `staging` GitHub environment and its secrets (the known_hosts
   line comes from your own `~/.ssh/known_hosts`, i.e. the host key you
   already trust):

   ```sh
   gh api -X PUT repos/pekkanikander/docker-moodle-STACK-goemaxima/environments/staging
   gh secret set DEPLOY_SSH_KEY --env staging < ~/.ssh/to_moodle_hetzner_deploy_ed25519
   gh secret set DEPLOY_PORT --env staging --body 33101
   gh variable set DEPLOY_KNOWN_HOSTS --env staging \
     --body "$(ssh-keygen -F '[oivus.pnr.iki.fi]:33101' | grep -v '^#')"
   ```

### Manual update

As an alternative to the Github Actions based automated update,
you can update the server manually, with the following commands:

```sh
ssh moodle-hetzner
cd /opt/moodle-stack
git fetch --tags origin
git checkout --detach <tag-or-sha>   # or: git checkout --detach origin/main
./infra/hetzner/scripts/server-update.sh
```

The intention here is that the server repo always sits
detached at the deployed commit, both when updating via Github Actions
and when updating manually. In particular, do not `git checkout main`:
that would check out the *local* `main`, which `git fetch` does not move,
and silently deploy an old commit.
