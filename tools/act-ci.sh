#!/bin/sh
set -eu

if ! command -v act >/dev/null 2>&1; then
  echo "ERROR: act is not installed. Install it and try again." >&2
  exit 1
fi

if [ ! -f .github/workflows/ci.yml ]; then
  echo "ERROR: .github/workflows/ci.yml not found. Add the CI workflow first." >&2
  exit 1
fi

image="ubuntu-latest=ghcr.io/catthehacker/ubuntu:act-latest"

if [ "$#" -eq 0 ]; then
  exec act -W .github/workflows/ci.yml -P "$image" --container-architecture linux/amd64 workflow_dispatch
fi

exec act -P "$image" --container-architecture linux/amd64 "$@"
