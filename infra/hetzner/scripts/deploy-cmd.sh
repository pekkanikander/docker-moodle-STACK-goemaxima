#!/bin/sh
set -eu

# Forced-command entry point for the GitHub Actions deploy key: sshd runs this
# instead of the requested command, which must be the full commit SHA to
# deploy (see infra/hetzner/DEPLOY.md). Only commits already on origin can be
# deployed, so the key cannot introduce code.
#
# Everything lives inside main(): the checkout below replaces this very file,
# and the function body must be fully parsed before execution begins.
main() {
  sha=${SSH_ORIGINAL_COMMAND:-}
  case $sha in
    *[!0-9a-f]*|"") echo "ERROR: expected a full 40-hex commit SHA" >&2; exit 64 ;;
  esac
  [ "${#sha}" -eq 40 ] || { echo "ERROR: expected a full 40-hex commit SHA" >&2; exit 64; }

  # One deploy at a time, shared with deploy-content-cmd.sh: a stack update and
  # a content import both drive the same running Moodle. fd 9 survives the exec
  # below, so the lock is held for the whole run.
  exec 9>"$HOME/.moodle-deploy.lock"
  flock -n 9 || { echo "ERROR: another deploy is running" >&2; exit 75; }

  cd /opt/moodle-stack
  git fetch --tags origin
  git rev-parse --verify --quiet "$sha^{commit}" > /dev/null \
    || { echo "ERROR: unknown commit $sha" >&2; exit 65; }

  echo "Deploying $sha (previous: $(git rev-parse HEAD))"
  git -c advice.detachedHead=false checkout --detach "$sha"
  exec ./infra/hetzner/scripts/server-update.sh
}

main
