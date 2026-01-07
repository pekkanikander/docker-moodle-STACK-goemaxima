#!/bin/sh
set -eu

. ./init/scripts/init-env.sh

MOODLE_HTTP_PORT="${MOODLE_HTTP_PORT:-8080}"

echo "Checking Moodle HTTP..."
if ! curl -fsS "http://localhost:${MOODLE_HTTP_PORT}/login/index.php" >/dev/null; then
  echo "ERROR: Moodle HTTP check failed at http://localhost:${MOODLE_HTTP_PORT}/login/index.php" >&2
  exit 1
fi

echo "Checking STACK plugin registration..."
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
foreach (["dfexplicitvaildate", "dfcbmexplicitvaildate", "adaptivemultipart"] as $p) {
  if (!isset($qb[$p])) {
    $errors[] = "qbehaviour_" . $p . " not registered. Found behaviours: " . implode(", ", array_keys($qb));
  }
}
if ($errors) {
  fwrite(STDERR, implode("\n", $errors) . "\n");
  exit(1);
}
'

echo "Checking STACK settings and noreply address..."
dc exec -T moodle php -r '
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
