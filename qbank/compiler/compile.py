#!/usr/bin/env python3
"""Compile question and quiz sources into Moodle XML / JSON for import.

Sources are YAML. Questions become one Moodle XML file each, laid out under
the build directory by their category path, which is what
qbank/cli/import-questions.php expects. Quizzes become JSON consumed by
qbank/cli/build-quiz.php.

Run inside the qbank-tools container; see tools/qbank.sh.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

# Answer type -> (STACK answer test, default tolerance). 'algebraic' compares
# symbolically; the other two compare numerically, within a relative tolerance,
# because a drilling answer is a rounded measurement rather than an exact form.
ANSWER_TESTS = {
    "algebraic": ("AlgEquiv", ""),
    "numerical": ("NumRelative", "0.01"),
    "units": ("UnitsRelative", "0.01"),
}

# Fading ladder, easiest first: the intended reading is stated, then chosen
# from a list, then left to be inferred. Distractor feedback is given at every
# rung, so a misreading is always named rather than just marked wrong.
SCAFFOLDS = ("stated", "choice", "none")

ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# A reading key becomes part of a Maxima variable name (ta_<key>).
KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Quiz behaviours worth using with STACK. Under 'adaptive' STACK swaps in the
# adaptivemultipart behaviour per question, which grades each PRT on its own --
# what the interpretation scaffold needs. adaptivemultipart cannot be named
# here: it is not archetypal, so Moodle rejects it as a quiz setting.
QUIZ_BEHAVIOURS = (
    "adaptive",
    "adaptivenopenalty",
    "deferredfeedback",
    "immediatefeedback",
    "interactive",
)


class SourceError(Exception):
    """A problem in a source file, reported with its path."""


@dataclass
class Reading:
    key: str
    label: str
    value: str
    intended: bool = False
    why: str = ""


@dataclass
class Question:
    path: Path
    id: str
    name: str
    category: list[str]
    variables: str
    stem: str
    answer: dict
    scaffold: str = "none"
    interpretation: dict | None = None
    readings: list[Reading] = field(default_factory=list)
    general_feedback: str = ""
    note: str = ""
    tags: list[str] = field(default_factory=list)
    seeds: list[int] = field(default_factory=list)
    grade: float = 1.0
    penalty: float = 0.1


def fail(path: Path, message: str) -> None:
    raise SourceError(f"{path}: {message}")


def require(path: Path, source: dict, key: str):
    if key not in source or source[key] in (None, ""):
        fail(path, f"missing required key '{key}'")
    return source[key]


def to_html(text: str) -> str:
    """Blank-line separated paragraphs and '- ' bullet lists.

    Nothing else is interpreted: LaTeX, CASText ({@...@}) and inline HTML are
    passed through byte for byte, so that maths is never mangled.
    """
    blocks = re.split(r"\n\s*\n", text.strip())
    out = []
    for block in blocks:
        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if block.lstrip().startswith("<"):
            out.append(block.strip())
        elif all(line.lstrip().startswith("- ") for line in lines):
            items = "".join(f"<li>{line.lstrip()[2:]}</li>" for line in lines)
            out.append(f"<ul>{items}</ul>")
        else:
            out.append("<p>" + "\n".join(lines) + "</p>")
    return "\n".join(out)


def cdata(text: str) -> str:
    if "]]>" in text:
        raise SourceError("text may not contain ']]>'")
    return f"<![CDATA[{text}]]>"


def maxima_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def element(name: str, value) -> str:
    return f"    <{name}>{value}</{name}>\n"


def text_element(name: str, html: str, indent: str = "    ") -> str:
    return f'{indent}<{name} format="html">\n{indent}  <text>{cdata(html)}</text>\n{indent}</{name}>\n'


def load_question(path: Path, source: dict) -> Question:
    qid = str(require(path, source, "id"))
    if not ID_RE.match(qid):
        fail(path, f"id '{qid}' must be lowercase kebab-case")

    category = require(path, source, "category")
    if not isinstance(category, list) or not category:
        fail(path, "'category' must be a non-empty list of category names")

    scaffold = source.get("scaffold", "none")
    if scaffold not in SCAFFOLDS:
        fail(path, f"scaffold must be one of {', '.join(SCAFFOLDS)}")

    interpretation = source.get("interpretation")
    readings: list[Reading] = []
    if interpretation:
        for entry in interpretation.get("readings", []):
            if not KEY_RE.match(str(entry["key"])):
                fail(path, f"reading key '{entry['key']}' must match {KEY_RE.pattern}")
            readings.append(
                Reading(
                    key=entry["key"],
                    label=entry["label"],
                    value=str(entry["value"]),
                    intended=bool(entry.get("intended", False)),
                    why=entry.get("why", ""),
                )
            )
        if len(readings) < 2:
            fail(path, "'interpretation' needs at least two readings")
        if sum(r.intended for r in readings) != 1:
            fail(path, "exactly one reading must be marked 'intended: true'")
    elif scaffold != "none":
        fail(path, f"scaffold '{scaffold}' requires an 'interpretation' block")

    # Without deployed seeds a randomised question has no fixed set of variants,
    # so its question tests only ever exercise whichever variant comes up.
    if "rand" in str(source.get("variables", "")) and not source.get("seeds"):
        fail(path, "randomised questions need a 'seeds' list of deployed seeds")

    answer = require(path, source, "answer")
    for key in ("prompt", "formula"):
        if not answer.get(key):
            fail(path, f"missing required key 'answer.{key}'")
    if answer.get("type", "algebraic") not in ANSWER_TESTS:
        fail(path, f"answer.type must be one of {', '.join(ANSWER_TESTS)}")
    if readings and "quantity" not in answer:
        fail(path, "'answer.quantity' must name the symbol the readings stand for")
    if scaffold == "choice" and not interpretation.get("prompt"):
        fail(path, "scaffold 'choice' requires 'interpretation.prompt'")
    if scaffold == "stated" and not interpretation.get("stated_prefix"):
        fail(path, "scaffold 'stated' requires 'interpretation.stated_prefix'")

    return Question(
        path=path,
        id=qid,
        name=str(require(path, source, "name")),
        category=[str(part) for part in category],
        variables=str(source.get("variables", "")).strip(),
        stem=str(require(path, source, "stem")),
        answer=answer,
        scaffold=scaffold,
        interpretation=interpretation,
        readings=readings,
        general_feedback=source.get("feedback", ""),
        note=source.get("note", ""),
        tags=[str(tag) for tag in source.get("tags", [])],
        seeds=[int(seed) for seed in source.get("seeds", [])],
        grade=float(source.get("grade", 1.0)),
        penalty=float(source.get("penalty", 0.1)),
    )


def answer_expressions(question: Question) -> str:
    """Maxima defining ta (intended answer) and ta_<key> for each misreading."""
    formula = str(question.answer["formula"])
    if not question.readings:
        return f"ta : {formula};"

    quantity = str(question.answer["quantity"])
    lines = []
    for reading in question.readings:
        target = "ta" if reading.intended else f"ta_{reading.key}"
        lines.append(f"{target} : subst({quantity} = {reading.value}, {formula});")
    return "\n".join(lines)


def dropdown_teacher_answer(question: Question) -> str:
    options = ", ".join(
        f"[{maxima_string(r.key)}, {'true' if r.intended else 'false'}, {maxima_string(r.label)}]"
        for r in question.readings
    )
    return f"ta_interp : [{options}];"


def question_variables(question: Question) -> str:
    parts = [question.variables, answer_expressions(question)]
    if question.scaffold == "choice":
        parts.append(dropdown_teacher_answer(question))
    return "\n".join(part for part in parts if part)


def stem_html(question: Question) -> str:
    parts = [to_html(question.stem)]

    if question.scaffold == "stated":
        intended = next(r for r in question.readings if r.intended)
        prefix = question.interpretation["stated_prefix"]
        parts.append(f"<p><em>{prefix} {intended.label}.</em></p>")

    if question.scaffold == "choice":
        parts.append(to_html(question.interpretation["prompt"]))
        # STACK requires exactly one [[validation:...]] per input, even for a
        # dropdown, whose showvalidation is 0 so it renders nothing.
        parts.append("<p>[[input:interp]] [[validation:interp]] [[feedback:interp]]</p>")

    parts.append(to_html(question.answer["prompt"]))
    parts.append("<p>[[input:ans1]] [[validation:ans1]]</p>")
    return "\n".join(parts)


def input_elements(question: Question) -> str:
    xml = ""

    if question.scaffold == "choice":
        xml += render_input(
            name="interp",
            itype="dropdown",
            tans="ta_interp",
            boxsize=0,
            mustverify=0,
            showvalidation=0,
        )

    answer = question.answer
    itype = answer.get("type", "algebraic")
    xml += render_input(
        name="ans1",
        itype=itype,
        tans="ta",
        boxsize=int(answer.get("boxsize", 15)),
        mustverify=1,
        showvalidation=1,
        forbidfloat=0 if itype in ("numerical", "units") else 1,
        syntaxhint=answer.get("syntaxhint", ""),
        options=answer.get("options", ""),
    )
    return xml


def render_input(
    name: str,
    itype: str,
    tans: str,
    boxsize: int,
    mustverify: int,
    showvalidation: int,
    forbidfloat: int = 0,
    syntaxhint: str = "",
    options: str = "",
) -> str:
    return (
        "    <input>\n"
        f"      <name>{name}</name>\n"
        f"      <type>{itype}</type>\n"
        f"      <tans>{tans}</tans>\n"
        f"      <boxsize>{boxsize}</boxsize>\n"
        "      <strictsyntax>1</strictsyntax>\n"
        # 4 = insert stars for implied multiplication and for spaces, so
        # students may write "2 m/s" or "2m/s" for 2*m/s.
        "      <insertstars>4</insertstars>\n"
        f"      <syntaxhint>{syntaxhint}</syntaxhint>\n"
        "      <syntaxattribute>0</syntaxattribute>\n"
        "      <forbidwords></forbidwords>\n"
        "      <allowwords></allowwords>\n"
        f"      <forbidfloat>{forbidfloat}</forbidfloat>\n"
        "      <requirelowestterms>0</requirelowestterms>\n"
        "      <checkanswertype>0</checkanswertype>\n"
        f"      <mustverify>{mustverify}</mustverify>\n"
        f"      <showvalidation>{showvalidation}</showvalidation>\n"
        f"      <options>{options}</options>\n"
        "    </input>\n"
    )


def render_node(
    index: int,
    answertest: str,
    sans: str,
    tans: str,
    prt: str,
    testoptions: str = "",
    truescore: float = 1.0,
    falsescore: float = 0.0,
    truenext: int = -1,
    falsenext: int = -1,
    truefeedback: str = "",
    falsefeedback: str = "",
) -> str:
    return (
        "      <node>\n"
        f"        <name>{index}</name>\n"
        "        <description></description>\n"
        f"        <answertest>{answertest}</answertest>\n"
        f"        <sans>{sans}</sans>\n"
        f"        <tans>{tans}</tans>\n"
        f"        <testoptions>{testoptions}</testoptions>\n"
        "        <quiet>0</quiet>\n"
        "        <truescoremode>=</truescoremode>\n"
        f"        <truescore>{truescore:.7f}</truescore>\n"
        "        <truepenalty></truepenalty>\n"
        f"        <truenextnode>{truenext}</truenextnode>\n"
        f"        <trueanswernote>{prt}-{index}-T</trueanswernote>\n"
        + text_element("truefeedback", truefeedback, "        ")
        + "        <falsescoremode>=</falsescoremode>\n"
        f"        <falsescore>{falsescore:.7f}</falsescore>\n"
        "        <falsepenalty></falsepenalty>\n"
        f"        <falsenextnode>{falsenext}</falsenextnode>\n"
        f"        <falseanswernote>{prt}-{index}-F</falseanswernote>\n"
        + text_element("falsefeedback", falsefeedback, "        ")
        + "      </node>\n"
    )


def reading_nodes(
    prt: str,
    answertest: str,
    sans: str,
    tans_of,
    testoptions: str,
    readings: list[Reading],
    intended_feedback: bool = True,
) -> str:
    """A chain of nodes: node 0 is the credited answer, then one per misreading.

    Landing on node i > 0 means the answer is wrong but explicable, so that
    reading's explanation can be given instead of a bare 'incorrect'.
    """
    intended = next(r for r in readings if r.intended)
    misreadings = [r for r in readings if not r.intended]

    nodes = render_node(
        index=0,
        answertest=answertest,
        sans=sans,
        tans=tans_of(intended),
        prt=prt,
        testoptions=testoptions,
        truescore=1.0,
        truefeedback=f"<p>{intended.why}</p>" if intended_feedback and intended.why else "",
        falsenext=1 if misreadings else -1,
    )
    for offset, reading in enumerate(misreadings):
        index = offset + 1
        nodes += render_node(
            index=index,
            answertest=answertest,
            sans=sans,
            tans=tans_of(reading),
            prt=prt,
            testoptions=testoptions,
            truescore=0.0,
            truefeedback=f"<p>{reading.why}</p>" if reading.why else "",
            falsenext=index + 1 if index < len(misreadings) else -1,
        )
    return nodes


def render_prt(name: str, value: float, nodes: str, feedbackvariables: str = "") -> str:
    return (
        "    <prt>\n"
        f"      <name>{name}</name>\n"
        f"      <value>{value:.7f}</value>\n"
        "      <autosimplify>1</autosimplify>\n"
        "      <feedbackstyle>1</feedbackstyle>\n"
        f"      <feedbackvariables>\n        <text>{escape(feedbackvariables)}</text>\n      </feedbackvariables>\n"
        + nodes
        + "    </prt>\n"
    )


def prt_elements(question: Question) -> str:
    weight = float(question.interpretation.get("weight", 0.5)) if question.scaffold == "choice" else 0.0
    answertest, defaulttolerance = ANSWER_TESTS[question.answer.get("type", "algebraic")]
    testoptions = str(question.answer.get("tolerance", defaulttolerance))
    xml = ""

    if question.scaffold == "choice":
        xml += render_prt("interp", weight, reading_nodes(
            "interp", "String", "interp", lambda r: maxima_string(r.key), "", question.readings
        ))
        # The answer is graded against the reading the student selected, so a
        # misreading costs exactly `weight` and correct execution of the chosen
        # reading earns the rest. The two marks are independent.
        pairs = ", ".join(
            f"[{maxima_string(r.key)}, {'ta' if r.intended else f'ta_{r.key}'}]"
            for r in question.readings
        )
        nodes = reading_nodes(
            "ans",
            answertest,
            "ans1",
            lambda r: "ta_sel" if r.intended else f"ta_{r.key}",
            testoptions,
            question.readings,
            intended_feedback=False,
        )
        xml += render_prt("ans", 1.0 - weight, nodes,
                          feedbackvariables=f"ta_sel : assoc(interp, [{pairs}]);")
        return xml

    if question.readings:
        nodes = reading_nodes(
            "ans",
            answertest,
            "ans1",
            lambda r: "ta" if r.intended else f"ta_{r.key}",
            testoptions,
            question.readings,
        )
    else:
        nodes = render_node(
            index=0,
            answertest=answertest,
            sans="ans1",
            tans="ta",
            prt="ans",
            testoptions=testoptions,
            truescore=1.0,
        )

    xml += render_prt("ans", 1.0 - weight, nodes)
    return xml


def qtest_elements(question: Question) -> str:
    """One test per reading: the intended one scores full marks, each
    misreading must land on its own answer note. Under `choice` every
    misreading is tested both ways: selected and executed correctly (full
    answer credit, reading credit lost), and answered without being selected
    (named by the answer tree)."""
    misreadings = [r for r in question.readings if not r.intended]

    if question.scaffold == "choice":
        intended = next(r for r in question.readings if r.intended)
        # (ans1 value, interp key, ans score, ans note, interp score, interp note)
        cases = [("ta", intended.key, 1.0, "ans-0-T", 1.0, "interp-0-T")]
        for offset, reading in enumerate(misreadings):
            node = offset + 1
            cases.append((f"ta_{reading.key}", reading.key, 1.0, "ans-0-T", 0.0, f"interp-{node}-T"))
            cases.append((f"ta_{reading.key}", intended.key, 0.0, f"ans-{node}-T", 1.0, "interp-0-T"))
    else:
        cases = [("ta", None, 1.0, "ans-0-T", None, None)]
        for offset, reading in enumerate(misreadings):
            cases.append((f"ta_{reading.key}", None, 0.0, f"ans-{offset + 1}-T", None, None))

    xml = ""
    for number, (value, chosen, score, note, iscore, inote) in enumerate(cases, start=1):
        inputs = f"      <testinput>\n        <name>ans1</name>\n        <value>{value}</value>\n      </testinput>\n"
        expectations = [("ans", score, note)]
        if chosen is not None:
            inputs += (
                "      <testinput>\n"
                "        <name>interp</name>\n"
                f"        <value>{maxima_string(chosen)}</value>\n"
                "      </testinput>\n"
            )
            expectations.append(("interp", iscore, inote))
        expected = "".join(
            "      <expected>\n"
            f"        <name>{name}</name>\n"
            f"        <expectedscore>{s:.7f}</expectedscore>\n"
            f"        <expectedpenalty>{0.0 if s else question.penalty:.7f}</expectedpenalty>\n"
            f"        <expectedanswernote>{n}</expectedanswernote>\n"
            "      </expected>\n"
            for name, s, n in expectations
        )
        xml += (
            "    <qtest>\n"
            f"      <testcase>{number}</testcase>\n"
            "      <description></description>\n" + inputs + expected + "    </qtest>\n"
        )
    return xml


def render_question(question: Question, stackversion: str) -> str:
    tags = ""
    if question.tags:
        items = "".join(f"      <tag><text>{escape(tag)}</text></tag>\n" for tag in question.tags)
        tags = f"    <tags>\n{items}    </tags>\n"

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<quiz>\n"
        '  <question type="stack">\n'
        f"    <name>\n      <text>{escape(question.name)}</text>\n    </name>\n"
        + text_element("questiontext", stem_html(question))
        + text_element("generalfeedback", to_html(question.general_feedback) if question.general_feedback else "")
        + element("defaultgrade", f"{question.grade:g}")
        + element("penalty", f"{question.penalty:g}")
        + element("hidden", 0)
        + element("idnumber", question.id)
        + f"    <stackversion>\n      <text>{stackversion}</text>\n    </stackversion>\n"
        + f"    <questionvariables>\n      <text>{cdata(question_variables(question))}</text>\n    </questionvariables>\n"
        + text_element("specificfeedback", "<p>[[feedback:ans]]</p>")
        + f'    <questionnote format="moodle_auto_format">\n      <text>{cdata(question.note or "{@ta@}")}</text>\n    </questionnote>\n'
        + '    <questiondescription format="moodle_auto_format">\n      <text></text>\n    </questiondescription>\n'
        + element("questionsimplify", 1)
        + element("assumepositive", 0)
        + element("assumereal", 0)
        + element("decimals", ",")
        + element("scientificnotation", "*10")
        + element("multiplicationsign", "dot")
        + element("sqrtsign", 1)
        + element("complexno", "i")
        + element("inversetrig", "cos-1")
        + element("logicsymbol", "lang")
        + element("matrixparens", "[")
        + "    <variantsselectionseed></variantsselectionseed>\n"
        + input_elements(question)
        + prt_elements(question)
        + "".join(f"    <deployedseed>{seed}</deployedseed>\n" for seed in question.seeds)
        + qtest_elements(question)
        + tags
        + "  </question>\n"
        "</quiz>\n"
    )


def load_quiz(path: Path, source: dict) -> dict:
    behaviour = source.get("behaviour", "adaptive")
    if behaviour not in QUIZ_BEHAVIOURS:
        fail(path, f"behaviour must be one of {', '.join(QUIZ_BEHAVIOURS)}")

    quiz = {
        "id": str(require(path, source, "id")),
        "name": str(require(path, source, "name")),
        "intro": to_html(source.get("intro", "")),
        "behaviour": behaviour,
        "questionsperpage": int(source.get("questionsperpage", 1)),
        "attempts": int(source.get("attempts", 0)),
        "grademethod": source.get("grademethod", "highest"),
        "questions": [],
    }
    for entry in require(path, source, "questions"):
        quiz["questions"].append(
            {"id": str(entry["id"]), "maxmark": float(entry.get("maxmark", 1.0))}
        )
    return quiz


def compile_tree(source: Path, out: Path, stackversion: str) -> int:
    questions: dict[str, Question] = {}
    quizzes: list[dict] = []

    for path in sorted(source.rglob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data is None:
            fail(path, "file is empty")
        if "questions" in data:
            quizzes.append(load_quiz(path, data))
            continue
        question = load_question(path, data)
        if question.id in questions:
            fail(path, f"id '{question.id}' already used by {questions[question.id].path}")
        questions[question.id] = question

    for quiz in quizzes:
        for entry in quiz["questions"]:
            if entry["id"] not in questions:
                raise SourceError(f"quiz '{quiz['id']}' refers to unknown question '{entry['id']}'")

    # Start from a clean tree so that renamed or deleted sources cannot leave
    # stale XML behind for the importer to pick up.
    for stale in (out / "questions", out / "quizzes"):
        shutil.rmtree(stale, ignore_errors=True)

    for question in questions.values():
        target = out.joinpath("questions", *question.category, f"{question.id}.xml")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render_question(question, stackversion), encoding="utf-8")

    if quizzes:
        quizdir = out / "quizzes"
        quizdir.mkdir(parents=True, exist_ok=True)
        for quiz in quizzes:
            (quizdir / f"{quiz['id']}.json").write_text(
                json.dumps(quiz, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

    print(f"compiled {len(questions)} questions, {len(quizzes)} quizzes into {out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--stack-version", required=True)
    args = parser.parse_args()

    if not args.source.is_dir():
        print(f"Source directory not found: {args.source}", file=sys.stderr)
        return 1

    try:
        return compile_tree(args.source, args.out, args.stack_version)
    except SourceError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
