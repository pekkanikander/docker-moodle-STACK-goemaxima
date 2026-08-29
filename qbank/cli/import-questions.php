<?php
// Import a tree of Moodle XML question files into a question bank activity.
//
// Questions are identified by their <idnumber>. A question whose idnumber is
// not in the bank yet is created; one that is already there gets a new Moodle
// question version, so that attempt history against earlier versions survives.
// Files whose contents have not changed since the last import are skipped.
//
// The provenance of the build comes from the compiler's manifest: the commits
// the questions were made from are recorded per run, and each question carries
// the content commit as a tag, which the compiler stamped and this script only
// passes on.

require_once(__DIR__ . '/lib.php');

[$options, $unrecognised] = cli_get_params([
    'source' => '',
    'manifest' => '',
    'course' => '',
    'course-fullname' => '',
    'bank' => '',
    'bank-name' => '',
    'dry-run' => false,
    'force' => false,
    'allow-dirty' => false,
    'help' => false,
], [
    'h' => 'help',
    'n' => 'dry-run',
]);

if ($unrecognised) {
    cli_error('Unrecognised options: ' . implode(', ', $unrecognised));
}

if ($options['help'] || $options['source'] === '' || $options['manifest'] === ''
        || $options['course'] === '' || $options['bank'] === '') {
    echo <<<EOL
Import Moodle XML questions into a question bank activity.

Options:
  --source=DIR          Directory tree of .xml files to import (required).
  --manifest=FILE       Build manifest written by the compiler (required).
  --course=SHORTNAME    Course shortname; created if missing (required).
  --course-fullname=S   Full name to use when creating the course.
  --bank=IDNUMBER       Question bank activity idnumber; created if missing (required).
  --bank-name=NAME      Display name to use when creating the bank.
  -n, --dry-run         Report what would happen, change nothing.
  --force               Re-import questions even if the source file is unchanged.
  --allow-dirty         Import a build made from an uncommitted tree.
  -h, --help            Show this help.

EOL;
    exit($options['help'] ? 0 : 1);
}

$source = rtrim($options['source'], '/');
if (!is_dir($source)) {
    cli_error("Source directory not found: {$source}");
}

$manifest = qbank_read_manifest($options['manifest']);

// A commit recorded from a tree with uncommitted or untracked changes, or from
// no git checkout at all, does not describe the bytes that were compiled, and
// a wrong provenance is worse than none because it will be believed. Local
// iteration passes --allow-dirty and keeps the -dirty marker in the tag; a
// site that accumulates real attempts does not.
if (!$options['allow-dirty']) {
    $problems = [];
    foreach (['content' => $manifest->content, 'compiler' => $manifest->compiler] as $name => $tree) {
        if ($tree->commit === '') {
            $problems[] = "the {$name} tree is not a git checkout";
        } else if ($tree->dirty) {
            $problems[] = "the {$name} tree had uncommitted changes";
        }
    }
    if ($problems) {
        cli_error("Refusing to import: " . implode(', ', $problems)
            . ".\nCommit the changes and recompile, or pass --allow-dirty for a throwaway site.");
    }
}

qbank_become_admin();

$course = qbank_ensure_course($options['course'], $options['course-fullname'] ?: $options['course']);
$cm = qbank_ensure_bank($course, $options['bank'], $options['bank-name'] ?: $options['bank']);
$context = context_module::instance($cm->id);

cli_writeln("Course:  {$course->shortname} (id {$course->id})");
cli_writeln("Bank:    {$options['bank']} (cmid {$cm->id}, context {$context->id})");
cli_writeln("Source:  {$source}");
cli_writeln("Content: {$manifest->content->tag}, compiled "
    . ($manifest->compiler->commit === '' ? 'by an unversioned compiler' : "by {$manifest->compiler->commit}"
        . ($manifest->compiler->dirty ? ' (dirty)' : ''))
    . " at {$manifest->builtat}");

$files = qbank_xml_files($source);
if (!$files) {
    cli_error("No .xml files found under {$source}");
}

$created = [];
$updated = [];
$skipped = 0;
$errors = [];
$seen = [];

foreach ($files as $relative) {
    $path = "{$source}/{$relative}";
    $question = qbank_read_single_question($path);
    if (is_string($question)) {
        $errors[] = "{$relative}: {$question}";
        continue;
    }

    $idnumber = trim((string) $question->idnumber);
    if ($idnumber === '') {
        $errors[] = "{$relative}: <idnumber> is empty; every question needs a stable idnumber";
        continue;
    }
    if (isset($seen[$idnumber])) {
        $errors[] = "{$relative}: idnumber '{$idnumber}' already used by {$seen[$idnumber]}";
        continue;
    }
    $seen[$idnumber] = $relative;

    $validationerrors = qbank_stack_validation_errors($path);
    if ($validationerrors !== '') {
        $errors[] = "{$relative}: {$validationerrors}";
        continue;
    }

    $categorypath = array_values(array_filter(explode('/', dirname($relative)), fn($part) => $part !== '.'));
    $hash = qbank_content_hash($path);
    $statekey = qbank_state_key($options['bank'], $idnumber);
    $entry = qbank_find_entry($context->id, $idnumber);

    if ($entry && !$options['force'] && get_config(QBANK_STATE_PLUGIN, $statekey) === $hash) {
        $skipped++;
        continue;
    }

    if ($options['dry-run']) {
        cli_writeln(($entry ? 'would update  ' : 'would create  ') . $idnumber);
        if ($entry) {
            $updated[] = $idnumber;
        } else {
            $created[] = $idnumber;
        }
        continue;
    }

    $qformat = new qformat_xml();
    $qformat->setCourse($course);
    $qformat->setContexts([$context]);
    $qformat->setFilename($path);
    $qformat->setRealfilename($relative);
    $qformat->setMatchgrades('error');
    $qformat->setCatfromfile(false);
    $qformat->setContextfromfile(false);
    $qformat->setStoponerror(true);
    $qformat->set_display_progress(false);

    if ($entry) {
        // Existing question: add a new version to the same bank entry, keeping
        // it wherever the bank has it, rather than creating a second entry.
        $qformat->setCategory($DB->get_record(
            'question_categories',
            ['id' => $entry->questioncategoryid],
            '*',
            MUST_EXIST
        ));
        $existing = question_bank::load_question(qbank_latest_questionid($entry->id));
        $result = \qbank_importasversion\importer::import_file($qformat, $existing, $path);
        if ($result !== true && !empty($result->error)) {
            $errors[] = "{$relative}: {$result->error}";
            continue;
        }
        cli_writeln("updated  {$idnumber}");
        $updated[] = $idnumber;
    } else {
        $qformat->setCategory(qbank_ensure_category($context->id, $categorypath));
        if (!$qformat->importpreprocess() || !$qformat->importprocess() || !$qformat->importpostprocess()) {
            $errors[] = "{$relative}: import failed";
            continue;
        }
        cli_writeln("created  {$idnumber}");
        $created[] = $idnumber;
    }

    set_config($statekey, $hash, QBANK_STATE_PLUGIN);
}

// Questions that exist in the bank but no longer in the source tree are only
// reported: deleting them would orphan any attempt data that refers to them.
$stale = $DB->get_fieldset_sql(
    "SELECT qbe.idnumber
       FROM {question_bank_entries} qbe
       JOIN {question_categories} qc ON qc.id = qbe.questioncategoryid
      WHERE qc.contextid = :contextid AND qbe.idnumber IS NOT NULL",
    ['contextid' => $context->id]
);
foreach (array_diff($stale, array_keys($seen)) as $idnumber) {
    cli_writeln("stale    {$idnumber} (in the bank, not in the source tree)");
}

// The questions that changed in one run are the ones changed together, which
// is the unit a design cycle is reported in. Record them with the commits they
// came from and the source file of each, so that "these questions changed on
// this date, from this commit" survives in the database that gets backed up.
if (!$options['dry-run'] && ($created || $updated)) {
    $paths = array_column($manifest->questions, 'source', 'id');
    qbank_record_run([
        'bank' => $options['bank'],
        'builtat' => $manifest->builtat,
        'content' => $manifest->content,
        'compiler' => $manifest->compiler,
        'created' => array_intersect_key($paths, array_flip($created)),
        'updated' => array_intersect_key($paths, array_flip($updated)),
        'unchanged' => $skipped,
    ]);
}

cli_writeln('created ' . count($created) . ', updated ' . count($updated)
    . ", unchanged {$skipped}, failed " . count($errors));

if ($errors) {
    cli_error("Import errors:\n  " . implode("\n  ", $errors));
}
