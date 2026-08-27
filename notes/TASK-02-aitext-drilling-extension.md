# Task 2: Essay-drilling extension on top of qtype_aitext

## Context and intent

Oivus (Moodle-based homeschooling environment) needs a *formative* essay
practice loop — drilling for exam essay writing, explicitly **not** summative
grading. The learner is an autistic student; the design principles below
(criterion-referenced feedback, fixed output format, de-emphasised numeric
marks, honest framing of AI fallibility) are requirements, not suggestions.

Base: Marcus Green's `qtype_aitext`
(https://github.com/marcusgreen/moodle-qtype_aitext, GPL). It already
provides: free-text question type, per-question feedback and grading prompts,
multiple LLM backends including the Moodle core AI subsystem, a prompt tester
in the editing form, and cron-based async evaluation.

Strategy: **fork** (or vendor as a submodule with patches) rather than
reimplement. Where a feature is generic enough, prepare it as an upstreamable
PR; keep Oivus-specific behaviour in the fork or in a small companion
`local_` plugin. Decide and document the split early.

First: read the actual qtype_aitext source at the version compatible with
this repo's Moodle version. Verify which backend modes it supports there and
confirm the core-AI-subsystem path works with our provider (see Task 1). Do
not trust secondhand descriptions of its internals.

## Feature 1 — Criterion-referenced structured feedback

Replace holistic "here is what could be better" output with a fixed checklist
evaluation.

- Per question, the author defines a rubric: an ordered list of criteria,
  each with an id, a short name, a machine-checkable description, and a type
  (`boolean` | `count` | `list`). Store as JSON in a new question field
  (schema + upgrade step).
- The grading prompt instructs the model to return **JSON only**, evaluating
  each criterion and, for every criterion not met, quoting the student's own
  sentence(s) as evidence and giving exactly one concrete "next move" — a
  rewritten sentence or a reordering instruction, not abstract advice.
- Rendering: the model's JSON is validated against a schema and rendered by a
  **fixed Mustache template** — same sections, same order, every time.
  Invalid/unparseable model output → show a neutral "evaluation failed, flag
  sent to teacher" state, never raw model text.
- The numeric mark, when shown at all (see Feature 3), is **derived
  mechanically from the checklist** (weights per criterion), never asked from
  the model as a holistic score.

## Feature 2 — Scaffold-then-fade question levels

A question authoring option `scaffold_level`:

- **Level 0 (full scaffold):** the response area is split into labelled boxes
  (e.g. Claim / Evidence / Counterpoint / Conclusion; labels author-defined,
  reuse the rubric criteria ids where sensible). Implement as multiple
  textareas whose contents are concatenated with markers before evaluation,
  so the rubric can address parts individually.
- **Level 1 (visible skeleton):** single textarea, but the expected structure
  is displayed above it as a static outline.
- **Level 2 (no scaffold):** plain essay box; the rubric silently still
  checks the same structure.

Keep the levels as three configurations of one question type, not three
question types.

## Feature 3 — Grading progression: none → coarse → fine

Question-level setting `grading_mode`:

1. `feedback_only` — no mark recorded/displayed; checklist feedback only.
   (Check how qtype/gradebook handles a 0-weight or ungraded question in a
   quiz; pick the least surprising mechanism and document it.)
2. `coarse` — three levels only (e.g. Needs work / Adequate / Good), derived
   from checklist weights by thresholds.
3. `fine` — percentage mark derived from weights, **plus an unreliability
   display**, one of two author-selectable variants:
   - `fuzz`: add announced random noise (configurable ±N points, seeded per
     attempt for reproducibility) and display: "Score 71 ±8 — the ±8 is
     deliberate: AI marking is not precise."
   - `double_run`: evaluate the submission twice (two model calls) and
     display both derived scores side by side: "Run A: 68, Run B: 74 — the
     difference is real model variance." Costs one extra API call; shows
     genuine rather than artificial uncertainty. Make this the default.

## Feature 4 — "I disagree" / flag-for-teacher button

On the review/feedback display, one button: **"Flag for teacher review"**.

- One click, optional short free-text note (not required — do not force
  explanation).
- Persists a row (new DB table: attempt/question ref, timestamp, note,
  status open/resolved) and sends a Moodle Message API notification to the
  teacher with a deep link to the attempt/question.
- Flagged responses must be visibly marked in the quiz manual grading report
  (or an equivalent list view if hooking that report is impractical — in that
  case add a simple index page in the companion local plugin).
- Log a Moodle event for the flag; add capability
  (`qtype/aitext:flagforreview` or companion-plugin equivalent) granted to
  students by default.

## Feature 5 — Framing

- A standing, non-dismissable short notice rendered with every AI feedback
  block: AI-generated, can be wrong, flag anything that seems off. Author-
  editable site default (admin setting) with per-question override. Keep the
  default text literal and brief; no hedging boilerplate.
- All AI output visually distinguished (existing Moodle AI-content styling
  where available).

## Non-functional requirements

- Provider-agnostic: all model calls go through the core AI subsystem
  `generate_text` action; nothing Anthropic-specific in this plugin.
- Prompts and JSON schemas live in lang-string-free template files under
  version control, overridable per question.
- Privacy API coverage for the new table and for text sent to the provider.
- Backup/restore support for new question fields and the flags table.
- PHPUnit tests: rubric→mark derivation, fuzz determinism per seed,
  JSON-validation failure path, flag lifecycle. Behat for the student flow
  (submit → feedback → flag) if the repo already runs Behat; otherwise note
  as TODO.
- moodle-cs clean; GPL v3 headers.

## Suggested order of work

1. Read qtype_aitext source; write a one-page architecture note mapping each
   feature above to concrete extension points (which functions/classes/
   renderers change; fork vs companion-plugin split).
2. Feature 1 (rubric + JSON + fixed template) — this is the core.
3. Feature 3 (grading modes; `double_run` first, `fuzz` second).
4. Feature 4 (flagging) — independent of 1–3, can be parallelised.
5. Feature 2 (scaffolding UI) — largest UI surface, last.
6. Feature 5 alongside whichever renderer work touches the feedback block.

At step 1, stop and present the architecture note for review before writing
code.

## Known issues (return to these)

- Flag notification does not appear in the bell icon (observed 2026-08-27,
  local manual test). The `notifications` table row is created with correct
  content, so `message_send()` works; the bell UI reads
  `message_popup_notifications`, written by the popup message processor.
  Check whether the popup processor is enabled and whether the failing email
  processor (no MTA in the local container) is implicated. Re-test on the
  server, which has a working MTA.
