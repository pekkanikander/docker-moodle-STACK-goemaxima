#!/bin/sh
# Idempotent outgoing-mail configuration from .env: noreply address, SMTP
# target and transport security. Unlike moodle-init.sh, this is safe to rerun
# at any time; that is how an already-installed site gets new mail settings
# after editing .env. SMTP credentials are set only in the Moodle admin UI
# (Server > Email > Outgoing mail configuration), never here.
set -eu

. ./init/scripts/init-env.sh

require_nonempty "MOODLE_NOREPLY_EMAIL" "${MOODLE_NOREPLY_EMAIL:-}"
require_nonempty "MOODLE_SMTPHOSTS" "${MOODLE_SMTPHOSTS:-}"

log "Setting Moodle noreply address."
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --name=noreplyaddress \
  --set="${MOODLE_NOREPLY_EMAIL}"
log "Setting outgoing SMTP host."
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --name=smtphosts \
  --set="${MOODLE_SMTPHOSTS}"
log "Setting SMTP transport security."
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --name=smtpsecure \
  --set="${MOODLE_SMTPSECURE:-}"
