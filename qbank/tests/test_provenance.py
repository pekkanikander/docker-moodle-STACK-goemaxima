#!/usr/bin/env python3
"""Tests for the provenance the compiler stamps on every question.

Run by qbank/tests/run-tests.sh inside the qbank-tools container, where the
pinned PyYAML the compiler needs is installed.
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

# The line qbank_content_hash() in qbank/cli/lib.php removes before hashing.
PROVENANCE_LINE = re.compile(r"^[ \t]*<tag><text>src-[^<]*</text></tag>$")

CONTENT_COMMIT = "0123456789abcdef0123456789abcdef01234567"
OTHER_COMMIT = "fedcba9876543210fedcba9876543210fedcba98"
COMPILER_COMMIT = "89abcdef0123456789abcdef0123456789abcdef"


def build(tmp: Path, name: str, commit: str = CONTENT_COMMIT, source: Path = FIXTURES,
          extra: list[str] = []) -> Path:
    out = tmp / name
    out.mkdir()
    subprocess.run(
        [sys.executable, str(COMPILER),
         "--source", str(source), "--out", str(out), "--stack-version", "5.44.0",
         "--content-commit", commit, "--compiler-commit", COMPILER_COMMIT, *extra],
        check=True, stdout=subprocess.DEVNULL,
    )
    return out


def questions(out: Path) -> dict[str, str]:
    return {
        str(path.relative_to(out)): path.read_text(encoding="utf-8")
        for path in sorted((out / "questions").rglob("*.xml"))
    }


def without_provenance(xml: str) -> str:
    return "\n".join(line for line in xml.splitlines() if not PROVENANCE_LINE.match(line))


def test_every_question_carries_the_content_commit(tmp: Path) -> None:
    out = build(tmp, "tagged")
    for name, xml in questions(out).items():
        tags = [line.strip() for line in xml.splitlines() if PROVENANCE_LINE.match(line)]
        assert tags == ["<tag><text>src-0123456789ab</text></tag>"], f"{name}: {tags}"


def test_manifest_names_both_repositories_and_every_source(tmp: Path) -> None:
    out = build(tmp, "manifest")
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["content"] == {
        "commit": CONTENT_COMMIT, "dirty": False, "tag": "src-0123456789ab"}
    assert manifest["compiler"] == {"commit": COMPILER_COMMIT, "dirty": False}
    assert manifest["builtat"].endswith("+00:00")

    entries = {entry["id"]: entry for entry in manifest["questions"]}
    sources = sorted((FIXTURES / "questions").rglob("*.yaml"))
    assert len(entries) == len(sources)
    for entry in entries.values():
        source = FIXTURES / entry["source"]
        assert source.is_file(), entry
        assert (out / entry["xml"]).is_file(), entry
        assert len(entry["sha256"]) == 64


def test_a_dirty_tree_is_marked_as_such(tmp: Path) -> None:
    out = build(tmp, "dirty", extra=["--content-dirty", "--compiler-dirty"])
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["content"]["tag"] == "src-0123456789ab-dirty"
    assert manifest["content"]["dirty"] and manifest["compiler"]["dirty"]
    assert "<tag><text>src-0123456789ab-dirty</text></tag>" in "".join(questions(out).values())


def test_a_tree_without_a_commit_says_unknown(tmp: Path) -> None:
    out = build(tmp, "unknown", commit="")
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["content"]["tag"] == "src-unknown"


def test_a_new_commit_alone_does_not_look_like_a_change(tmp: Path) -> None:
    """The trap: a commit stamp inside the hashed XML would re-import every
    question on every commit and add a Moodle version nobody edited."""
    before = questions(build(tmp, "before"))
    after = questions(build(tmp, "after", commit=OTHER_COMMIT))

    assert before.keys() == after.keys()
    assert before != after, "the provenance tag is not reaching the XML at all"
    for name in before:
        assert without_provenance(before[name]) == without_provenance(after[name]), name


def test_an_edited_question_still_looks_like_a_change(tmp: Path) -> None:
    edited = tmp / "content"
    shutil.copytree(FIXTURES, edited)
    target = sorted((edited / "questions").rglob("*.yaml"))[0]
    target.write_text(
        target.read_text(encoding="utf-8").replace("stem: |", "stem: |\n  Uusi rivi.\n", 1),
        encoding="utf-8",
    )

    before = questions(build(tmp, "unedited"))
    after = questions(build(tmp, "edited", commit=OTHER_COMMIT, source=edited))

    differing = [name for name in before
                 if without_provenance(before[name]) != without_provenance(after[name])]
    assert len(differing) == 1, differing


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
