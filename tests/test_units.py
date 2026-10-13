# Copyright (c) 2026 Arm Limited (or its affiliates). All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Reading and checking units: every problem with its file and line, and the next file read anyway."""

from __future__ import annotations

from pathlib import Path

from cmsis_knowledge.build import Options, build
from cmsis_knowledge.diagnostics import Report

from conftest import unit_text, write_unit


def messages(pack: Path, pack_root: Path, severity: str = "error") -> list[str]:
    report: Report = build(Options(pack, pack_root=pack_root), write=False).report
    return [f"{report.where(d)}: {d.message}" for d in report.items if d.severity == severity]


def test_an_unquoted_colon_is_reported_with_its_line_and_the_fix(pack: Path, pack_root: Path) -> None:
    write_unit(pack, "concept-colon.md", unit_text("concept-colon", summary="The DFP is old: decide BSP-only first."))
    found = messages(pack, pack_root)
    assert found == [".knowledge/units/concept-colon.md:5: frontmatter is not valid YAML: mapping values are not "
                     "allowed here; a ': ' inside an unquoted value starts a new field, so put the value in double quotes"]


def test_readme_files_are_skipped_and_other_files_need_frontmatter(pack: Path, pack_root: Path) -> None:
    write_unit(pack, "notes.md", "# Notes\n")
    assert messages(pack, pack_root) == [".knowledge/units/notes.md:1: no frontmatter: a unit starts with a line '---', "
                                         "its YAML fields, and another '---'"]


def test_required_fields_types_and_ids(pack: Path, pack_root: Path) -> None:
    write_unit(pack, "a.md", "---\nid: Bad_Id\ntype: howto\ntitle: A\nsummary: S.\nstatus: final\nlicense: MIT\n---\n\nText.\n")
    write_unit(pack, "b.md", "---\nid: b\ntype: concept\nsummary: S.\nstatus: draft\n---\n\nText.\n")
    found = messages(pack, pack_root)
    assert ".knowledge/units/a.md:2: id 'Bad_Id': use lower-case letters, digits, '-', '_' and '.'" in found
    assert ".knowledge/units/a.md:3: type 'howto' is none of concept, procedure, rule, pattern, troubleshooting" in found
    assert ".knowledge/units/a.md:6: status 'final' is none of draft, reviewed" in found
    assert ".knowledge/units/b.md:2: 'title' is missing or not a text" in found


def test_summaries_licences_and_empty_text_are_warnings(pack: Path, pack_root: Path) -> None:
    write_unit(pack, "c.md", unit_text("c", summary=" ".join(["w"] * 45)))
    write_unit(pack, "d.md", "---\nid: d\ntype: rule\ntitle: D\nsummary: S.\nstatus: draft\n---\n\n_to be written_\n")
    found = messages(pack, pack_root, "warning")
    assert any(m.startswith(".knowledge/units/c.md:5: summary has 45 words") for m in found)
    assert ".knowledge/units/d.md:2: no 'license': name the licence of the unit's text (an SPDX identifier)" in found
    assert ".knowledge/units/d.md: the unit has no text yet and is left out of search" in found


def test_troubleshooting_units_need_a_message_and_a_cause(pack: Path, pack_root: Path) -> None:
    write_unit(pack, "ts-x.md", unit_text("ts-x", type_="troubleshooting",
                                          body="## Symptom\n\nx\n\n## Cause\n\n_open_\n\n## Fix\n\ny"))
    found = messages(pack, pack_root, "warning")
    assert any("without 'symptoms' or 'symptom_regex' is never found" in m for m in found)
    assert any("the '## Cause' section is empty" in m for m in found)


def test_symptom_patterns_must_work_in_javascript_too(pack: Path, pack_root: Path) -> None:
    write_unit(pack, "ts-a.md", unit_text("ts-a", type_="troubleshooting", extra='symptom_regex: "(?i)^no board"\n'))
    write_unit(pack, "ts-b.md", unit_text("ts-b", type_="troubleshooting", extra='symptom_regex: "(?P<x>a)(unclosed"\n'))
    found = messages(pack, pack_root)
    assert any(m.startswith(".knowledge/units/ts-a.md:8: symptom_regex: inline flags") for m in found)
    assert any(m.startswith(".knowledge/units/ts-b.md:8: symptom_regex does not compile") for m in found)
    assert any(m.startswith(".knowledge/units/ts-b.md:8: symptom_regex: named groups") for m in found)


def test_applies_to_keys_and_relation_lists(pack: Path, pack_root: Path) -> None:
    write_unit(pack, "e.md", unit_text("e", extra="applies_to:\n  chip: [X]\nrequires: concept-mini-board\nrefines: [{a: b}]\n"))
    found = messages(pack, pack_root)
    assert any("applies_to key 'chip' is none of device, family, board, part" in m for m in found)
    assert any("'refines' is not a list of unit ids" in m for m in found)
    assert not any("'requires'" in m for m in found)  # one id instead of a list is fine


def test_one_broken_file_does_not_hide_the_others(pack: Path, pack_root: Path) -> None:
    write_unit(pack, "x1.md", "---\nid: [\n---\n")
    write_unit(pack, "x2.md", "no frontmatter")
    result = build(Options(pack, pack_root=pack_root), write=False)
    assert len(result.report.errors) == 2 and result.counts["units"] == 3
