#!/bin/sh
set -eu

# Give the server an authenticated route to GitHub, so that `git fetch` in
# deploy-cmd.sh is not subject to GitHub's throttling of anonymous downloads
# ("GitHub is temporarily limiting some unauthenticated downloads").
#
# Generates a read-only deploy key, pins GitHub's host keys from its own
# published metadata, and points origin at the SSH remote. Idempotent: safe
# to re-run. Run as admin on the server; register the printed public key as a
# read-only deploy key on the repo (see DEPLOY.md).

REPO_DIR=${REPO_DIR:-/opt/moodle-stack}
KEY_PATH=${KEY_PATH:-"$HOME/.ssh/github_deploy_ed25519"}
KNOWN_HOSTS=${KNOWN_HOSTS:-"$HOME/.ssh/github_known_hosts"}
REMOTE_URL=${REMOTE_URL:-"git@github.com:pekkanikander/docker-moodle-STACK-goemaxima.git"}

umask 077
mkdir -p "$HOME/.ssh"

[ -f "$KEY_PATH" ] || ssh-keygen -t ed25519 -a 64 -f "$KEY_PATH" -N "" \
  -C "moodle-hetzner-github-deploy"

# GitHub publishes its current SSH host keys at api.github.com/meta; take them
# from there (authenticated by TLS) rather than trusting an ssh-keyscan.
tmp=$(mktemp)
curl -fsS https://api.github.com/meta \
  | python3 -c 'import json,sys
for k in json.load(sys.stdin)["ssh_keys"]: print("github.com", k)' > "$tmp"
[ -s "$tmp" ] || { echo "ERROR: no host keys from api.github.com/meta" >&2; exit 1; }
mv "$tmp" "$KNOWN_HOSTS"

ssh_cmd="ssh -i $KEY_PATH -o IdentitiesOnly=yes -o UserKnownHostsFile=$KNOWN_HOSTS -o StrictHostKeyChecking=yes"

# github.com closes the session with status 1 after greeting an accepted key;
# only the greeting distinguishes success from a rejected key.
if ! $ssh_cmd -o BatchMode=yes -T git@github.com 2>&1 | grep -q 'successfully authenticated'; then
  echo
  echo "Deploy key not accepted yet. Register this public key on the repo"
  echo "(Settings -> Deploy keys -> Add deploy key, write access OFF), then re-run:"
  echo
  cat "$KEY_PATH.pub"
  exit 1
fi

cd "$REPO_DIR"
git config core.sshCommand "$ssh_cmd"
git remote set-url origin "$REMOTE_URL"
git fetch --tags origin
echo "OK: $REPO_DIR fetches from $REMOTE_URL over an authenticated SSH connection."
