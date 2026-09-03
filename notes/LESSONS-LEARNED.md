# Lessons learned

Distilled from the TASK-01…TASK-07 briefs when they were retired at v0.2.0
(2026-09-03). The briefs themselves are in git history; what is kept here is
what would otherwise have to be rediscovered.

Two sections, with different shelf lives:

- **Decisions** are durable. They record what was chosen *and what was
  rejected*, so a settled question is not reopened for free.
- **Verified platform facts** were read out of the Moodle and STACK source at
  the pinned tuple below. They expire when the pins move; re-verify rather
  than trust.

---

## Decisions and rejected alternatives

### AI grading

- **Provider: contributed `aiprovider_claude`**, baked into the image and
  pinned like the STACK plugins. Amazon Bedrock rejected (a second cloud
  vendor, IAM and model-access grants, a Claude catalogue that lags
  Anthropic's own API); the OpenAI-compatibility endpoint rejected (Anthropic
  itself calls it a test facility, not production). Full reasoning, including
  the runner-up and the provider's known gaps, in
  [`aiprovider-survey.md`](aiprovider-survey.md).
- **All model calls go through the core AI subsystem**, never to a vendor
  directly. Swapping providers is then a configuration change and the question
  type does not move. This is why the provider was settled before the
  question type was touched.
- **The mark is computed in PHP from validated criterion levels, never taken
  from the model's prose.** Asking a model for a holistic score was the
  upstream behaviour and is exactly what a formative drilling loop must not
  do.
- **Fail closed, three ways.** A rubric that will not parse (author error), a
  provider call that throws (network), and a model reply that fails schema or
  evidence validation (model) all land on the same exit: mark 0,
  `needsgrading`, one neutral localised string. **Raw model output is never
  shown to the student.** Nothing is repaired; a violation throws.
- **Evidence quotes must be verbatim substrings of the student's answer**
  (after whitespace collapse, case folding and quote straightening). This is
  the cheap prompt-injection tripwire: an instruction-following derailment
  tends to break it, which routes the attempt to the fail-closed path.
- **Fork/companion split.** Presentational and grading changes live in the
  question-type fork, gated on "rubric present" so vanilla questions behave
  identically and rebases against active upstream stay cheap. Workflow state —
  the flag-for-teacher table, event, capability and notification — lives in a
  companion `local_` plugin, which the fork's renderer calls into when
  installed. The fork later became a separate component,
  `qtype_aitext_rubric`, which is why it needs the two behaviour forks: the
  upstream adapters pinned themselves to `qtype_aitext` by name.
- **Flags-table backup deliberately omitted** — transient workflow data;
  rationale in the companion's README.

### Question bank

- **Drilling is a property of the quiz, not of the question.** One source
  serves exam and drill; a question is never forked into two copies that drift
  apart. This is what the hint mechanism had to be chosen to preserve (see the
  `interactive` fact below).
- **Genuine spaced repetition (Leitner, SM-2) is out of scope.** Not in Moodle
  core; it would need a plugin. Recorded so it is not rediscovered as an idea.
- **Figures: static SVG, base64-embedded as a `<file>` and referenced via
  `@@PLUGINFILE@@`.** Inline `<svg>` rejected: it survives only the question
  render path, which sets `noclean`, and dies wherever the same text is
  cleaned. JSXGraph rejected: with the content rule below the diagram is
  static, so its one advantage does not apply, and a JavaScript dependency in
  the exam render path fails in a way the student cannot diagnose.
- **Content rule: the schematic goes in the figure, the numbers go in the
  prose.** A circuit labelled R1, R2, U with values in the stem is what real
  exam papers do. It is also what makes every schematic figure genuinely
  static, so no diagram generator is needed.
- **MCQ on STACK `radio`, not core `qtype_multichoice`.** Multichoice would add
  a second import and validation path and lose the question-test gate
  entirely.
- **Pooled MCQs: one static question test for the correct key** (always shown);
  distractor key → answer note → `why:` is covered by compiler unit tests
  instead. Per-distractor Maxima tests are impossible under a pool — the test
  input can be computed per variant but the *expected answer note* is static,
  and the note is exactly what varies. Unpooled MCQs keep full per-option
  tests. `qbank/README.md` states what the gate does and does not cover.
- **Provenance by question tag plus a build manifest, with no new database
  table.** A table means a plugin, an install/upgrade path and a restore
  concern, for what is a few strings. Question tags attach to `question.id`,
  i.e. to the version, which is exactly the object an attempt points at.

### Operations

- **Backups: the GitHub repos are the source of truth and Moodle state is
  expendable.** The response to suspected compromise is rebuild-from-scratch
  plus a weekly dump predating the suspicion, not forensics. Append-only
  archives and dump baselining/diffing were rejected as disproportionate.
  Stance recorded in `infra/BACKUP.md`.
- **fail2ban rejected.** With key-only auth on a firewalled non-default port it
  is log-noise reduction only, at the cost of a daemon and its own nftables
  machinery on a host with no local firewall. The built-in replacement is
  OpenSSH `PerSourcePenalties` (≥ 9.8; see ROADMAP "Version watch").
- **Sign in with Apple deferred.** Moodle 5.1 core cannot complete an Apple
  login — verified in source, not folklore. Revisit triggers in
  [`sso-apple-survey.md`](sso-apple-survey.md), to be checked at each Moodle
  version bump.
- **DNS automation rejected.** An easyDNS API integration would not be portable
  for anyone forking this repo; DNS stays a documented manual step.
- **OAuth client credentials may live in `.env`** (gitignored, per-machine) so
  `auth-init.sh` can converge the issuer. The Anthropic API key and the SMTP
  password stay admin-UI-only; "no secrets in the repo" is unchanged.

---

## Verified platform facts

Read from source against **Moodle 5.1.6 / STACK 4.13.0 / goemaxima
2026062900-1.2.0**, Aug–Sep 2026. Re-verify when `versions.yml` moves.

### Hints and behaviours

- **Only the `interactive` behaviour reads hints.** `get_applicable_hint()` is
  called from `question/behaviour/interactive/behaviour.php` and nowhere else
  under `question/behaviour/`. A question carrying hints therefore renders
  byte-identically under `deferredfeedback`, `adaptive`, `adaptivenopenalty`
  and `immediatefeedback`. **This is the fact that makes one shared source safe
  for both exams and drills.**
- **Tries = hints + 1** (`behaviour.php:150` sets `_triesleft`). The hint count
  *is* the try count, so it is an authoring decision, not a config.
- **STACK renders hints as CASText** — `renderer.php` overrides `hint()` and
  evaluates it in the question's Maxima session, so `{@dv@}` interpolates and a
  hint is correct for whichever variant was drawn. Hints are validated on
  import like any other CASText, but are *not* covered by question tests.
- **STACK imports hint text only.** `import_hints(..., withparts: false,
  withoptions: false)` — so `shownumcorrect` and `clearwrong` must not be
  emitted; they would be silently dropped.
- **Hints and per-part grading are mutually exclusive.**
  `qtype_stack_question::make_behaviour()` swaps in `adaptivemultipart` only
  for `adaptive` and `adaptivenopenalty`. Under `interactive` a multi-PRT
  question grades as one unit: for a two-input `choice` question the reading
  and the answer stop being independently graded. One PRT (`stated`, `none`)
  loses nothing. The escape hatch, if the pacing ever proves wrong, is STACK's
  `[[hint]]` reveal block, which works in any behaviour and even inside PRT
  feedback — at the cost of putting the text in the page source everywhere the
  question id is used, exams included.
- **STACK's validation step is free.** `process_submit()` marks an incomplete
  response `invalid` *before* decrementing `_triesleft`, so the extra *Check*
  press that `mustverify: 1` inputs require does not consume a try.

### Figures and plots

- **`$CFG->dataroot/stack/` is never created in server mode.** Only
  `create_maximalocal()` creates it, and that is reached only on a local Maxima
  install. The connector wrote every CAS-generated plot into a directory that
  was not there, silently — so every plot rendered as a broken image, on both
  local and staging, for as long as it took to find. `stack-init.sh` now
  creates the directories and **clears the CAS cache**, which holds plot
  filenames that outlive the files; `smoke-tests.sh` asserts they are writable.
- **Plot filenames are non-deterministic** (`rand(10^8)`), so an image is a
  per-render artefact in moodledata: nothing to version, and nothing a test can
  pin. A test can assert the CAS produced an image without error; visual
  correctness stays a human preview step.
- **`PLOT_TERM_OPT` is a question's only hook into gnuplot's preamble** — STACK
  splices it verbatim into the `set terminal` line. That is where
  `set decimalsign ","` goes, to stop an axis reading `2.5` next to a stem
  reading `2,5`. It depends on an internal STACK setting name, so the fragility
  is converted into a test: the figure gate fails if a tick label comes back
  with a decimal point.
- **STACK's default plot alt text is unusable** — an English string
  concatenated with a dump of the Maxima expression. Author-supplied alt text
  is mandatory in the compiler for this reason.

### Multiple choice and random slots

- **STACK `radio` has no native shuffling, and quiz-level `shuffleanswers` is
  ignored by STACK.** All randomisation is what the author writes in question
  variables — `random_permutation()` for order, `rand_selection(L, n)` for the
  subset draw. Both are seed-dependent, which is why `seeds:` is required iff
  `shuffle` or `show`.
- **Where the chosen option is actually recorded.** Raw step data
  (`question_attempt_step_data`) stores the *positional* index under `ans1`,
  plus `_seed` on the first step. The key *string* appears in
  `question_attempts.responsesummary` on finished attempts, as
  `ans1: "key" [score]` followed by the PRT answer note. So seed, chosen key
  and answer note are all recoverable per attempt; the bare index decodes via
  the seed, provided the question note pins the shown set and order.
- **Random slots:** `\mod_quiz\structure::add_random_questions($addonpage,
  $number, $filtercondition)`, persisted in `question_set_references`. Tag
  filtering works via key `qtagids`, AND-joined; tag-only pools ride on the
  bank's top category with `includesubcategories: true`. Slots insert with
  maxmark 1; other marks are set afterwards. Each attempt draws a question not
  already used in that attempt, and an exhausted pool throws
  `notenoughrandomquestions` — hence the build-time pool check.

### Versioning and provenance

- **Moodle already binds an attempt to an exact question version.**
  `question_attempts.questionid` → `question.id`, and `question_versions` maps
  `(questionbankentryid, version)`; old rows are retained. The wording a
  student saw is recoverable from the database alone, and
  `question_attempts.variant` recovers the seed. Provenance only had to add the
  link *out* to the content repo, not the version history itself.
- **The trap:** a provenance stamp inside the change-detection hash makes every
  content commit re-import every question and spawn a spurious Moodle version
  for each — turning a fix for version tracking into a generator of meaningless
  versions. The stamp is excluded from the hash, and the hash is taken over the
  YAML source rather than the compiled artefact.

### Core AI subsystem

- **The naming convention is the registry.** `manager::process_action()` builds
  the processor class name as a string — provider namespace + `process_` +
  action base name → `aiprovider_claude\process_generate_text` — and
  instantiates it. There is no registration step to look for.
- **Failure telemetry is flat.** A failed action gives the caller
  `errorcode: -1` and a generic string, whatever actually went wrong: no
  provider enabled, bad key, HTTP 500. The real reason is in
  `mdl_ai_action_register` and the provider log, not in the exception. We lost
  time to a provider instance that existed but had `enabled=0`, and nothing in
  the surfaced error said so. **Check that table first.**
- **Provider credentials live in `mdl_ai_providers`**, written by the admin UI:
  JSON `config` (API key, rate limits) and JSON `actionconfig` (per-action
  model, endpoint, system instruction, `max_tokens`). Never in code or env.
- **Grading is synchronous.** The adapter behaviours call `grade_response()` at
  submit/finish and the student waits for the model call — acceptable for one
  learner, and the reason `double_run` (two calls) was deferred.

### Moodle miscellany

- **Mustache `{{! ... }}` comments end at the *first* `}}`.** A template
  comment must not contain moustaches. Learnt the hard way.
- **`auth_none` is not passwordless for existing accounts.** Core validates the
  stored hash; `auth_none` is password-free only for accounts it would
  *create*, a path `authpreventaccountcreation` closes. So on a loopback
  wwwroot `auth-init.sh` both switches local accounts to `auth=none` *and*
  blanks their passwords. Off-loopback it asserts the opposite, and
  `smoke-tests.sh` fails the deploy if any active account accepts an empty
  password.
- **`auth_oauth2` accounts need no password at all.** The admin form demands
  one only for internal auth plugins; `prevent_local_passwords()` keeps the
  hash unset (`AUTH_PASSWORD_NOT_CACHED`, which
  `validate_internal_user_password()` rejects), and `user_login()` returns
  false outside an OAuth callback. So SSO-only accounts do not weaken the
  empty-password posture checks.
- **Moodle 5.1's `oauth2\client` has no id_token claim path**; a userinfo
  endpoint is mandatory (`get_raw_userinfo()` returns false without one, and
  `complete_login()` then fails with `loginerror_nouserinfo`). This is the
  single fatal blocker for Sign in with Apple, which has no userinfo endpoint.

---

## See also

- [`aiprovider-survey.md`](aiprovider-survey.md) — AI provider selection.
- [`sso-apple-survey.md`](sso-apple-survey.md) — Sign in with Apple, deferred.
- [`ai-grading-walkthrough.md`](ai-grading-walkthrough.md) — one student answer
  traced from submit to feedback, file by file.
- `qbank/README.md` — the authoring format these decisions produced.
- `ROADMAP.md` — what remains, including what was deferred by decision.
