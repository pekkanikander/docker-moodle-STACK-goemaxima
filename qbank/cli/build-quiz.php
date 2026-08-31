<?php
// Create or refresh a quiz from a compiled quiz spec (JSON), taking its
// questions from a question bank activity by their idnumbers. A spec entry
// may also be a random slot, drawing from the bank by category and/or tags.

require_once(__DIR__ . '/lib.php');
require_once($CFG->dirroot . '/mod/quiz/locallib.php');

use mod_quiz\question\bank\filter\custom_category_condition;

/**
 * Resolve a random-slot entry against the bank: the category path and tag
 * names become ids, and the pool is counted, returning the filter condition
 * to persist. Moodle throws notenoughrandomquestions at attempt start when a
 * pool runs dry, which is the wrong moment to find out; the compiler has
 * checked the compiled tree, this checks the actual bank.
 */
function qbank_random_slot(context_module $bankcontext, array $entry, string $bankname): array {
    global $DB;

    // No category in the spec means the whole bank: its top category with
    // subcategories included, which is also how a named category matches the
    // questions below it.
    $category = question_get_top_category($bankcontext->id, true);
    foreach ($entry['category'] ?? [] as $name) {
        $category = $DB->get_record('question_categories', [
            'contextid' => $bankcontext->id,
            'parent' => $category->id,
            'name' => $name,
        ]);
        if (!$category) {
            cli_error("Random slot: category '{$name}' does not exist in bank '{$bankname}'.");
        }
    }

    $filter = [
        'category' => [
            'jointype' => custom_category_condition::JOINTYPE_DEFAULT,
            'values' => [$category->id],
            'filteroptions' => ['includesubcategories' => true],
        ],
    ];

    if (!empty($entry['tags'])) {
        $known = [];
        foreach (\core_tag_tag::get_tags_by_area_in_contexts('core_question', 'question', [$bankcontext]) as $tag) {
            $known[$tag->name] = $tag->id;
        }
        $tagids = [];
        foreach ($entry['tags'] as $name) {
            $normalised = core_text::strtolower($name);
            if (!isset($known[$normalised])) {
                cli_error("Random slot: no question in bank '{$bankname}' is tagged '{$name}'.");
            }
            $tagids[] = $known[$normalised];
        }
        $filter['qtagids'] = [
            'jointype' => \qbank_tagquestion\tag_condition::JOINTYPE_DEFAULT,
            'values' => $tagids,
        ];
    }

    $loader = new \core_question\local\bank\random_question_loader(new qubaid_list([]));
    $pool = $loader->count_filtered_questions($filter);
    if ($pool < $entry['random']) {
        cli_error("Random slot draws {$entry['random']} but only {$pool} question(s) "
            . "in bank '{$bankname}' match its selectors.");
    }

    return [
        'count' => (int) $entry['random'],
        'filtercondition' => [
            'qpage' => 0,
            'cat' => "{$category->id},{$bankcontext->id}",
            'qperpage' => 100,
            'tabname' => 'questions',
            'sortdata' => [],
            'filter' => $filter,
        ],
    ];
}

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

// Resolve every question and random-slot pool up front, so a typo in the
// spec fails before we create anything.
$entries = [];
foreach ($spec['questions'] as $entry) {
    if (isset($entry['random'])) {
        $entries[] = [qbank_random_slot($bankcontext, $entry, $options['bank']), (float) $entry['maxmark']];
        continue;
    }
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

// The review* bitmasks cannot be given directly: quiz_process_options()
// rebuilds them from these form-checkbox fields, and any field left unset
// turns that option off. 'marks' in the spec covers both Moodle fields.
$review = [];
foreach ($spec['review'] as $phase => $parts) {
    $times = $phase === 'during' ? ['during'] : ['immediately', 'open', 'closed'];
    foreach ($parts as $part) {
        foreach ($part === 'marks' ? ['maxmarks', 'marks'] : [$part] as $field) {
            foreach ($times as $time) {
                $review[$field . $time] = 1;
            }
        }
    }
}

$moduleinfo = (object) array_merge((array) get_config('quiz'), $review, [
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
    'grade' => $spec['grade'],
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
    if (is_array($entry)) {
        // A random slot. The structure is re-created per call because the
        // explicit adds beside it bypass it and would leave it stale.
        $structure = \mod_quiz\quiz_settings::create($quiz->id)->get_structure();
        $structure->add_random_questions(0, $entry['count'], $entry['filtercondition']);
        if ($maxmark != 1.0) {
            // Random slots always insert with maxmark 1. No attempts exist
            // (checked above), so the field can be set directly; the sum is
            // recomputed below.
            $slots = $DB->get_records('quiz_slots', ['quizid' => $quiz->id],
                'slot DESC', 'id', 0, $entry['count']);
            foreach ($slots as $slot) {
                $DB->set_field('quiz_slots', 'maxmark', $maxmark, ['id' => $slot->id]);
            }
        }
        continue;
    }
    $questionid = qbank_latest_questionid($entry->id);
    quiz_add_quiz_question($questionid, $quiz, 0, $maxmark);
}

\mod_quiz\quiz_settings::create($quiz->id)->get_grade_calculator()->recompute_quiz_sumgrades();
rebuild_course_cache($course->id, true);

cli_writeln('Questions: ' . count($entries));
