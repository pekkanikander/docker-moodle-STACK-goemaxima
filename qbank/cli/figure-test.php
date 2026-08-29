<?php
// Render gate for figures: every figure question, at every deployed seed, must
// produce an image that a student would actually see.
//
// A plot is a per-render artefact. STACK names it with rand(10^8) and writes it
// into $CFG->dataroot/stack/plots, so nothing about the file can be pinned in
// advance; what can be checked is that the CAS ran without error, that the file
// the <img> points at exists and is a non-empty SVG, and that its tick labels
// use a decimal comma like the prose beside them.
//
// The CAS result cache holds the filename, not the file, so a purged plots
// directory leaves cached questions pointing at images that are gone. That
// breaks the question for the student and fails here for the same reason.

require_once(__DIR__ . '/lib.php');

require_once($CFG->dirroot . '/question/type/stack/question.php');

$usage = "Render every figure question at every deployed seed and check its images.

Usage: php figure-test.php --course=SHORTNAME --bank=IDNUMBER [--manifest=FILE]

  --course=SHORTNAME  Course holding the question bank (required).
  --bank=IDNUMBER     Question bank module idnumber (required).
  --manifest=FILE     Build manifest listing the questions (default
                      /opt/qbank-build/manifest.json).
";

[$options, $unrecognised] = cli_get_params(
    ['course' => '', 'bank' => '', 'manifest' => '/opt/qbank-build/manifest.json', 'help' => false],
    ['h' => 'help']
);
if ($unrecognised) {
    cli_error($usage);
}
if ($options['help'] || $options['course'] === '' || $options['bank'] === '') {
    cli_writeln($usage);
    exit($options['help'] ? 0 : 1);
}

qbank_become_admin();

$course = $DB->get_record('course', ['shortname' => $options['course']], '*', MUST_EXIST);
$bankcontext = context_module::instance(qbank_ensure_bank($course, $options['bank'], $options['bank'])->id);
$manifest = qbank_read_manifest($options['manifest']);

/**
 * Render one question at one seed, as the quiz would.
 *
 * A clone per render: instantiation caches on the question object, and a seed
 * set on the shared instance would leak into the next one.
 */
function figure_test_render(qtype_stack_question $question, ?int $seed): array {
    $attempt = clone($question);
    if ($seed !== null) {
        $attempt->seed = $seed;
    }

    $quba = question_engine::make_questions_usage_by_activity('qtype_stack', context_system::instance());
    $quba->set_preferred_behaviour('adaptive');
    $slot = $quba->add_question($attempt, $attempt->defaultmark);
    $quba->start_question($slot);

    $display = new question_display_options();
    $display->readonly = true;
    $display->flags = question_display_options::HIDDEN;

    return [$quba->render_question($slot, $display), $attempt];
}

/**
 * The src and alt of every image in a rendered question.
 */
function figure_test_images(string $html): array {
    preg_match_all('~<img\b[^>]*>~i', $html, $matches);

    $images = [];
    foreach ($matches[0] as $tag) {
        preg_match('~\bsrc\s*=\s*("[^"]*"|\'[^\']*\')~i', $tag, $src);
        preg_match('~\balt\s*=\s*("[^"]*"|\'[^\']*\')~i', $tag, $alt);
        $images[] = [
            'src' => isset($src[1]) ? html_entity_decode(trim($src[1], '"\''), ENT_QUOTES) : '',
            'alt' => isset($alt[1]) ? html_entity_decode(trim($alt[1], '"\''), ENT_QUOTES) : '',
        ];
    }

    return $images;
}

/**
 * What is wrong with a CAS-generated plot, if anything.
 *
 * The decimal check is on the tick labels, which gnuplot writes as <tspan>
 * text. It guards the PLOT_TERM_OPT override the compiler injects: that
 * depends on an internal STACK setting name, and if the name ever changes the
 * override silently stops applying. A dot on the axis next to a comma in the
 * prose is exactly the inconsistency this project exists to remove.
 */
function figure_test_plot_problems(string $src): array {
    global $CFG;

    $file = $CFG->dataroot . '/stack/plots/' . basename(urldecode(parse_url($src, PHP_URL_PATH)));
    if (!is_file($file)) {
        return ["the plot file is missing: {$file}\n" .
                "    (the filename is cached; if the plots directory was cleared, purge the STACK CAS cache too)"];
    }

    $svg = file_get_contents($file);
    if (trim($svg) === '' || !str_contains($svg, '<svg')) {
        return ["the plot file is not an SVG: {$file}"];
    }

    preg_match_all('~<(?:text|tspan)\b[^>]*>([^<]*)</~i', $svg, $labels);
    $decimals = array_filter(array_map('trim', $labels[1]), fn($label) => (bool) preg_match('~^-?\d+\.\d+$~', $label));
    if ($decimals) {
        return ['axis labels use a decimal point: ' . implode(', ', array_unique($decimals))];
    }

    return [];
}

/**
 * What is wrong with an embedded schematic, if anything.
 */
function figure_test_file_problems(string $src, qtype_stack_question $question): array {
    $filename = basename(urldecode(parse_url($src, PHP_URL_PATH)));
    $file = get_file_storage()->get_file(
        $question->contextid, 'question', 'questiontext', $question->id, '/', $filename);

    if (!$file) {
        return ["the question has no stored file '{$filename}'"];
    }
    if ($file->get_filesize() === 0) {
        return ["the stored file '{$filename}' is empty"];
    }

    return [];
}

$failures = [];
$questions = 0;
$renders = 0;

foreach ($manifest->questions as $entry) {
    $bankentry = qbank_find_entry($bankcontext->id, $entry->id);
    if (!$bankentry) {
        cli_error("Question {$entry->id} is in the manifest but not in the bank; import first.");
    }

    $question = question_bank::load_question(qbank_latest_questionid($bankentry->id));
    if (!$question instanceof qtype_stack_question) {
        continue;
    }
    if (!preg_match('~\{@\s*plot\(|@@PLUGINFILE@@~', $question->questiontext)) {
        continue;
    }

    $questions++;
    $before = count($failures);
    cli_write($entry->id . ':');

    foreach ($question->deployedseeds ?: [null] as $seed) {
        $renders++;
        $where = $entry->id . ($seed === null ? '' : " (seed {$seed})");
        cli_write(' ' . ($seed ?? '-'));

        [$html, $attempt] = figure_test_render($question, $seed === null ? null : (int) $seed);
        if ($attempt->runtimeerrors) {
            $failures[] = $where . ': ' . implode('; ', array_keys($attempt->runtimeerrors));
            continue;
        }

        $images = figure_test_images($html);
        if (!$images) {
            $failures[] = $where . ': the question renders no image at all';
            continue;
        }

        foreach ($images as $image) {
            if (trim($image['alt']) === '') {
                $failures[] = $where . ': an image has no alt text';
            }
            if (str_contains($image['src'], '/question/type/stack/plot.php')) {
                $problems = figure_test_plot_problems($image['src']);
            } else if (str_contains($image['src'], '/pluginfile.php/')) {
                $problems = figure_test_file_problems($image['src'], $question);
            } else {
                $problems = ["the image is not served by this site: {$image['src']}"];
            }
            foreach ($problems as $problem) {
                $failures[] = $where . ': ' . $problem;
            }
        }
    }

    cli_writeln(count($failures) > $before ? ' FAILED' : ' ok');
}

cli_writeln("{$questions} figure questions, {$renders} renders.");

if ($failures) {
    cli_writeln('');
    foreach ($failures as $failure) {
        cli_writeln('  ' . $failure);
    }
    cli_error('Figure tests failed.');
}

if ($questions === 0) {
    cli_writeln('No figure questions found.');
}
