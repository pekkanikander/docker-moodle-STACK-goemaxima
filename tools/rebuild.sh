#!/bin/sh
set -eu

. ./init/scripts/init-env.sh

dc build --no-cache --pull
dc up -d --force-recreate

sleep 10

dc exec -T moodle sh -c '
  if [ -f /var/www/moodledata/config.php ] && \
     [ ! -f /var/www/html/config.php ]; then \
     cp /var/www/moodledata/config.php /var/www/html/config.php && \
     chown www-data:www-data /var/www/html/config.php && \
     chmod 0640 /var/www/html/config.php; \
   fi'
