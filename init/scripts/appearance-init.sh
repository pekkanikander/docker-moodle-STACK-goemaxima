#!/bin/sh
# Idempotent per-environment marking: tints every page and puts a corner
# badge with MOODLE_ENV_LABEL on it, so localhost, staging and production
# are told apart at a glance. Like lang-init.sh/mail-init.sh, safe to rerun
# at any time; an empty label clears the marking.
#
# The whole marking is one core setting, additionalhtmlhead (Appearance >
# Additional HTML), which every theme emits at the end of <head>, after its
# own CSS, on every page including login. This script owns that setting, so
# anything put there by hand is overwritten.
set -eu

. ./init/scripts/init-env.sh

label="${MOODLE_ENV_LABEL:-}"

if [ -n "$label" ]; then
  require_nonempty "MOODLE_ENV_COLOUR" "${MOODLE_ENV_COLOUR:-}"
  # Both values land inside <style> in <head>: keep them to characters that
  # cannot close a CSS string, a declaration or the element.
  case "$label" in
    *[!A-Za-z0-9\ ._-]*)
      die "MOODLE_ENV_LABEL: letters, digits, space, dot, underscore and hyphen only." ;;
  esac
  case "$MOODLE_ENV_COLOUR" in
    *[!A-Za-z0-9#]*)
      die "MOODLE_ENV_COLOUR: a hex colour or a CSS colour name, e.g. #2e7d32." ;;
  esac
  log "Marking this instance as ${label}."
  # The page tint is the badge colour heavily diluted into whatever the
  # theme's own body background is, so one colour configures both and dark
  # mode still gets a dark page. Browsers without color-mix() drop the tint
  # and keep the badge.
  html="<style>
body{background-color:color-mix(in srgb, ${MOODLE_ENV_COLOUR} 8%, var(--bs-body-bg))}
body::after{content:\"${label}\";position:fixed;left:0;bottom:0;z-index:1080;
padding:.15rem .5rem;border-top-right-radius:.3rem;pointer-events:none;
background:${MOODLE_ENV_COLOUR};color:#fff;font:600 .75rem/1.4 system-ui,sans-serif}
</style>"
else
  log "MOODLE_ENV_LABEL is empty: leaving this instance unmarked."
  html=""
fi

dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --name=additionalhtmlhead --set="$html"
