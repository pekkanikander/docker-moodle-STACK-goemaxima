# Task 6: Multiple-choice questions, ungraded quizzes, random slots

## Context and intent

Analysis of the only physics valtakunnallinen koe we got (2021–22 sample,
in `../../esimerkkikokeita/`) showed multiple choice and short
explanations as major answer modes that the current machinery cannot express, while
STACK-graded calculation covers only about a fifth of the exam. The content
plan (`../../oivus-questions/suunnitelmat/03-monivalintastrategia.md`) therefore
opens content production with MCQs serving two purposes at once: cheap
drillable coverage of all topic areas, and probing this student's
comprehension difficulties with hand-written, hypothesis-bearing distractors.
The two purposes share one bank — whether drill and probe items need
explicit separating at all is an empirical question the plan leaves open — but every
question is tagged with its primary purpose from the start, so the question stays
answerable from the data.

That plan needs four machinery features, bundled here because the first is
useless without the last two:

1. `type: mcq` question sources — n options, per-option `why:`, shuffled
   order.
2. Distractor pools — a question may carry more wrong options than are shown
   at once, the shown subset varying per variant. Dilutes memorisation in
   drill and tests more hypotheses per question in probing.
3. Quiz `grade:` — a drill quiz must carry no grade (moved from TASK-03).
4. Random slots in quiz specs — drawing N questions from a pool by tag or
   category is what makes an MCQ bank drillable at all (moved forward from
   TASK-03 Feature 4 tier 3, where it was deferred; the MCQ plan promotes it).

It is an open question how well the existing Moodle mechanisms can support
distractor pools and random-slot quizzes.
These shall be studied and tested before actually
implementing anything in the compiler.

**Relation to TASK-03.** Features 2 and 4.3 move here. Hints (Features 1
and 3) stay in TASK-03 and are *not* a dependency of this task: the drilling
axis of an MCQ is pool size and repetition, not hint escalation — with six
options, one hint halves the question. TASK-03's open behaviour question
(Moodle hints only fire under `interactive`, which forfeits per-part grading)
is unaffected but will bite harder once two-input MCQ rungs exist; decide it
before building TASK-03 Feature 1.

## What is already verified

From the compiler source (`qbank/compiler/compile.py`), this repo:

1. The `interpretation:` dropdown already builds everything an MCQ needs:
   a teacher-answer list `[[key, correct, label], ...]`
   (`dropdown_teacher_answer`), an input with `mustverify: 0` /
   `showvalidation: 0` (`input_elements`), a PRT with one node per option
   using the `String` answer test so each distractor lands on its own answer
   note (`reading_nodes`), and generated question tests per option
   (`qtest_elements`). `type: mcq` is that plumbing minus the
   `quantity`/`formula` substitution apparatus.
2. `build-quiz.php` hard-codes `'grade' => 10` and `'shuffleanswers' => 1`,
   and adds only explicit slots (`quiz_add_quiz_question` per entry). The
   attempts guard already skips slot rebuilding when attempts exist.
3. `type:` dispatch exists (`type: aitext`), so a second question kind is a
   precedented branch, not a new mechanism.

## What was verified in the running container

Against the pinned STACK 4.13.0 / Moodle 5.1.6 tuple (code paths under
`/var/www/html/public/` — Moodle 5.x layout).

1. **Where the chosen option is recorded.** The raw step data
   (`question_attempt_step_data`) stores the *positional* choice: STACK's
   `radio` extends `dropdown`, whose submitted value is the 1-based index
   into the rendered list, stored under `ans1`; the attempt's first step
   also stores `_seed`. The key *string* lands in
   `question_attempts.responsesummary` on finished attempts:
   `summarise_response` (question.php:874) emits `Seed: N`, then
   `ans1: "key" [score]` — `contents_to_maxima` maps index back to the
   list value — then the PRT answer note (`ans-i-T`). So per attempt the
   seed, the chosen key, and the answer note are all recoverable; the bare
   index in step data decodes via the seed. Confirmed end to end with a
   scripted attempt against an imported fixture.
2. **Option order and subset.** Confirmed: `radio` renders the
   teacher-answer list in list order and has no native shuffling; the only
   randomisation is what the author writes in question variables —
   `random_permutation()` for order, `rand_selection(L, n)` for the subset
   draw (n distinct, random order, Maxima error if n > length;
   stackmaxima.mac). Both are seed-dependent, so `seeds:` is required iff
   `shuffle` or `show`, and the shown set and order are recoverable from
   the seed provided the question note pins them —
   `{@maplist(first, ta_mcq)@}` is the generated default. Quiz-level
   `shuffleanswers` is passed to `question_bank::load_question()` and
   ignored by STACK, as expected. (`multiselqn()` exists as a native
   draw-and-permute helper but builds bare value lists without display
   strings, so it does not fit keyed CASText labels.)
3. **Question tests against a `radio` input.** Qtest input values are CAS
   expressions evaluated per variant in the question-variables context
   (`stack_question_test::compute_response`, questiontest.php:206), and
   value→index mapping is order-independent — so static per-distractor
   tests (`"key"` as the value) pass at every seed for *unpooled* MCQs,
   shuffled or not. The bulk tester runs every test at every deployed seed
   (bulktester.class.php:588). Under a pool, a hidden key is an invalid
   response and the test fails; and while the test *input* could be
   variant-computed, the *expected answer note* is static per test — route
   (a) is confirmed dead. **Route (b) adopted:** pooled MCQs get one
   static qtest for the correct key (always shown), and distractor
   key→note→`why:` mapping is covered by compiler unit tests. Route (c)
   not needed. Corollary: unpooled MCQs keep full per-option qtests.
4. **Random slot API in Moodle 5.1.** Confirmed:
   `\mod_quiz\structure::add_random_questions(int $addonpage, int $number,
   array $filtercondition)` (structure.php:1673); the filter condition is
   persisted in `question_set_references`. Canonical shape (from
   `mod_quiz\external\add_random_questions`): `{qpage: 0, cat:
   "<categoryid>,<contextid>", qperpage: 100, tabname: 'questions',
   sortdata: [], filter: {...}}` with `filter.category` = `{jointype,
   values: [categoryid], filteroptions: {includesubcategories}}`
   (recursive via `question_categorylist`). **Tag filtering works:** key
   `qtagids`, values = tag ids, AND-joined
   (`qbank_tagquestion\tag_condition`); tag-only pools ride on the bank's
   top category with `includesubcategories: true`. Slots insert with
   maxmark 1; other marks are set after insert. At attempt start each
   random slot draws a question not already used in that attempt (explicit
   slots included) via `random_question_loader`; an exhausted pool throws
   `notenoughrandomquestions` — so the pool size is validated at build
   time (`random_question_loader::count_filtered_questions` on the Moodle
   side, plus a compiler-side check over the compiled tree).
5. **STACK `radio` vs core `qtype_multichoice`.** STACK. Neither
   balance-shifting condition materialised: the pool draw is a few
   generated lines of Maxima (`rand_selection` + `sublist`), and qtests
   cover every option for unpooled MCQs — only pooled ones fall back to
   route (b). Labels go through `castext()` (STACK ≥ 4.4; the list must be
   defined in question variables, which it is), so LaTeX in options works.
   Multichoice would add a second import/validation path and lose the test
   gate entirely.

## Feature 1 — `type: mcq`, including distractor pools

```yaml
id: mv-nopeus-kasite-01
type: mcq
name: "Mitä nopeus kuvaa"
category: [Fysiikka, Liike]
tags: [fysiikka, liike, drilli]
seeds: [101, 102, 103]        # required iff shuffle or a pool subset
shuffle: true                  # default true
show: 6                        # optional: options shown per variant,
                               # correct one always included; omitted =
                               # show all

stem: |
  Nopeus kuvaa

options:
  - key: liike
    label: "liikkeen suuruutta (itseisarvoa)"
    correct: true
    why: |
      Nopeus kuvaa, kuinka pitkän matkan kappale kulkee tietyssä ajassa.
  - key: matka
    label: "kuljettua matkaa"
    why: |
      Matka on oma suureensa; nopeus kertoo, kuinka nopeasti matka kertyy.
  # ... ~6 shown; the pool may hold more distractors than `show`

feedback: |
  Worked explanation, shown after the attempt.
```

Semantics and implementation notes:

- Exactly one option `correct: true`. Keys lowercase kebab-case, stable —
  they are the analysis vocabulary, same rule as interpretation reading keys.
- `why:` required on every option (the no-dark-patterns rule is enforced by
  review, but a missing `why:` is a compile error, as for readings).
- Input: STACK `radio` (all options visible; a six-option dropdown hides the
  alternatives, and the alternatives are the content). `boxsize 0`,
  `mustverify 0`, `showvalidation 0`, as the dropdown does now.
- Grading: one PRT, `String` test against the intended key, one node per
  option → per-distractor feedback (`why:`) and a distinct answer note per
  option. Reuse `reading_nodes`.
- `shuffle: true` wraps the teacher-answer list in `random_permutation()`;
  `show: k` (with a pool of more than k) additionally draws the shown
  subset, correct option always included, in question variables
  (`rand_selection()` or equivalent — verification item 2). Either makes
  the question random, so `seeds:` is required, per the existing rule.
  Each deployed seed fixes one subset-and-order; shown set and order are
  recoverable from the seed. `shuffle: false` without a pool needs no
  seeds. Exact implementation depends on the research results from above.
- No `answer:` block, no `variables:` in the common case; `figure:` stays
  available (an MCQ about a graph is expected: "which claim does this graph
  support?").
- Question tests: one per option, each asserting score and its own answer
  note, generated as for readings today — **except under a pool, where
  this breaks. This is the feature's main design question.** The bulk
  tester runs every test at every deployed variant, and a test submitting
  a key that variant does not show is an invalid response, so static
  per-distractor tests fail wherever the distractor is hidden. Candidate
  routes, to be settled during verification:
  - (a) Test inputs are CAS expressions evaluated per variant, so a test
    could submit "the shown list's i-th element" — but the *expected
    answer note* is static per test, and the note is exactly what varies.
    Probably a dead end; check anyway.
  - (b) Generate a static qtest only for the correct key (always shown),
    and cover distractors by construction instead: the node-per-option PRT
    is mechanically generated (key → note → `why:`), so a compiler unit
    test of the generation covers what a per-question Maxima test would.
    The residual risk — a `why:` that mismatches its label — is not
    Maxima-testable anyway. Honest, and probably the answer.
  - (c) Constrain seed deployment so every option is shown in at least one
    variant, and generate per-variant expectations — only if the qtest
    format turns out to support it, which is not expected.
  Whichever route is taken, the README must say what the test gate does
  and does not cover for pooled MCQs.
- "Least-wrong" items (no fully correct option) are content, not machinery:
  the correct: true option is the least-wrong one and its `why:` says so.
  The `choice` rung of the least-wrong ladder (student first judges whether
  a precise option exists, then answers; two independently graded inputs)
  is the same two-input shape as the interpretation `choice` scaffold —
  design it when the content plan actually asks for it, not now.

Prose fields follow the existing rules (paragraphs, `- ` bullets, no
Markdown emphasis; LaTeX/CASText/HTML pass through). Labels are CASText, so
LaTeX in options works.

## Feature 2 — quiz `grade:`

As specified in TASK-03 Feature 2, unchanged: a `grade:` field in the quiz
spec, default 10, validated as a number ≥ 0, passed through to
`build-quiz.php`. `grade: 0` means Moodle creates no gradebook item. The
drill-quiz recipe (behaviour, review lists without `marks`) moves into
`qbank/README.md` with it.

## Feature 3 — random slots

Quiz spec entries gain a random form:

```yaml
questions:
  - id: mv-nopeus-kasite-01     # explicit slot, as today
  - random: 5                   # draw 5 per attempt
    tags: [drilli, liike]
    category: [Fysiikka, Liike] # and/or; at least one selector required
    maxmark: 1                  # default 1, as today
```

- Implemented in `build-quiz.php` via the core random-question API (see
  verification item 4). The existing attempts guard applies unchanged.
- Each attempt draws a fresh subset — the across-sessions repetition tier
  that TASK-03 Feature 4 wanted, at MCQ-bank cost.
- Validation: `random` a positive integer; refuse a draw larger than the
  matching pool at build time if that is cheaply checkable, otherwise
  document that Moodle repeats questions / errors (whichever the verified
  behaviour is).

Again, the exact implementation depends on the research results from above.

## Constraints

- No change to any existing question source. Existing quiz specs compile
  unchanged (`grade:` defaults to 10, `questions:` entries with `id:` behave
  as today).
- Fixture coverage: at least one `mcq` fixture with `shuffle: true`, one
  with `shuffle: false`, and one with a pool (`show:` smaller than the
  option count); one drill quiz fixture with `grade: 0`,
  `behaviour: interactive` or `immediatefeedback`, and a random slot; CI
  runs all of it.
- `qbank/README.md` is the format reference and is updated in the same
  change: `type: mcq`, pools and `show:`, quiz `grade:`, random slots, the
  drill-quiz recipe, the seeds-iff-random rule, and what the test gate
  covers for pooled MCQs.
- `id:` permanence applies to MCQs exactly as to STACK questions. Drill and
  probe items live in one bank, distinguished by purpose tags, not by
  machinery; whether they need harder separation is answered by use.

## Suggested order of work

1. Verification items 1–5, findings recorded above. Item 3 settles the
   pool-vs-qtest design question and item 5 the target question type
   before any code.
2. Feature 2 (`grade:`) — smallest, independently useful, unblocks nothing
   downstream being wrong.
3. Feature 1 (`type: mcq` with pools) with fixtures and README.
4. Feature 3 (random slots) with the drill quiz fixture.
5. In `oivus-questions`: the pilot per
   `suunnitelmat/03-monivalintastrategia.md` (drill bank + procedural-step
   probe + aitext items), run with the student.

Step 5 is the review gate, as always: whether six options is the right
count, and whether the two-population split holds up, is answered by the
student, not the test suite.
