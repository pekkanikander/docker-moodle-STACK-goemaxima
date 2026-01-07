#!/bin/sh
set -eu

. ./init/scripts/init-env.sh

dc down -v --remove-orphans
dc rm -fsv
docker image prune -f
dc build --no-cache --pull
dc up -d --force-recreate
./init/scripts/moodle-init.sh
./init/scripts/stack-init.sh
