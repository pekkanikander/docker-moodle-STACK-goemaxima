<?php
// Import a tree of Moodle XML question files into a question bank activity.
//
// Questions are identified by their <idnumber>. A question whose idnumber is
// not in the bank yet is created; one that is already there gets a new Moodle
// question version, so that attempt history against earlier versions survives.
// Files whose contents have not changed since the last import are skipped.

require_once(__DIR__ . '/lib.php');

[$options, $unrecognised] = cli_get_params([
    'source' => '',
    'course' => '',
    'course-fullname' => '',
    'bank' => '',
    'bank-name' => '',
    'dry-run' => false,
    'force' => false,
    'help' => false,
], [
    'h' => 'help',
    'n' => 'dry-run',
]);

if ($unrecognised) {
    cli_error('Unrecognised options: ' . implode(', ', $unrecognised));
}

if ($options['help'] || $options['source'] === '' || $options['course'] === '' || $options['bank'] === '') {
    echo <<<EOL
Import Moodle XML questions into a question bank activity.

Options:
  --source=DIR          Directory tree of .xml files to import (required).
  --course=SHORTNAME    Course shortname; created if missing (required).
  --course-fullname=S   Full name to use when creating the course.
  --bank=IDNUMBER       Question bank activity idnumber; created if missing (required).
  --bank-name=NAME      Display name to use when creating the bank.
  -n, --dry-run         Report what would happen, change nothing.
  --force               Re-import questions even if the source file is unchanged.
  -h, --help            Show this help.

EOL;
    exit($options['help'] ? 0 : 1);
}

$source = rtrim($options['source'], '/');
if (!is_dir($source)) {
    cli_error("Source directory not found: {$source}");
}

qbank_become_admin();

$course = qbank_ensure_course($options['course'], $options['course-fullname'] ?: $options['course']);
$cm = qbank_ensure_bank($course, $options['bank'], $options['bank-name'] ?: $options['bank']);
$context = context_module::instance($cm->id);

cli_writeln("Course:  {$course->shortname} (id {$course->id})");
cli_writeln("Bank:    {$options['bank']} (cmid {$cm->id}, context {$context->id})");
cli_writeln("Source:  {$source}");

$files = qbank_xml_files($source);
if (!$files) {
    cli_error("No .xml files found under {$source}");
}

$created = 0;
$updated = 0;
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
    $hash = hash_file('sha256', $path);
    $statekey = qbank_state_key($options['bank'], $idnumber);
    $entry = qbank_find_entry($context->id, $idnumber);

    if ($entry && !$options['force'] && get_config(QBANK_STATE_PLUGIN, $statekey) === $hash) {
        $skipped++;
        continue;
    }

    if ($options['dry-run']) {
        cli_writeln(($entry ? 'would update  ' : 'would create  ') . $idnumber);
        $entry ? $updated++ : $created++;
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
        $updated++;
    } else {
        $qformat->setCategory(qbank_ensure_category($context->id, $categorypath));
        if (!$qformat->importpreprocess() || !$qformat->importprocess() || !$qformat->importpostprocess()) {
            $errors[] = "{$relative}: import failed";
            continue;
        }
        cli_writeln("created  {$idnumber}");
        $created++;
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

cli_writeln("created {$created}, updated {$updated}, unchanged {$skipped}, failed " . count($errors));

if ($errors) {
    cli_error("Import errors:\n  " . implode("\n  ", $errors));
}
