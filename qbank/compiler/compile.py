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
import base64
import hashlib
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
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

# Provenance: every question is tagged with the content-repo commit it was
# compiled from, so that an attempt made against a question version leads back
# to the source and to the commit message explaining why it is worded that way.
# The importer strips tags with this prefix before deciding whether a question
# has changed; without that, a new commit would re-import every question and
# create a meaningless Moodle version for each.
PROVENANCE_TAG_PREFIX = "src-"

# Figures. A data-bearing figure is a STACK plot() call written as its Maxima
# argument list; a schematic is an SVG file from the content repo, embedded
# into the XML as base64 so that the content author never handles a binary.
#
# Gnuplot writes axis ticks with a decimal point, and a graph whose axis reads
# "2.5" beside prose reading "2,5" is exactly the inconsistency this project
# exists to remove. STACK splices PLOT_TERM_OPT verbatim into gnuplot's "set
# terminal" line, which is the only hook a question has into the plot
# preamble; appending a command there reaches gnuplot intact. Read the site
# value rather than restating it, so the font and line width stay whatever the
# Maxima image was built with.
DECIMAL_COMMA = (
    'PLOT_TERM_OPT : sconcat(PLOT_TERM_OPT, ascii(10), "set decimalsign \\",\\"");'
)

# Names a plot expression may use besides the question's own variables: the
# plot forms and options STACK permits (stackmaxima.mac, permitted_options),
# the axis variables, and the Maxima functions a school-physics graph needs.
FIGURE_NAMES = frozenset("""
    x y t discrete parametric contour minus plus
    xlabel ylabel label legend levels color style point_type nticks
    logx logy axes box plot_realpart yx_ratio xtics ytics ztics adapt_depth
    plotepsilon xy_scale same_xy sample margin size plottags true false
    sin cos tan asin acos atan sqrt exp log abs min max floor ceiling round
    if then else and or not
""".split())

# An SVG is text, but not everything text can do belongs in an exam page: a
# script or an external reference turns a figure into a fetch the student's
# browser makes mid-exam, and a diagram that silently fails to load breaks a
# question in a way the student cannot diagnose.
SVG_FORBIDDEN = (
    (re.compile(r"<script", re.I), "a <script> element"),
    (re.compile(r"\son[a-z]+\s*=", re.I), "an inline event handler"),
    (re.compile(r"""["'(]\s*(?:https?:)?//""", re.I), "an external reference"),
    (re.compile(r"<!ENTITY", re.I), "an entity declaration"),
)

# Ways to put a figure into a question that would bypass the checks above:
# the prose fields pass CASText, LaTeX and HTML through untouched, so each of
# these would reach STACK with no alt text and outside the rendering gate.
PROSE_FORBIDDEN = (
    ("{@plot(", "a plot() call"),
    ("<img", "an <img> element"),
    ("<svg", "an <svg> element"),
)

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
class Figure:
    alt: str
    plot: str = ""
    svg: Path | None = None

    @property
    def filename(self) -> str:
        return self.svg.name if self.svg else ""


@dataclass
class Question:
    path: Path
    id: str
    name: str
    category: list[str]
    variables: str
    stem: str
    answer: dict | None = None
    figure: Figure | None = None
    scaffold: str = "none"
    interpretation: dict | None = None
    readings: list[Reading] = field(default_factory=list)
    # type: mcq. Options reuse the Reading shape: key/label/why as for
    # readings, intended = correct, value unused.
    options: list[Reading] = field(default_factory=list)
    shuffle: bool = True
    show: int = 0  # options shown per variant; 0 = all of them
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


def text_element(name: str, html: str, indent: str = "    ", files: str = "") -> str:
    return (f'{indent}<{name} format="html">\n{indent}  <text>{cdata(html)}</text>\n'
            f'{files}{indent}</{name}>\n')


def assigned_names(variables: str) -> list[str]:
    """The variable names a Maxima 'variables:' block assigns."""
    return re.findall(r"(?:^|;)\s*([A-Za-z][A-Za-z0-9_]*)\s*:", variables, re.M)


def check_prose(path: Path, field: str, text: str) -> None:
    """Refuse a figure smuggled into a prose field.

    Prose passes through untouched, so a figure written there would carry no
    alt text and would never be seen by the rendering gate. Figures go in
    'figure:', which is checked.
    """
    lowered = str(text).lower()
    for marker, what in PROSE_FORBIDDEN:
        if marker in lowered:
            fail(path, f"'{field}' contains {what}; figures belong in 'figure:'")


def load_figure(path: Path, source: dict, sourceroot: Path) -> Figure | None:
    figure = source.get("figure")
    if not figure:
        return None
    if not isinstance(figure, dict):
        fail(path, "'figure' must be a mapping")

    unknown = set(figure) - {"alt", "plot", "svg"}
    if unknown:
        fail(path, f"figure has unknown key(s): {', '.join(sorted(unknown))}")

    # STACK's default alt text is an English dump of the Maxima expression,
    # which is worse than none. There is no default here.
    alt = " ".join(str(figure.get("alt", "")).split())
    if not alt:
        fail(path, "'figure.alt' is required: describe the figure in Finnish")
    # A plot's alt text is a Maxima string inside a CASText block, where a
    # nested {@...@} does not survive the parse. Rather than let alt mean one
    # thing for a graph and another for a schematic, it is prose in both.
    if "{@" in alt:
        fail(path, "'figure.alt' cannot interpolate variables; describe the "
                   "figure, and put the numbers in the stem")

    if bool(figure.get("plot")) == bool(figure.get("svg")):
        fail(path, "figure needs exactly one of 'plot' (a graph) or 'svg' (a schematic)")

    if figure.get("plot"):
        plot = " ".join(str(figure["plot"]).split())
        check_plot(path, plot, str(source.get("variables", "")))
        return Figure(alt=alt, plot=plot)

    return Figure(alt=alt, svg=resolve_svg(path, str(figure["svg"]), sourceroot))


def check_plot(path: Path, plot: str, variables: str) -> None:
    """A plot draws the variant's numbers, so it must read them from
    'variables:' rather than repeat them. A repeated constant is a grading
    defect waiting to happen: the student reads the picture correctly and is
    marked wrong. Neither a decimal number nor a constant the variables
    already define may appear in the plot."""
    # Labels are prose; nothing inside them is a value or a variable name.
    bare = re.sub(r'"[^"]*"', '""', plot)

    if re.search(r"\d*\.\d+|\d+\.\d*", bare):
        fail(path, "'figure.plot' contains a decimal number; "
                   "plotted values must come from 'variables:'")

    known = set(assigned_names(variables)) | FIGURE_NAMES
    used = {name for name in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", bare)}
    unknown = sorted(used - known)
    if unknown:
        fail(path, "'figure.plot' uses name(s) not defined in 'variables:': "
                   + ", ".join(unknown))

    # 0 and 1 are structure (an origin, a unit step), not measurements.
    constants = {n for n in re.findall(r"\b\d+\b", re.sub(r'"[^"]*"', '""', variables))}
    repeated = sorted({n for n in re.findall(r"\b\d+\b", bare)} & constants - {"0", "1"})
    if repeated:
        fail(path, "'figure.plot' repeats constant(s) from 'variables:': "
                   + ", ".join(repeated) + "; name them instead")


def resolve_svg(path: Path, name: str, sourceroot: Path) -> Path:
    """Locate a schematic in the content repository and refuse an unsafe one."""
    if name.startswith("/"):
        fail(path, f"'figure.svg' must be relative to the content root: {name}")
    target = (sourceroot / name).resolve()
    if not target.is_relative_to(sourceroot.resolve()):
        fail(path, f"'figure.svg' points outside the content root: {name}")
    if target.suffix != ".svg":
        fail(path, f"'figure.svg' must be an .svg file: {name}")
    if not target.is_file():
        fail(path, f"'figure.svg' not found: {name}")

    # Namespace declarations are URLs that are never fetched; everything else
    # that looks like a URL is a fetch the student's browser would make.
    content = re.sub(r'xmlns(:\w+)?\s*=\s*"[^"]*"', "", target.read_text(encoding="utf-8"))
    for pattern, what in SVG_FORBIDDEN:
        if pattern.search(content):
            fail(path, f"'figure.svg' {name} contains {what}")

    return target


def load_question(path: Path, source: dict, sourceroot: Path) -> Question:
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
        assigned = assigned_names(str(source.get("variables", "")))
        shadowed = [n for n in assigned + [str(answer.get("quantity", ""))] if n in UNIT_NAMES]
        if shadowed:
            fail(path, "variable(s) shadow STACK unit names in a units question: "
                 + ", ".join(shadowed))
    if scaffold == "choice" and not interpretation.get("prompt"):
        fail(path, "scaffold 'choice' requires 'interpretation.prompt'")
    if scaffold == "stated" and not interpretation.get("stated_prefix"):
        fail(path, "scaffold 'stated' requires 'interpretation.stated_prefix'")

    check_prose(path, "stem", source["stem"])
    check_prose(path, "feedback", source.get("feedback", ""))
    check_prose(path, "answer.prompt", answer["prompt"])
    for key in ("prompt", "stated_prefix"):
        check_prose(path, f"interpretation.{key}", (interpretation or {}).get(key, ""))
    for reading in readings:
        check_prose(path, f"reading '{reading.key}'", reading.label + reading.why)

    return Question(
        path=path,
        id=qid,
        name=str(require(path, source, "name")),
        category=[str(part) for part in category],
        variables=str(source.get("variables", "")).strip(),
        stem=str(require(path, source, "stem")),
        answer=answer,
        figure=load_figure(path, source, sourceroot),
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


def load_mcq_question(path: Path, source: dict, sourceroot: Path) -> Question:
    """Validate a multiple-choice question (type: mcq).

    The options become a STACK radio input whose teacher answer is a list of
    [key, correct, label] triples. Shuffling and the distractor-pool draw
    ('show:') both run in question variables, so either makes the question
    random and seeds become required, per the existing rule.
    """
    qid = str(require(path, source, "id"))
    if not ID_RE.match(qid):
        fail(path, f"id '{qid}' must be lowercase kebab-case")

    category = require(path, source, "category")
    if not isinstance(category, list) or not category:
        fail(path, "'category' must be a non-empty list of category names")

    entries = require(path, source, "options")
    if not isinstance(entries, list) or len(entries) < 2:
        fail(path, "'options' must be a list of at least two options")
    options: list[Reading] = []
    for entry in entries:
        # Option keys are the analysis vocabulary, so they follow the id
        # convention; unlike reading keys they never become variable names,
        # only Maxima strings, so kebab-case is safe.
        key = str(entry.get("key", ""))
        if not ID_RE.match(key):
            fail(path, f"option key '{key}' must be lowercase kebab-case")
        if any(option.key == key for option in options):
            fail(path, f"duplicate option key '{key}'")
        for wanted in ("label", "why"):
            if not str(entry.get(wanted, "")).strip():
                fail(path, f"option '{key}' needs a '{wanted}'")
        options.append(Reading(
            key=key,
            label=" ".join(str(entry["label"]).split()),
            value="",
            intended=bool(entry.get("correct", False)),
            why=str(entry["why"]).strip(),
        ))
    if sum(option.intended for option in options) != 1:
        fail(path, "exactly one option must be marked 'correct: true'")

    shuffle = bool(source.get("shuffle", True))
    show = source.get("show", 0)
    if "show" in source:
        if not isinstance(show, int) or not 2 <= show < len(options):
            fail(path, "'show' must be an integer at least 2 and smaller than "
                       "the option count (omit it to show every option)")

    if (shuffle or show or "rand" in str(source.get("variables", ""))) \
            and not source.get("seeds"):
        fail(path, "randomised questions need a 'seeds' list of deployed seeds")

    stem = str(require(path, source, "stem"))
    check_prose(path, "stem", stem)
    check_prose(path, "feedback", source.get("feedback", ""))
    for option in options:
        check_prose(path, f"option '{option.key}'", option.label + option.why)

    return Question(
        path=path,
        id=qid,
        name=str(require(path, source, "name")),
        category=[str(part) for part in category],
        variables=str(source.get("variables", "")).strip(),
        stem=stem,
        figure=load_figure(path, source, sourceroot),
        options=options,
        shuffle=shuffle,
        show=show,
        general_feedback=source.get("feedback", ""),
        note=source.get("note", ""),
        tags=[str(tag) for tag in source.get("tags", [])],
        seeds=[int(seed) for seed in source.get("seeds", [])],
        grade=float(source.get("grade", 1.0)),
        penalty=float(source.get("penalty", 0.1)),
    )


def load_aitext_question(path: Path, source: dict) -> dict:
    """Validate an aitext drilling question and return its spec.

    The spec is written twice: as an eval spec (JSON under <out>/aitext/)
    carrying the rubric in the exact shape qtype_aitext_rubric stores it
    plus the golden tests for the evaluation harness (qbank/cli/
    aitext-test.php), and as Moodle XML under <out>/questions/ for import.
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

    scaffold = str(source.get("scaffold", "")).strip()

    return {
        "id": qid,
        "name": str(source["name"]),
        "category": [str(part) for part in category],
        "tags": [str(tag) for tag in source.get("tags", [])],
        "stem_html": to_html(str(source["stem"])),
        "context": str(source.get("context", "")).strip(),
        "feedback_html": to_html(str(source.get("feedback", ""))),
        # An authored skeleton turns the visible-scaffold level on (Feature 2);
        # purely presentational, the grading pipeline never sees it.
        "scaffold_html": to_html(scaffold) if scaffold else "",
        # The rubric column of qtype_aitext_rubric, verbatim.
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


def render_aitext_question(spec: dict) -> str:
    """Moodle XML for an aitext question, mirroring qbank/cli/aitext-test.php:
    the grading context becomes the aiprompt, the rubric JSON goes in
    verbatim, and the markscheme stays empty so grading takes the rubric
    path. The element names are qtype_aitext_rubric's extra_question_fields()."""
    tags = ""
    if spec["tags"]:
        items = "".join(f"      <tag><text>{escape(tag)}</text></tag>\n" for tag in spec["tags"])
        tags = f"    <tags>\n{items}    </tags>\n"

    # The sample answer doubles as a sample response for the prompt tester
    # in the question editing form.
    sampleresponse = ""
    if spec["rubric"]["sampleanswer"]:
        sampleresponse = (
            "    <sampleresponse>\n"
            f"      <response>{escape(spec['rubric']['sampleanswer'])}</response>\n"
            "    </sampleresponse>\n"
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<quiz>\n"
        '  <question type="aitext_rubric">\n'
        f"    <name>\n      <text>{escape(spec['name'])}</text>\n    </name>\n"
        + text_element("questiontext", spec["stem_html"])
        + text_element("generalfeedback", spec["feedback_html"])
        + element("defaultgrade", 1)
        + element("penalty", 0)
        + element("hidden", 0)
        + element("idnumber", spec["id"])
        + element("responseformat", "plain")
        + element("responsefieldlines", 10)
        + element("minwordlimit", "")
        + element("maxwordlimit", "")
        + text_element("graderinfo", "")
        + text_element("responsetemplate", "")
        + element("aiprompt", escape(spec["context"]))
        + element("markscheme", "")
        + element("rubric", escape(json.dumps(spec["rubric"], ensure_ascii=False)))
        + element("scaffold", escape(spec["scaffold_html"]))
        + element("scaffoldlevel", 1 if spec["scaffold_html"] else 2)
        + element("model", "")
        + element("spellcheck", 0)
        + sampleresponse
        + tags
        + "  </question>\n"
        "</quiz>\n"
    )


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


def mcq_teacher_answer(question: Question) -> str:
    """Maxima defining ta_mcq, the [key, correct, label] triples the radio
    shows, in shown order. A pool keeps the full authored list and draws the
    shown keys per variant, the correct one always included; shuffling then
    permutes. Labels go through castext() so LaTeX in options works."""
    triples = ",\n  ".join(
        f"[{maxima_string(option.key)}, {'true' if option.intended else 'false'}, "
        f"castext({maxima_string(option.label)})]"
        for option in question.options
    )
    if question.show:
        correct = next(option for option in question.options if option.intended)
        distractors = ", ".join(
            maxima_string(option.key) for option in question.options if not option.intended
        )
        lines = [
            f"ta_mcq_all : [\n  {triples}\n];",
            f"ta_mcq_keys : append([{maxima_string(correct.key)}], "
            f"rand_selection([{distractors}], {question.show - 1}));",
            "ta_mcq : sublist(ta_mcq_all, lambda([ex], member(first(ex), ta_mcq_keys)));",
        ]
    else:
        lines = [f"ta_mcq : [\n  {triples}\n];"]
    if question.shuffle:
        lines.append("ta_mcq : random_permutation(ta_mcq);")
    return "\n".join(lines)


def question_variables(question: Question) -> str:
    parts = [question.variables]
    if question.options:
        parts.append(mcq_teacher_answer(question))
    else:
        parts.append(answer_expressions(question))
        if question.scaffold == "choice":
            parts.append(dropdown_teacher_answer(question))
    if question.figure and question.figure.plot:
        parts.append(DECIMAL_COMMA)
    return "\n".join(part for part in parts if part)


def figure_html(figure: Figure) -> str:
    """The figure as it appears in the stem: a plot() call STACK evaluates
    against the question's variables, or an <img> pointing at the embedded
    schematic. The alt text is the author's in both cases."""
    if figure.plot:
        # plot() returns its own <div>, so it is not wrapped in a paragraph.
        return "{@plot(" + figure.plot + ", [alt, " + maxima_string(figure.alt) + "])@}"
    return f'<p><img src="@@PLUGINFILE@@/{figure.filename}" alt="{escape(figure.alt)}" /></p>'


def figure_file_element(figure: Figure) -> str:
    """The schematic itself, base64 in the XML, so the content repository
    holds text and the importer needs nothing beside the .xml file."""
    if not figure.svg:
        return ""
    encoded = base64.b64encode(figure.svg.read_bytes()).decode("ascii")
    return f'      <file name="{escape(figure.filename)}" path="/" encoding="base64">{encoded}</file>\n'


def stem_html(question: Question) -> str:
    parts = [to_html(question.stem)]

    if question.figure:
        parts.append(figure_html(question.figure))

    if question.options:
        parts.append("<p>[[input:ans1]] [[validation:ans1]]</p>")
        return "\n".join(parts)

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
    if question.options:
        # Radio renders no validation, but STACK still requires exactly one
        # [[validation:...]] per input; showvalidation 0, as for the dropdown.
        return render_input(
            name="ans1",
            itype="radio",
            tans="ta_mcq",
            boxsize=0,
            mustverify=0,
            showvalidation=0,
        )

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
    if question.options:
        # One node per option: per-distractor feedback ('why:') and a
        # distinct answer note per option, exactly as for readings.
        return render_prt("ans", 1.0, reading_nodes(
            "ans", "String", "ans1", lambda r: maxima_string(r.key), "", question.options
        ))

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
    if question.options:
        # Test input values are CAS expressions mapped to whatever position
        # the key holds in the variant, so per-option tests hold at every
        # seed -- except under a pool, where a hidden key is an invalid
        # response. A pooled question therefore tests only the correct key
        # (always shown); the distractor key -> note -> why mapping is
        # covered by the compiler's own tests instead.
        correct = next(option for option in question.options if option.intended)
        cases = [(maxima_string(correct.key), None, 1.0, "ans-0-T", None, None)]
        if not question.show:
            cases += [
                (maxima_string(option.key), None, 0.0, f"ans-{offset + 1}-T", None, None)
                for offset, option in enumerate(
                    option for option in question.options if not option.intended)
            ]
        return render_qtests(cases, question.penalty)

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

    return render_qtests(cases, question.penalty)


def render_qtests(cases: list[tuple], penalty: float) -> str:
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
            f"        <expectedpenalty>{0.0 if s == 1.0 else penalty:.7f}</expectedpenalty>\n"
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

    # The note identifies a variant; for an MCQ that is the shown keys in
    # shown order, which is what makes subset and order seed-recoverable.
    note = question.note or (
        "{@maplist(first, ta_mcq)@}" if question.options else "{@ta@}")

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<quiz>\n"
        '  <question type="stack">\n'
        f"    <name>\n      <text>{escape(question.name)}</text>\n    </name>\n"
        + text_element("questiontext", stem_html(question),
                       files=figure_file_element(question.figure) if question.figure else "")
        + text_element("generalfeedback", to_html(question.general_feedback) if question.general_feedback else "")
        + element("defaultgrade", f"{question.grade:g}")
        + element("penalty", f"{question.penalty:g}")
        + element("hidden", 0)
        + element("idnumber", question.id)
        + f"    <stackversion>\n      <text>{stackversion}</text>\n    </stackversion>\n"
        + f"    <questionvariables>\n      <text>{cdata(question_variables(question))}</text>\n    </questionvariables>\n"
        + text_element("specificfeedback", "<p>[[feedback:ans]]</p>")
        + f'    <questionnote format="moodle_auto_format">\n      <text>{cdata(note)}</text>\n    </questionnote>\n'
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

    grade = float(source.get("grade", 10))
    if grade < 0:
        fail(path, "'grade' must be a number >= 0 (0 means no gradebook item)")

    quiz = {
        "id": str(require(path, source, "id")),
        "name": str(require(path, source, "name")),
        "intro": to_html(source.get("intro", "")),
        "behaviour": behaviour,
        "grade": grade,
        "questionsperpage": int(source.get("questionsperpage", 1)),
        "attempts": int(source.get("attempts", 0)),
        "grademethod": source.get("grademethod", "highest"),
        "review": review,
        "questions": [],
    }
    for entry in require(path, source, "questions"):
        if "random" in entry:
            count = entry["random"]
            if not isinstance(count, int) or count < 1:
                fail(path, "'random' must be a positive integer")
            tags = [str(tag) for tag in entry.get("tags", [])]
            category = entry.get("category")
            if category is not None and (not isinstance(category, list) or not category):
                fail(path, "a random entry's 'category' must be a non-empty list "
                           "of category names")
            if not tags and not category:
                fail(path, "a random entry needs 'tags', 'category' or both")
            quiz["questions"].append({
                "random": count,
                "tags": tags,
                "category": [str(part) for part in category] if category else None,
                "maxmark": float(entry.get("maxmark", 1.0)),
            })
        else:
            quiz["questions"].append(
                {"id": str(entry["id"]), "maxmark": float(entry.get("maxmark", 1.0))}
            )
    return quiz


def random_pool(entry: dict, questions: dict[str, Question], aitext: dict[str, dict]) -> int:
    """How many compiled questions a random entry's selectors match.

    Mirrors what the built filter condition does at the Moodle end: tags are
    AND-joined, and a category selector matches the category itself and its
    subcategories. Moodle refuses an attempt when a random slot's pool runs
    out, so a draw larger than the pool is refused here, where the mistake is
    still cheap. build-quiz.php re-checks against the actual bank.
    """
    def matches(category: list[str], tags: list[str]) -> bool:
        if entry["category"] and category[:len(entry["category"])] != entry["category"]:
            return False
        return all(tag in tags for tag in entry["tags"])

    return sum(matches(q.category, q.tags) for q in questions.values()) + \
        sum(matches(spec["category"], spec["tags"]) for spec in aitext.values())


def manifest_entry(qid: str, path: Path, sourceroot: Path, target: Path, out: Path,
                   figure: Figure | None = None) -> dict:
    """One question's line in the build manifest: where it came from.

    A schematic is part of the source even though it lives in its own file, so
    it is listed too; without that, editing an SVG would change the question
    Moodle stores and nothing in the manifest would say so.
    """
    entry = {
        "id": qid,
        "source": str(path.relative_to(sourceroot)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "xml": str(target.relative_to(out)),
    }
    if figure and figure.svg:
        entry["assets"] = [{
            "source": str(figure.svg.relative_to(sourceroot.resolve())),
            "sha256": hashlib.sha256(figure.svg.read_bytes()).hexdigest(),
        }]
    return entry


def provenance_tag(commit: str, dirty: bool) -> str:
    """The tag naming the content commit a question was compiled from."""
    return PROVENANCE_TAG_PREFIX + (commit[:12] if commit else "unknown") + ("-dirty" if dirty else "")


def compile_tree(source: Path, out: Path, stackversion: str, provenance: dict) -> int:
    questions: dict[str, Question] = {}
    quizzes: list[dict] = []
    aitext: dict[str, dict] = {}
    sources: dict[str, Path] = {}

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
            sources[spec["id"]] = path
            continue
        if qtype == "mcq":
            question = load_mcq_question(path, data, source)
        elif qtype == "stack":
            question = load_question(path, data, source)
        else:
            fail(path, f"unknown question type '{qtype}'")
        if question.id in questions or question.id in aitext:
            fail(path, f"id '{question.id}' already in use")
        questions[question.id] = question
        sources[question.id] = path

    for quiz in quizzes:
        for entry in quiz["questions"]:
            if "random" in entry:
                pool = random_pool(entry, questions, aitext)
                if pool < entry["random"]:
                    raise SourceError(
                        f"quiz '{quiz['id']}': random slot draws {entry['random']} "
                        f"but only {pool} compiled question(s) match its selectors")
            elif entry["id"] not in questions and entry["id"] not in aitext:
                raise SourceError(f"quiz '{quiz['id']}' refers to unknown question '{entry['id']}'")

    # Start from a clean tree so that renamed or deleted sources cannot leave
    # stale XML behind for the importer to pick up.
    for stale in (out / "questions", out / "quizzes", out / "aitext"):
        shutil.rmtree(stale, ignore_errors=True)

    tag = provenance_tag(provenance["content"]["commit"], provenance["content"]["dirty"])
    imported: list[dict] = []

    for question in questions.values():
        target = out.joinpath("questions", *question.category, f"{question.id}.xml")
        target.parent.mkdir(parents=True, exist_ok=True)
        question.tags.append(tag)
        target.write_text(render_question(question, stackversion), encoding="utf-8")
        imported.append(manifest_entry(question.id, sources[question.id], source, target, out,
                                       question.figure))

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
            target = out.joinpath("questions", *spec["category"], f"{spec['id']}.xml")
            target.parent.mkdir(parents=True, exist_ok=True)
            spec["tags"].append(tag)
            target.write_text(render_aitext_question(spec), encoding="utf-8")
            imported.append(manifest_entry(spec["id"], sources[spec["id"]], source, target, out))

    # The manifest is what the importer records as the provenance of an import
    # run: which commits produced these questions, when, and from which files.
    manifest = {
        "builtat": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "stackversion": stackversion,
        "content": {**provenance["content"], "tag": tag},
        "compiler": provenance["compiler"],
        "questions": sorted(imported, key=lambda entry: entry["id"]),
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"compiled {len(questions)} STACK and {len(aitext)} aitext questions, "
          f"{len(quizzes)} quizzes into {out} from {tag}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--stack-version", required=True)
    # Provenance is passed in rather than read here: git lives on the host,
    # this runs in a container that sees only the two mounted trees. An empty
    # commit means the tree is not a git checkout at all; the importer treats
    # that like a dirty one and refuses it outside local iteration.
    parser.add_argument("--content-commit", required=True)
    parser.add_argument("--content-dirty", action="store_true")
    parser.add_argument("--compiler-commit", required=True)
    parser.add_argument("--compiler-dirty", action="store_true")
    args = parser.parse_args()

    if not args.source.is_dir():
        print(f"Source directory not found: {args.source}", file=sys.stderr)
        return 1

    provenance = {
        "content": {"commit": args.content_commit, "dirty": args.content_dirty},
        "compiler": {"commit": args.compiler_commit, "dirty": args.compiler_dirty},
    }

    try:
        return compile_tree(args.source, args.out, args.stack_version, provenance)
    except SourceError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
