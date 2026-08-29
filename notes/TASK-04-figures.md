# Task 4: Figures in questions

## Context and intent

The physics coverage map in `oivus-questions/suunnitelmat/01-fysiikka-kattavuuskartta.md`
marks four topics as needing a figure:

| Topic | Content area | What the figure is |
| --- | --- | --- |
| Liikekuvaajat | S5 | (s,t) and (v,t) plots of a motion |
| Virtapiirin kytkentäkaavio | S6 | circuit schematic |
| Valon heijastuminen ja taittuminen | S2 | ray diagram |
| Linssit ja kuvan muodostuminen | S2 | lens ray diagram |

None of these can be written today: the qbank compiler has no notion of a
figure, and nothing in the YAML source format refers to one.

This is not a peripheral gap. Motion graphs are core S5 material, they are
standard fare in the national exam, and — for this project specifically —
they are one of the richest sites of the misreading that the whole
interpretation ladder exists to train: *which* graph is this, and does the
answer come from the slope or from the area under the curve? A question bank
that cannot show a graph cannot train that.

This brief specifies requirements. It does not choose an implementation.

## What was verified before writing this brief

Read in the running container against the pinned STACK 4.13.0 / Moodle 5.1.6
tuple, 2026-08-28. Checked facts, not assumptions; re-verify if the pins move.

1. **STACK has a CASText plotting function.** `plot(ex, [ra])` is defined in
   `question/type/stack/stack/maxima/stackmaxima.mac:1034`, marked
   `/*stack_web_plot*/`. It is a Maxima function, so it sees the question's
   variables directly. Plot format is gnuplot
   (`set_plot_option([plot_format, gnuplot])` in the same file).
2. **It emits an `<img>` with alt text.** The function builds
   `<img src='...' alt='...' width='...'/>`, optionally wrapped in
   `<div class='stack_plot'>`.
3. **Alt text is author-settable but defaults to something unusable.** The
   default is `concat("STACK auto-generated plot of ", string(ex), " with
   parameters ", string(ral))` — English, and a dump of the Maxima
   expression. An `[alt, "..."]` option in the argument list overrides it,
   and a non-string alt raises a Maxima error.
4. **Other supported plot options**, read from the same function body:
   `[size, w, h]`, `grid2d` / `STACKGRID`, `[box, false]` / `nobox`,
   `[plottags, bool]`. Plotting more than two variables is a hard error.
   `discrete`, `parametric` and `contour` are recognised plot forms, so
   plotting measured points, not only functions, is available.
5. **Server-mode plotting works end to end** — *wrong, corrected during
   implementation.* The CAS round trip worked; the image did not survive it.
   `$CFG->dataroot/stack/` did not exist, because only `create_maximalocal()`
   creates it and that is reached only on a local Maxima install. The plot was
   written by the connector into a directory that was not there, silently, so
   every plot rendered as a broken image. Fixed in `stack-init.sh` (create the
   directories, and clear the CAS cache, which holds plot filenames that
   outlive the files) with an assertion in `smoke-tests.sh`. The original
   evidence below is otherwise accurate. `platform` is `server` and
   `plotcommand` is empty (`admin/cli/cfg.php --component=qtype_stack`).
   `stack/cas/connector.server.class.php` is documented as handling
   "transfer of the plots generated on possibly remote servlet", passes a
   `ploturlbase` parameter, and writes returned images to
   `$CFG->dataroot . "/stack/plots/"`. gnuplot 6.0 patchlevel 2 is present in
   the goemaxima container.
6. **Plot filenames are not deterministic.** The filename is built with
   `rand(10^8)`, so an image is a per-render artefact in moodledata, not a
   stable asset. Nothing to version, but also nothing a test can pin.
7. **STACK ships diagram blocks.** `stack/cas/castext2/blocks/` contains
   `jsxgraph.block.php` and `geogebra.block.php`, so a JS-driven diagram is
   available without adding a dependency.
8. **The compiler handles no figures of any kind.** `qbank/compiler/compile.py`
   contains no reference to images, files or base64.

## Two classes of figure, and why the distinction matters

**Class A — data-bearing.** The figure encodes the variant's numbers. Motion
graphs are the only current example. Here the figure must be generated from
the same `variables:` block that drives the stem. If the figure and the prose
can disagree, that is a grading defect, not a cosmetic one: the student would
be marked wrong for reading the picture correctly. STACK's `plot()` covers
this class and needs no new machinery beyond a way to write it in YAML.

**Class B — schematic.** Circuit and ray diagrams. Gnuplot draws functions,
not resistor symbols, so `plot()` is the wrong tool.

The obvious worry about class B is that resistor values or object distances
change per variant, which would force the diagram to be generated too. That
worry can be designed away, and should be: **put the schematic in the figure
and the numbers in the prose.** A circuit diagram labelled R1, R2, U with the
values given in the stem is what real exam papers do anyway, it is what the
student will meet, and it makes every class B figure genuinely static. This
should be a rule for content authors, not merely an implementation
convenience.

With that rule, class B reduces to "embed a fixed image", and no diagram
generator is needed.

## Requirements

**R1. Figure source is text, and lives with the question.**
`oivus-questions` stays a text repository: diffable, reviewable, no binaries
whose contents cannot be seen in a pull request. For class A this is the
Maxima expression. For class B, SVG is text and satisfies this; a PNG does
not.

**R2. A class A figure derives from the question's `variables:`.**
No constant may appear both in `variables:` and in the figure definition. The
compiler should make the duplicated-constant case impossible to write rather
than merely discouraged.

**R3. Author-supplied alt text is mandatory, in Finnish.**
STACK's default alt text is an English dump of a Maxima expression (fact 3).
Emitting that would be worse than nothing. The compiler must reject a figure
with no alt text, the same way it rejects other incomplete questions.

**R4. Every deployed seed must render.**
A figure that works for seed 161 and throws for seed 162 is exactly the
failure mode `seeds:` exists to catch. Figure rendering must be inside the
`./tools/qbank.sh all` gate, not merely visible in preview. Note fact 6:
the test can assert that the CAS produced an image without error, not that
the image is correct. Visual correctness stays a human preview step, and the
`README.md` preview checklist in `oivus-questions` should gain a figure item.

**R5. Figures must work at all three scaffold rungs and under both
behaviours.** A figure sits in the stem, so in principle nothing special
happens under `stated` / `choice` / `none`, nor between the exam behaviour
and TASK-03's drilling behaviour. "In principle" is not verification; the
fixture exam should cover it.

**R6. Decimal separator.** The content rules require a decimal comma in
Finnish prose. Gnuplot will tick an axis `2.5`. A graph whose axis contradicts
the stem next to it is precisely the kind of inconsistency this project exists
to remove, and it is the one requirement here with no obvious solution.
Options: a gnuplot locale or `set decimalsign`, post-processing the SVG, or
choosing plot ranges with integer ticks only. The last is a content
constraint rather than a fix, and may be the cheapest honest answer.

**R7. Interaction with `interpretation:`.** For the liikekuvaaja rows the
figure is *where the ambiguity lives*. It must be settled whether the
`interpretation.prompt` and the reading `label`s can refer to the figure, and
whether a reading may need its own figure — for instance, showing the student
what the area-under-the-curve reading would have meant. This is the one
requirement that touches the interpretation machinery rather than only the
compiler, and it is the one most likely to be underestimated.

**R8. No new binary formats in the content repo.** If class B needs asset
files, the compiler embeds them into the Moodle XML (`<file>` elements are
base64). Where the assets live and how they are referenced is a machinery
decision, but the content author must not be asked to manage a binary blob.

## Decisions taken (2026-08-29)

- **Class B route: static SVG**, embedded in the question XML as a base64
  `<file>` and referenced with `@@PLUGINFILE@@`. Not inline `<svg>`: that
  survives only the question render path, which sets `noclean`, and dies
  wherever the same text is cleaned. Not JSXGraph: with "labels in the
  figure, numbers in the prose" the diagram is static, so its one advantage
  does not apply, and a JavaScript dependency in the exam render path fails
  in a way the student cannot diagnose.
- **YAML: a `figure:` key**, thin, with static checks. `alt` plus exactly one
  of `plot` (class A) or `svg` (class B). The unchecked route is closed
  rather than left available: `{@plot(`, `<img` and `<svg` in any prose field
  are compile errors that name `figure:`.
- **R6: inject the decimal comma.** The compiler appends `set decimalsign
  ","` to `PLOT_TERM_OPT` in every question with a plot — STACK splices that
  setting verbatim into gnuplot's `set terminal` line, which is the only hook
  a question has into the preamble, and reading the site value rather than
  restating it keeps the font and line width. This depends on an internal
  STACK setting name, so the fragility is converted into a test: the figure
  gate fails if a tick label comes back with a decimal point. Verified live:
  ticks read `0 | 0,5 | 1 | 1,5 | 2`. The alternative — choosing ranges with
  integer ticks — was a content constraint, not a fix.
- **R7: the figure is stem-only.** It is emitted after the stem prose and
  before the scaffold, at every rung; a reading gets no figure of its own.
  Showing the student what the area-under-the-curve reading would have looked
  like is a feedback figure, which is already out of scope below, and it
  should follow the stem case rather than precede it.

## What was built

- `qbank/compiler/compile.py`: the `figure:` block, its validation (R2, R3,
  R8 and the prose bypass), `PLOT_TERM_OPT` injection, base64 embedding, and
  the schematic's hash in the build manifest.
- `qbank/cli/figure-test.php`, run by `tools/qbank.sh test`: renders every
  figure question at every deployed seed and checks each image exists, is a
  non-empty SVG, carries alt text and uses a decimal comma (R4).
- `qbank/tests/test_figures.py`: what the compiler emits and what it refuses.
- Fixtures: `matkakuvaaja-stated`, `virtapiiri-choice`, `nopeuskuvaaja-none`
  — both figure classes across all three rungs, in the fixture exam (R5).
- Docs: `qbank/README.md`; the content rules and preview checklist in
  `oivus-questions`; the coverage map's `kuv` rows are no longer blocked.

## Out of scope

- Interactive or manipulable figures (JSXGraph, GeoGebra as an input).
- Figures as answers: student-drawn graphs, dragging points.
- Figures in feedback rather than the stem. Likely wanted eventually —
  showing the correct graph next to the student's misreading is exactly the
  project's pedagogy — but it should follow the stem case, not precede it.

## Sequencing

After TASK-03. Content work in `oivus-questions` for the non-figure rows of
the coverage map can proceed in parallel and does not depend on this.
