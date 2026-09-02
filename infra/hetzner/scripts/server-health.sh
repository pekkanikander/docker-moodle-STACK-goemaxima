#!/bin/sh
set -eu

# Dead-man health check: ping healthchecks.io only when every check passes.
# A missed ping (a failure here, a dead VM, a full disk) triggers the alert
# email from healthchecks.io. Driven daily by moodle-health.timer; setup and
# verification in infra/hetzner/DEPLOY.md.

REPO_DIR=${REPO_DIR:-/opt/moodle-stack}
cd "$REPO_DIR"

disk_limit=${DISK_LIMIT_PCT:-85}
dump_max_age_min=${DUMP_MAX_AGE_MIN:-1560}  # 26 h: one missed 03:30 backup trips it

fail() { echo "HEALTH FAIL: $*" >&2; exit 1; }

ping_url=$(sed -n 's/^HEALTHCHECKS_PING_URL=//p' .env)
[ -n "$ping_url" ] || fail "HEALTHCHECKS_PING_URL not set in .env"
site_url=$(sed -n 's/^MOODLE_SITE_URL=//p' .env)
[ -n "$site_url" ] || fail "MOODLE_SITE_URL not set in .env"

for fs in / /srv/moodle-persistent; do
  pct=$(df -P "$fs" | awk 'NR==2 { sub("%", "", $5); print $5 }')
  [ "$pct" -lt "$disk_limit" ] || fail "$fs at ${pct}% (limit ${disk_limit}%)"
done

fresh=$(find /srv/moodle-persistent/backups/db/daily \
  -name 'moodle-*.sql.gz' -mmin "-$dump_max_age_min" | head -n 1)
[ -n "$fresh" ] || fail "no DB dump younger than $dump_max_age_min min"

# Through Caddy on the public URL, so TLS validity is checked too.
curl -fsS --max-time 30 "$site_url/login/index.php" > /dev/null \
  || fail "site check failed: $site_url/login/index.php"

curl -fsS --max-time 30 "$ping_url" > /dev/null
echo "health OK: pinged healthchecks.io"
