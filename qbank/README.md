# Question banks as code

Questions are written as YAML, compiled to Moodle XML, and pushed into a
running Moodle by CLI.
Nothing should be authored in the Moodle web UI; the git tree is
the source of truth and every change is reviewable as a diff.
Any changes within Moodle will be overwritten by the next import.

```
content repo (YAML)  --compile-->  .generated/qbank (XML + JSON)  --import-->  Moodle
```

## Where the content lives

The machinery is in this repo.
The content is in a separate folder, located by `QBANK_CONTENT_DIR`.

```sh
QBANK_CONTENT_DIR=~/path/to/oivus-questions ./tools/qbank.sh all
```

With `QBANK_CONTENT_DIR` unset, the test fixtures in `qbank/fixtures/` are used.
Those are not teaching material: they exist to exercise every supported feature
and are what CI runs.

## Commands

`tools/qbank.sh <command>`, all of which are idempotent and safe to repeat:

| command   | what it does |
| --------- | ------------ |
| `compile` | YAML → `${QBANK_BUILD_DIR:-.generated/qbank}`, in the `qbank-tools` container |
| `import`  | XML → question bank activity, in the `moodle` container |
| `quizzes` | quiz specs → quiz activities |
| `test`    | STACK's `bulktestall.php` (every question's own tests through Maxima), then the figure render gate |
| `all`     | all four, in that order |

Course and bank are taken from `QBANK_COURSE` and `QBANK_BANK` env vars
(defaults to `qbank` and `qbank-main`); both are created if missing.
Their display names come from `QBANK_COURSE_FULLNAME` and `QBANK_BANK_NAME`,
and are used only when creating them.

`import` also accepts `-n` (dry run) and `--force` (re-import unchanged files).

`qbank/tests/run-tests.sh` tests the compiler on the fixtures, inside the
`qbank-tools` container; it needs no Moodle.

Only one `qbank.sh` run at a time may touch a stack, and the script enforces it:
a second run refuses to start and names the one already in flight. This matters
because two concurrent runs do not fail like contention. Two `bulktestall.php`
runs abort each other with `!!! Error writing to database !!!` at a point that
moves between runs, which reads as a broken question or a broken database; two
imports race on the same bank and the same build directory. The lock is a
directory under `$TMPDIR`, keyed on the compose project, and is released however
the run ends; one left behind by a `kill -9` is cleared by the next run, which
checks whether the recorded owner is still alive.

The gate cannot see a bulk test started from Moodle's own web interface
(`/question/type/stack/adminui/bulktestindex.php`, linked from the STACK
settings page). Use `qbank.sh test` rather than that page while working.

## What happens when a question changes

A question's identity is the `id:` field,
which becomes the Moodle `idnumber` of the question bank entry.
It must never change once a question has been attempted;
renaming `id:` reads as "delete one question, add another".

- **New `id`** — a question is created in the category given by `category:`.
- **Edited file, same `id`** — a *new Moodle version* is added to the existing
  bank entry. Earlier attempts keep pointing at the version they were made
  against, so attempt history stays intact and quizzes pick up the new version.
- **Unchanged file** — skipped. The importer stores a hash of each compiled
  question in `{config_plugins}` under the `qbankimport` plugin name and
  compares. The provenance tag is left out of that hash, so a new content
  commit on its own is not a change (see below).
- **Deleted file** — reported as `stale`, never deleted at Moodle.
  Removing a question from Moodle would orphan attempt data, so that stays a manual decision.
- **Moved to another `category:`** — the question stays where Moodle has it.
  Categories are only used when creating a question.

Because the state lives in the Moodle instance and not in a per-site manifest,
the content repo is not coupled to any particular Moodle site: the same tree can be
imported into the local stack and into production independently.

Before importing, each file is put through STACK's own validation.
STACK otherwise saves an invalid question silently,
marked broken and invisible to students,
so the importer asks up front and refuses instead.

## Provenance

An attempt is bound to the exact question version the student saw: Moodle keeps
every version, and `question_attempts` points at one of them. What Moodle does
not know is where that wording came from. So the compiler stamps each question
with the content-repo commit it was built from, as a tag:

```
src-b144009b281a          # clean tree
src-b144009b281a-dirty    # tree had uncommitted or untracked changes
src-unknown               # not a git checkout at all
```

Tags attach to the question version, not to the bank entry, so an attempt from
six months ago still names the commit whose message explains why the question
is worded that way — read out of the Moodle database alone, which is what gets
backed up and restored.

The tag is deliberately outside the hash that decides whether a question has
changed. Hashing it would make every commit look like an edit to every
question and add a Moodle version nobody wrote.
Because of that, the tag names the commit at which the question last actually
changed, not the commit of the most recent import.

Each build also writes `manifest.json` next to the XML: both commits (content
and this repo's compiler), their dirty flags, the build time, and the source
path and SHA-256 of every question. The importer records the manifest, and the
questions it created or updated, as one row per import run in
`{config_plugins}` — enough to reconstruct which questions changed together on
which date, which is the unit a design cycle is reported in. Runs that changed
nothing are not recorded.

A commit recorded from a tree with uncommitted or untracked changes does not
describe what was compiled, and a wrong provenance is worse than none because
it will be believed. The importer therefore refuses such a build. `qbank.sh`
waives that for a site on `localhost`, where attempts are throwaway; set
`QBANK_ALLOW_DIRTY=1` to waive it for another throwaway site (running CI
locally under `act`, say).

## Question source format

One question per file, anywhere in the content folder that `QBANK_CONTENT_DIR` points to.
The file name is irrelevant; `id:` and `category:` decide everything.

An example:
```yaml
id: motion-average-speed-01    # lowercase kebab-case, stable, unique
name: "Average speed"          # shown in the question bank
category: [Physics, Motion]    # category path inside the bank
tags: [physics, motion]
grade: 1.0                     # default 1.0
penalty: 0.1                   # default 0.1
seeds: [101, 102, 103]         # required if `variables` uses rand()

variables: |
  k : rand([1, 2, 3]);
  sx : 300 * k;

stem: |
  Prose shown before the question.

answer:
  type: numerical               # algebraic | numerical | units
  prompt: "What is …?"
  formula: sx/t                 # the correct answer, in Maxima
  tolerance: 0.01               # answer-test option; type-specific default
  strict: false                 # units only: accept any compatible unit
  boxsize: 8
  syntaxhint: "?*m/s"

hints:                          # optional; see Hints below
  - |
    Shown after the first failed try, under `behaviour: interactive`.

feedback: |
  Worked solution, shown after the question is finished.
```

Prose fields (`stem`, `prompt`, `feedback`, `why`, `hints`) take blank-line-separated
paragraphs and `- ` bullet lists.
Nothing else is interpreted: LaTeX, CASText (`{@...@}`) and inline HTML
pass through byte for byte.
This is deliberate — a Markdown renderer would eat the underscores and backslashes in
`\(v_0 = \frac{s}{t}\)`. Use `<em>…</em>`, not `*…*`.

Answer types map onto STACK answer tests:

| `type`      | answer test    | default `tolerance` |
| ----------- | -------------- | ------------------- |
| `algebraic` | `AlgEquiv`     | — (exact, symbolic) |
| `numerical` | `NumRelative`  | `0.01` |
| `units`     | `UnitsStrictRelative`, then `UnitsRelative` | `0.01` |

A `units` answer is graded strictly by default: full marks need the unit the
`formula` uses, so the prompt should name it. A correct value in a different
but compatible unit earns 0.75 of the marks and feedback asking for a
conversion, instead of passing silently or failing bare. Set `strict: false`
to accept any compatible unit for full marks, for questions where the student
chooses the unit; the prompt should then say so.

Randomised questions must list `seeds:` — a question whose `variables:` use
`rand()`, and an MCQ that shuffles or draws from a pool. Without deployed
seeds a question has no fixed set of variants and its tests only ever
exercise whichever one comes up, so `tools/qbank.sh test` would not be a
real gate.

Three seeds is enough for an exam question, which is seen once. A question
used for drilling is seen repeatedly: *Try another question like this one*
walks the deployed seeds, so with three of them the third redraw already
repeats numbers the student has just worked through. Give such questions
eight to twelve seeds. The cost is bulk-test time, which is the honest trade.

## Hints

`hints:` is an ordered list of prose blocks, shown one at a time as the student
runs out of tries:

```yaml
hints:
  - |
    Mitä suuretta tehtävässä kysytään, ja mikä lukema on nopeuden muutos?
  - |
    Kiihtyvyys on nopeuden muutos jaettuna ajalla: \(a = \frac{\Delta v}{t}\).
  - |
    Sijoita: \(\Delta v = {@dv@}\,\mathrm{m/s}\), \(t = {@aika@}\,\mathrm{s}\).
```

**Only the `interactive` behaviour reads hints.** Under every other behaviour a
question that carries them renders exactly as if it did not, which is what lets
one source serve both an exam quiz and a drill quiz — a question is never
forked into an exam copy and a drill copy that then drift apart. Drilling is a
property of the quiz, not of the question. Under `interactive`, the number of
tries is the number of hints plus one, so the length of the ladder is the
author's decision and there is no cap. STACK's *Check*-to-validate step does
not consume a try.

STACK evaluates a hint inside the question's Maxima session, so `{@...@}`
interpolates and a hint is correct for whichever variant the student drew.
A hint is CASText and is checked as such at import, like any other prose here.

The ladder should mirror the `stated`/`choice`/`none` ladder *inside* a single
question — each rung removes one thing the student has to supply:

1. which quantity is asked, and which reading of the stem applies;
2. the relation, with symbols;
3. the numbers substituted, leaving only the arithmetic.

`feedback:` remains the worked solution and is unaffected. A hint that merely
restates the stem is worse than no hint.

Note the trade-off for `scaffold: choice` questions: STACK grades each PRT on
its own only under `adaptive`, so under `interactive` the reading and the
answer stop being independently graded and both inputs must be filled before a
try counts. The PRT feedback naming the misreading still appears. For `stated`
and `none` questions — one PRT — nothing is lost. Escalating hints or per-part
independence, not both.

Hints are **not** covered by `tools/qbank.sh test`: STACK question tests
exercise the PRTs, not the hints. A hint with a CASText error fails the import
gate, and beyond that a hint ladder is reviewed by reading it.

`hints:` applies to STACK questions, `type: mcq` included; it is refused on
`type: aitext`.

## Figures

A question may carry one figure, in the stem, written as a `figure:` block.

(Note: the prose fields pass HTML and CASText through untouched, so a
`{@plot(...)@}`, an `<img>` or an `<svg>` written there would reach STACK with
no alt text and outside the render gate. The compiler refuses all three.)

Two kinds, and the difference decides which key to use:

```yaml
figure:                                  # a graph: STACK's plot() draws it
  alt: |
    Matka-aikakuvaaja: origosta lähtevä nouseva suora.
  plot: |
    [[discrete, [[0, 0], [tloppu, sloppu]]]],
    [x, 0, tloppu], [y, 0, sloppu],
    [xlabel, "aika (s)"], [ylabel, "matka (m)"]
```

```yaml
figure:                                  # a schematic: a file in the content repo
  alt: |
    Virtapiirin kaaviokuva: paristo ja kaksi vastusta R1 ja R2 samassa
    silmukassa peräkkäin.
  svg: kuvat/virtapiiri-sarja.svg        # relative to the content root
```

`alt:` is required, in Finnish, and is prose: it cannot interpolate variables,
because a plot's alt text is a Maxima string inside a CASText block. STACK's
own default is an English dump of the plotted expression, which is worse than
nothing.

**`plot:` is for a figure that carries the variant's numbers.** Everything
inside it comes from `variables:`: a decimal number, or a constant that
`variables:` also defines, is refused. If the picture and the prose can
disagree, the student who reads the picture correctly is marked wrong. The
contents are the arguments of STACK's `plot()`, minus the alt text, which the
compiler adds; the permitted options are STACK's (`stackmaxima.mac`), and more
than two variables is a Maxima error.

Axis ticks are written with a decimal comma. The compiler appends `set
decimalsign ","` to `PLOT_TERM_OPT` in any question with a plot, which is the
only hook a question has into gnuplot's preamble; `figure-test.php` fails if a
tick label comes back with a decimal point anyway.

**`svg:` is for a static diagram** — circuits, ray paths — that gnuplot cannot
draw. The rule that makes this work is a content rule: **labels in the figure,
numbers in the prose.** A circuit drawn with `R1`, `R2` and `U`, with the
values given in the stem, is what an exam paper does anyway, and it makes the
diagram the same for every variant. The SVG is embedded in the question XML as
base64 and referenced through `@@PLUGINFILE@@`, so Moodle serves it from its
own file store; the content repo holds text, never a binary. An SVG containing
a script, an event handler, an external reference or an entity declaration is
refused: an exam page fetches nothing, and a diagram that quietly fails to
load breaks a question in a way the student cannot diagnose.

A plot file is a per-render artefact. STACK names it with `rand(10^8)` and
writes it into `$CFG->dataroot/stack/plots`, so nothing about it can be pinned
in advance and the gate is a render instead: `qbank/cli/figure-test.php`, run
by `tools/qbank.sh test`, renders every figure question at every deployed seed
and checks that each image exists, is a non-empty SVG and has alt text. It
cannot check that the figure is *right*; that stays a preview step.

The plot filename is cached in the CAS result cache, which outlives the file:
if `$CFG->dataroot/stack/plots` is ever cleared, clear the CAS cache too
(`question/type/stack/cli/clearcascache.php`, which `stack-init.sh` runs), or
questions will point at images that are gone. The figure gate catches this.

## Interpretation scaffolding

Exam questions often require inferring the intended reading of a word before any
physics happens — "distance" may mean the length of the route walked or the
distance from the starting point.
An `interpretation:` block makes that step explicit and gradeable.
The fixtures do this in Finnish, where the everyday word `matka` spans more
readings than English `distance` does; see `qbank/fixtures/questions/tulkinta/`.

```yaml
scaffold: choice                # stated | choice | none

interpretation:
  weight: 0.4                   # share of the marks for the reading (choice only)
  prompt: |                     # required for `choice`
    What does the word <em>distance</em> mean in this question?
  readings:
    - key: distance
      label: "distance along a specific path"
      value: sx + sy
      intended: true
      why: "Named when the student gets this right."
    - key: displacement
      label: "direct displacement from the origin"
      value: sqrt(sx^2 + sy^2)
      why: "Named when the student answers as if this were meant."

answer:
  quantity: s                   # required: the symbol the readings stand for
  formula: s                    # each reading substitutes its value for `quantity`
```

Exactly one reading is `intended: true`.

Each reading's `value` is substituted for `answer.quantity` in `answer.formula`,
producing the answer that reading leads to.
Those become extra nodes in the grading tree,
so an answer that is wrong *for an explicable reason* is named
rather than merely marked wrong.
This holds at every rung, including `none`.

The three rungs are a fading ladder:

- `stated` — the intended reading is spelled out in the stem, introduced by
  `interpretation.stated_prefix` (required for this rung, as the wording is
  content and belongs in the content repo).
  The student practises the physics, not the inference.
- `choice` — the student picks the reading from a dropdown,
  and it is graded separately (`weight` of the marks).
  The inference becomes visible and correctable on its own.
- `none` — the stem says nothing; the reading has to be inferred,
  as in a real exam.
  Distractor feedback still explains a misreading afterwards.

A question is written once per rung, with its own `id`, so that progress through
the ladder is a matter of which questions are in the quiz.

Under `choice`, the two marks are genuinely independent:
the reading carries `weight` of the marks, and the answer is graded against
the reading the student *selected*, not the intended one.
Picking a misreading and then computing correctly for it therefore costs
exactly `weight` and nothing more, and "sound method, wrong reading" is
visible in the score itself, not only in the feedback.
The answer is not graded until a reading has been selected —
the student must commit to a reading first.

## Multiple-choice questions (mcq)

A file with `type: mcq` compiles to a STACK question whose only input is a
`radio` over named options. The option keys, not letters or positions, are
what attempt data records, so the distractors are the analysis vocabulary:
each one carries a hypothesis about a misunderstanding, and its `why:` names
it back to the student.

```yaml
id: mv-nopeus-kasite-01
type: mcq
name: "Mitä nopeus kuvaa"
category: [Fysiikka, Liike]
tags: [fysiikka, liike, drilli]
seeds: [101, 102, 103]        # required iff shuffle or show
shuffle: true                 # default true; false keeps the authored order
show: 4                       # optional: options shown per variant; the
                              # correct one is always among them

stem: |
  Nopeus kuvaa

options:
  - key: liike                # lowercase kebab-case, stable
    label: "liikkeen suuruutta"
    correct: true             # exactly one
    why: |
      Shown when this option is chosen.
  - key: matka
    label: "kuljettua matkaa"
    why: |
      Required on every option: names the misunderstanding.

feedback: |
  Worked explanation, shown after the attempt.
```

Grading is one node per option: choosing a distractor lands on its own
answer note with its `why:`, so every choice is machine-coded data, not
just "wrong". Labels are CASText, so LaTeX in options works; `figure:` and
`variables:` are available as for any question — an MCQ about a graph is
expected.

`shuffle:` and the pool draw both run in the question variables
(`random_permutation()`, `rand_selection()`), so either makes the question
random and `seeds:` required. Each deployed seed fixes one shown subset and
order, and the generated question note records the shown keys in shown
order — both are recoverable from the seed, which the analysis of
chosen-distractor distributions needs. `show: k` shows the correct option
and k−1 of the distractors, drawn per variant; it must be at least 2 and
smaller than the option count. `shuffle: false` without `show:` is not
random and needs no seeds; use it when the option order carries meaning,
such as an ordered scale.

What the test gate covers: for an unpooled MCQ the generated question tests
submit every option key and assert its score and answer note, at every
deployed seed. Under a pool a hidden key is an invalid response, so the
generated test covers only the correct key, which every variant shows; the
distractor key → note → `why:` mapping is mechanically generated and covered
by the compiler's own tests (`qbank/tests/test_mcq.py`) instead. What no
machine test covers is a `why:` that mismatches its label — that stays a
review step.

## AI-graded explanation questions (aitext)

A file with `type: aitext` is an explanation question graded by an LLM
against a criterion rubric, not by Maxima. The design and its rationale are
in the plugin repo's [docs/rubric-design.md](https://github.com/pekkanikander/moodle-qtype_aitext_rubric/blob/main/docs/rubric-design.md); the grading pipeline is our
`qtype_aitext_rubric` plugin (a fork of `qtype_aitext`). Each source
compiles to two artefacts: Moodle XML under
`questions/` for import (quizzes may reference aitext questions like any
other), and an eval spec under `aitext/` for the golden-test harness
(`tools/qbank.sh aitest`).

```yaml
id: selitys-kelluminen-01
type: aitext
name: "Kelluminen ja tiheys"
category: [Fysiikka, Selitys]
language: fi                  # language of the student-facing feedback

stem: |
  The question shown to the student.

context: |                    # optional; grader-model context, never shown
  Peruskoulun fysiikan selitystehtävä. Älä vaadi kaavoja.

sampleanswer: |               # a model answer, given to the grader

scaffold: |                   # optional answer skeleton (see below)
  Vastauksen runko:

  - Vertaa kappaleiden tiheyttä veden tiheyteen.

rubric:
  criteria:                   # 2-5 criteria
    - id: noste               # stable slug; the JSON round-trip key
      title: "Noste"          # shown to the student
      levels:                 # 2-5 descriptors; index = points earned
        - "Nostetta ei mainita, tai se kuvataan väärin."
        - "Noste mainitaan, mutta sen rooli jää epäselväksi."
        - "Vastaus selittää, että kappale kelluu, kun noste kannattelee
           sen painon."

tests:                        # golden sample answers, see below
  - name: taysi-vastaus
    answer: |
      ...
    expect:
      noste: 2                # or a list of acceptable levels: [1, 2]

feedback: |
  Worked explanation, shown after the attempt.
```

The mark is Σlevel/Σmax, computed in PHP — the criterion levels are the
only thing the model decides. Three levels is the intended default
(absent / partial / met); two make a strict met-or-not criterion.
Descriptors must be observable ("mainitsee X"), not mental-state
("ymmärtää X").

`scaffold:` is the scaffold-then-fade support (formatted like `stem`):
when present, it is shown above the answer box while the student is
answering — a suggested structure, typically mirroring the rubric criteria
without giving the answer away. It is purely presentational: the grader
model never sees it. A question without `scaffold` shows a plain answer
box. Each quiz can override the level in its settings ("AI text
questions"), forcing the skeleton on or off for every aitext question in
that quiz.

`tests:` are the aitext analogue of STACK question tests: each sample
answer is run through the real grading pipeline and the criterion levels
the model chose are compared against `expect:`. Because a live model call
is involved, evaluation costs API money and is not perfectly
deterministic: use a list of acceptable levels for genuinely borderline
answers, and keep single expected values for the clear-cut ones.

## Quiz source format

A file containing a `questions:` key is a quiz spec rather than a question.

```yaml
id: physics-exam-01
name: "Physics practice exam 1"
intro: |
  Prose shown on the quiz front page.
behaviour: adaptive             # see below
grade: 10                       # default 10; 0 = ungraded, no gradebook item
questionsperpage: 1
attempts: 0                     # 0 = unlimited
grademethod: highest            # highest | average
review:                         # see below; the values shown are the defaults
  during: [correctness, marks, specificfeedback]
  after: [attempt, correctness, marks, specificfeedback,
          generalfeedback, overallfeedback]

questions:
  - id: motion-average-speed-01
  - id: motion-distance-02
    maxmark: 2                  # default 1
  - random: 5                   # a random slot: draw 5 per attempt
    tags: [drilli, liike]       # AND: a question must carry all of them
    category: [Fysiikka, Liike] # this category and everything below it
    maxmark: 1                  # default 1
```

A `random:` entry is a random slot: each attempt draws that many questions
from the bank among those matching the selectors — `tags:` (all of them),
`category:` (the named path and everything below it), or both; at least one
is required. A question already used earlier in the same attempt, explicit
slots included, is never drawn again, so the matching pool must cover the
overlapping explicit slots plus every draw: Moodle refuses to start an
attempt on an exhausted pool. A draw larger than the pool is refused twice
before that, by the compiler against the compiled tree and by
`build-quiz.php` against the actual bank.

`grade: 0` makes the quiz ungraded: no gradebook item is created, so there is
no hidden mark for the student to go and find. That is the drill recipe —
ungraded, unlimited attempts, `correctness` for the right/wrong verdict and no
`marks` in either review list, which is what keeps the numbers off the screen.
With `attempts: 0` and `grade: 0` the `grademethod` is meaningless; leave it at
its default.

Two variants, by what the question set is:

```yaml
# Hint ladder: interactive gives hints + 1 tries, escalating the support
# after each failed try, and "Try another question like this one" redraws a
# variant.  See qbank/fixtures/quizzes/tulkintadrilli.yaml.
behaviour: interactive
grade: 0
attempts: 0
review:
  during: [correctness, specificfeedback]
  after: [attempt, correctness, specificfeedback, generalfeedback]
questions:
  - id: liike-kiihtyvyys-01
```

```yaml
# Multiple choice: check once, see the feedback, move on -- free retries
# would make clicking through the options a winning strategy.  A random slot
# over the drill tags makes each attempt a different set.  See
# qbank/fixtures/quizzes/drillikoe.yaml.
behaviour: immediatefeedback
grade: 0
attempts: 0
review:
  during: [correctness, specificfeedback]
  after: [attempt, correctness, specificfeedback, generalfeedback]
questions:
  - random: 5
    tags: [drilli]
```

`behaviour: adaptive` is what makes STACK grade each part of a question on its
own as the student presses *Check* — which is what the interpretation scaffold
needs. (STACK swaps in its `adaptivemultipart` behaviour internally; that name
cannot be given here, as Moodle only accepts archetypal behaviours.) It also
lets the student revise an answer and check again, against a penalty. Under
`immediatefeedback` the answer locks on the first *Check*: for an MCQ, free
retries would make clicking through the options a winning strategy, so the
retry is the next attempt at the whole quiz, on a fresh variant.
`interactive` gives hints + 1 tries, revealing one hint per failed try (see
[Hints](#hints)), and — like `immediatefeedback`, and unlike `adaptive` —
finishes each question during the attempt, which is what puts *Try another
question like this one* on the page. A question with no hints gets one try
under it, as under `immediatefeedback`.

`review:` says what the student is shown: `during` while answering, `after`
when looking at a submitted attempt. Each takes `all` or a list drawn from
`attempt`, `correctness`, `marks`, `specificfeedback`, `generalfeedback`,
`rightanswer`, `overallfeedback` (`marks` covers both the maximum and the
earned mark). The defaults make *Check* visibly grade the answer and explain
the reading it came from, while the model solution stays hidden until the
attempt is submitted. `rightanswer` is off by default even after submission:
Moodle renders a STACK teacher answer as raw Maxima (`(50*km)/h`), which only
confuses — the model solution in the general feedback presents the correct
answer properly typeset. `during: []` together with
`behaviour: deferredfeedback` gives a real-exam rehearsal in which nothing is
revealed until the attempt is handed in.

Rebuilding a quiz replaces its question list. If the quiz already has attempts,
the list is left alone and only its settings are updated.

## The CLI scripts

`qbank/cli/*.php` run inside the `moodle` container, where `qbank/` is
bind-mounted read-only at `/opt/qbank` and the build directory at
`/opt/qbank-build`. They live outside `$CFG->dirroot` so that the Moodle code
tree stays untouched and read-only.

Moodle 5.1 has no core CLI for importing questions, and the only maintained
alternative (`qbank_gitsync`) needs web services and tokens enabled on the site
and keeps a manifest that ties the content repo to one Moodle instance. These
scripts use the same `qformat_xml` importer the web UI uses, plus
`qbank_importasversion` for the new-version-of-an-existing-question case.
