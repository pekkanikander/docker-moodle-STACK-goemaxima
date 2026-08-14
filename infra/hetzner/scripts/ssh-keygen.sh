#!/bin/sh
#
# Generate an admin SSH key for the Moodle Hetzner host and update ~/.ssh/config.
#
# Behavior:
# - Creates an ed25519 key at $KEY_PATH if it does not already exist.
# - Replaces any existing "Host $HOST_ALIAS" block in ~/.ssh/config with a
#   canonical block (HostName/User/Port/IdentityFile etc.); keys are matched
#   case-insensitively, so e.g. an old "Hostname" line is replaced too.
#   A backup is kept at ~/.ssh/config.bak.
# - If no matching Host block exists, appends a new one.

set -eu

HOST_ALIAS=${HOST_ALIAS:-moodle-hetzner}
HOSTNAME=${HOSTNAME:-oivus.pnr.iki.fi}
SSH_USER=${SSH_USER:-admin}
SSH_PORT=${SSH_PORT:-33101}
KEY_PATH=${KEY_PATH:-"$HOME/.ssh/to_moodle_hetzner_admin_ed25519"}
KEY_COMMENT=${KEY_COMMENT:-"moodle-hetzner-admin@`uname -n`"}

CONFIG="$HOME/.ssh/config"

umask 077
mkdir -p "$HOME/.ssh"

if [ -e "$KEY_PATH" ] || [ -e "$KEY_PATH.pub" ]; then
  echo "$0: warning: key exists: $KEY_PATH" >&2
else
  ssh-keygen -t ed25519 -a 64 -f "$KEY_PATH" -C "$KEY_COMMENT" -N ""
fi

if [ ! -e "$CONFIG" ]; then
  touch "$CONFIG"
  chmod 600 "$CONFIG"
fi

tmp=$(mktemp)

# Drop any existing block for the alias (from its "Host" line up to, but not
# including, the next "Host"/"Match" line), then append the canonical block.
awk -v host="$HOST_ALIAS" '
  tolower($1) == "host" || tolower($1) == "match" { skip = 0 }
  tolower($1) == "host" && $2 == host && NF == 2   { skip = 1 }
  !skip { print }
' "$CONFIG" > "$tmp"

cat >> "$tmp" <<EOF
Host $HOST_ALIAS
   HostName $HOSTNAME
   User $SSH_USER
   Port $SSH_PORT
   IdentityFile $KEY_PATH
   PreferredAuthentications publickey
   IdentitiesOnly yes
EOF

cp "$CONFIG" "$CONFIG.bak"
# Preserve the original file permissions.
cat "$tmp" > "$CONFIG"
rm "$tmp"

cat "$KEY_PATH.pub"
