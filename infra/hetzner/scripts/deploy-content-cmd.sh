#!/bin/sh
set -eu

# Forced-command entry point for the GitHub Actions content deploy key: sshd
# runs this instead of the requested command, which must be the full commit SHA
# of the content repo to deploy (see infra/hetzner/DEPLOY.md). Only commits
# already on origin can be deployed, so the key cannot introduce content.
#
# Unlike deploy-cmd.sh this needs no main() wrapper: the checkout below replaces
# a different tree, not this file.

REPO_DIR=${REPO_DIR:-/opt/moodle-stack}
CONTENT_DIR=${CONTENT_DIR:-/opt/oivus-questions}

sha=${SSH_ORIGINAL_COMMAND:-}
case $sha in
  *[!0-9a-f]*|"") echo "ERROR: expected a full 40-hex commit SHA" >&2; exit 64 ;;
esac
[ "${#sha}" -eq 40 ] || { echo "ERROR: expected a full 40-hex commit SHA" >&2; exit 64; }

[ -d "$CONTENT_DIR/.git" ] || {
  echo "ERROR: no content checkout at $CONTENT_DIR; see infra/hetzner/DEPLOY.md" >&2
  exit 66
}

# One deploy at a time. A content import and a stack update both drive the same
# running Moodle, and qbank.sh's own lock does not know about server-update.sh.
# fd 9 survives the exec below, so the lock is held for the whole run.
exec 9>"$HOME/.moodle-deploy.lock"
flock -n 9 || { echo "ERROR: another deploy is running" >&2; exit 75; }

cd "$CONTENT_DIR"
git fetch --tags origin
git rev-parse --verify --quiet "$sha^{commit}" > /dev/null \
  || { echo "ERROR: unknown commit $sha" >&2; exit 65; }

echo "Deploying content $sha (previous: $(git rev-parse HEAD))"
git -c advice.detachedHead=false checkout --detach "$sha"

# compile, import, build the quizzes, then the STACK question and figure tests.
# 'aitest' is not part of 'all': it costs API money per run.
cd "$REPO_DIR"
QBANK_CONTENT_DIR="$CONTENT_DIR"
export QBANK_CONTENT_DIR
exec ./tools/qbank.sh all
