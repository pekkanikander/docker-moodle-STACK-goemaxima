#!/bin/sh
set -eu

# Offline tests for infra/hetzner scripts.
# Runs hcloud-create.sh against a stubbed `hcloud` and asserts on the calls
# it makes and on the rendered cloud-init user-data.
#
# Requirements: sh, jq, envsubst, yq. No network, no real hcloud access.

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
script="$repo_root/infra/hetzner/scripts/hcloud-create.sh"
template="$repo_root/infra/hetzner/cloud-init/cloud-init.yml"

for cmd in jq envsubst yq; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "SKIP: missing $cmd" >&2; exit 1; }
done

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# --- hcloud stub -------------------------------------------------------------
mkdir -p "$tmp/bin" "$tmp/state"
cat > "$tmp/bin/hcloud" <<'EOF'
#!/bin/sh
echo "hcloud $*" >> "$HCLOUD_LOG"
case "$1 $2" in
  "server list") echo '[]' ;;
  "server describe") echo '{"id":42,"public_net":{"ipv4":{"ip":"192.0.2.10"},"ipv6":{"ip":"2001:db8::1"}}}' ;;
  "volume list")
    if [ -f "$STATE_DIR/volume_created" ]; then echo '[{"name":"moodle","id":7}]'; else echo '[]'; fi ;;
  "volume create") : > "$STATE_DIR/volume_created" ;;
  "volume describe") echo '{"id":7,"server":null}' ;;
  "firewall list")
    if [ "${FW_EXISTS:-0}" = "1" ] || [ -f "$STATE_DIR/fw_created" ]; then echo '[{"name":"moodle","id":9}]'; else echo '[]'; fi ;;
  "firewall create") : > "$STATE_DIR/fw_created" ;;
  *) : ;;
esac
EOF
chmod +x "$tmp/bin/hcloud"
PATH="$tmp/bin:$PATH"
export STATE_DIR="$tmp/state"

fail() { echo "FAIL: $*" >&2; exit 1; }

run_script() {
  workdir="$1"
  mkdir -p "$workdir"
  ( cd "$workdir" && \
    ADMIN_SSH_PUBKEY="ssh-ed25519 TESTKEY test@example" \
    CLOUD_INIT_TEMPLATE="$template" \
    HCLOUD_LOG="$workdir/hcloud.log" \
    sh "$script" > "$workdir/stdout" 2>&1 ) || {
      cat "$workdir/stdout" >&2
      fail "hcloud-create.sh exited non-zero"
    }
}

# --- Scenario 1: nothing exists yet ------------------------------------------
run_script "$tmp/s1"
log="$tmp/s1/hcloud.log"

# Server is created with explicit type and image.
grep -q -- 'server create --name moodle --type cx23 --image ubuntu-24.04' "$log" \
  || fail "server create lacks --type/--image: $(grep 'server create' "$log")"

# Firewall is created and populated with the three planned inbound rules.
grep -q -- 'firewall create --name moodle' "$log" || fail "firewall not created"
for port in 80 443 33101; do
  grep -q -- "firewall add-rule moodle --direction in --protocol tcp --port $port" "$log" \
    || fail "missing firewall rule for port $port"
done
grep -q -- 'server create .* --firewall moodle' "$log" || fail "firewall not attached"

# Volume is created attached to the server, formatted, with automount.
# (A bare "volume create" without --server/--location is an hcloud error, and
# automount of an unformatted volume cannot work.)
grep -q -- 'volume create --name moodle --size 10 --server 42 --automount --format ext4' "$log" \
  || fail "volume create lacks --server/--automount/--format: $(grep 'volume create' "$log")"
grep -q -- 'volume attach' "$log" && fail "volume attach called although create attached it"

# Rendered user-data: valid YAML, key substituted, correct docker packages.
rendered="$tmp/s1/.generated/cloud-init.rendered.yml"
[ -f "$rendered" ] || fail "rendered cloud-init missing"
yq eval '.' "$rendered" > /dev/null || fail "rendered cloud-init is not valid YAML"
grep -q 'ssh-ed25519 TESTKEY' "$rendered" || fail "SSH key not substituted into user-data"
yq eval -r '.packages[]' "$rendered" | grep -qx 'docker-compose-v2' \
  || fail "docker-compose-v2 package missing"
yq eval -r '.packages[]' "$rendered" | grep -qx 'docker-compose-plugin' \
  && fail "docker-compose-plugin is not an Ubuntu package"

# --- Scenario 2: firewall and a detached volume already exist ----------------
rm -f "$STATE_DIR/fw_created"
export FW_EXISTS=1
: > "$STATE_DIR/volume_created"
run_script "$tmp/s2"
grep -q -- 'firewall create' "$tmp/s2/hcloud.log" && fail "firewall re-created although it exists"
grep -q -- 'server create .* --firewall moodle' "$tmp/s2/hcloud.log" || fail "existing firewall not attached"
grep -q -- 'volume create' "$tmp/s2/hcloud.log" && fail "volume re-created although it exists"
grep -q -- 'volume attach --automount --server 42 7' "$tmp/s2/hcloud.log" || fail "existing detached volume not attached"

# --- Scenario 3: ssh-keygen.sh replaces a stale Host block --------------------
sshtest="$tmp/ssh"
mkdir -p "$sshtest/.ssh"
cat > "$sshtest/.ssh/config" <<'EOF'
Host other-box
   HostName other.example.org

Host moodle-hetzner
   Hostname 198.51.100.99
   Port 33101
   PreferredAuthentications publickey
   IdentityFile /old/key/path

Host tail-box
   HostName tail.example.org
EOF
HOME="$sshtest" HOSTNAME=oivus.example.test \
  sh "$repo_root/infra/hetzner/scripts/ssh-keygen.sh" > /dev/null 2>&1 \
  || fail "ssh-keygen.sh exited non-zero"
cfg="$sshtest/.ssh/config"
grep -q '198.51.100.99' "$cfg" && fail "stale Hostname survived block replacement"
grep -q '/old/key/path' "$cfg" && fail "stale IdentityFile survived block replacement"
[ "$(grep -c '^Host moodle-hetzner' "$cfg")" = "1" ] || fail "expected exactly one moodle-hetzner block"
grep -q '   HostName oivus.example.test' "$cfg" || fail "new HostName missing"
grep -q '   User admin' "$cfg" || fail "User line missing"
grep -q 'HostName other.example.org' "$cfg" || fail "unrelated host block damaged"
grep -q 'HostName tail.example.org' "$cfg" || fail "following host block damaged"

echo "OK: infra tests passed"
