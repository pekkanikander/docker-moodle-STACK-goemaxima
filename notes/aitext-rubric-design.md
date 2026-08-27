# Rubric design for the aitext drilling extension (Task 2, Feature 1)

What the rubric is, why it is shaped the way it is, and how it flows from
authoring to the student's screen. Companion to
`aitext-extension-architecture.md`; this is the review deliverable before
Feature 1 code.

## Why criterion-referenced, and why this shape

Four converging reasons, in decreasing order of weight:

1. **LLM reliability.** Holistic scoring ("give this essay 7/10") is the
   least reliable thing one can ask of a language model: noisy, prompt-
   sensitive, poorly calibrated. Judging a short answer against one explicit,
   observable descriptor ("does the answer state the units for every
   quantity?") is a much smaller judgement and empirically far more stable.
   The rubric decomposes one unreliable judgement into several reliable ones,
   and the arithmetic moves into PHP where it is exact.
2. **Formative value.** A number tells the student nothing actionable.
   Per-criterion feedback maps directly onto Hattie & Timperley's triad:
   the descriptors say where you are aiming (*feed up*), the achieved level
   plus evidence says how it went (*feed back*), and the next level's
   descriptor says what to do differently (*feed forward*) — the last one
   falls out of the structure for free, see Rendering below.
3. **Learner fit.** Explicit success criteria remove the "guess what the
   grader wants" layer — which is exactly the skill being trained
   *separately and deliberately* via the interpretation ladder, not
   something feedback should demand implicitly. A fixed, predictable
   feedback structure with literal language and no simulated emotion keeps
   the processing cost low; vague praise ("hyvä yritys!") is worse than
   silence.
4. **Exam realism.** Peruskoulu and YO grading is itself criterion-based
   (pisteytysohje: points are earned for specific, listed things). Drilling
   against a rubric teaches the meta-skill that answers earn points for
   identifiable features, not for overall impression.

## Rubric anatomy (authored side)

Authored in the question YAML in `oivus-questions`; the qbank compiler
validates the shape at compile time and emits canonical JSON into the
question XML; the fork stores it in a new `rubric` column. The Moodle edit
form gets only a validated JSON textarea — good enough for a single-author
workflow; a proper form UI is upstream-PR territory, later, maybe.

```yaml
rubric:
  criteria:
    - id: tulkinta                # stable slug; the JSON round-trip key
      title: "Tulkinta"           # short label the student sees
      levels:                     # index = points earned; observable wording
        - "Vastaus ei tunnista, että 'matka' tarkoittaa tässä reittiä pitkin."
        - "Tulkinta mainitaan, mutta laskussa käytetään silti suoraa etäisyyttä."
        - "Vastaus tunnistaa tulkinnan ja käyttää sitä johdonmukaisesti."
    - id: yksikot
      title: "Yksiköt"
      levels:
        - "Yksiköt puuttuvat tai ovat vääriä."
        - "Yksiköt esiintyvät, mutta epäjohdonmukaisesti."
        - "Kaikki suureet on ilmaistu yksiköineen."
```

Design decisions and their reasons:

- **Level index = points.** No separate weight field. A criterion with four
  levels (0–3) simply weighs more than one with three (0–2). Fewer knobs,
  and the arithmetic stays legible to a 15-year-old: your points are the
  levels you reached, added up. Mark fraction = Σlevel / Σmax, computed in
  PHP. The model's own `marks` number (upstream's mechanism) never reaches
  the gradebook.
- **Three levels as the default.** Binary loses "partially there", which is
  where most formative signal lives. Four or more reintroduces LLM noise:
  adjacent-level confusion grows quickly with scale length. Three is the
  compromise; the format permits more for the rare criterion that earns it.
- **Descriptors must be observable.** "Mainitsee oletuksen" (states the
  assumption), not "ymmärtää oletuksen" (understands it). This is what makes
  the LLM judgement small and checkable, and it is also what makes the
  feedback literal rather than mind-reading.
- **2–5 criteria per question.** Below two, use a plain STACK question;
  above five, the question is doing too much for one drill item.
- **Interpretation is a convention, not a type.** An interpretation-training
  question simply makes its first criterion the reading itself (as
  `tulkinta` above). This composes with the existing qbank scaffolding
  ladder: at `stated` the intended reading is in the question text and the
  criterion checks it was *used*; at `none` the criterion checks it was
  *identified*. No special machinery in the rubric code.
- **`rubric` and upstream's freetext `markscheme` are mutually exclusive**;
  the compiler refuses a question with both. All gating in the fork is
  "rubric present?", keeping vanilla behaviour byte-identical.

## What the model is asked to return

The prompt (built by extending `build_template_prompt()`) contains: the
question text, the sample answer, the criteria with their descriptors and
indices, the student's answer, and a JSON-only instruction with the exact
response schema:

```json
{
  "criteria": [
    {
      "id": "yksikot",
      "level": 1,
      "evidence": ["nopeus oli 5"],
      "comment": "Nopeudelle puuttuu yksikkö; ajalle se on annettu."
    }
  ],
  "next_step": "Kirjoita jokaisen suureen perään sen yksikkö."
}
```

**Evidence quotes are the load-bearing novelty.** For every criterion above
the lowest level, the model must copy verbatim the span(s) of the student's
answer its judgement rests on. Three purposes:

1. *Hallucination tripwire.* PHP checks each quote is a substring of the
   answer (whitespace-normalised). A model that grades a text it imagined
   fails validation mechanically — no judgement call needed.
2. *Checkability for the student.* "This sentence is why" is literal and
   verifiable; the student can look at the quoted span and agree or
   disagree — and disagreement has a concrete referent for the flag button
   (Feature 4).
3. *Grounding.* Forcing the model to locate its evidence before judging
   measurably improves judgement quality; it is chain-of-thought with a
   verifiable artefact.

Validation is fail-closed, in order: parses as a single JSON object
(upstream's `extract_single_json_object()` is reusable); criterion ids are
exactly the authored set, each once; each level is an integer within that
criterion's range; evidence quotes substring-match; length caps on
`comment` and `next_step`. Any failure → needs-grading state, a neutral
"arviointi ei onnistunut, opettaja katsoo tämän" message, and an automatic
flag. Raw model text is never shown (upstream shows it on parse failure;
that is the main surgery point).

The fixed Mustache template renders only known fields, so unexpected extra
JSON is ignored rather than rejected — strictness where it protects the
mark, tolerance where it only protects tidiness.

**On the per-criterion `comment`:** the alternative — showing only the
authored descriptor for the achieved level — would be fully deterministic
but generic: it cannot reference what the student actually wrote. The
model comment is adaptive but is unvetted AI prose. Chosen mitigations:
hard length cap, rendering inside the fixed template visually marked as AI
text, the flag button adjacent, and the framing banner (Feature 5). If the
comments prove distracting in practice, dropping them is a template change,
not a schema change.

## Rendering (student side)

One fixed Mustache template, identical structure for every question, every
time — predictability is a feature in itself here:

1. AI framing banner (Feature 5): non-dismissable, names the model, states
   that the assessment is machine-made and can be wrong.
2. Per criterion, in authored order: title; achieved-level descriptor with
   a level badge; evidence quote(s) in quotation styling; the AI comment,
   visually marked as AI text; and for any criterion below its top level,
   the **next level's descriptor** as "seuraavaksi:" — the improvement hint
   is authored text, not AI text, and costs nothing.
3. The overall `next_step`.
4. Marks block, per grading mode.
5. Flag button (Feature 4, when the companion plugin is installed).

**The grading progression (Feature 3) becomes purely presentational.** The
same validated JSON supports all three display modes with template
conditionals only, no grading-code branches:

- *none*: criteria, descriptors, evidence — no numbers anywhere;
- *coarse*: a three-way badge per criterion (achieved / partly / not) — no
  arithmetic shown;
- *fine*: points per criterion and the total.

Similarly `double_run`: two independent model calls yield two level
judgements *per criterion*. Criteria where the runs disagree are rendered
with an explicit "epävarma" marker, and the mark records the lower level
(conservative; disagreement should never inflate). This is *real* measured
unreliability shown honestly — which raises the question whether the task
brief's `fuzz` mode (artificial seeded noise) still earns its place:
genuine disagreement is honest, simulated noise is theatre. Proposal: build
`double_run`, defer `fuzz`, decide on evidence.

Student-facing text: descriptors and titles are authored in Finnish; the
prompt instructs the model to write `comment`/`next_step` in the language
of the descriptors; template labels come from lang strings (fi + en).

## What this does *not* try to do

- No adaptive rubrics, no model-generated criteria: the criteria are the
  pedagogy and stay under version control in `oivus-questions`.
- No teaching the model to compute: it only ever selects level indices and
  copies quotes.
- No persuasion that the AI is right. The design goal is trust
  *calibration*: evidence quotes, uncertainty markers and the flag button
  all frame the AI's judgement as evidence to weigh, not verdict to accept.

## Decisions (review 2026-08-27)

1. Three levels as the default, with proper support for strict two-level
   (met / not met) criteria.
2. Model free-text comments from the start — they are a main point of the
   exercise. Additionally, fully free-form feedback *alongside* the graded
   rubric is to be trialled later; expect prompt-engineering work.
3. & 4. `double_run` and `fuzz` are both experiments; whether either is
   really included is decided later, on evidence.
5. Student-facing language follows the question's `language` field.

Fixture: `qbank/fixtures/questions/selitys/kelluminen.yaml` (source format
in `qbank/README.md`); the compiler validates aitext sources now and
compiles them once the extension lands.
