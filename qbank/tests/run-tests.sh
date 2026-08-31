#!/bin/sh
set -eu

# Tests for the question compiler. They run inside the qbank-tools container,
# which is where the pinned PyYAML lives, against qbank/fixtures; nothing
# outside the container is written and no Moodle is needed.

cd "$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
. ./init/scripts/init-env.sh

# The service bind-mounts the build directory; without this Docker creates it
# root-owned and later runs cannot write into it.
mkdir -p "${QBANK_BUILD_DIR:-./.generated/qbank}"

dc build qbank-tools
for test in test_provenance.py test_figures.py test_mcq.py test_hints.py; do
  dc run --rm --user "$(id -u):$(id -g)" --entrypoint python3 qbank-tools \
    "/opt/qbank/tests/$test"
done
