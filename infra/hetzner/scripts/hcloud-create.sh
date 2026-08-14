#!/bin/sh
set -eu

# Minimal Hetzner Cloud server create helper for admins.
#
# Configuration is via environment variables with sensible defaults.
# This script is intentionally not a general-purpose CLI.
#
# Required:
#   ADMIN_SSH_PUBKEY    SSH public key line to inject into cloud-init template rendering
#
# Optional:
#   SERVER_NAME         Hetzner server name (default: moodle)
#   SERVER_TYPE         Hetzner server type (default: cx23)
#   IMAGE               OS image (default: ubuntu-24.04)
#   LOCATION            Hetzner location (default: Hetzner's choice)
#   CLOUD_INIT_TEMPLATE Cloud-init template path (default: infra/hetzner/cloud-init/cloud-init.yml)
#   USER_DATA_FILE      If set, use this file directly (skips template rendering)
#   SSH_KEY             Hetzner SSH key name/id to attach (optional but recommended)
#   FIREWALL            Hetzner firewall name to attach; created with rules for
#                       TCP 80/443/33101 if it does not exist (default: moodle)
#   VOLUME_NAME         Volume name to create/attach (optional)
#   VOLUME_SIZE_GB      Volume size if created (default: 10)
#   RECREATE            If set to 1, delete existing server with same name (default: 0)
#   HOST_DNS_NAME       DNS name of the server, for known_hosts cleanup
#                       (default: oivus.pnr.iki.fi)
#   SSH_PORT            SSH port used in known_hosts entries (default: 33101)
#
# Notes:
# - Uses Hetzner defaults wherever reasonable.
# - Prints IPv4/IPv6 and suggested DNS A/AAAA values.

SERVER_NAME=${SERVER_NAME:-moodle}
SERVER_TYPE=${SERVER_TYPE:-cx23}
IMAGE=${IMAGE:-ubuntu-24.04}
LOCATION=${LOCATION:-}
CLOUD_INIT_TEMPLATE=${CLOUD_INIT_TEMPLATE:-infra/hetzner/cloud-init/cloud-init.yml}
RECREATE=${RECREATE:-0}

VOLUME_NAME=${VOLUME_NAME:-moodle}
VOLUME_SIZE_GB=${VOLUME_SIZE_GB:-10}
FIREWALL=${FIREWALL:-moodle}
HOST_DNS_NAME=${HOST_DNS_NAME:-oivus.pnr.iki.fi}
SSH_PORT=${SSH_PORT:-33101}

# Prefer explicit user-data file; otherwise render from template.
USER_DATA_FILE=".generated/cloud-init.rendered.yml"

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "$0: missing command: $1" >&2; exit 1; }
}

need hcloud
need jq

: "${ADMIN_SSH_PUBKEY:?set ADMIN_SSH_PUBKEY}"
[ -f "$CLOUD_INIT_TEMPLATE" ] || { echo "$0: missing template: $CLOUD_INIT_TEMPLATE" >&2; exit 1; }

mkdir -p "$(dirname "$USER_DATA_FILE")"
# shellcheck disable=SC2016
envsubst '${ADMIN_SSH_PUBKEY}' < "$CLOUD_INIT_TEMPLATE" > "$USER_DATA_FILE"

[ -f "$USER_DATA_FILE" ] || { echo "$0: missing user-data: $USER_DATA_FILE" >&2; exit 1; }

# Delete existing server if requested.
existing_id=$(hcloud server list -o json | jq -r --arg n "$SERVER_NAME" '.[] | select(.name==$n) | .id' | head -n 1)
if [ -n "$existing_id" ] && [ "$existing_id" != "null" ]; then
  if [ "$RECREATE" = "1" ]; then
    hcloud server delete "$existing_id"
  else
    echo "$0: server exists: $SERVER_NAME (id=$existing_id). Set RECREATE=1 to replace." >&2
    exit 1
  fi
fi

# Ensure the firewall exists with the planned inbound rules (TCP 80/443/33101).
fw_id=$(hcloud firewall list -o json | jq -r --arg n "$FIREWALL" '.[] | select(.name==$n) | .id' | head -n 1)
if [ -z "$fw_id" ] || [ "$fw_id" = "null" ]; then
  hcloud firewall create --name "$FIREWALL"
  for port in 80 443 33101; do
    hcloud firewall add-rule "$FIREWALL" --direction in --protocol tcp --port "$port" \
      --source-ips 0.0.0.0/0 --source-ips ::/0
  done
fi

# Create server.
args="server create --name $SERVER_NAME --type $SERVER_TYPE --image $IMAGE --user-data-from-file $USER_DATA_FILE"

if [ -n "$LOCATION" ]; then
  args="$args --location $LOCATION"
fi

if [ -n "${SSH_KEY:-}" ]; then
  args="$args --ssh-key $SSH_KEY"
fi

args="$args --firewall $FIREWALL"

# shellcheck disable=SC2086
hcloud $args

# Fetch details.
server_json=$(hcloud server describe "$SERVER_NAME" -o json)
server_id=$(echo "$server_json" | jq -r '.id')
ipv4=$(echo "$server_json" | jq -r '.public_net.ipv4.ip')
ipv6=$(echo "$server_json" | jq -r '.public_net.ipv6.ip')

# A new server has new host keys: drop stale known_hosts entries for its
# DNS name and IPs. Not ssh-keygen -R, which refuses to rewrite a known_hosts
# file that contains any old-format ("invalid") lines.
known_hosts="$HOME/.ssh/known_hosts"
if [ -f "$known_hosts" ]; then
  cp "$known_hosts" "$known_hosts.bak"
  awk -v h1="[$HOST_DNS_NAME]:$SSH_PORT" -v h2="[$ipv4]:$SSH_PORT" \
      -v h3="[$ipv6]:$SSH_PORT" -v h4="$ipv4" -v h5="$ipv6" '
    {
      n = split($1, a, ",")
      for (i = 1; i <= n; i++)
        if (a[i] == h1 || a[i] == h2 || a[i] == h3 || a[i] == h4 || a[i] == h5)
          next
      print
    }
  ' "$known_hosts.bak" > "$known_hosts"
fi

vol_id=$(hcloud volume list -o json | jq -r --arg n "$VOLUME_NAME" '.[] | select(.name==$n) | .id' | head -n 1)
if [ -z "$vol_id" ] || [ "$vol_id" = "null" ]; then
  # --server both places the volume and attaches it; automount needs a
  # filesystem, hence --format.
  hcloud volume create --name "$VOLUME_NAME" --size "$VOLUME_SIZE_GB" \
    --server "$server_id" --automount --format ext4
else
  attached_to=$(hcloud volume describe "$vol_id" -o json | jq -r '.server // empty')
  if [ -z "$attached_to" ] || [ "$attached_to" = "null" ]; then
    hcloud volume attach --automount --server "$server_id" "$vol_id"
  fi
fi

cat <<EOF
server:  $SERVER_NAME (id=$server_id)
ipv4:    $ipv4
ipv6:    $ipv6

dns:
  A     $SERVER_NAME -> $ipv4
  AAAA  $SERVER_NAME -> $ipv6

ssh:
  ssh -p 33101 admin@$ipv4

next:
  ssh in and run: cloud-init status --wait
EOF
