#!/bin/sh
set -eu

if [ ! -f ./.env ]; then
  echo "Missing .env. Copy .env.example to .env and fill required values." >&2
  exit 1
fi

set -a
. ./.env
set +a

require_nonempty() {
  name="$1"
  value="$2"

  if [ -z "$value" ]; then
    echo "Set ${name} in .env." >&2
    exit 1
  fi
}

require_set() {
  name="$1"

  eval "value_set=\${${name}+x}"
  if [ "$value_set" != "x" ]; then
    echo "Set ${name} in .env (empty allowed)." >&2
    exit 1
  fi
}

require_nonempty "MOODLE_NOREPLY_EMAIL" "${MOODLE_NOREPLY_EMAIL:-}"
require_nonempty "MOODLE_STACK_MAXIMAVERSION" "${MOODLE_STACK_MAXIMAVERSION:-}"
require_nonempty "MOODLE_STACK_MAXIMACOMMANDSERVER" "${MOODLE_STACK_MAXIMACOMMANDSERVER:-}"
require_set "MOODLE_STACK_MAXIMACOMMAND"
require_set "MOODLE_STACK_MAXIMACOMMANDOPT"
require_set "MOODLE_STACK_MAXIMALIBRARIES"

docker compose exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --name=noreplyaddress \
  --set="${MOODLE_NOREPLY_EMAIL}"

docker compose exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=qtype_stack \
  --name=maximaversion \
  --set="${MOODLE_STACK_MAXIMAVERSION}"
docker compose exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=qtype_stack \
  --name=maximacommand \
  --set="${MOODLE_STACK_MAXIMACOMMAND}"
docker compose exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=qtype_stack \
  --name=maximacommandopt \
  --set="${MOODLE_STACK_MAXIMACOMMANDOPT}"
docker compose exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=qtype_stack \
  --name=maximacommandserver \
  --set="${MOODLE_STACK_MAXIMACOMMANDSERVER}"
docker compose exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=qtype_stack \
  --name=maximalibraries \
  --set="${MOODLE_STACK_MAXIMALIBRARIES}"

docker compose exec -T moodle php /var/www/html/admin/cli/purge_caches.php
