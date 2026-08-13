# Hetzner hosting task plan (Moodle + STACK + Maxima)

## Goal

Deploy a reproducible, single‑VM hosted environment on **Hetzner Cloud**, based on this GitHub repo:
- Moodle configured automatically
- STACK installed and usable
- Maxima (via goemaxima) working
- TLS termination via **Caddy on the VM host**
- Persisted storage on a **Hetzner Volume** mounted to a stable path
- Automated, release-based updates from GitHub using a hardened SSH forced-command deploy key
- External backups pulled to a macOS laptop (then backed up locally to two external drives)

This plan assumes there is **no existing data** that needs preserving, yet.
Once the hosted system is there,
then at some point we will start accumulating data that needs to be preserved,
but when this task starts, there is no such need.

## Non-goals / explicit out-of-scope
- Moodle outbound email configuration (SMTP/MTA). To be implemented as a separate future task.
- HA / clustering / multi-node deployment.
- WAF/CDN or advanced DDoS mitigation.

## Decisions already made
- Hosting: Hetzner Cloud VM, CX23 (smallest ~4 GB tier suffices; resizing is trivial)
- Phase 6 (release-based deploy automation) is deferred; go-live is Phases 1–4
  plus minimal backups, with a documented manual deploy (see `ROADMAP.md`)
- DNS: domain hosted at Gandi, add subdomain; use both IPv4 and IPv6
- SSH: hardened internet SSH on **port 33101** (non-standard port reduces scanner noise)
- TLS: Caddy automatic HTTPS; keep port **80 open** for ACME HTTP-01 issuance/renewal; redirect HTTP→HTTPS
- Storage: Hetzner Volume automatic attach + bind mount to stable path;
  Docker Compose to use bind mounts from that path
- Cron: dedicated cron-runner container (the existing one)
- Update strategy: “release in GitHub → deploy that release”; no watchtower
- Backups: implement before creating content to be preserved

## Deliverables
1. A Hetzner VM provisioned via Console + cloud-init.
2. Hetzner Cloud Firewall rules created and attached.
3. DNS records in Gandi created (A + AAAA) for the chosen hostname.
4. Caddy installed on host, configured for reverse proxy to Moodle.
5. Docker/Compose installed; repo deployed; persistent directories wired to Hetzner Volume.
6. Hardened SSH configuration (keys-only, no root, port 33101) and deploy key with forced command.
7. A root-owned update script + tight sudoers.
8. Backup scripts:
   - server side: periodic DB dump + optional integrity checks
   - backup client (macOS) side: rsync pull of moodledata + db dumps
9. GitHub Actions workflows:
   - build/test (already exists)
   - release packaging
   - deploy release to VM
10. A short runbook: how to verify, how to roll back, how to restore from backups.

## Preconditions
- A Hetzner Cloud account and API access (Console is sufficient).
- A chosen hostname, e.g. `moodle.<domain>`.
- SSH public key(s) for admin access from macOS.
- A GitHub repo with the Compose setup and CI already passing.

---

## Phase 0 — Repository preparation (one-time)

### 0.1 Establish a stable on-VM directory layout
Choose a single stable path for all persistent state:

```
/srv/moodle-persistent/
  moodledata/
  mariadb/
  backups/
    db/
```

Compose must use **bind mounts** to these directories.

### 0.2 Ensure containers are suitable for host reverse proxy
- Moodle container listens on an internal port (e.g. 8080) on localhost only, or on a Docker network with host proxy connecting.
- No TLS inside containers.

### 0.3 Health check endpoint (optional but recommended)
Add a minimal health check used by deployment verification:
- simplest: HTTP GET `/login/index.php` returns 200
- or a static `/health` file served by Caddy (separate from Moodle)

### 0.4 Define “release input” variables
Decide how the VM selects what to run:
- Option A: VM runs `git pull` on a stable branch/tag
- Option B (preferred): VM pulls a GitHub Release artefact (zip/tar) with a pinned `compose.yml` + `.env.example` and runs it

This plan targets **Option B** to keep deployments reproducible.

---

## Phase 1 — Hetzner provisioning (Console + cloud-init)

### 1.1 Create Cloud Firewall
Attach rules:
- Inbound TCP 33101 (SSH) from 0.0.0.0/0 and ::/0
- Inbound TCP 80 (HTTP) from 0.0.0.0/0 and ::/0
- Inbound TCP 443 (HTTPS) from 0.0.0.0/0 and ::/0
- Inbound deny: everything else

### 1.2 Create VM
- Image: Ubuntu LTS (current supported at time of deployment)
- Size: CX23
- Enable IPv4 + IPv6
- Attach the Firewall above
- Add your admin SSH public key(s)

### 1.3 Attach Hetzner Volume
- Create Volume sized with headroom (start modest; can be expanded)
- Attach with **automatic mount**
- Note the mount path: `/mnt/HC_Volume_<id>`

### 1.4 Provide cloud-init user-data
Cloud-init should:
- Create a non-root admin user (e.g. `admin`) with your SSH key(s)
- Harden sshd:
  - port 33101
  - keys-only auth
  - no root login
  - disable password auth
  - optional: limited auth tries/timeouts
- Install:
  - Docker Engine + Docker Compose plugin
  - Caddy
  - rsync, git, jq, curl
- Create stable mountpoint and bind mount volume:
  - `/srv/moodle-persistent` bind-mounted from `/mnt/HC_Volume_<id>`
  - create subdirectories: moodledata/mariadb/backups/db
  - ensure correct ownership for container UIDs/GIDs (documented)
- Prepare deploy user (e.g. `deploy`) with no interactive login beyond forced command

Cloud-init should also print/record key diagnostics:
- `sshd -T | grep -E 'port|passwordauthentication|permitrootlogin'`
- `docker --version`, `docker compose version`
- `caddy version`

Acceptance:
- You can SSH to `admin@VM` on port 33101 using your key.
- `/srv/moodle-persistent` exists and is on the Volume.

---

## Phase 2 — DNS at Gandi (A + AAAA)

### 2.1 Choose hostname
Example: `moodle.<domain>`

### 2.2 Create DNS records in Gandi
- A record → VM IPv4
- AAAA record → VM IPv6

### 2.3 Verify
From macOS:
- `dig A moodle.<domain> +short`
- `dig AAAA moodle.<domain> +short`

Acceptance:
- Both resolve to the VM.

Note: Automated DNS management is not required for this phase.

---

## Phase 3 — Caddy TLS reverse proxy on host

### 3.1 Install Caddy (if not already from cloud-init)
Prefer official packages.

### 3.2 Caddyfile
Create a Caddyfile that:
- Serves `https://moodle.<domain>`
- Redirects HTTP→HTTPS
- Reverse proxies to Moodle upstream (localhost port or docker network)
- Sets sane security headers (without HSTS initially)

Avoid enabling HSTS initially; add later after stable.

### 3.3 Open ports
Ensure firewall allows 80/443.

### 3.4 Verification
- `curl -I http://moodle.<domain>` returns a redirect to https
- `curl -I https://moodle.<domain>` returns 200/303 as expected
- Browser loads login page without certificate warnings

Acceptance:
- Valid TLS certificate issued automatically
- HTTP redirects to HTTPS

---

## Phase 4 — Docker Compose deployment with bind mounts

### 4.1 Prepare runtime directory
Choose a working directory, e.g.:

```
/opt/moodle-stack/
```

This holds:
- compose.yml
- .env
- any config templates

### 4.2 Bind mounts
Update compose to bind-mount:
- Moodledata → `/srv/moodle-persistent/moodledata`
- MariaDB → `/srv/moodle-persistent/mariadb`
- DB dumps → `/srv/moodle-persistent/backups/db` (read/write by dump job)

### 4.3 Bring up stack
- `docker compose pull`
- `docker compose up -d`

### 4.4 First boot initialisation
Verify:
- Moodle config is generated automatically
- STACK plugin present
- Maxima connectivity validated (existing repo test)
- Cron runner container present and unique

Acceptance:
- Login page loads through Caddy
- STACK question can evaluate a basic expression

---

## Phase 5 — Backups (server-side + macOS pull)

### 5.1 Server-side DB dumps
Implement a DB dump mechanism that produces daily dumps to:

```
/srv/moodle-persistent/backups/db/
```

Requirements:
- Rotation/retention (e.g. keep 14 daily + 8 weekly)
- Compression
- Non-interactive
- Log success/failure

Schedule:
- systemd timer or cron on host

### 5.2 macOS pull backups
On macOS, create a backup directory, e.g.:

```
~/Backups/moodle/
  moodledata/
  db/
```

Implement rsync pull commands (script) that:
- pulls `moodledata/` (incremental)
- pulls DB dumps
- verifies recent dump exists

Run it manually at first; later schedule with `launchd`.

### 5.3 Restore drill (mandatory before creating content)
Document and perform a minimal restore drill:
- spin up a fresh VM (or stop services)
- restore DB from dump
- restore moodledata
- confirm Moodle loads

Acceptance:
- You have a written restore procedure
- A test restore succeeds

---

## Phase 6 — Hardened release-based updates from GitHub

### 6.1 Create a deploy user and deploy key
On VM:
- user `deploy` with minimal privileges
- no interactive shell (or forced-command only)

### 6.2 Root-owned update script
Create:
- `/usr/local/sbin/moodle-stack-update` (root-owned, executable)

Responsibilities:
- download selected GitHub Release artefact
- verify checksum (store checksum with release)
- unpack to `/opt/moodle-stack/releases/<version>`
- update `/opt/moodle-stack/current` symlink
- run `docker compose pull`
- run `docker compose up -d`
- run verification checks (HTTP + container health)
- keep last-known-good release for rollback

### 6.3 Tight sudoers rule
Allow `deploy` to run only:

```
sudo /usr/local/sbin/moodle-stack-update
```

No other sudo.

### 6.4 authorized_keys forced command
In `~deploy/.ssh/authorized_keys`, constrain the deploy key:
- forced command executes only the update path
- disable pty, forwarding

### 6.5 GitHub Actions
Implement workflows:

1) **Build/Test** (already exists; keep)
2) **Release**
   - tag-based (e.g. v0.1.0)
   - build artefact containing compose + env templates
   - produce SHA256 checksums
3) **Deploy**
   - triggered on release publish
   - SSH using deploy key secret
   - run the forced update command

Secrets:
- `DEPLOY_SSH_PRIVATE_KEY`
- `DEPLOY_SSH_KNOWN_HOSTS`

Acceptance:
- Creating a GitHub Release triggers deploy
- VM updates without manual SSH login
- Rollback to previous release is documented and tested

---

## Phase 7 — Runbook and operational checklist

### 7.1 Runbook: common operations
- Check status: `docker compose ps`, logs
- Update manually (admin only)
- Rollback to last-known-good
- Backup now + verify
- Restore from backup

### 7.2 Security checklist
- SSH keys only; root login disabled
- SSH on port 33101
- Fail2ban (or equivalent) enabled
- Firewall only allows 80/443/33101
- Regular OS security updates (unattended-upgrades) enabled

### 7.3 Monitoring (minimal)
- Disk usage alert threshold
- Basic uptime check (external or self)

---

## Acceptance criteria (end-to-end)
- [ ] VM reachable via SSH on port 33101 using admin key
- [ ] DNS A+AAAA resolve correctly
- [ ] HTTPS works with a valid certificate; HTTP redirects to HTTPS
- [ ] Moodle loads, STACK works, Maxima works
- [ ] Cron runner active (single)
- [ ] Persistent directories exist under `/srv/moodle-persistent`
- [ ] Daily DB dumps created and rotated
- [ ] macOS rsync pull works and is documented
- [ ] Restore drill completed successfully
- [ ] GitHub Release → automatic deploy succeeds
- [ ] Rollback procedure tested
- [ ] Outbound email explicitly documented as out-of-scope
