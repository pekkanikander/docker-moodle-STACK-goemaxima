#!/bin/sh
set -eu

CONFIG_SRC="/var/www/moodledata/config.php"
CONFIG_DST="/var/www/html/config.php"

if [ ! -f "$CONFIG_DST" ]; then
  if [ ! -f "$CONFIG_SRC" ]; then
    echo "config.php not found in ${CONFIG_SRC}; run moodle-init.sh first." >&2
    exit 1
  fi
  cp "$CONFIG_SRC" "$CONFIG_DST"
  chown www-data:www-data "$CONFIG_DST"
  chmod 0640 "$CONFIG_DST"
fi

exec /usr/local/bin/php /var/www/html/admin/cli/cron.php
