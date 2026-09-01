#!/bin/sh
set -eu

. ./init/scripts/init-env.sh

MOODLE_HTTP_PORT="${MOODLE_HTTP_PORT:-8000}"

echo "Checking Moodle HTTP..."
if ! curl -fsS "http://localhost:${MOODLE_HTTP_PORT}/login/index.php" >/dev/null; then
  echo "ERROR: Moodle HTTP check failed at http://localhost:${MOODLE_HTTP_PORT}/login/index.php" >&2
  exit 1
fi
if ! curl -fsS "http://[::1]:${MOODLE_HTTP_PORT}/login/index.php" >/dev/null; then
  echo "ERROR: Moodle HTTP check failed at http://[::1]:${MOODLE_HTTP_PORT}/login/index.php" >&2
  exit 1
fi

echo "Checking published ports bind loopback only..."
for cid in $(dc ps -q); do
  if docker port "$cid" | grep -E '0\.0\.0\.0|\[::\]'; then
    echo "ERROR: container $(docker inspect -f '{{.Name}}' "$cid") publishes a wildcard listener." >&2
    exit 1
  fi
done

echo "Checking STACK, aitext and AI provider plugin registration..."
dc exec -T moodle php -r '
define("CLI_SCRIPT", true);
require "/var/www/html/config.php";
require_once "$CFG->dirroot/lib/classes/component.php";
$errors = [];
$qt = core_component::get_plugin_list("qtype");
if (!isset($qt["stack"])) {
  $errors[] = "qtype_stack not registered. Found qtypes: " . implode(", ", array_keys($qt));
}
$qb = core_component::get_plugin_list("qbehaviour");
foreach (["dfexplicitvaildate", "dfcbmexplicitvaildate", "adaptivemultipart", "deferred_for_aitext", "immediate_for_aitext"] as $p) {
  if (!isset($qb[$p])) {
    $errors[] = "qbehaviour_" . $p . " not registered. Found behaviours: " . implode(", ", array_keys($qb));
  }
}
if (!isset($qt["aitext_rubric"])) {
  $errors[] = "qtype_aitext_rubric not registered. Found qtypes: " . implode(", ", array_keys($qt));
} else if (!get_config("qtype_aitext_rubric", "version")) {
  $errors[] = "qtype_aitext_rubric files present but not installed in the DB; run admin/cli/upgrade.php";
}
$local = core_component::get_plugin_list("local");
if (!isset($local["aitextflags"])) {
  $errors[] = "local_aitextflags not registered. Found local plugins: " . implode(", ", array_keys($local));
} else if (!get_config("local_aitextflags", "version")) {
  $errors[] = "local_aitextflags files present but not installed in the DB; run admin/cli/upgrade.php";
}
$qbank = core_component::get_plugin_list("qbank");
if (!isset($qbank["importasversion"])) {
  $errors[] = "qbank_importasversion not registered. Found qbank plugins: " . implode(", ", array_keys($qbank));
}
$ai = core_component::get_plugin_list("aiprovider");
if (!isset($ai["claude"])) {
  $errors[] = "aiprovider_claude not registered. Found aiproviders: " . implode(", ", array_keys($ai));
} else if (!get_config("aiprovider_claude", "version")) {
  $errors[] = "aiprovider_claude files present but not installed in the DB; run admin/cli/upgrade.php";
}
if ($errors) {
  fwrite(STDERR, implode("\n", $errors) . "\n");
  exit(1);
}
'

echo "Checking STACK settings, noreply address and languages..."
dc exec -T -e EXPECTED_LANG="${MOODLE_LANG:-en}" -e EXPECTED_LANGPACKS="${MOODLE_LANGPACKS:-}" moodle php -r '
define("CLI_SCRIPT", true);
require "/var/www/html/config.php";
$errors = [];
$cfg = get_config("qtype_stack");
$required = ["maximaversion", "maximacommandserver"];
foreach ($required as $key) {
  if (!isset($cfg->$key) || $cfg->$key === "") {
    $errors[] = "qtype_stack/" . $key . " is empty";
  }
}
$expected = ["maximacommand", "maximacommandopt", "maximalibraries"];
foreach ($expected as $key) {
  if (!property_exists($cfg, $key)) {
    $errors[] = "qtype_stack/" . $key . " is unset";
  }
}
foreach (["stack/plots", "stack/tmp"] as $dir) {
  if (!is_dir("$CFG->dataroot/$dir") || !is_writable("$CFG->dataroot/$dir")) {
    $errors[] = $dir . " is missing or not writable; CAS-generated plots would be dropped on arrival";
  }
}
$noreply = get_config("core", "noreplyaddress");
if (!$noreply) {
  $errors[] = "core/noreplyaddress is empty";
}
$lang = get_config("core", "lang");
if ($lang !== getenv("EXPECTED_LANG")) {
  $errors[] = "core/lang is " . var_export($lang, true) . ", expected " . getenv("EXPECTED_LANG");
}
if (!get_config("core", "autolang")) {
  $errors[] = "core/autolang is off; browser language autodetect will not work";
}
foreach (preg_split("/[\s,]+/", trim(getenv("EXPECTED_LANGPACKS")), -1, PREG_SPLIT_NO_EMPTY) as $code) {
  if ($code !== "en" && !is_dir("$CFG->dataroot/lang/$code")) {
    $errors[] = "language pack " . $code . " is not installed";
  }
}
if ($errors) {
  fwrite(STDERR, implode("\n", $errors) . "\n");
  exit(1);
}
'

echo "Checking authentication posture..."
dc exec -T moodle php -r '
define("CLI_SCRIPT", true);
require "/var/www/html/config.php";
$errors = [];
if (empty($CFG->authpreventaccountcreation)) {
  $errors[] = "authpreventaccountcreation is off; an IdP login could create an account";
}
if (!empty($CFG->registerauth)) {
  $errors[] = "registerauth is set; self-registration must stay off";
}
if (get_config("core", "guestloginbutton")) {
  $errors[] = "guest login button is not hidden";
}
$enabled = get_enabled_auth_plugins();
if (!in_array("oauth2", $enabled)) {
  $errors[] = "auth_oauth2 is not enabled; run auth-init.sh";
}
$loopback = (bool) preg_match("~^http://(localhost|127\\.0\\.0\\.1|\\[::1\\])(:\\d+)?$~", $CFG->wwwroot);
if ($loopback) {
  if (!in_array("none", $enabled)) {
    $errors[] = "auth_none is not enabled on loopback wwwroot; run auth-init.sh";
  }
} else {
  if (in_array("none", $enabled)) {
    $errors[] = "auth_none (passwordless) is enabled on non-loopback wwwroot " . $CFG->wwwroot;
  }
  foreach ($DB->get_records_select("user", "deleted = 0 AND suspended = 0") as $user) {
    if (validate_internal_user_password($user, "")) {
      $errors[] = "account " . $user->username . " accepts an empty password on non-loopback wwwroot";
    }
  }
}
if ($errors) {
  fwrite(STDERR, implode("\n", $errors) . "\n");
  exit(1);
}
'

# Functional check of passwordless local login (loopback wwwroot only): the
# blank-password mechanism must keep working across Moodle bumps.
case "${MOODLE_SITE_URL:-}" in
  "http://localhost"|"http://localhost:"*|"http://127.0.0.1"|"http://127.0.0.1:"*|"http://[::1]"|"http://[::1]:"*)
    echo "Checking passwordless login..."
    login_url="http://localhost:${MOODLE_HTTP_PORT}/login/index.php"
    jar="$(mktemp)"
    token="$(curl -fsS -c "$jar" "$login_url" \
      | sed -n 's/.*name="logintoken" value="\([^"]*\)".*/\1/p' | head -n 1)"
    if [ -z "$token" ]; then
      echo "ERROR: could not extract a logintoken from ${login_url}" >&2
      exit 1
    fi
    final="$(curl -fsS -b "$jar" -c "$jar" -L -o /dev/null -w '%{url_effective}' \
      --data-urlencode "username=${MOODLE_ADMIN_USER:-admin}" \
      --data-urlencode "password=" \
      --data-urlencode "logintoken=${token}" \
      "$login_url")"
    rm -f "$jar"
    case "$final" in
      *"/login/"*)
        echo "ERROR: passwordless login as ${MOODLE_ADMIN_USER:-admin} failed (landed on ${final})." >&2
        exit 1
        ;;
    esac
    ;;
esac

# Only when Moodle sends to the bundled Mailpit (local/CI); production
# points smtphosts at a real relay, which this check cannot inspect.
if [ "${MOODLE_SMTPHOSTS:-}" = "mailpit:1025" ]; then
  echo "Checking outgoing mail via Mailpit..."
  subject="smoke-$(date +%s)-$$"
  dc exec -T -u www-data -e SMOKE_SUBJECT="$subject" moodle php -r '
  define("CLI_SCRIPT", true);
  require "/var/www/html/config.php";
  $ok = email_to_user(get_admin(), core_user::get_noreply_user(),
      getenv("SMOKE_SUBJECT"), "Outgoing mail smoke test.");
  exit($ok ? 0 : 1);
  '
  if ! curl -fsS "http://localhost:${MAILPIT_HTTP_PORT:-8025}/api/v1/search?query=subject:${subject}" \
      | grep -q "$subject"; then
    echo "ERROR: message '${subject}' not found in Mailpit" >&2
    exit 1
  fi
fi

echo "Checking goemaxima endpoint..."
if dc exec -T moodle curl -fsS http://maxima:8080/goemaxima >/dev/null; then
  exit 0
fi
if dc exec -T moodle curl -fsS http://maxima:8080/maxima >/dev/null; then
  echo "WARN: goemaxima responded at /maxima instead of /goemaxima" >&2
  exit 0
fi
echo "ERROR: goemaxima not reachable at /goemaxima or /maxima" >&2
exit 1
