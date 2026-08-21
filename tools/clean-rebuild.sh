#!/bin/sh
set -eu

. ./init/scripts/init-env.sh

dc down -v --remove-orphans
docker image prune -f

root="${MOODLE_PERSISTENT_ROOT:-/srv/moodle-persistent}"
case "$root" in
  /*)
    if [ "${PURGE_PERSISTENT:-0}" = "1" ]; then
      rm -rf "$root"
      mkdir -p "$root/mariadb" "$root/moodledata" "$root/backups/db"
    fi
    ;;
  *)
    rm -rf "$root"
    mkdir -p "$root/mariadb" "$root/moodledata" "$root/backups/db"
    chmod -R 777 "$root"
    ;;
esac

# Pre-create the qbank build dir: the moodle service bind-mounts it, and a
# missing bind-mount source would be created root-owned by dockerd, leaving
# tools/qbank.sh unable to write into it on Linux hosts.
mkdir -p "${QBANK_BUILD_DIR:-./.generated/qbank}"

dc build --no-cache --pull

dc up -d --force-recreate
./init/scripts/moodle-init.sh
./init/scripts/lang-init.sh
./init/scripts/stack-init.sh
