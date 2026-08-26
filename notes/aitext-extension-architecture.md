# qtype_aitext drilling extension — architecture note (Task 2, step 1)

Source read: `marcusgreen/moodle-qtype_aitext` @ c45b8d2 (v2.1.0, unreleased —
35 commits past the last tag v2.03), plus `qbehaviour_deferred_for_aitext` and
`qbehaviour_immediate_for_aitext` (hard dependencies since 2.1.0, untagged).
Supports Moodle 4.5–5.2; our 5.1.6 is in range. Baked into the image as
milestone 1; pins in `versions.yml` (commit-SHA archives until upstream tags).

## Corrections to the task brief

- **No cron/async evaluation.** Grading is synchronous: the adapter behaviours
  call `grade_response()` at submit/finish; the student waits for the model
  call. Acceptable for a single learner; `double_run` doubles that wait.
- Backend abstraction confirmed: `perform_request()` uses core
  `core_ai\aiactions\generate_text`; default backend config is
  `core_ai_subsystem`. Works with our `aiprovider_claude`, nothing
  Anthropic-specific needed.
- Partially present already: JSON output is requested and extracted
  (`process_feedback()` / `extract_single_json_object()`), a `disclaimer`
  admin setting with `{{model}}` placeholder exists (Feature 5 ≈ done
  upstream), a prompt tester exists, privacy/backup/PHPUnit/Behat scaffolding
  exists. `perform_request()` returns a canned string under PHPUnit/Behat.
- The gaps that force real surgery: on JSON parse failure the **raw model
  text** is shown as feedback, and the mark is a **holistic model score**
  (`marks` field → fraction). Both violate Feature 1.

## Fork vs companion split

- **Fork `qtype_aitext`** (Features 1, 2, 3, 5). Keep changes additive and
  gated on "rubric present": vanilla questions must behave identically, to
  keep rebases against active upstream (~monthly releases) cheap. Candidate
  upstream PRs: schema-validated JSON with fail-closed rendering; per-question
  disclaimer override.
- **Companion `local_` plugin** (Feature 4, flagging): own table, event,
  capability, Message API notification, index page. The fork's renderer calls
  into it when installed.
- Behaviour plugins vendored unchanged.

## Feature → extension point map

| Feature | Touch points in the fork |
|---|---|
| 1 rubric | New `rubric` JSON column in `qtype_aitext` table (install.xml + upgrade.php), form section in `edit_aitext_form.php`, save/load in `questiontype.php`, backup/restore classes. Prompt build: `build_template_prompt()` emits rubric + JSON-only instruction. Response path: replace `process_feedback()` with schema validation; store the validated JSON (not HTML) in a behaviour var; render with a fixed Mustache template in `renderer.php`. Parse failure → needsgrading + neutral message + auto-flag, never raw text. Mark = weighted criteria sum in `grade_response()`, never the model's number. |
| 2 scaffold | New `scaffold_level` field. Level 1: renderer-only (outline above textarea). Level 0: multiple textareas — changes `get_expected_data()`, `is_complete_response()`, `is_same_response()`, `summarise_response()`; concatenate with markers before grading. Riskiest UI surface (mobile output, response serialisation); last. |
| 3 grading modes | New `grading_mode` field. `double_run`: second `perform_request()` call, render both derived scores. `fuzz`: noise seeded from attempt id. `feedback_only`: gradebook semantics genuinely open — investigate 0-weight vs needsgrading, document choice. |
| 4 flagging | Companion plugin only; button injected from feedback rendering via webservice. Independent of 1–3. |
| 5 framing | Upstream disclaimer + per-question override + non-dismissable styling. Small; do alongside renderer work. |

## Order

1. ~~Bake vanilla plugin into image, verify against `aiprovider_claude`~~
   (milestone 1, done).
2. Fork + companion skeleton on GitHub.
3. Feature 1 → 3 → 4 → 2, with 5 alongside renderer work.
