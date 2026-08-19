#!/bin/sh
set -eu

# config.php is written into the image's writable layer, so it does not survive
# a container recreate. moodle-init.sh keeps the durable copy in moodledata;
# restore from it here so that a rebuild does not drop the site back to the
# installer. Absent on both sides means the site is not installed yet.
CONFIG_SRC="/var/www/moodledata/config.php"
CONFIG_DST="/var/www/html/config.php"

if [ ! -f "$CONFIG_DST" ] && [ -f "$CONFIG_SRC" ]; then
  cp "$CONFIG_SRC" "$CONFIG_DST"
  chown www-data:www-data "$CONFIG_DST"
  chmod 0640 "$CONFIG_DST"
fi

exec docker-php-entrypoint "$@"
