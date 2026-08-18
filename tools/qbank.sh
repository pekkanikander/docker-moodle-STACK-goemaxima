#!/bin/sh
# Compile question sources and push them into the running Moodle stack.
#
# The content lives in its own repository; point QBANK_CONTENT_DIR at a checkout
# of it. Without that, the test fixtures in qbank/fixtures are used.
set -eu

. ./init/scripts/init-env.sh

QBANK_CONTENT_DIR="${QBANK_CONTENT_DIR:-./qbank/fixtures}"
QBANK_BUILD_DIR="${QBANK_BUILD_DIR:-./.generated/qbank}"
QBANK_COURSE="${QBANK_COURSE:-qbank}"
QBANK_COURSE_FULLNAME="${QBANK_COURSE_FULLNAME:-Question bank}"
QBANK_BANK="${QBANK_BANK:-qbank-main}"
QBANK_BANK_NAME="${QBANK_BANK_NAME:-Question bank}"
export QBANK_CONTENT_DIR QBANK_BUILD_DIR

if [ ! -d "$QBANK_CONTENT_DIR" ]; then
  die "QBANK_CONTENT_DIR does not exist: ${QBANK_CONTENT_DIR}"
fi
mkdir -p "$QBANK_BUILD_DIR"

compile() {
  dc build qbank-tools
  # The container writes into the build directory; make it do so as us, not root.
  dc run --rm --user "$(id -u):$(id -g)" qbank-tools \
    --source /opt/qbank-content \
    --out /opt/qbank-build \
    --stack-version "${STACK_MAXIMA_VERSION}"
}

import() {
  dc exec -T moodle php /opt/qbank/cli/import-questions.php \
    --source=/opt/qbank-build/questions \
    --course="$QBANK_COURSE" \
    --course-fullname="$QBANK_COURSE_FULLNAME" \
    --bank="$QBANK_BANK" \
    --bank-name="$QBANK_BANK_NAME" \
    "$@"
}

quizzes() {
  specs="$(find "${QBANK_BUILD_DIR}/quizzes" -name '*.json' 2>/dev/null | sort)"
  if [ -z "$specs" ]; then
    log "No quiz specs to build."
    return 0
  fi
  for spec in $specs; do
    dc exec -T moodle php /opt/qbank/cli/build-quiz.php \
      --spec="/opt/qbank-build/quizzes/$(basename "$spec")" \
      --course="$QBANK_COURSE" \
      --bank="$QBANK_BANK"
  done
}

# bulktestall always exits 0, so the verdict has to come from its output.
questiontests() {
  out="$(dc exec -T moodle php public/question/type/stack/cli/bulktestall.php)"
  echo "$out"
  case "$out" in
    *'Not all tests passed!'*) die "STACK question tests failed." ;;
  esac
}

command="${1:-all}"
[ $# -gt 0 ] && shift

case "$command" in
  compile) compile ;;
  import) import "$@" ;;
  quizzes) quizzes ;;
  test) questiontests ;;
  all)
    compile
    import
    quizzes
    questiontests
    ;;
  *)
    echo "Usage: $0 [compile|import|quizzes|test|all]" >&2
    exit 1
    ;;
esac
