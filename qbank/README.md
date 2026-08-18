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
| `test`    | STACK's `bulktestall.php`, i.e. every question's own tests through Maxima |
| `all`     | all four, in that order |

Course and bank are taken from `QBANK_COURSE` and `QBANK_BANK` env vars
(defaults to `qbank` and `qbank-main`); both are created if missing.
Their display names come from `QBANK_COURSE_FULLNAME` and `QBANK_BANK_NAME`,
and are used only when creating them.

`import` also accepts `-n` (dry run) and `--force` (re-import unchanged files).

## What happens when a question changes

A question's identity is the `id:` field,
which becomes the Moodle `idnumber` of the question bank entry.
It must never change once a question has been attempted;
renaming `id:` reads as "delete one question, add another".

- **New `id`** — a question is created in the category given by `category:`.
- **Edited file, same `id`** — a *new Moodle version* is added to the existing
  bank entry. Earlier attempts keep pointing at the version they were made
  against, so attempt history stays intact and quizzes pick up the new version.
- **Unchanged file** — skipped. The importer stores a hash of each source file
  in `{config_plugins}` under the `qbankimport` plugin name and compares.
- **Deleted file** — reported as `stale`, never deleted at Moodle.
  Removing a question from Moodle would orphan attempt data, so that stays a manual decision.
- **Moved to another `category:`** — the question stays where Moodle has it.
  Categories are only used when creating a question.

Because the state lives in the Moodle instance and not in a manifest file,
the content repo is not coupled to any particular Moodle site: the same tree can be
imported into the local stack and into production independently.

Before importing, each file is put through STACK's own validation.
STACK otherwise saves an invalid question silently,
marked broken and invisible to students,
so the importer asks up front and refuses instead.

## Question source format

One question per file, anywhere under `questions/` in the content repo.
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
  boxsize: 8
  syntaxhint: "?*m/s"

feedback: |
  Worked solution, shown after the question is finished.
```

Prose fields (`stem`, `prompt`, `feedback`, `why`) take blank-line-separated
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
| `units`     | `UnitsRelative`| `0.01` |

Randomised questions must list `seeds:`. Without deployed seeds a question has
no fixed set of variants and its tests only ever exercise whichever one comes
up, so `tools/qbank.sh test` would not be a real gate.

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

Under `choice`, a student who picks the wrong reading and then computes
correctly for it scores 0 on the answer part.
That is a deliberate choice: the question is about the reading.

## Quiz source format

A file containing a `questions:` key is a quiz spec rather than a question.

```yaml
id: physics-exam-01
name: "Physics practice exam 1"
intro: |
  Prose shown on the quiz front page.
behaviour: adaptive             # see below
questionsperpage: 1
attempts: 0                     # 0 = unlimited
grademethod: highest            # highest | average

questions:
  - id: motion-average-speed-01
  - id: motion-distance-02
    maxmark: 2                  # default 1
```

`behaviour: adaptive` is what makes STACK grade each part of a question on its
own as the student presses *Check* — which is what the interpretation scaffold
needs. (STACK swaps in its `adaptivemultipart` behaviour internally; that name
cannot be given here, as Moodle only accepts archetypal behaviours.)

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
