#!/usr/bin/env python3
"""Tests for type: mcq, quiz grade: and random slots (TASK-06).

Whether a radio actually renders and grades needs a CAS and a Moodle; that is
the question tests run by the bulk tester. What is decidable here is what the
compiler emits — the teacher-answer list, the pool draw, the node-per-option
PRT, the generated question tests — and what it refuses. For pooled MCQs this
is the promised coverage of the distractor key -> note -> why mapping, which
the Maxima-side tests cannot exercise (a hidden key is an invalid response).

Run by qbank/tests/run-tests.sh inside the qbank-tools container.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

COMPILER = Path("/opt/qbank/compiler/compile.py")
FIXTURES = Path("/opt/qbank/fixtures")

MCQ_SHUFFLED = "questions/monivalinta/kuvaaja-mv.yaml"
MCQ_FIXED = "questions/monivalinta/kiehumispiste-mv.yaml"
MCQ_POOLED = "questions/monivalinta/tiheys-mv.yaml"
DRILL_QUIZ = "quizzes/drillikoe.yaml"

COMMIT = "0123456789abcdef0123456789abcdef01234567"


def compile_tree(tmp: Path, name: str, source: Path = FIXTURES) -> Path:
    out = tmp / name
    out.mkdir()
    result = run(source, out)
    assert result.returncode == 0, result.stderr
    return out


def compile_error(tmp: Path, name: str, source: Path) -> str:
    """The message the compiler refused a broken source with."""
    out = tmp / name
    out.mkdir()
    result = run(source, out)
    assert result.returncode != 0, "the compiler accepted a source it should have refused"
    return result.stderr


def run(source: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(COMPILER),
         "--source", str(source), "--out", str(out), "--stack-version", "5.44.0",
         "--content-commit", COMMIT, "--compiler-commit", COMMIT],
        capture_output=True, text=True,
    )


def content(tmp: Path, name: str) -> Path:
    """A private copy of the fixture tree, to break in one specific way."""
    target = tmp / (name + "-content")
    shutil.copytree(FIXTURES, target)
    return target


def patch(root: Path, relative: str, old: str, new: str) -> None:
    path = root / relative
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{relative}: fixture no longer contains {old!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def question_xml(out: Path, qid: str) -> str:
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    entry = next(entry for entry in manifest["questions"] if entry["id"] == qid)
    return (out / entry["xml"]).read_text(encoding="utf-8")


def quiz_json(out: Path, qid: str) -> dict:
    return json.loads((out / "quizzes" / f"{qid}.json").read_text(encoding="utf-8"))


def test_an_mcq_compiles_to_a_radio_over_the_authored_list(tmp: Path) -> None:
    xml = question_xml(compile_tree(tmp, "radio"), "fixture-mv-kuvaaja")

    assert "<type>radio</type>" in xml
    assert "<tans>ta_mcq</tans>" in xml
    assert "[[input:ans1]] [[validation:ans1]]" in xml
    # Labels go through castext so LaTeX in options works; triples keep the
    # authored order, and the correct option is marked, wherever it sits.
    assert '["tasainen", true, castext("kappale liikkuu tasaisella nopeudella")]' in xml
    assert '["kiihtyy", false, castext("kappaleen nopeus kasvaa koko ajan")]' in xml
    assert xml.index('"tasainen"') < xml.index('"kiihtyy"') < xml.index('"akselit"')
    # shuffle: true is the randomisation, and the note is what makes the
    # shown order recoverable from the seed.
    assert "random_permutation(ta_mcq)" in xml
    assert "{@maplist(first, ta_mcq)@}" in xml
    assert xml.count("<deployedseed>") == 3


def test_an_mcq_grades_each_option_on_its_own_node(tmp: Path) -> None:
    xml = question_xml(compile_tree(tmp, "nodes"), "fixture-mv-kuvaaja")

    # Node 0 credits the correct key; each distractor lands on its own note
    # with its own why. This is the mapping the Maxima-side tests cannot
    # check for pooled questions, so it is pinned down here.
    assert xml.count("<node>") == 5
    assert re.search(r'<answertest>String</answertest>\s*<sans>ans1</sans>\s*<tans>"tasainen"</tans>', xml)
    assert "<trueanswernote>ans-0-T</trueanswernote>" in xml
    assert "<trueanswernote>ans-4-T</trueanswernote>" in xml
    kiihtyy = xml.index('<tans>"kiihtyy"</tans>')
    assert xml.index("ylöspäin jyrkkenevänä käyränä", kiihtyy) < xml.index("</node>", kiihtyy)


def test_an_unpooled_mcq_tests_every_option(tmp: Path) -> None:
    xml = question_xml(compile_tree(tmp, "qtests"), "fixture-mv-kuvaaja")

    assert xml.count("<qtest>") == 5
    for index in range(5):
        assert f"<expectedanswernote>ans-{index}-T</expectedanswernote>" in xml
    correct = xml.index('<value>"tasainen"</value>')
    assert "<expectedscore>1.0000000</expectedscore>" in xml[correct:xml.index("</qtest>", correct)]


def test_a_fixed_order_mcq_is_not_random(tmp: Path) -> None:
    xml = question_xml(compile_tree(tmp, "fixed"), "fixture-mv-kiehumispiste")

    assert "random_permutation" not in xml
    assert "rand_selection" not in xml
    assert "<deployedseed>" not in xml
    assert xml.count("<qtest>") == 4


def test_a_pooled_mcq_draws_the_shown_subset_per_variant(tmp: Path) -> None:
    xml = question_xml(compile_tree(tmp, "pool"), "fixture-mv-tiheys-pooli")

    # The correct key is always shown; three of the six distractors join it,
    # in authored order, then the whole list is shuffled.
    assert 'append(["massa-tilavuus"], rand_selection(["paino", "massa", ' \
           '"tilavuus", "kovuus", "raskaus", "uppoaminen"], 3))' in xml
    assert "sublist(ta_mcq_all, lambda([ex], member(first(ex), ta_mcq_keys)))" in xml
    assert "random_permutation(ta_mcq)" in xml
    # The PRT still knows every option; only the qtest surface shrinks to the
    # correct key, which every variant shows.
    assert xml.count("<node>") == 7
    assert xml.count("<qtest>") == 1
    assert '<value>"massa-tilavuus"</value>' in xml
    assert "<expectedanswernote>ans-0-T</expectedanswernote>" in xml


def test_every_option_needs_a_why(tmp: Path) -> None:
    source = content(tmp, "nowhy")
    patch(source, MCQ_FIXED,
          "    why: |\n"
          "      Vesi höyrystyy pinnaltaan kaikissa lämpötiloissa, mutta kiehuminen\n"
          "      alkaa normaalipaineessa vasta 100 °C:ssa.\n",
          "")
    assert "option 'c-50' needs a 'why'" in compile_error(tmp, "nowhy", source)


def test_exactly_one_option_is_correct(tmp: Path) -> None:
    none = content(tmp, "nocorrect")
    patch(none, MCQ_FIXED, "    correct: true\n", "")
    assert "exactly one option" in compile_error(tmp, "nocorrect", none)

    two = content(tmp, "twocorrect")
    patch(two, MCQ_FIXED, "  - key: c-90\n", "  - key: c-90\n    correct: true\n")
    assert "exactly one option" in compile_error(tmp, "twocorrect", two)


def test_option_keys_are_kebab_case_and_unique(tmp: Path) -> None:
    badkey = content(tmp, "badkey")
    patch(badkey, MCQ_FIXED, "  - key: c-50", "  - key: C_50")
    assert "must be lowercase kebab-case" in compile_error(tmp, "badkey", badkey)

    duplicate = content(tmp, "dupkey")
    patch(duplicate, MCQ_FIXED, "  - key: c-110", "  - key: c-50")
    assert "duplicate option key 'c-50'" in compile_error(tmp, "dupkey", duplicate)


def test_show_must_leave_a_real_pool(tmp: Path) -> None:
    source = content(tmp, "showall")
    patch(source, MCQ_POOLED, "show: 4", "show: 7")
    assert "'show' must be an integer" in compile_error(tmp, "showall", source)


def test_a_random_mcq_needs_seeds(tmp: Path) -> None:
    shuffled = content(tmp, "shuffled-noseeds")
    patch(shuffled, MCQ_SHUFFLED, "seeds: [801, 802, 803]\n", "")
    assert "need a 'seeds' list" in compile_error(tmp, "shuffled-noseeds", shuffled)

    pooled = content(tmp, "pooled-noseeds")
    patch(pooled, MCQ_POOLED, "seeds: [811, 812, 813]\n", "")
    assert "need a 'seeds' list" in compile_error(tmp, "pooled-noseeds", pooled)


def test_a_figure_may_not_be_smuggled_into_an_option(tmp: Path) -> None:
    source = content(tmp, "imgwhy")
    patch(source, MCQ_POOLED, "      Kovuus ja tiheys",
          "      <img src='x.svg'> Kovuus ja tiheys")
    assert "figures belong in 'figure:'" in compile_error(tmp, "imgwhy", source)


def test_quiz_grade_defaults_to_ten_and_zero_means_ungraded(tmp: Path) -> None:
    out = compile_tree(tmp, "grade")
    # The existing spec carries no grade: and compiles as before.
    assert quiz_json(out, "fixture-testikoe")["grade"] == 10
    assert quiz_json(out, "fixture-drillikoe")["grade"] == 0

    negative = content(tmp, "negative")
    patch(negative, DRILL_QUIZ, "grade: 0", "grade: -1")
    assert "'grade' must be a number >= 0" in compile_error(tmp, "negative", negative)


def test_random_entries_carry_their_selectors(tmp: Path) -> None:
    quiz = quiz_json(compile_tree(tmp, "randoms"), "fixture-drillikoe")

    assert quiz["questions"][0] == {"id": "fixture-mv-kiehumispiste", "maxmark": 1.0}
    assert quiz["questions"][1] == {
        "random": 1, "tags": ["mv"], "category": None, "maxmark": 1.0}
    assert quiz["questions"][2] == {
        "random": 1, "tags": [], "category": ["Testi", "Monivalinta"], "maxmark": 1.0}


def test_a_random_entry_is_validated(tmp: Path) -> None:
    zero = content(tmp, "zero")
    patch(zero, DRILL_QUIZ, "- random: 1\n    tags: [mv]", "- random: 0\n    tags: [mv]")
    assert "'random' must be a positive integer" in compile_error(tmp, "zero", zero)

    unselective = content(tmp, "unselective")
    patch(unselective, DRILL_QUIZ, "- random: 1\n    tags: [mv]\n", "- random: 1\n")
    assert "needs 'tags', 'category' or both" in compile_error(tmp, "unselective", unselective)


def test_a_draw_larger_than_the_pool_is_refused(tmp: Path) -> None:
    large = content(tmp, "large")
    patch(large, DRILL_QUIZ, "- random: 1\n    tags: [mv]", "- random: 9\n    tags: [mv]")
    assert "only 3 compiled question(s) match" in compile_error(tmp, "large", large)

    unknown = content(tmp, "unknowntag")
    patch(unknown, DRILL_QUIZ, "tags: [mv]", "tags: [olematon]")
    assert "only 0 compiled question(s) match" in compile_error(tmp, "unknowntag", unknown)


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        with tempfile.TemporaryDirectory() as workdir:
            test(Path(workdir))
        print(f"ok  {test.__name__}")
    print(f"{len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
