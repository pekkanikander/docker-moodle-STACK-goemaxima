#!/bin/sh
set -eu

docker compose down -v --remove-orphans
docker compose rm -fsv
docker image prune -f
docker compose build --no-cache --pull
docker compose up -d --force-recreate
./init/scripts/moodle-init.sh
