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

# A units answer is graded strictly by default: full marks need the unit the
# teacher's formula uses. A correct value in a different but compatible unit
# would pass UnitsRelative silently and fail UnitsStrictRelative with nothing
# usable, so strict questions chain both: a strict node for full marks, then a
# UnitsRelative node for partial credit and a conversion prompt. `strict:
# false` keeps plain UnitsRelative, for questions that let the student choose
# the unit.
UNIT_STRICT_TEST = "UnitsStrictRelative"
UNIT_FALLBACK_SCORE = 0.75
UNIT_FALLBACK_FEEDBACK = (
    "<p>Lukuarvosi vastaa oikeaa arvoa, mutta vastausta pyydettiin toisessa "
    "yksikössä. Muunna vastauksesi pyydettyyn yksikköön.</p>"
)
# Multiplying by 1000 ms/s leaves the quantity unchanged but the units
# different, whatever they are: the question-test input for the fallback node.
UNIT_FALLBACK_TESTINPUT = "1000*ta*ms/s"

# Fading ladder, easiest first: the intended reading is stated, then chosen
# from a list, then left to be inferred. Distractor feedback is given at every
# rung, so a misreading is always named rather than just marked wrong.
SCAFFOLDS = ("stated", "choice", "none")

# AI-graded explanation questions (type: aitext). Bounds per
# notes/aitext-rubric-design.md: few small judgements grade reliably, one
# big one does not. Three levels is the intended default; two is a strict
# met/not-met criterion.
AITEXT_CRITERIA_RANGE = (2, 5)
AITEXT_LEVELS_RANGE = (2, 5)

# How much of the grading the student is shown (Feature 3, purely
# presentational): no numbers at all, a three-way badge per criterion, or
# points per criterion plus the total.
AITEXT_GRADINGS = ("none", "coarse", "fine")

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

# Review options: what the student is shown while answering ('during') and
# when looking at a submitted attempt ('after'). 'marks' covers both the
# maximum and the earned mark. Moodle always shows the attempt itself during
# it and never shows overall feedback during it, whatever is listed here.
REVIEW_PARTS = (
    "attempt",
    "correctness",
    "marks",
    "specificfeedback",
    "generalfeedback",
    "rightanswer",
    "overallfeedback",
)
REVIEW_DEFAULTS = {
    "during": ["correctness", "marks", "specificfeedback"],
    # No 'rightanswer': Moodle renders STACK teacher answers as raw Maxima
    # ("(50*km)/h"), which only confuses. The model solution in the general
    # feedback shows the correct answer properly typeset.
    "after": ["attempt", "correctness", "marks", "specificfeedback",
              "generalfeedback", "overallfeedback"],
}

# Symbols STACK treats as units in units questions, generated the way STACK
# generates them (stack/cas/casstring.units.class.php): each prefix with each
# prefixable unit, plus the non-prefixable names. A question variable with one
# of these names shadows the unit in every expression of the question --
# including the teacher's answer -- so it is refused outright.
UNIT_PREFIXES = "y z a f p n u m c d da h k M G T P E Z Y".split()
UNIT_PREFIXABLE = (
    "m l L g t s h Hz Bq cd N Pa cal Cal Btu eV J W Wh A ohm Omega C V F S "
    "Wb T H Gy rem Sv lx lm mol M kat rad sr K VA Ci"
).split()
UNIT_NONPREFIX = (
    "min amu u mmHg bar ha cc gal mbar atm torr rev deg rpm au Da Np B dB "
    "day year hp in ft yd mi lb dpt"
).split()
UNIT_NAMES = frozenset(UNIT_NONPREFIX).union(
    prefix + unit for prefix in [""] + UNIT_PREFIXES for unit in UNIT_PREFIXABLE
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
    if "strict" in answer and answer.get("type") != "units":
        fail(path, "'answer.strict' only applies to answer type 'units'")
    if readings and "quantity" not in answer:
        fail(path, "'answer.quantity' must name the symbol the readings stand for")
    if answer.get("type") == "units":
        assigned = re.findall(
            r"(?:^|;)\s*([A-Za-z][A-Za-z0-9_]*)\s*:", str(source.get("variables", "")), re.M
        )
        shadowed = [n for n in assigned + [str(answer.get("quantity", ""))] if n in UNIT_NAMES]
        if shadowed:
            fail(path, "variable(s) shadow STACK unit names in a units question: "
                 + ", ".join(shadowed))
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


def load_aitext_question(path: Path, source: dict) -> dict:
    """Validate an aitext drilling question and return its eval spec.

    The spec (JSON, written under <out>/aitext/) carries the question, the
    rubric in the exact shape the qtype_aitext fork stores it, and the
    golden tests for the evaluation harness (qbank/cli/aitext-test.php).
    Import into Moodle is still pending; until it lands these compile to
    eval specs only, and quizzes may not reference them.
    """
    qid = str(require(path, source, "id"))
    if not ID_RE.match(qid):
        fail(path, f"id '{qid}' must be lowercase kebab-case")
    require(path, source, "name")
    require(path, source, "stem")
    require(path, source, "language")
    category = require(path, source, "category")
    if not isinstance(category, list) or not category:
        fail(path, "'category' must be a non-empty list of category names")
    grading = source.get("grading", "fine")
    if grading not in AITEXT_GRADINGS:
        fail(path, f"'grading' must be one of {', '.join(AITEXT_GRADINGS)}")

    rubric = require(path, source, "rubric")
    criteria = rubric.get("criteria") if isinstance(rubric, dict) else None
    lo, hi = AITEXT_CRITERIA_RANGE
    if not isinstance(criteria, list) or not lo <= len(criteria) <= hi:
        fail(path, f"'rubric.criteria' must be a list of {lo}-{hi} criteria")

    # Criterion id -> its highest level index (= its points).
    ranges: dict[str, int] = {}
    for criterion in criteria:
        cid = str(criterion.get("id", ""))
        if not ID_RE.match(cid):
            fail(path, f"criterion id '{cid}' must be lowercase kebab-case")
        if cid in ranges:
            fail(path, f"duplicate criterion id '{cid}'")
        if not criterion.get("title"):
            fail(path, f"criterion '{cid}' needs a 'title'")
        levels = criterion.get("levels")
        lo_l, hi_l = AITEXT_LEVELS_RANGE
        if not isinstance(levels, list) or not lo_l <= len(levels) <= hi_l:
            fail(path, f"criterion '{cid}' needs {lo_l}-{hi_l} level descriptors")
        if not all(isinstance(level, str) and level.strip() for level in levels):
            fail(path, f"criterion '{cid}' has an empty level descriptor")
        ranges[cid] = len(levels) - 1

    names: set[str] = set()
    tests: list[dict] = []
    for test in source.get("tests", []):
        tname = str(test.get("name", ""))
        if not tname:
            fail(path, "every test needs a 'name'")
        if tname in names:
            fail(path, f"duplicate test name '{tname}'")
        names.add(tname)
        if not str(test.get("answer", "")).strip():
            fail(path, f"test '{tname}' needs an 'answer'")
        expect = test.get("expect")
        if not isinstance(expect, dict) or set(expect) != set(ranges):
            fail(path, f"test '{tname}': 'expect' must cover exactly the "
                 f"criterion ids: {', '.join(ranges)}")
        normalised: dict[str, list[int]] = {}
        for cid, expected in expect.items():
            values = expected if isinstance(expected, list) else [expected]
            if not values or any(
                not isinstance(v, int) or not 0 <= v <= ranges[cid] for v in values
            ):
                fail(path, f"test '{tname}': expected level for '{cid}' must be "
                     f"an integer 0-{ranges[cid]} or a list of them")
            normalised[cid] = values
        tests.append({
            "name": tname,
            "answer": str(test["answer"]).strip(),
            "expect": normalised,
            "why": str(test.get("why", "")).strip(),
        })

    return {
        "id": qid,
        "name": str(source["name"]),
        "category": [str(part) for part in category],
        "tags": [str(tag) for tag in source.get("tags", [])],
        "stem_html": to_html(str(source["stem"])),
        "context": str(source.get("context", "")).strip(),
        "feedback_html": to_html(str(source.get("feedback", ""))),
        # The rubric column of the qtype_aitext fork, verbatim.
        "rubric": {
            "language": str(source["language"]),
            "display": grading,
            "sampleanswer": str(source.get("sampleanswer", "")).strip(),
            "criteria": [
                {
                    "id": str(criterion["id"]),
                    "title": str(criterion["title"]),
                    "levels": [str(level).strip() for level in criterion["levels"]],
                }
                for criterion in criteria
            ],
        },
        "tests": tests,
    }


def strict_units(question: Question) -> bool:
    return question.answer.get("type") == "units" and question.answer.get("strict", True)


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
    strict_test: str = "",
) -> str:
    """A chain of nodes: node 0 is the credited answer, then one per misreading.

    Landing on node i > 0 means the answer is wrong but explicable, so that
    reading's explanation can be given instead of a bare 'incorrect'.
    With `strict_test`, node 0 uses it and node 1 is the compatible-unit
    fallback, so the misreadings start at node 2.
    """
    intended = next(r for r in readings if r.intended)
    misreadings = [r for r in readings if not r.intended]
    first_misreading = 2 if strict_test else 1

    nodes = render_node(
        index=0,
        answertest=strict_test or answertest,
        sans=sans,
        tans=tans_of(intended),
        prt=prt,
        testoptions=testoptions,
        truescore=1.0,
        truefeedback=f"<p>{intended.why}</p>" if intended_feedback and intended.why else "",
        falsenext=1 if strict_test or misreadings else -1,
    )
    if strict_test:
        nodes += render_node(
            index=1,
            answertest=answertest,
            sans=sans,
            tans=tans_of(intended),
            prt=prt,
            testoptions=testoptions,
            truescore=UNIT_FALLBACK_SCORE,
            truefeedback=UNIT_FALLBACK_FEEDBACK,
            falsenext=2 if misreadings else -1,
        )
    for offset, reading in enumerate(misreadings):
        index = offset + first_misreading
        nodes += render_node(
            index=index,
            answertest=answertest,
            sans=sans,
            tans=tans_of(reading),
            prt=prt,
            testoptions=testoptions,
            truescore=0.0,
            truefeedback=f"<p>{reading.why}</p>" if reading.why else "",
            falsenext=index + 1 if offset < len(misreadings) - 1 else -1,
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
    strict_test = UNIT_STRICT_TEST if strict_units(question) else ""
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
            strict_test=strict_test,
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
            strict_test=strict_test,
        )
    elif strict_test:
        nodes = render_node(
            index=0,
            answertest=strict_test,
            sans="ans1",
            tans="ta",
            prt="ans",
            testoptions=testoptions,
            truescore=1.0,
            falsenext=1,
        )
        nodes += render_node(
            index=1,
            answertest=answertest,
            sans="ans1",
            tans="ta",
            prt="ans",
            testoptions=testoptions,
            truescore=UNIT_FALLBACK_SCORE,
            truefeedback=UNIT_FALLBACK_FEEDBACK,
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
    misreading must land on its own answer note. Strict units questions add a
    case for the compatible-unit fallback node. Under `choice` every
    misreading is tested both ways: selected and executed correctly (full
    answer credit, reading credit lost), and answered without being selected
    (named by the answer tree)."""
    misreadings = [r for r in question.readings if not r.intended]
    strict = strict_units(question)
    first_misreading = 2 if strict else 1

    if question.scaffold == "choice":
        intended = next(r for r in question.readings if r.intended)
        # (ans1 value, interp key, ans score, ans note, interp score, interp note)
        cases = [("ta", intended.key, 1.0, "ans-0-T", 1.0, "interp-0-T")]
        if strict:
            cases.append((UNIT_FALLBACK_TESTINPUT, intended.key,
                          UNIT_FALLBACK_SCORE, "ans-1-T", 1.0, "interp-0-T"))
        for offset, reading in enumerate(misreadings):
            cases.append((f"ta_{reading.key}", reading.key, 1.0, "ans-0-T", 0.0, f"interp-{offset + 1}-T"))
            cases.append((f"ta_{reading.key}", intended.key, 0.0, f"ans-{offset + first_misreading}-T", 1.0, "interp-0-T"))
    else:
        cases = [("ta", None, 1.0, "ans-0-T", None, None)]
        if strict:
            cases.append((UNIT_FALLBACK_TESTINPUT, None, UNIT_FALLBACK_SCORE, "ans-1-T", None, None))
        for offset, reading in enumerate(misreadings):
            cases.append((f"ta_{reading.key}", None, 0.0, f"ans-{offset + first_misreading}-T", None, None))

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
            f"        <expectedpenalty>{0.0 if s == 1.0 else question.penalty:.7f}</expectedpenalty>\n"
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

    review_source = source.get("review", {})
    if not isinstance(review_source, dict) or set(review_source) - set(REVIEW_DEFAULTS):
        fail(path, "review takes 'during' and 'after' only")
    review = {}
    for phase, default in REVIEW_DEFAULTS.items():
        parts = review_source.get(phase, default)
        if parts == "all":
            parts = list(REVIEW_PARTS)
        if not isinstance(parts, list) or any(p not in REVIEW_PARTS for p in parts):
            fail(path, f"review {phase} must be 'all' or a list from: {', '.join(REVIEW_PARTS)}")
        review[phase] = parts

    quiz = {
        "id": str(require(path, source, "id")),
        "name": str(require(path, source, "name")),
        "intro": to_html(source.get("intro", "")),
        "behaviour": behaviour,
        "questionsperpage": int(source.get("questionsperpage", 1)),
        "attempts": int(source.get("attempts", 0)),
        "grademethod": source.get("grademethod", "highest"),
        "review": review,
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
    aitext: dict[str, dict] = {}

    for path in sorted(source.rglob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data is None:
            fail(path, "file is empty")
        if "questions" in data:
            quizzes.append(load_quiz(path, data))
            continue
        qtype = data.get("type", "stack")
        if qtype == "aitext":
            spec = load_aitext_question(path, data)
            if spec["id"] in questions or spec["id"] in aitext:
                fail(path, f"id '{spec['id']}' already used")
            aitext[spec["id"]] = spec
            continue
        if qtype != "stack":
            fail(path, f"unknown question type '{qtype}'")
        question = load_question(path, data)
        if question.id in questions or question.id in aitext:
            fail(path, f"id '{question.id}' already in use")
        questions[question.id] = question

    for quiz in quizzes:
        for entry in quiz["questions"]:
            if entry["id"] not in questions:
                raise SourceError(f"quiz '{quiz['id']}' refers to unknown question '{entry['id']}'")

    # Start from a clean tree so that renamed or deleted sources cannot leave
    # stale XML behind for the importer to pick up.
    for stale in (out / "questions", out / "quizzes", out / "aitext"):
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

    if aitext:
        aitextdir = out / "aitext"
        aitextdir.mkdir(parents=True, exist_ok=True)
        for spec in aitext.values():
            (aitextdir / f"{spec['id']}.json").write_text(
                json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

    print(f"compiled {len(questions)} questions, {len(quizzes)} quizzes into {out}")
    if aitext:
        print(f"compiled {len(aitext)} aitext questions into eval specs "
              "(Moodle import still pending)")
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
