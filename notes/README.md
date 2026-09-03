# notes/

Three kinds of document live here, and only two of them persist.

- **Task briefs** (`TASK-NN-*.md`) are transient. A brief specifies one piece
  of work, accretes status as it is done, and is then retired: whatever in it
  would otherwise have to be rediscovered moves into `LESSONS-LEARNED.md`, the
  authoring-facing parts move into `qbank/README.md` or the relevant runbook,
  and the brief is deleted. Git history keeps the original. TASK-01…TASK-07
  were retired this way at v0.2.0.
- **Surveys** persist. A survey records what was investigated and *rejected*,
  with the conditions under which the question should be reopened. That value
  does not decay with the code.
- **`LESSONS-LEARNED.md`** persists: decisions with their rejected
  alternatives, and platform facts read out of the Moodle and STACK source.
  The facts are pinned to a version tuple and need re-verifying when
  `versions.yml` moves.

Rationale for settled decisions belongs in code comments, in `versions.yml`,
or here in `LESSONS-LEARNED.md` — not scattered through retired briefs.

## Contents

- [`LESSONS-LEARNED.md`](LESSONS-LEARNED.md) — why the machinery is the way it
  is, and what was verified about the platform to get there.
- [`ai-grading-walkthrough.md`](ai-grading-walkthrough.md) — one student answer
  traced from submit to feedback, naming every file on the way. Start here to
  understand the AI grading path.
- [`aiprovider-survey.md`](aiprovider-survey.md) — choosing an Anthropic
  provider for the Moodle AI subsystem (2026-08).
- [`sso-apple-survey.md`](sso-apple-survey.md) — why Sign in with Apple is
  deferred, and what would reopen it (2026-09).
