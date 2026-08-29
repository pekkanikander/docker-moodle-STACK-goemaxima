#!/usr/bin/env python3
"""Tests for figures: what the compiler emits, and what it refuses.

Whether an image actually renders is not decidable here — that needs a CAS and
a Moodle, and is qbank/cli/figure-test.php. What is decidable here is that a
figure reaches the question text with its alt text, that a schematic travels
with the XML, and that the ways of writing a figure which would bypass those
checks are refused.

Run by qbank/tests/run-tests.sh inside the qbank-tools container.
"""

import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

COMPILER = Path("/opt/qbank/compiler/compile.py")
FIXTURES = Path("/opt/qbank/fixtures")

PLOT_QUESTION = "questions/kuvaajat/matkakuvaaja-stated.yaml"
SVG_QUESTION = "questions/kuvaajat/virtapiiri-choice.yaml"
SCHEMATIC = "kuvat/virtapiiri-sarja.svg"

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


def test_a_plot_reaches_the_question_text_with_its_alt_text(tmp: Path) -> None:
    xml = question_xml(compile_tree(tmp, "plot"), "fixture-matkakuvaaja-stated")

    plot = re.search(r"\{@plot\((.*)\)@\}", xml)
    assert plot, xml
    assert '[alt, "Matka-aikakuvaaja: origosta' in plot.group(1)
    assert "[discrete" in plot.group(1)


def test_a_schematic_travels_with_the_question(tmp: Path) -> None:
    """R8: the author writes a path, and Moodle gets the bytes."""
    xml = question_xml(compile_tree(tmp, "svg"), "fixture-virtapiiri-choice")

    assert '<img src="@@PLUGINFILE@@/virtapiiri-sarja.svg"' in xml
    embedded = re.search(r'<file name="virtapiiri-sarja\.svg" path="/" encoding="base64">([^<]+)<', xml)
    assert embedded, xml
    assert base64.b64decode(embedded.group(1)) == (FIXTURES / SCHEMATIC).read_bytes()


def test_a_plot_question_asks_for_a_decimal_comma(tmp: Path) -> None:
    """R6. That the override works is checked against gnuplot itself, by
    qbank/cli/figure-test.php; that it is requested, once and only where it is
    needed, is checked here."""
    out = compile_tree(tmp, "comma")

    plotted = question_xml(out, "fixture-matkakuvaaja-stated")
    assert plotted.count('set decimalsign') == 1
    assert 'PLOT_TERM_OPT : sconcat(PLOT_TERM_OPT' in plotted

    for qid in ("fixture-virtapiiri-choice", "fixture-matka-stated"):
        assert 'decimalsign' not in question_xml(out, qid), qid


def test_a_figure_is_recorded_in_the_manifest(tmp: Path) -> None:
    """Editing a schematic changes what Moodle stores, so it has to change the
    manifest too; otherwise the build says nothing about it."""
    before = compile_tree(tmp, "assets")
    manifest = json.loads((before / "manifest.json").read_text(encoding="utf-8"))
    entry = next(e for e in manifest["questions"] if e["id"] == "fixture-virtapiiri-choice")
    assert entry["assets"][0]["source"] == SCHEMATIC

    edited = content(tmp, "edited")
    patch(edited, SCHEMATIC, '<text x="66" y="75">U</text>', '<text x="66" y="75">E</text>')
    after = compile_tree(tmp, "assets-edited", source=edited)
    changed = json.loads((after / "manifest.json").read_text(encoding="utf-8"))
    other = next(e for e in changed["questions"] if e["id"] == "fixture-virtapiiri-choice")

    assert other["assets"][0]["sha256"] != entry["assets"][0]["sha256"]
    assert question_xml(after, "fixture-virtapiiri-choice") != question_xml(before, "fixture-virtapiiri-choice")


def test_a_figure_works_at_every_scaffold_rung(tmp: Path) -> None:
    """R5: the fixture exam covers all three rungs with a figure, and the
    figure sits in the stem, before the scaffold, in each."""
    out = compile_tree(tmp, "rungs")
    rungs = {
        "fixture-matkakuvaaja-stated": "Tässä tehtävässä käytetään tulkintaa",
        "fixture-virtapiiri-choice": "[[input:interp]]",
        "fixture-nopeuskuvaaja-none": "[[input:ans1]]",
    }
    for qid, marker in rungs.items():
        xml = question_xml(out, qid)
        figure = xml.index("{@plot(") if "{@plot(" in xml else xml.index("@@PLUGINFILE@@")
        assert figure < xml.index(marker), qid


def test_alt_text_is_required(tmp: Path) -> None:
    """R3: STACK's default alt text is an English dump of the expression."""
    source = content(tmp, "noalt")
    patch(source, PLOT_QUESTION,
          "  alt: |\n    Matka-aikakuvaaja: origosta lähtevä nouseva suora. Vaaka-akselilla on\n"
          "    aika sekunteina ja pystyakselilla kuljettu matka metreinä.\n",
          '  alt: ""\n')
    assert "'figure.alt' is required" in compile_error(tmp, "noalt", source)


def test_alt_text_cannot_interpolate_variables(tmp: Path) -> None:
    source = content(tmp, "castextalt")
    patch(source, PLOT_QUESTION, "Matka-aikakuvaaja:", "Matka-aikakuvaaja hetkeen {@tloppu@} asti:")
    assert "cannot interpolate variables" in compile_error(tmp, "castextalt", source)


def test_a_figure_is_either_a_plot_or_a_schematic(tmp: Path) -> None:
    both = content(tmp, "both")
    patch(both, SVG_QUESTION, "  svg: kuvat/", "  plot: |\n    [x, 0, r1]\n  svg: kuvat/")
    assert "exactly one of" in compile_error(tmp, "both", both)

    neither = content(tmp, "neither")
    patch(neither, SVG_QUESTION, "  svg: kuvat/virtapiiri-sarja.svg", "")
    assert "exactly one of" in compile_error(tmp, "neither", neither)


def test_an_unknown_figure_key_is_refused(tmp: Path) -> None:
    source = content(tmp, "unknownkey")
    patch(source, SVG_QUESTION, "  svg: kuvat/", "  caption: Kuva 1\n  svg: kuvat/")
    assert "unknown key(s): caption" in compile_error(tmp, "unknownkey", source)


def test_a_plot_may_not_use_an_undefined_name(tmp: Path) -> None:
    source = content(tmp, "undefined")
    patch(source, PLOT_QUESTION, "[y, 0, sloppu]", "[y, 0, smax]")
    assert "not defined in 'variables:': smax" in compile_error(tmp, "undefined", source)


def test_a_plot_may_not_carry_its_own_numbers(tmp: Path) -> None:
    """R2, in its two forms: a decimal, and a constant copied out of
    'variables:'. Either lets the picture and the prose disagree, and the
    student is marked wrong for reading the picture correctly."""
    decimal = content(tmp, "decimal")
    patch(decimal, PLOT_QUESTION, "[x, 0, tloppu]", "[x, 0, 7.5]")
    assert "contains a decimal number" in compile_error(tmp, "decimal", decimal)

    repeated = content(tmp, "repeated")
    patch(repeated, PLOT_QUESTION, "[x, 0, tloppu]", "[x, 0, 5]")
    assert "repeats constant(s) from 'variables:': 5" in compile_error(tmp, "repeated", repeated)


def test_a_schematic_path_is_checked(tmp: Path) -> None:
    missing = content(tmp, "missing")
    patch(missing, SVG_QUESTION, "kuvat/virtapiiri-sarja.svg", "kuvat/puuttuu.svg")
    assert "not found" in compile_error(tmp, "missing", missing)

    outside = content(tmp, "outside")
    patch(outside, SVG_QUESTION, "kuvat/virtapiiri-sarja.svg", "../../etc/hosts.svg")
    assert "outside the content root" in compile_error(tmp, "outside", outside)

    absolute = content(tmp, "absolute")
    patch(absolute, SVG_QUESTION, "kuvat/virtapiiri-sarja.svg", "/etc/hosts.svg")
    assert "must be relative to the content root" in compile_error(tmp, "absolute", absolute)

    wrongtype = content(tmp, "wrongtype")
    (wrongtype / "kuvat" / "virtapiiri.png").write_bytes(b"not an svg")
    patch(wrongtype, SVG_QUESTION, "kuvat/virtapiiri-sarja.svg", "kuvat/virtapiiri.png")
    assert "must be an .svg file" in compile_error(tmp, "wrongtype", wrongtype)


def test_a_schematic_may_not_run_or_fetch_anything(tmp: Path) -> None:
    """A figure that quietly fails to load breaks a question in a way the
    student cannot diagnose, and an exam page should fetch nothing."""
    dangerous = {
        "script": ('<path d="M25 70 H55', '<script>x=1</script><path d="M25 70 H55'),
        "handler": ('<rect x="100"', '<rect onload="x()" x="100"'),
        "external": ('<path d="M25 70 H55', '<image href="//example.org/r.png" /><path d="M25 70 H55'),
        "entity": ('<svg xmlns', '<!ENTITY xxe SYSTEM "file:///etc/passwd">\n<svg xmlns'),
    }
    for name, (old, new) in dangerous.items():
        source = content(tmp, name)
        patch(source, SCHEMATIC, old, new)
        assert "contains a" in compile_error(tmp, name, source), name


def test_a_figure_may_not_be_smuggled_into_the_prose(tmp: Path) -> None:
    """The prose fields pass HTML and CASText through untouched, so a figure
    written there would reach STACK with no alt text and outside the render
    gate. Whichever way is left open is the one that gets used."""
    fields = {
        "stem": ("  Kuvaaja esittää kappaleen liikettä.",
                 "  Kuvaaja esittää kappaleen liikettä. {@plot([x], [x, 0, tloppu])@}"),
        "feedback": ("  Kappale kulkee {@sloppu@} metriä",
                     '  <img src="kuva.svg" alt="" /> Kappale kulkee {@sloppu@} metriä'),
        "answer prompt": ('prompt: "Kuinka suuri kappaleen nopeus on?',
                          'prompt: "<svg></svg> Kuinka suuri kappaleen nopeus on?'),
        "reading why": ('why: "Nopeus on matkan muutos',
                        'why: "<img src=\'x.svg\'> Nopeus on matkan muutos'),
    }
    for name, (old, new) in fields.items():
        source = content(tmp, name.replace(" ", "-"))
        patch(source, PLOT_QUESTION, old, new)
        assert "figures belong in 'figure:'" in compile_error(tmp, name.replace(" ", "-"), source), name


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
