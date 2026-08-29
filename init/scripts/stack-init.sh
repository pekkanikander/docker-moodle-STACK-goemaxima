#!/bin/sh
set -eu

. ./init/scripts/init-env.sh

require_nonempty "MOODLE_STACK_MAXIMAVERSION" "${MOODLE_STACK_MAXIMAVERSION:-}"
require_nonempty "MOODLE_STACK_MAXIMACOMMANDSERVER" "${MOODLE_STACK_MAXIMACOMMANDSERVER:-}"
require_set "MOODLE_STACK_MAXIMACOMMAND"
require_set "MOODLE_STACK_MAXIMACOMMANDOPT"
require_set "MOODLE_STACK_MAXIMALIBRARIES"
require_set "MOODLE_STACK_PLATFORM"

log "Setting STACK configuration."
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=qtype_stack \
  --name=maximaversion \
  --set="${MOODLE_STACK_MAXIMAVERSION}"
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=qtype_stack \
  --name=maximacommand \
  --set="${MOODLE_STACK_MAXIMACOMMAND}"
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=qtype_stack \
  --name=maximacommandopt \
  --set="${MOODLE_STACK_MAXIMACOMMANDOPT}"
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=qtype_stack \
  --name=maximacommandserver \
  --set="${MOODLE_STACK_MAXIMACOMMANDSERVER}"
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=qtype_stack \
  --name=maximalibraries \
  --set="${MOODLE_STACK_MAXIMALIBRARIES}"
dc exec -T moodle php /var/www/html/admin/cli/cfg.php \
  --component=qtype_stack \
  --name=platform \
  --set="${MOODLE_STACK_PLATFORM}"

log "Purging Moodle caches."
dc exec -T moodle php /var/www/html/admin/cli/purge_caches.php

# STACK caches CAS results, including the generated name of each plot file, in
# the database. That name outlives the file, so a cache kept across a rebuilt
# moodledata points questions at images that are gone.
log "Clearing the STACK CAS cache."
dc exec -T moodle php /var/www/html/public/question/type/stack/cli/clearcascache.php

# STACK writes plots that the CAS generated into $CFG->dataroot/stack/plots and
# serves them from there. In server mode nothing creates those directories:
# create_maximalocal() does it, and that is only reached on a local Maxima
# install. Without them the CAS call still succeeds and the image is dropped on
# arrival, so every plot renders as a broken image.
log "Ensuring STACK's dataroot directories."
dc exec -T moodle php -r '
define("CLI_SCRIPT", true);
require "/var/www/html/config.php";
foreach (["stack", "stack/plots", "stack/tmp", "stack/logs"] as $dir) {
  make_upload_directory($dir);
}
'
