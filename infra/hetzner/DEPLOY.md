# Go-live runbook: Hetzner VM for oivus.pnr.iki.fi

Concrete steps for hetzner-hosting-task.md Phases 1–4. Run the macOS steps from
the repo root. Deployment is manual by design (Phase 6 automation is deferred).

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
- Cloud-init creates user `admin` (key-only, passwordless sudo), hardens sshd,
  installs Docker + compose v2 + Caddy + yq, and bind-mounts the volume to
  `/srv/moodle-persistent`.

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

## 5. Caddy

From macOS:

```sh
scp infra/hetzner/caddy/Caddyfile moodle-hetzner:/tmp/Caddyfile
ssh moodle-hetzner 'sudo install -m 0644 -o root -g root /tmp/Caddyfile /etc/caddy/Caddyfile && sudo systemctl reload caddy'
```

Caddy fetches the certificate on first request; verify from macOS:

```sh
curl -I http://oivus.pnr.iki.fi     # 308 redirect to https
curl -I https://oivus.pnr.iki.fi   # 502 until Moodle is up; no certificate warning
```

## 6. Deploy the stack

On the VM (`ssh moodle-hetzner`):

```sh
sudo install -d -o admin -g admin /opt/moodle-stack
git clone https://github.com/pekkanikander/docker-moodle-STACK-goemaxima.git /opt/moodle-stack
cd /opt/moodle-stack
git checkout <tag>                 # pick the release tag; main while pre-alpha
./tools/update-versions.sh
cp .env.example .env
```

Edit `.env` (nano or vi):
- `MOODLE_SITE_URL=https://oivus.pnr.iki.fi`
- `MOODLE_HTTP_PORT=8080` (must match the Caddyfile upstream)
- `MOODLE_PERSISTENT_ROOT=/srv/moodle-persistent`
- `MOODLE_ADMIN_EMAIL`, `MOODLE_ADMIN_PASSWORD` (real values; the password is
  the actual admin login)
- `MOODLE_SITE_FULLNAME`, `MOODLE_SITE_SHORTNAME`, `MOODLE_NOREPLY_EMAIL`

Then:

```sh
docker compose --env-file .env.versions --env-file .env build
docker compose --env-file .env.versions --env-file .env up -d
./init/scripts/moodle-init.sh      # also sets $CFG->sslproxy for the https wwwroot
./init/scripts/stack-init.sh
MOODLE_HTTP_PORT=8080 ./init/scripts/smoke-tests.sh
```

Note: `admin` is in the `docker` group (no sudo needed for docker), but the
group membership takes effect only on a fresh login after cloud-init.

## 7. Site posture checks (go-live policy)

Fresh Moodle defaults already match the policy; verify rather than trust:

```sh
docker compose --env-file .env.versions --env-file .env exec -T moodle \
  php /var/www/html/admin/cli/cfg.php --name=registerauth        # must be empty (no self-registration)
docker compose --env-file .env.versions --env-file .env exec -T moodle \
  php /var/www/html/admin/cli/cfg.php --name=guestloginbutton    # 0 = hidden
```

Accounts are created manually in the admin UI (*Site administration → Users*).

## 8. Verify end-to-end

- https://oivus.pnr.iki.fi loads the login page with a valid certificate.
- Log in as admin; *Site administration → Plugins → Question types → STACK*
  health check passes (Maxima connection).

## Updating later (manual deploy)

```sh
ssh moodle-hetzner
cd /opt/moodle-stack
git fetch --tags && git checkout <new-tag>
./tools/update-versions.sh
docker compose --env-file .env.versions --env-file .env build
docker compose --env-file .env.versions --env-file .env up -d
docker compose --env-file .env.versions --env-file .env exec -T -u www-data moodle \
  php /var/www/html/admin/cli/upgrade.php --non-interactive
```

Take a backup first once M2 (backups) exists. Do NOT run `moodle-init.sh` on an
installed site: it forces a fresh install.
