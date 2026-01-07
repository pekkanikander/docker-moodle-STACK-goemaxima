#!/bin/sh
set -eu

. ./init/scripts/init-env.sh

require_nonempty "MOODLE_STACK_MAXIMAVERSION" "${MOODLE_STACK_MAXIMAVERSION:-}"
require_nonempty "MOODLE_STACK_MAXIMACOMMANDSERVER" "${MOODLE_STACK_MAXIMACOMMANDSERVER:-}"
require_set "MOODLE_STACK_MAXIMACOMMAND"
require_set "MOODLE_STACK_MAXIMACOMMANDOPT"
require_set "MOODLE_STACK_MAXIMALIBRARIES"

log "Setting STACK configuration."
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=qtype_stack \
  --name=maximaversion \
  --set="${MOODLE_STACK_MAXIMAVERSION}"
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=qtype_stack \
  --name=maximacommand \
  --set="${MOODLE_STACK_MAXIMACOMMAND}"
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=qtype_stack \
  --name=maximacommandopt \
  --set="${MOODLE_STACK_MAXIMACOMMANDOPT}"
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=qtype_stack \
  --name=maximacommandserver \
  --set="${MOODLE_STACK_MAXIMACOMMANDSERVER}"
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=qtype_stack \
  --name=maximalibraries \
  --set="${MOODLE_STACK_MAXIMALIBRARIES}"

log "Purging Moodle caches."
dc exec -T moodle php /var/www/html/admin/cli/purge_caches.php
