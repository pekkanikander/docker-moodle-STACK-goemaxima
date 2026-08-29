# Task 5: Bind question versions to content-repo commits

## Context and intent

Real attempt history starts accumulating as soon as the content phase ends.
Attempts are the primary research record for the planned design-based-research
report (`oivus-questions/suunnitelmat/99-julkaisu.md`), and they are
unrecoverable if the provenance is not captured at the moment they are made.

The question is: given an attempt from six months ago, can we say **which
version of the source produced the question the student saw, and why it was
worded that way**?

Half of that is already solved, and the half that is missing is smaller than
it first looked.

## What was verified before writing this brief

Read against the pinned tuple in the running container, 2026-08-28.

1. **Moodle already binds an attempt to an exact question version.**
   `question_attempts.questionid` is a foreign key to `question.id`, and
   `question_versions` maps `(questionbankentryid, version) -> questionid`.
   Each edit produces a new row, and old rows are retained. **The wording the
   student saw is therefore already recoverable from the database.**
2. **The importer versions rather than overwrites.** Its header states it, and
   `import-questions.php:140` reports `updated {$idnumber}` on the path that
   creates a new Moodle question version, precisely so that attempt history
   against earlier versions survives.
3. **`question_attempts.variant` records which variant was drawn**, so the
   seed is recoverable too.
4. **Change detection is a cache, not a record.** `import-questions.php:99`
   takes `hash_file('sha256', $path)` of the *compiled XML* and stores it via
   `set_config()` under `qbank_state_key($bank, $idnumber)` (line 152). It is
   overwritten on every import, keeps no history, and hashes the build
   artefact rather than the YAML source.
5. **Nothing anywhere records a git commit, an import time, or the source
   path.** Grepping the compiler and both CLI scripts finds no reference.
6. **The compiler already emits question tags.** `compile.py:404-407` and
   `814-817` build a `<tags>` element from the source `tags:` list. Moodle
   question tags attach to `question.id`, i.e. to the version, so a tag is
   carried by exactly the object an attempt points at.
7. **The compiler can see the content repository.** `tools/qbank.sh:10` sets
   `QBANK_CONTENT_DIR` to a checkout of `oivus-questions` and exports it; the
   compiler runs on the host against that directory. The importer, by
   contrast, only sees `--source`, the build directory of generated XML.

## The actual gap

Not "which wording" — fact 1 settles that. The gap is:

- **No link from a question version to the content-repo commit.** The wording
  can be read out of the database, but not connected to the YAML source, the
  commit message that explains why it was changed, or the surrounding design
  reasoning. For a design-based-research report the commit *is* the design-cycle
  record; the database row without it is an artefact with no history.
- **No record of when a question was imported or what else went in with it.**
  A design cycle is a set of changes made together. Nothing groups them.
- **No integrity guarantee.** A commit SHA recorded from a dirty working tree
  is a false statement about what was imported.

## Requirements

**R1. Every imported question version carries the content-repo commit that
produced it.** It must be readable from an attempt without consulting anything
outside the Moodle database, because the database is what gets backed up,
restored and analysed.

**R2. Provenance is captured where the git working tree is visible.** By fact 7
that is the compiler, not the importer. The compiler stamps; the importer
carries what it is given and invents nothing.

**R3. A dirty working tree is recorded as such, and a production import
refuses.** A SHA that does not describe the bytes that were compiled is worse
than no SHA, because it will be believed. For local iteration a `-dirty`
marker is enough; for an import that will accumulate real attempts it must be
a hard stop.

**R4. Both repositories are recorded.** The wording comes from
`oivus-questions`, but the XML is what Moodle stores, and the compiler that
produced it lives here and changes. Two commits, not one.

**R5. Import runs are grouped and timestamped.** Enough to reconstruct "these
questions changed together on this date", which is the unit a design cycle is
reported in.

**R6. Provenance does not disturb the change-detection cache.** The hash at
fact 4 decides whether a question is re-imported. If a commit stamp lands
inside the hashed XML, every commit re-imports every question and creates a
spurious Moodle version for each — turning a fix for version tracking into a
generator of meaningless versions. This is the trap in this task and the one
thing most likely to be got wrong.

**R7. No new database tables.** A custom table means a Moodle plugin, an
install/upgrade path and a restore concern, for what is a few strings.

## Sketch of a satisfying design

Not a decision, but the cheapest route that meets all seven:

- The compiler stamps each question with a provenance tag, e.g.
  `src-<short-sha>`, alongside the tags it already emits (fact 6). Tags travel
  with the version, are queryable, and are visible in the bank UI.
- R6 is handled by excluding the provenance tag from the hash the importer
  compares, rather than by hashing the XML as a whole: hash the YAML source
  instead, which is what actually determines the content and is more honest
  than hashing the build artefact anyway.
- The compiler writes a manifest per build — content SHA, compiler SHA, dirty
  flag, timestamp, and the source path of every question — and the importer
  logs which manifest it applied. That covers R4 and R5 without a new table.
- `qbank.sh` grows a check that refuses a non-local import from a dirty tree
  (R3).

## Sequencing

**Before content production begins**, and therefore before TASK-03 and TASK-04
if they slip. This is small, and unlike them it has a deadline that is not
under our control: the value of doing it is zero once the attempts it was
meant to describe have already been recorded.

## Out of scope

- Extracting or anonymising attempt data for analysis. Separate concern,
  different data-protection class; see `99-julkaisu.md` in the content repo.
- Recording anything about the student.
