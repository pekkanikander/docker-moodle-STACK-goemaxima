#!/usr/bin/env python3
"""Tests for question hints and the drill quiz recipe (TASK-03).

Whether a hint reads well after a failed try is a question for the student,
and whether it renders is the bulk tester's business -- STACK question tests
do not cover hints at all. What is decidable here is what the compiler emits
for a 'hints:' block, what it refuses, and the promise the whole feature rests
on: that adding hints to a question changes nothing else about it, so one
source can serve both the exam quiz and the drill quiz.

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

HINTED = "questions/tulkinta/matka-none.yaml"
DRILL_QUIZ = "quizzes/tulkintadrilli.yaml"

COMMIT = "0123456789abcdef0123456789abcdef01234567"

HINT_RE = re.compile(
    r'    <hint format="html">\n      <text><!\[CDATA\[(.*?)\]\]></text>\n    </hint>\n',
    re.S)


def run(source: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(COMPILER),
         "--source", str(source), "--out", str(out), "--stack-version", "5.44.0",
         "--content-commit", COMMIT, "--compiler-commit", COMMIT],
        capture_output=True, text=True,
    )


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


def content(tmp: Path, name: str) -> Path:
    """A private copy of the fixture tree, to change in one specific way."""
    target = tmp / (name + "-content")
    shutil.copytree(FIXTURES, target)
    return target


def patch(root: Path, relative: str, old: str, new: str) -> None:
    path = root / relative
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{relative}: fixture no longer contains {old!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def set_hints(root: Path, block: str) -> None:
    """Replace the hinted fixture's whole 'hints:' block; '' removes it."""
    path = root / HINTED
    text = path.read_text(encoding="utf-8")
    head, marker, rest = text.partition("hints:\n")
    assert marker, f"{HINTED}: fixture no longer has a hints: block"
    _, _, tail = rest.partition("\nanswer:\n")
    path.write_text(head + block + "answer:\n" + tail, encoding="utf-8")


def question_xml(out: Path, qid: str) -> str:
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    entry = next(entry for entry in manifest["questions"] if entry["id"] == qid)
    return (out / entry["xml"]).read_text(encoding="utf-8")


def hints(out: Path, qid: str) -> list[str]:
    return HINT_RE.findall(question_xml(out, qid))


def test_hints_become_hint_elements_in_source_order(tmp: Path) -> None:
    out = compile_tree(tmp, "ladder")
    ladder = hints(out, "fixture-matka-none")
    assert len(ladder) == 3, ladder
    # The ladder mirrors the interpretation ladder: which reading applies,
    # then the relation, then the numbers.
    assert "<em>matka</em>" in ladder[0]
    assert "s = s_1 + s_2" in ladder[1]
    assert "s_1 = {@sx@}" in ladder[2]


def test_hints_take_the_prose_rules(tmp: Path) -> None:
    out = compile_tree(tmp, "prose")
    first = hints(out, "fixture-matka-none")[0]
    assert first.startswith("<p>Mieti ensin,")
    assert "<ul><li>kuljetun reitin pituus</li>" in first
    # LaTeX and CASText pass through byte for byte, as in every other prose
    # field: STACK evaluates a hint inside the question's Maxima session, so
    # {@sx@} is the value of the variant the student actually drew.
    assert r"\(s_1 = {@sx@}\,\mathrm{m}\)" in hints(out, "fixture-matka-none")[2]


def test_no_hint_options_are_emitted(tmp: Path) -> None:
    # STACK calls import_hints() with withparts and withoptions both false, so
    # these would be dropped on import; emitting them would only mislead.
    out = compile_tree(tmp, "bare")
    xml = question_xml(out, "fixture-matka-none")
    assert "shownumcorrect" not in xml
    assert "clearwrong" not in xml


def test_a_question_without_hints_emits_none(tmp: Path) -> None:
    out = compile_tree(tmp, "none")
    for qid in ("fixture-matka-stated", "fixture-summa", "fixture-mv-kiehumispiste"):
        assert "<hint" not in question_xml(out, qid), qid


def test_hints_change_nothing_else_in_the_question(tmp: Path) -> None:
    """One source serves both uses, so hints must be purely additive."""
    stripped = content(tmp, "stripped")
    set_hints(stripped, "")

    with_hints = question_xml(compile_tree(tmp, "with"), "fixture-matka-none")
    without = question_xml(compile_tree(tmp, "without", stripped), "fixture-matka-none")
    assert "<hint" not in without
    assert HINT_RE.sub("", with_hints) == without


def test_a_broken_hints_key_is_refused(tmp: Path) -> None:
    scalar = content(tmp, "scalar")
    set_hints(scalar, 'hints: "Yksi vihje."\n\n')
    assert "'hints' must be a non-empty list" in compile_error(tmp, "scalar", scalar)

    empty = content(tmp, "empty")
    set_hints(empty, "hints: []\n\n")
    assert "'hints' must be a non-empty list" in compile_error(tmp, "empty", empty)

    blank = content(tmp, "blank")
    set_hints(blank, 'hints:\n  - "Vihje."\n  - "   "\n\n')
    assert "hint 2 must be a non-empty string" in compile_error(tmp, "blank", blank)

    number = content(tmp, "number")
    set_hints(number, 'hints:\n  - "Vihje."\n  - 42\n\n')
    assert "hint 2 must be a non-empty string" in compile_error(tmp, "number", number)


def test_a_figure_may_not_be_smuggled_into_a_hint(tmp: Path) -> None:
    smuggled = content(tmp, "smuggled")
    patch(smuggled, HINTED, "    Kuljettu matka on reitin osien",
          "    {@plot([x], [x, 0, 1])@} Kuljettu matka on reitin osien")
    error = compile_error(tmp, "smuggled", smuggled)
    assert "'hint 2' contains a plot() call" in error


def test_hints_are_refused_on_an_aitext_question(tmp: Path) -> None:
    essay = content(tmp, "essay")
    patch(essay, "questions/selitys/kelluminen.yaml", "\nrubric:", "\nhints:\n  - Vihje.\n\nrubric:")
    assert "'hints' applies to STACK questions only" in compile_error(tmp, "essay", essay)


def test_the_drill_quiz_is_ungraded_and_interactive(tmp: Path) -> None:
    out = compile_tree(tmp, "drill")
    quiz = json.loads((out / "quizzes" / "fixture-tulkintadrilli.json")
                      .read_text(encoding="utf-8"))
    # grade 0 means Moodle creates no gradebook item, which is what "no
    # grading" has to mean concretely; dropping 'marks' from both review lists
    # is what keeps the numbers off the screen.
    assert quiz["grade"] == 0.0
    assert quiz["behaviour"] == "interactive"
    assert "marks" not in quiz["review"]["during"]
    assert "marks" not in quiz["review"]["after"]
    assert [entry["id"] for entry in quiz["questions"]] == [
        "fixture-matka-none", "fixture-matka-stated"]


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
