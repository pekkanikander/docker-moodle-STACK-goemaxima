#!/bin/sh
set -eu

. ./init/scripts/init-env.sh

MOODLE_LANG="${MOODLE_LANG:-en}"
MOODLE_LANGPACKS="${MOODLE_LANGPACKS:-}"

# Accept either commas or whitespace as separators.
langs="$(echo "${MOODLE_LANGPACKS}" | tr ',' ' ')"

# The codes end up in container paths; reject anything but Moodle's own form.
for lang in ${langs} "${MOODLE_LANG}"; do
  case "${lang}" in
    ''|*[!a-z0-9_]*) die "Invalid Moodle language code: '${lang}'." ;;
  esac
done

if [ "${MOODLE_LANG}" != "en" ]; then
  in_list=0
  for lang in ${langs}; do
    if [ "${lang}" = "${MOODLE_LANG}" ]; then
      in_list=1
    fi
  done
  if [ "${in_list}" = 0 ]; then
    die "MOODLE_LANG=${MOODLE_LANG} is not listed in MOODLE_LANGPACKS."
  fi
fi

# Only contact download.moodle.org when a pack is actually missing; otherwise
# re-runs (and offline starts) stay fast. English needs no pack.
missing=""
for lang in ${langs}; do
  if [ "${lang}" = "en" ]; then
    continue
  fi
  if dc exec -T moodle test -d "/var/www/moodledata/lang/${lang}"; then
    continue
  fi
  missing="${missing:+${missing} }${lang}"
done

if [ -n "${missing}" ]; then
  log "Installing language packs: ${missing}"
  # As www-data: the packs land in the bind-mounted moodledata.
  dc exec -T -u www-data -e LANGS="${missing}" moodle php -r '
    define("CLI_SCRIPT", true);
    require "/var/www/html/config.php";
    $controller = new \tool_langimport\controller();
    $controller->install_languagepacks(preg_split("/\s+/", trim(getenv("LANGS"))));
    echo implode("\n", $controller->info), "\n";'
fi

log "Setting the default site language to ${MOODLE_LANG}."
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --name=lang --set="${MOODLE_LANG}"
log "Enabling browser language autodetect."
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --name=autolang --set=1

if [ -n "${missing}" ]; then
  log "Purging Moodle caches."
  dc exec -T moodle php /var/www/html/admin/cli/purge_caches.php
fi
