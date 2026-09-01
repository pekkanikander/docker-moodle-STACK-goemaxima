#!/bin/sh
# Idempotent authentication configuration; like lang-init.sh/mail-init.sh,
# safe to rerun at any time. Everywhere: OAuth 2 login (Google SSO) is
# enabled and logins never create accounts, they only map to pre-created
# ones; issuer client IDs/secrets live in the Moodle admin UI only (see
# infra/hetzner/DEPLOY.md), never in the repo or .env.
#
# Passwordless local login is decided by the live wwwroot, failing closed in
# both directions:
#   - loopback wwwroot (http://localhost, 127.0.0.1 or [::1]; the compose
#     file publishes on loopback only): auth_none is enabled and the local
#     accounts switch to it with a blank password, so logging in takes a
#     username and an empty password field;
#   - anything else: auth_none is disabled (accounts converted on a loopback
#     instance cannot log in at all), and the run dies if any active account
#     still accepts an empty password.
set -eu

. ./init/scripts/init-env.sh

wwwroot="$(dc exec -T moodle php -r '
  define("CLI_SCRIPT", true);
  require "/var/www/html/config.php";
  echo $CFG->wwwroot;')"

case "$wwwroot" in
  "http://localhost"|"http://localhost:"*|"http://127.0.0.1"|"http://127.0.0.1:"*|"http://[::1]"|"http://[::1]:"*)
    loopback=1 ;;
  *)
    loopback=0 ;;
esac

log "Preventing account creation at login (accounts are pre-created)."
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --name=authpreventaccountcreation --set=1

log "Enabling OAuth 2 login."
dc exec -T moodle php -r '
  define("CLI_SCRIPT", true);
  require "/var/www/html/config.php";
  \core\plugininfo\auth::enable_plugin("oauth2", 1);'

if [ "$loopback" = 1 ]; then
  log "Loopback wwwroot (${wwwroot}): enabling passwordless local login."
  dc exec -T moodle php -r '
    define("CLI_SCRIPT", true);
    require "/var/www/html/config.php";
    \core\plugininfo\auth::enable_plugin("none", 1);
    // auth_none validates the stored hash for existing accounts, so
    // passwordless means auth=none plus a blank password.
    $users = $DB->get_records_select("user",
        "auth IN (?, ?) AND deleted = 0 AND username <> ?",
        ["manual", "none", "guest"]);
    foreach ($users as $user) {
        if ($user->auth !== "none") {
            $DB->set_field("user", "auth", "none", ["id" => $user->id]);
            $user->auth = "none";
        }
        if (!validate_internal_user_password($user, "")) {
            update_internal_user_password($user, "");
        }
        unset_user_preference("auth_forcepasswordchange", $user);
    }'
else
  log "Non-loopback wwwroot (${wwwroot}): ensuring passwordless login is disabled."
  dc exec -T moodle php -r '
    define("CLI_SCRIPT", true);
    require "/var/www/html/config.php";
    \core\plugininfo\auth::enable_plugin("none", 0);
    $open = [];
    foreach ($DB->get_records_select("user", "deleted = 0 AND suspended = 0") as $user) {
        if (validate_internal_user_password($user, "")) {
            $open[] = $user->username;
        }
    }
    if ($open) {
        fwrite(STDERR, "Active accounts accepting an empty password: "
            . implode(", ", $open) . "\n");
        exit(1);
    }'
fi
