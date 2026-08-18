<?php
// Shared bootstrap and helpers for the qbank CLI scripts.
//
// These scripts run inside the Moodle container, where this repo's qbank/
// directory is bind-mounted at /opt/qbank. They are deliberately outside
// $CFG->dirroot so that the Moodle code tree stays untouched.

define('CLI_SCRIPT', true);

require(getenv('MOODLE_CONFIG_PHP') ?: '/var/www/html/config.php');
require_once($CFG->libdir . '/clilib.php');
require_once($CFG->libdir . '/questionlib.php');
require_once($CFG->dirroot . '/course/lib.php');
require_once($CFG->dirroot . '/course/modlib.php');
require_once($CFG->dirroot . '/question/format.php');
require_once($CFG->dirroot . '/question/format/xml/format.php');
require_once($CFG->dirroot . '/question/bank/importasversion/classes/importer.php');
require_once($CFG->libdir . '/xmlize.php');

use core_question\category_manager;
use core_question\local\bank\question_bank_helper;

// Plugin name used for our own bookkeeping rows in {config_plugins}: one row
// per imported question, holding the hash of the source file it came from.
const QBANK_STATE_PLUGIN = 'qbankimport';

/**
 * Run as the site admin. Every CLI script here needs a user for capability
 * checks and for the createdby/modifiedby fields on questions.
 */
function qbank_become_admin(): void {
    \core\session\manager::set_user(get_admin());
}

/**
 * Find a course by shortname, creating it if it does not exist.
 */
function qbank_ensure_course(string $shortname, string $fullname): stdClass {
    global $DB;

    $course = $DB->get_record('course', ['shortname' => $shortname]);
    if ($course) {
        return $course;
    }

    $data = new stdClass();
    $data->category = \core_course_category::get_default()->id;
    $data->shortname = $shortname;
    $data->fullname = $fullname;
    $data->idnumber = $shortname;
    $data->format = 'topics';
    $data->visible = 1;

    return create_course($data);
}

/**
 * Find a question bank activity by its module idnumber, creating it if needed.
 */
function qbank_ensure_bank(stdClass $course, string $idnumber, string $name): cm_info {
    global $DB;

    $cmid = $DB->get_field_sql(
        "SELECT cm.id
           FROM {course_modules} cm
           JOIN {modules} m ON m.id = cm.module
          WHERE cm.course = :course AND m.name = 'qbank' AND cm.idnumber = :idnumber",
        ['course' => $course->id, 'idnumber' => $idnumber]
    );

    if (!$cmid) {
        $cm = question_bank_helper::create_default_open_instance($course, $name);
        $DB->set_field('course_modules', 'idnumber', $idnumber, ['id' => $cm->id]);
        rebuild_course_cache($course->id, true);
        $cmid = $cm->id;
    }

    return get_fast_modinfo($course)->get_cm($cmid);
}

/**
 * Resolve a category path (["Physics", "Motion"]) inside a bank context,
 * creating the categories that do not exist yet. An empty path resolves to the
 * bank's default category; questions cannot live in the "top" category.
 */
function qbank_ensure_category(int $contextid, array $path): stdClass {
    global $DB;

    if (!$path) {
        return question_get_default_category($contextid, true);
    }

    $parent = question_get_top_category($contextid, true);
    $manager = new category_manager();

    foreach ($path as $name) {
        $existing = $DB->get_record('question_categories', [
            'contextid' => $contextid,
            'parent' => $parent->id,
            'name' => $name,
        ]);
        if ($existing) {
            $parent = $existing;
            continue;
        }
        $categoryid = $manager->add_category("{$parent->id},{$contextid}", $name, '');
        $parent = $DB->get_record('question_categories', ['id' => $categoryid], '*', MUST_EXIST);
    }

    return $parent;
}

/**
 * Find the question bank entry with the given idnumber anywhere in a context.
 */
function qbank_find_entry(int $contextid, string $idnumber): ?stdClass {
    global $DB;

    $entry = $DB->get_record_sql(
        "SELECT qbe.*
           FROM {question_bank_entries} qbe
           JOIN {question_categories} qc ON qc.id = qbe.questioncategoryid
          WHERE qc.contextid = :contextid AND qbe.idnumber = :idnumber",
        ['contextid' => $contextid, 'idnumber' => $idnumber]
    );

    return $entry ?: null;
}

/**
 * The question id of the latest version of a bank entry.
 */
function qbank_latest_questionid(int $entryid): int {
    global $DB;

    $versions = $DB->get_records_sql(
        "SELECT qv.id, qv.questionid
           FROM {question_versions} qv
          WHERE qv.questionbankentryid = :entryid
       ORDER BY qv.version DESC",
        ['entryid' => $entryid],
        0,
        1
    );

    return (int) reset($versions)->questionid;
}

/**
 * Key under which the source hash of a question is remembered.
 */
function qbank_state_key(string $bankidnumber, string $idnumber): string {
    return 'h' . sha1($bankidnumber . "\0" . $idnumber);
}

/**
 * Read every .xml file below $root, returned as paths relative to $root, sorted.
 */
function qbank_xml_files(string $root): array {
    $iterator = new RecursiveIteratorIterator(
        new RecursiveDirectoryIterator($root, FilesystemIterator::SKIP_DOTS)
    );

    $files = [];
    foreach ($iterator as $file) {
        if ($file->isFile() && strtolower($file->getExtension()) === 'xml') {
            $files[] = ltrim(substr($file->getPathname(), strlen($root)), '/');
        }
    }
    sort($files);

    return $files;
}

/**
 * The single question element of a Moodle XML file, or an error string.
 */
function qbank_read_single_question(string $path): SimpleXMLElement|string {
    $previous = libxml_use_internal_errors(true);
    $xml = simplexml_load_file($path);
    libxml_use_internal_errors($previous);

    if ($xml === false) {
        return 'not well-formed XML';
    }

    $questions = [];
    foreach ($xml->question as $question) {
        if ((string) $question['type'] !== 'category') {
            $questions[] = $question;
        }
    }

    if (count($questions) !== 1) {
        return 'expected exactly one question per file, found ' . count($questions);
    }

    return $questions[0];
}

/**
 * STACK's own validation of a question file, run before importing it.
 *
 * On a validation failure STACK still saves the question, marked as broken and
 * hidden from students, and outside the web import pages it reports nothing at
 * all: the reason is not persisted either. So we ask it up front.
 */
function qbank_stack_validation_errors(string $path): string {
    $format = new qformat_xml();
    $readdata = new ReflectionMethod($format, 'readdata');
    $readdata->setAccessible(true);
    $xml = xmlize(implode('', $readdata->invoke($format, $path)), 0);

    $node = $xml['quiz']['#']['question'][0];
    if ($node['@']['type'] !== 'stack') {
        return '';
    }

    $fromform = question_bank::get_qtype('stack')->import_from_xml($node, null, $format);

    return trim(html_to_text($fromform->validationerrors ?? '', 0, false));
}
