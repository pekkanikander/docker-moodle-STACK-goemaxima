#!/bin/sh
set -eu

if [ ! -f ./.env ]; then
  echo "Missing .env. Copy .env.example to .env and fill required values." >&2
  exit 1
fi

set -a
. ./.env
set +a

log() {
  echo "$@"
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_nonempty() {
  name="$1"
  value="$2"

  if [ -z "$value" ]; then
    echo "Set ${name} in .env." >&2
    exit 1
  fi
}

require_set() {
  name="$1"

  eval "value_set=\${${name}+x}"
  if [ "$value_set" != "x" ]; then
    echo "Set ${name} in .env (empty allowed)." >&2
    exit 1
  fi
}

dc() {
  if [ -n "${DOCKER_COMPOSE_ARGS:-}" ]; then
    docker compose ${DOCKER_COMPOSE_ARGS} "$@"
  else
    docker compose "$@"
  fi
}
