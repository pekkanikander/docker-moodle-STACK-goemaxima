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

# One run at a time per stack. Two runs against one Moodle wreck each other in
# ways that do not look like contention: concurrent bulktestall.php runs abort
# at a moving point with an "Error writing to database" that is not real, and
# concurrent imports race on the same bank and the same build directory. The
# key is the compose project, i.e. the stack the 'dc' calls talk to, so a run
# elsewhere against another stack is not blocked.
lockdir="${TMPDIR:-/tmp}"
lockdir="${lockdir%/}/qbank-${COMPOSE_PROJECT_NAME:-$(basename "$(pwd)")}.lock"

lock() {
  if ! mkdir "$lockdir" 2>/dev/null; then
    holder="$(cat "${lockdir}/owner" 2>/dev/null || true)"
    pid="${holder#pid }"
    pid="${pid%%,*}"
    # Only a demonstrably dead owner makes the lock stale. An owner we cannot
    # read is one that has claimed the directory but not yet written itself
    # into it, so it counts as live: breaking that lock would let exactly the
    # two runs this guards against proceed together.
    if [ -z "$holder" ] || kill -0 "$pid" 2>/dev/null; then
      die "Another qbank run holds the lock: ${holder:-owner not yet recorded}.
Wait for it to finish, or kill it. If nothing is running, remove ${lockdir}."
    fi
    log "Clearing a stale qbank lock left by ${holder}."
    rm -rf "$lockdir"
    mkdir "$lockdir" || die "Cannot create the lock directory ${lockdir}."
  fi
  # Cleanup hangs off EXIT. INT and TERM have to be caught as well and turned
  # into an exit, because a shell killed by an untrapped signal runs no EXIT
  # trap at all under dash, which is the /bin/sh this gets in CI.
  trap 'rm -rf "$lockdir"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  echo "pid $$, '${command}', started $(date '+%Y-%m-%d %H:%M:%S')" >"${lockdir}/owner"
}

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

# Figures are rendered per attempt, not stored: the gate is a render of every
# figure question at every deployed seed, checking the images actually exist.
figuretests() {
  dc exec -T moodle php /opt/qbank/cli/figure-test.php \
    --manifest=/opt/qbank-build/manifest.json \
    --course="$QBANK_COURSE" \
    --bank="$QBANK_BANK"
}

command="${1:-all}"
[ $# -gt 0 ] && shift

lock

case "$command" in
  compile) compile ;;
  import) import "$@" ;;
  quizzes) quizzes ;;
  test) questiontests; figuretests ;;
  aitest) aitest "$@" ;;
  all)
    compile
    import
    quizzes
    questiontests
    figuretests
    ;;
  *)
    echo "Usage: $0 [compile|import|quizzes|test|aitest|all]" >&2
    exit 1
    ;;
esac
