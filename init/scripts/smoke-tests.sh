#!/bin/sh
set -eu

. ./init/scripts/init-env.sh

MOODLE_HTTP_PORT="${MOODLE_HTTP_PORT:-8000}"

echo "Checking Moodle HTTP..."
if ! curl -fsS "http://localhost:${MOODLE_HTTP_PORT}/login/index.php" >/dev/null; then
  echo "ERROR: Moodle HTTP check failed at http://localhost:${MOODLE_HTTP_PORT}/login/index.php" >&2
  exit 1
fi

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
