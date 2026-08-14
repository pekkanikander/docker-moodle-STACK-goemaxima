<?php
// Create or refresh a quiz from a compiled quiz spec (JSON), taking its
// questions from a question bank activity by their idnumbers.

require_once(__DIR__ . '/lib.php');
require_once($CFG->dirroot . '/mod/quiz/locallib.php');

[$options, $unrecognised] = cli_get_params([
    'spec' => '',
    'course' => '',
    'bank' => '',
    'help' => false,
], [
    'h' => 'help',
]);

if ($unrecognised) {
    cli_error('Unrecognised options: ' . implode(', ', $unrecognised));
}

if ($options['help'] || $options['spec'] === '' || $options['course'] === '' || $options['bank'] === '') {
    echo <<<EOL
Create or refresh a quiz from a compiled quiz spec.

Options:
  --spec=FILE           Compiled quiz spec, as written by the compiler (required).
  --course=SHORTNAME    Course the quiz lives in (required).
  --bank=IDNUMBER       Question bank activity to take the questions from (required).
  -h, --help            Show this help.

EOL;
    exit($options['help'] ? 0 : 1);
}

if (!is_readable($options['spec'])) {
    cli_error("Spec not readable: {$options['spec']}");
}

$spec = json_decode(file_get_contents($options['spec']), true);
if (!is_array($spec)) {
    cli_error("Spec is not valid JSON: {$options['spec']}");
}

qbank_become_admin();

$course = $DB->get_record('course', ['shortname' => $options['course']], '*', MUST_EXIST);
$bank = qbank_ensure_bank($course, $options['bank'], $options['bank']);
$bankcontext = context_module::instance($bank->id);

// Resolve every question up front, so a typo in the spec fails before we
// create anything.
$entries = [];
foreach ($spec['questions'] as $entry) {
    $found = qbank_find_entry($bankcontext->id, $entry['id']);
    if (!$found) {
        cli_error("Question '{$entry['id']}' is not in bank '{$options['bank']}'; import the questions first.");
    }
    $entries[] = [$found, (float) $entry['maxmark']];
}

$module = $DB->get_record('modules', ['name' => 'quiz'], '*', MUST_EXIST);
$cmid = $DB->get_field('course_modules', 'id', [
    'course' => $course->id,
    'module' => $module->id,
    'idnumber' => $spec['id'],
]);

$moduleinfo = (object) array_merge((array) get_config('quiz'), [
    'modulename' => 'quiz',
    'module' => $module->id,
    'course' => $course->id,
    'section' => 0,
    'visible' => 1,
    'cmidnumber' => $spec['id'],
    'idnumber' => $spec['id'],
    'name' => $spec['name'],
    'introeditor' => ['text' => $spec['intro'], 'format' => FORMAT_HTML, 'itemid' => 0],
    'preferredbehaviour' => $spec['behaviour'],
    'questionsperpage' => $spec['questionsperpage'],
    'attempts' => $spec['attempts'],
    'grademethod' => $spec['grademethod'] === 'highest' ? QUIZ_GRADEHIGHEST : QUIZ_GRADEAVERAGE,
    'grade' => 10,
    'sumgrades' => 0,
    'timeopen' => 0,
    'timeclose' => 0,
    'timelimit' => 0,
    'overduehandling' => 'autosubmit',
    'graceperiod' => 0,
    'canredoquestions' => 1,
    'attemptonlast' => 0,
    'shuffleanswers' => 1,
    'navmethod' => 'free',
    'password' => '',
    'subnet' => '',
    'browsersecurity' => '-',
    'delay1' => 0,
    'delay2' => 0,
    'showuserpicture' => 0,
    'showblocks' => 0,
    'completionattemptsexhausted' => 0,
    'completionminattempts' => 0,
    'allowofflineattempts' => 0,
]);

if ($cmid) {
    $cmrecord = get_coursemodule_from_id('quiz', $cmid, 0, false, MUST_EXIST);
    $moduleinfo->coursemodule = $cmid;
    $moduleinfo->instance = $cmrecord->instance;
    update_moduleinfo($cmrecord, $moduleinfo, $course);
    cli_writeln("Quiz:    {$spec['id']} (cmid {$cmid}, updated)");
} else {
    $moduleinfo = add_moduleinfo($moduleinfo, $course);
    $cmid = $moduleinfo->coursemodule;
    cli_writeln("Quiz:    {$spec['id']} (cmid {$cmid}, created)");
}

$quiz = $DB->get_record('quiz', ['id' => get_fast_modinfo($course)->get_cm($cmid)->instance], '*', MUST_EXIST);

if ($DB->record_exists('quiz_attempts', ['quiz' => $quiz->id])) {
    cli_writeln('Quiz has attempts; leaving its questions alone.');
    exit(0);
}

// No attempts yet, so the slot list can safely be rebuilt from the spec.
$structure = \mod_quiz\quiz_settings::create($quiz->id)->get_structure();
foreach ($structure->get_slots() as $slot) {
    $structure->remove_slot($slot->slot);
}

foreach ($entries as [$entry, $maxmark]) {
    $questionid = qbank_latest_questionid($entry->id);
    quiz_add_quiz_question($questionid, $quiz, 0, $maxmark);
}

\mod_quiz\quiz_settings::create($quiz->id)->get_grade_calculator()->recompute_quiz_sumgrades();
rebuild_course_cache($course->id, true);

cli_writeln('Questions: ' . count($entries));
