#!/bin/sh
#
# Generate an admin SSH key for the Moodle Hetzner host and update ~/.ssh/config.
#
# Behavior:
# - Creates an ed25519 key at $KEY_PATH if it does not already exist.
# - If a "Host $HOST_ALIAS" entry exists (matched via grep -E), rewrites only
#   HostName/User/Port/IdentityFile lines inside that block; other lines are left
#   untouched.
# - If no matching Host block exists, creates a new Host block.
#
# Caveats:
# - The update only replaces keys that are already present in the block; it does
#   not add missing HostName/User/Port/IdentityFile lines.
# - The Host match is conservative but not perfect: a Host line with extra
#   patterns or inline comments may still match or be missed.

set -eu

HOST_ALIAS=${HOST_ALIAS:-moodle-hetzner}
HOSTNAME=${HOSTNAME:-moodle.example.com}
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

if grep -qE "^Host[[:space:]]+$HOST_ALIAS[[:space:]]*$" "$CONFIG"; then
  awk -v host="$HOST_ALIAS" -v hostname="$HOSTNAME" -v user="$SSH_USER" \
  -v port="$SSH_PORT" -v key="$KEY_PATH" '
  BEGIN { inblock=0; found=0 }
  $1=="Host" && $2==host        { inblock=1; found=1; print; next }
  $1=="Host" || $1=="Match"     { inblock=0 }
  inblock && $1=="HostName"     { print "   HostName " hostname; next }
  inblock && $1=="User"         { print "   User " user; next }
  inblock && $1=="Port"         { print "   Port " port; next }
  inblock && $1=="IdentityFile" { print "   IdentityFile " key; next }
  { print }
  END { if (!found) exit 1 }
  ' "$CONFIG" > "$tmp"
else
  cat "$CONFIG" > "$tmp"
  cat >> "$tmp" <<EOF

Host $HOST_ALIAS
   HostName $HOSTNAME
   User $SSH_USER
   Port $SSH_PORT
   IdentityFile $KEY_PATH
   PreferredAuthentications publickey
   IdentitiesOnly yes
EOF
fi

cp "$CONFIG" "$CONFIG.bak"
# Preserve the original file permissions.
cat "$tmp" > "$CONFIG"
rm "$tmp"

cat "$KEY_PATH.pub"
