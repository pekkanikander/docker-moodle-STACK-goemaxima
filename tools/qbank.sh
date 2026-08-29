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
if [ ! -w "$QBANK_BUILD_DIR" ]; then
  die "QBANK_BUILD_DIR is not writable: ${QBANK_BUILD_DIR}
Likely created root-owned by 'docker compose up'; remove it and rerun."
fi

# Provenance of a build: the content commit is what an attempt is traced back
# to, and the compiler commit is what turned that source into the XML Moodle
# stores. Git lives here, on the host; the compiler runs in a container that
# sees only the two mounted trees, so the commits are passed in to it.
git_commit() {
  git -C "$1" rev-parse --verify HEAD 2>/dev/null || true
}

# Uncommitted or untracked changes both count: an untracked question file is
# compiled into the build just the same, and neither is described by the SHA.
git_dirty_flag() {
  if [ -n "$(git -C "$1" status --porcelain 2>/dev/null)" ]; then
    echo "$2"
  fi
}

compile() {
  dc build qbank-tools
  # The container writes into the build directory; make it do so as us, not root.
  dc run --rm --user "$(id -u):$(id -g)" qbank-tools \
    --source /opt/qbank-content \
    --out /opt/qbank-build \
    --stack-version "${STACK_MAXIMA_VERSION}" \
    --content-commit "$(git_commit "$QBANK_CONTENT_DIR")" \
    --compiler-commit "$(git_commit .)" \
    $(git_dirty_flag "$QBANK_CONTENT_DIR" --content-dirty) \
    $(git_dirty_flag . --compiler-dirty)
}

# A build made from a dirty tree is fine to iterate against locally, where
# attempts are throwaway, and is refused anywhere else: a commit that does not
# describe what was compiled is worse than none, because it will be believed.
# QBANK_ALLOW_DIRTY=1 waives that for another throwaway site, e.g. under `act`.
import() {
  allowdirty=""
  case "${MOODLE_SITE_URL:-}" in
    ""|http://localhost*|http://127.0.0.1*) allowdirty="--allow-dirty" ;;
  esac
  if [ "${QBANK_ALLOW_DIRTY:-0}" = "1" ]; then
    allowdirty="--allow-dirty"
  fi

  dc exec -T moodle php /opt/qbank/cli/import-questions.php \
    --source=/opt/qbank-build/questions \
    --manifest=/opt/qbank-build/manifest.json \
    --course="$QBANK_COURSE" \
    --course-fullname="$QBANK_COURSE_FULLNAME" \
    --bank="$QBANK_BANK" \
    --bank-name="$QBANK_BANK_NAME" \
    $allowdirty \
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

# Golden tests of aitext questions through the real AI pipeline. Costs API
# money (one model call per test) and needs a working AI provider; run on
# demand, not part of 'all'.
aitest() {
  dc exec -T moodle php /opt/qbank/cli/aitext-test.php "$@"
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
  aitest) aitest "$@" ;;
  all)
    compile
    import
    quizzes
    questiontests
    ;;
  *)
    echo "Usage: $0 [compile|import|quizzes|test|aitest|all]" >&2
    exit 1
    ;;
esac
