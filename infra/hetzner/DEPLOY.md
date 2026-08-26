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
  the Hetzner web console), hardens sshd, installs Docker + compose v2 + Caddy
  + yq, bind-mounts the volume to `/srv/moodle-persistent`, clones this repo to
  `/opt/moodle-stack`, installs the Caddy vhost, and builds/pulls the images
  (`server-bootstrap.sh`). This takes a while; `cloud-init status --wait` on
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
- `MOODLE_LANGPACKS` (e.g. `fi`) and `MOODLE_LANG` (fallback, `en`); `.env.example`
  installs no packs, so this must be set here to get anything but English

Then:

```sh
cd /opt/moodle-stack
docker compose --env-file .env.versions --env-file .env up -d
./init/scripts/moodle-init.sh      # also sets $CFG->sslproxy for the https wwwroot
./init/scripts/lang-init.sh        # language packs + default language
./init/scripts/stack-init.sh
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

## 7. Site posture checks (go-live policy)

Verify rather than trust (`moodle-init.sh` hides the guest login button;
self-registration is off by Moodle default, not set explicitly):

```sh
docker compose --env-file .env.versions --env-file .env exec -T moodle \
  php /var/www/html/admin/cli/cfg.php --name=registerauth        # must be empty (no self-registration)
docker compose --env-file .env.versions --env-file .env exec -T moodle \
  php /var/www/html/admin/cli/cfg.php --name=guestloginbutton    # 0 = hidden
```

`lang-init.sh` sets these:

```sh
docker compose --env-file .env.versions --env-file .env exec -T moodle \
  php /var/www/html/admin/cli/cfg.php --name=lang                # fallback language
docker compose --env-file .env.versions --env-file .env exec -T moodle \
  php /var/www/html/admin/cli/cfg.php --name=autolang            # 1 = browser language wins
```

Accounts are created manually in the admin UI (*Site administration → Users*).

## 8. Enable the AI provider (Anthropic Claude)

In the admin UI (*Site administration → AI → AI providers*), add a
"Claude API Provider" instance, paste the Anthropic API key, set an explicit
`max_tokens` per action, and enable the provider. Use a dedicated production
key (own Anthropic Console workspace, spend limit set), not the key used in
local testing environments.

The key is stored in the Moodle database only — never in the repo or `.env`.
It survives updates and container rebuilds, and it is contained in the
database dumps (see `infra/BACKUP.md`); treat those accordingly.

Done on oivus.pnr.iki.fi 2026-08-26.

## 9. Verify end-to-end

- https://oivus.pnr.iki.fi loads the login page with a valid certificate.
- Log in as admin; *Site administration → Plugins → Question types → STACK*
  health check passes (Maxima connection).

## Updating later

An installed server is updated by checking out the new commit and running
`infra/hetzner/scripts/server-update.sh`. Both the automated and the manual
update path (below) use that same script; it performs a database backup,
re-runs `server-bootstrap.sh` (as root: Caddyfile, backup units,
`.env.versions`, image build), then `up -d`, `upgrade.php`, the smoke
tests, and an external check of the public site URL. It fails fast and
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
