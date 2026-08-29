# Task 3: Non-graded drilling mode on the existing STACK question material

## Context and intent

The exam path works: `oivus-questions/tentit/fysiikka-liike-01.yaml` was tested
with the student and the machinery held up. What is missing is the other half of
the practice loop — **drilling**: repeated attempts at the same material with no
grade attached, immediate correct/incorrect feedback, and guidance that escalates
when the student is stuck.

Requirement: **one question source serves both uses.** A question must not be
forked into an exam copy and a drill copy that then drift apart. Drilling is a
property of the quiz the question sits in, not of the question.

This is a machinery task. The content work (writing hints, writing drill quiz
specs) happens in `oivus-questions` afterwards.

## What was verified before writing this brief

Read in the running container against the pinned STACK 4.13.0 / Moodle 5.1.6
tuple. These are checked facts, not assumptions; re-verify if the pins move.

1. **STACK supports Moodle hints, and renders them as CASText.**
   `question/type/stack/renderer.php:629` overrides `hint()` and calls
   `qtype_stack_question::get_hint_castext()` (`question.php:657`), which
   evaluates the hint inside the question's Maxima session. So `{@dv@}`
   interpolates, and a hint is correct for whichever variant the student drew.
2. **Only the `interactive` behaviour reads hints.** `get_applicable_hint()` is
   called from `question/behaviour/interactive/behaviour.php` and from nowhere
   else in `question/behaviour/`. A question carrying hints therefore renders
   byte-identically under `deferredfeedback`, `adaptive`, `adaptivenopenalty`
   and `immediatefeedback`. **This is what makes shared sources safe.**
3. **Tries = hints + 1.** `behaviour.php:150` sets
   `_triesleft = count($this->question->hints) + 1`.
4. **STACK's validation step costs nothing.** `process_submit()` sets state
   `invalid` for an incomplete response *before* decrementing `_triesleft`, so
   the extra *Check* press that STACK's `mustverify: 1` inputs require does not
   consume a try.
5. **Penalty applies per used try** (`adjust_fraction()` subtracts
   `question->penalty` once per try consumed). Irrelevant once marks are hidden
   and the quiz grade is 0, but it is why drilling must hide marks rather than
   show discouraging ones.
6. **Redo already works and is already switched on.** `canredoquestions` is
   hard-coded to 1 in `qbank/cli/build-quiz.php:104`. Moodle offers *"Try
   another question like this one"* when `can_question_be_redone_now()` holds
   (`mod/quiz/classes/quiz_attempt.php:954`), which needs a behaviour where
   questions finish during the attempt — `interactive` and `immediatefeedback`,
   not `adaptive`. Pressing it redraws a variant, i.e. new numbers from the
   deployed seeds.
7. **STACK imports hint text only.** `questiontype.php:1922` calls
   `import_hints($fromform, $xml, false, false, ...)` — `withparts` and
   `withoptions` are both false, so `shownumcorrect` and `clearwrong` are not
   imported. Do not emit them.
8. **Hints are validated on import** (`questiontype.php:2506` runs
   `validate_cas_text` over every hint), so a broken hint fails the import gate
   like any other CASText error.

## The trade-off to be aware of

`qtype_stack_question::make_behaviour()` (`question.php:323`) swaps in
`adaptivemultipart` **only** for `adaptive` and `adaptivenopenalty`. Under
`interactive`, a multi-PRT question is graded as one unit: for `scaffold: choice`
questions the reading and the answer stop being independently graded, and both
inputs must be filled before a try counts. The PRT feedback that names the
misreading still appears.

For `stated` and `none` questions — one PRT — nothing is lost.

So: escalating hints (`interactive`) or per-part independence
(`adaptivenopenalty`), not both, on the Moodle-hint route. Feature 3 below is
the escape hatch if this turns out to matter.

## Feature 1 — `hints:` on question sources

Add an optional `hints:` key: an ordered list of prose blocks, each obeying the
existing prose rules (paragraphs and `- ` bullets, no Markdown emphasis, LaTeX
and CASText pass through).

```yaml
hints:
  - |
    Mitä suuretta tehtävässä kysytään, ja mikä lukema on nopeuden muutos?
  - |
    Kiihtyvyys on nopeuden muutos jaettuna ajalla: \(a = \frac{\Delta v}{t}\).
  - |
    Sijoita: \(\Delta v = {@dv@}\,\mathrm{m/s}\), \(t = {@aika@}\,\mathrm{s}\).
```

Compile each through the existing `to_html()` into
`<hint><text>…</text></hint>` elements. Nothing else: no `shownumcorrect`, no
`clearwrong` (see verified fact 7).

Validation: a list of non-empty strings; reject a `hints:` key that is not a
list. No cap on the count — the count *is* the try count, and that is the
author's decision.

Roughly fifteen lines in `qbank/compiler/compile.py`, reusing `to_html`.

**Authoring guidance for the README** (this is the point of the feature, so say
it there rather than leaving it implicit): the hint ladder should mirror the
`stated`/`choice`/`none` ladder inside a single question —

- hint 1: which quantity is asked, and which reading of the stem applies;
- hint 2: the relation, with symbols;
- hint 3: the numbers substituted, leaving only the arithmetic.

`feedback:` remains the worked solution and is unchanged. A hint that merely
restates the stem is worse than no hint.

## Feature 2 — quiz `grade:`

`qbank/cli/build-quiz.php:97` hard-codes `'grade' => 10`. Make it a quiz-spec
field, default 10. `grade: 0` means Moodle creates no gradebook item — which is
what "no grading" should mean concretely, rather than a hidden mark the student
can still find.

Compiler-side: validate it is a number `>= 0`; pass it through.

With that, a drill quiz spec is:

```yaml
behaviour: interactive
grade: 0
attempts: 0
questionsperpage: 1
review:
  during: [correctness, specificfeedback]
  after:  [attempt, correctness, specificfeedback, generalfeedback]
```

`correctness` gives the right/wrong mark. Dropping `marks` from both lists is
what keeps the numbers off the screen. Note that `attempts: 0` (unlimited) plus
`grade: 0` makes `grademethod` meaningless; leave it at its default rather than
adding a special case.

## Feature 3 — optional, only if Feature 1's pacing proves wrong

STACK 4.13 has a `[[hint title="…"]]` block: a button the student presses to
reveal text. It works in any CASText, **including inside PRT feedback nodes**,
and therefore in any behaviour. That gives guidance which is student-paced,
costs no try and no mark, and — because it can live in a feedback node — can be
conditional on the mistake actually made, including on which misreading the
student's answer came from. `[[adaptbutton … save_state="…"]]` additionally
records the reveal into an input, making "did he need the hint" observable
rather than lost.

The cost: block contents sit in the page source (STACK's own docs warn about
this for exam settings), so such hints are present wherever the question id is
used, exams included.

If that route is taken, the way to keep exams clean without forking sources is a
`drill:` block in the question source from which the compiler emits a **twin
question `<id>-drill`**: one authored source, two ids, separate attempt
histories, the exam question untouched. The twin needs its own generated
question tests. This is materially more compiler work than Features 1 and 2 and
should not be started speculatively.

## Feature 4 — repetition

Three tiers, in increasing cost:

1. **Within a question:** the hint ladder (Feature 1).
2. **Within a session:** *"Try another question like this one"*, already working
   under `interactive` (verified fact 6). The binding constraint is content, not
   machinery: questions currently deploy three seeds, so the third redraw starts
   repeating numbers. Raise seed counts to roughly eight to twelve for questions
   used in drilling; the cost is bulk-test time, which is the honest trade.
   Note this in the README next to the `seeds:` rule.
3. **Across sessions:** unlimited attempts on per-topic drill quizzes covers it
   for now. Random-slot support in the quiz spec (draw N questions from a
   category or tag via `quiz_add_random_questions`, instead of a fixed list)
   would make each attempt a different set; `build-quiz.php` currently only adds
   explicit slots. Worth doing when the bank is large enough to make it
   meaningful, not before.

Genuine spaced repetition — Leitner or SM-2 scheduling across days — is not in
Moodle core and would need a plugin. Explicitly **out of scope**; record the
decision so it is not rediscovered.

## Constraints

- No change to any existing question source may be required by this task.
  Adding `hints:` to a question must remain optional and must not alter its
  behaviour in the exam quiz that already exists.
- The fixture bank must gain coverage: at least one fixture question with
  `hints:`, and one fixture drill quiz spec with `grade: 0` and
  `behaviour: interactive`, so CI exercises both.
- `qbank/README.md` is the format reference and must be updated in the same
  change as the compiler — `hints:`, quiz `grade:`, the drill quiz recipe, the
  hint-ladder authoring guidance, and the seed-count note.
- Hints are not covered by STACK question tests. Say so in the README rather
  than implying the test gate covers them.

## Suggested order of work

1. Feature 2 (`grade:`) — smallest, and independently useful.
2. Feature 1 (`hints:`) plus fixtures and README.
3. In `oivus-questions`: hints on the existing `liike` questions, more seeds,
   and one drill quiz over the same ids the exam uses. Run it with the student.
4. Only then decide on Feature 3, on the evidence of whether `interactive`'s
   fixed try count reads as a helpful structure or as pressure.
5. Feature 4 tier 3 (random slots) when the bank justifies it.

Step 3 is the review gate: the question is whether shared sources actually hold
up in use, and that is answered by the student, not by the test suite.
