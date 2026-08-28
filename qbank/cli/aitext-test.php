<?php
// Run the golden tests of compiled aitext eval specs through the real
// grading pipeline: build the prompt, call the configured AI provider,
// validate the model reply against the rubric, and compare the criterion
// levels the model chose against each test's expectations.
//
// This costs API money (one model call per test) and is not perfectly
// deterministic; see qbank/README.md.

require_once(__DIR__ . '/lib.php');

require_once($CFG->dirroot . '/question/type/aitext_rubric/question.php');

$usage = "Run aitext golden tests through the real AI grading pipeline.

Usage: php aitext-test.php [--specdir=DIR] [--question=ID] [--test=NAME]

  --specdir=DIR   Directory of eval specs (default /opt/qbank-build/aitext).
  --question=ID   Only this question id.
  --test=NAME     Only tests with this name.
  --show-html     Print the rendered feedback HTML for each test.
";

[$options, $unrecognised] = cli_get_params(
    ['specdir' => '/opt/qbank-build/aitext', 'question' => '', 'test' => '', 'show-html' => false, 'help' => false],
    ['h' => 'help']
);
if ($unrecognised) {
    cli_error($usage);
}
if ($options['help']) {
    cli_writeln($usage);
    exit(0);
}

qbank_become_admin();

$specfiles = glob(rtrim($options['specdir'], '/') . '/*.json') ?: [];
if ($options['question'] !== '') {
    $specfiles = array_filter($specfiles,
        fn($file) => basename($file, '.json') === $options['question']);
}
if (!$specfiles) {
    cli_error("No eval specs found in {$options['specdir']} — run tools/qbank.sh compile first.");
}

$renderdir = '/tmp/qbank-aitext';
@mkdir($renderdir, 0777, true);

$failures = 0;
$total = 0;

foreach ($specfiles as $specfile) {
    $spec = json_decode(file_get_contents($specfile));
    if (!is_object($spec)) {
        cli_error("Unreadable spec: {$specfile}");
    }
    cli_writeln("== {$spec->id} ==");

    foreach ($spec->tests as $test) {
        if ($options['test'] !== '' && $test->name !== $options['test']) {
            continue;
        }
        $total++;

        // A fresh question instance per test: grade_response() caches
        // results on the object.
        $question = new qtype_aitext_rubric_question();
        $question->id = 0;
        $question->questiontext = $spec->stem_html;
        $question->questiontextformat = FORMAT_HTML;
        $question->defaultmark = 1.0;
        $question->aiprompt = $spec->context;
        $question->markscheme = '';
        $question->rubric = json_encode($spec->rubric);
        $question->spellcheck = false;
        $question->responseformat = 'plain';
        $question->minwordlimit = null;
        $question->maxwordlimit = null;
        $question->contextid = context_system::instance()->id;

        [$fraction, $state] = $question->grade_response([
            'answer' => $test->answer,
            'answerformat' => FORMAT_PLAIN,
        ]);

        $result = $question->lastrubricresult;
        if ($result === null) {
            $failures++;
            cli_writeln(sprintf('  %-24s FAIL: grading fell back to needs-grading', $test->name));
            cli_writeln('      student message: ' . trim(strip_tags((string) $question->lastaicomment)));
            continue;
        }

        $lines = [];
        $testfailed = false;
        foreach ($result->criteria as $criterion) {
            $expected = $test->expect->{$criterion->id};
            $accepted = in_array($criterion->level, $expected);
            if (!$accepted) {
                $testfailed = true;
            }
            $lines[] = sprintf('      %-20s got %d, expected %s %s',
                $criterion->id, $criterion->level, implode('|', $expected), $accepted ? '' : '<-- MISMATCH');
            if ($criterion->comment !== '') {
                $lines[] = "          comment: {$criterion->comment}";
            }
        }
        $lines[] = sprintf('      mark: %d/%d (fraction %.2f)  next_step: %s',
            $result->points, $result->maxpoints, $fraction, $result->nextstep);

        if ($testfailed) {
            $failures++;
        }
        cli_writeln(sprintf('  %-24s %s', $test->name, $testfailed ? 'FAIL' : 'pass'));
        cli_writeln(implode("\n", $lines));

        $htmlfile = "{$renderdir}/{$spec->id}-{$test->name}.html";
        file_put_contents($htmlfile, $question->lastaicomment);
        if ($options['show-html']) {
            cli_writeln($question->lastaicomment);
        }
    }
}

cli_writeln('');
cli_writeln(sprintf('%d tests, %d failed. Rendered feedback in %s (inside the container).',
    $total, $failures, $renderdir));
exit($failures > 0 ? 1 : 0);
