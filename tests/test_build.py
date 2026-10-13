# Copyright (c) 2026 Arm Limited (or its affiliates). All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""The index a build writes: the tables and info rows readers rely on, scope, targets, paths and the search."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from cmsis_knowledge.build import BuildError, Options, build, title_aliases
from cmsis_knowledge.schema import SCHEMA_VERSION

from conftest import unit_text, write_unit


def rows(db: Path, sql: str, *args: object) -> list[tuple]:
    with closing(sqlite3.connect(db)) as con:
        return con.execute(sql, args).fetchall()


def test_the_fixture_pack_builds_clean(pack: Path, pack_root: Path) -> None:
    result = build(Options(pack, pack_root=pack_root))
    assert result.written and not result.report.errors and not result.report.warnings, result.report.lines()
    db = pack / ".knowledge" / "knowledge.db"
    assert result.out == db and db.is_file()
    info = dict(rows(db, "SELECT key, value FROM info"))
    assert info == {"schema_version": str(SCHEMA_VERSION), "format_version": "1", "builder": "cmsis-knowledge",
                    "builder_version": "0.1.0", "pack": "Acme::Mini_BSP@0.2.0", "scope": "pack", "units": "3"}
    tables = {r[0] for r in rows(db, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"nodes", "edges", "nodes_fts", "unresolved", "info"} <= tables
    columns = [r[1] for r in rows(db, "PRAGMA table_info(nodes_fts)")]
    assert columns == ["id", "title", "summary", "body", "symptoms", "triggers"]


def test_every_unit_is_scoped_to_its_pack(pack: Path, pack_root: Path) -> None:
    build(Options(pack, pack_root=pack_root))
    db = pack / ".knowledge" / "knowledge.db"
    scoped = rows(db, "SELECT src FROM edges WHERE rel='scoped_to' AND dst='pack:Acme::Mini_BSP' ORDER BY src")
    assert [r[0] for r in scoped] == ["concept-mini-board", "proc-mini-bring-up", "ts-mini-flash-locked"]


def test_targets_take_the_ids_a_project_yields(pack: Path, pack_root: Path) -> None:
    build(Options(pack, pack_root=pack_root))
    db = pack / ".knowledge" / "knowledge.db"
    applies = rows(db, "SELECT src, dst, qual FROM edges WHERE rel='applies_to' ORDER BY src, dst")
    assert ("concept-mini-board", "board:Acme::mini-board", None) in applies
    assert ("concept-mini-board", "device:AC12_xA", None) in applies
    assert ("concept-mini-board", "part:LSM6DSO", None) in applies
    assert ("proc-mini-bring-up", "component:Acme::Board Support:LED", None) in applies
    assert ("proc-mini-bring-up", "pack:Acme::Acme_DFP", json.dumps({"range": ">=1.0.0"})) in applies
    assert ("ts-mini-flash-locked", "toolchain:GCC", None) in applies
    assert rows(db, "SELECT count(*) FROM unresolved") == [(0,)]


def test_the_pack_entities_carry_boards_parts_and_components(pack: Path, pack_root: Path) -> None:
    build(Options(pack, pack_root=pack_root))
    db = pack / ".knowledge" / "knowledge.db"
    edges = set(rows(db, "SELECT src, rel, dst FROM edges WHERE src NOT LIKE '%-%-%' OR src LIKE 'board:%'"))
    assert ("board:Acme::mini-board", "mounted_on", "device:AC12_xA") in edges
    assert ("board:Acme::mini-board", "has_part", "part:LSM6DSO") in edges
    assert ("board:Acme::mini-board", "part_of", "pack:Acme::Mini_BSP") in edges
    kinds = dict(rows(db, "SELECT id, type FROM nodes WHERE kind='entity'"))
    assert kinds["part:LSM6DSO"] == "part" and kinds["tool:pyocd"] == "tool"
    assert kinds["component:Acme::CMSIS Driver:VIO:Board"] == "component"
    # The required DFP is read for checking only: its devices stay out of this pack's index.
    assert "device:AC12_xA" not in kinds


def test_units_keep_their_frontmatter_and_a_path_relative_to_the_pack(pack: Path, pack_root: Path) -> None:
    build(Options(pack, pack_root=pack_root))
    db = pack / ".knowledge" / "knowledge.db"
    (meta,) = rows(db, "SELECT meta FROM nodes WHERE id='ts-mini-flash-locked'")[0]
    meta = json.loads(meta)
    assert meta["path"] == ".knowledge/units/ts-mini-flash-locked.md"
    assert meta["symptom_regex"] == r"flash is locked \(result code 0x42\)"
    assert meta["tool"] == "pyocd" and meta["status"] == "draft"
    assert "id" not in meta and "title" not in meta


def test_the_full_text_index_finds_symptoms_and_triggers(pack: Path, pack_root: Path) -> None:
    build(Options(pack, pack_root=pack_root))
    db = pack / ".knowledge" / "knowledge.db"
    hit = rows(db, "SELECT id FROM nodes_fts WHERE nodes_fts MATCH ? ORDER BY bm25(nodes_fts, 0, 8, 4, 1, 6, 6)",
               '"locked" OR "0x42"')
    assert hit[0] == ("ts-mini-flash-locked",)
    assert rows(db, "SELECT id FROM nodes_fts WHERE nodes_fts MATCH 'triggers:download'") == [("proc-mini-bring-up",)]


def test_the_same_input_gives_the_same_file(pack: Path, pack_root: Path, tmp_path: Path) -> None:
    build(Options(pack, pack_root=pack_root, out=tmp_path / "a.db"))
    build(Options(pack, pack_root=pack_root, out=tmp_path / "b.db"))
    assert (tmp_path / "a.db").read_bytes() == (tmp_path / "b.db").read_bytes()


def test_source_date_epoch_dates_the_build(pack: Path, pack_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1791936000")
    build(Options(pack, pack_root=pack_root))
    info = dict(rows(pack / ".knowledge" / "knowledge.db", "SELECT key, value FROM info"))
    assert info["built_at"] == "2026-10-14T00:00:00Z"


def test_errors_leave_the_old_index_in_place(pack: Path, pack_root: Path) -> None:
    assert build(Options(pack, pack_root=pack_root)).written
    db = pack / ".knowledge" / "knowledge.db"
    before = db.read_bytes()
    write_unit(pack, "broken.md", "---\nid: broken\ntype: concept\n---\n")
    result = build(Options(pack, pack_root=pack_root))
    assert not result.written and result.report.errors
    assert db.read_bytes() == before
    assert not [p for p in db.parent.iterdir() if p.name.startswith(".knowledge-")]


def test_strict_turns_warnings_into_failures(pack: Path, pack_root: Path) -> None:
    write_unit(pack, "concept-extra.md", unit_text(summary=" ".join(["word"] * 41)))
    assert build(Options(pack, pack_root=pack_root)).written
    result = build(Options(pack, pack_root=pack_root, out=pack / "strict.db", strict=True))
    assert not result.written and not (pack / "strict.db").exists()


def test_check_writes_nothing(pack: Path, pack_root: Path) -> None:
    result = build(Options(pack, pack_root=pack_root), write=False)
    assert not result.written and not (pack / ".knowledge" / "knowledge.db").exists()
    assert result.counts["units"] == 3


def test_relations_to_other_units_are_checked(pack: Path, pack_root: Path, tmp_path: Path) -> None:
    write_unit(pack, "rule-x.md", unit_text("rule-x", type_="rule", extra="requires: [proc-in-base]\nrefines: [rule-x]\n"))
    report = build(Options(pack, pack_root=pack_root)).report
    assert any("names the unit itself" in d.message for d in report.errors)
    assert any("requires 'proc-in-base': not a unit of this pack; pass --known" in d.message for d in report.warnings)

    base = tmp_path / "base.db"
    with closing(sqlite3.connect(base)) as con:
        con.execute("CREATE TABLE nodes(id TEXT PRIMARY KEY)")
        con.executemany("INSERT INTO nodes VALUES(?)", [("proc-in-base",), ("concept-mini-board",)])
        con.commit()
    write_unit(pack, "rule-x.md", unit_text("rule-x", type_="rule", extra="requires: [proc-in-base]\n"))
    report = build(Options(pack, pack_root=pack_root, known=[base])).report
    assert not any("proc-in-base" in d.message for d in report.items)
    assert any("'concept-mini-board' is also in a --known index" in d.message for d in report.warnings)


def test_duplicate_ids_are_errors(pack: Path, pack_root: Path) -> None:
    write_unit(pack, "sub/again.md", unit_text("concept-mini-board"))
    report = build(Options(pack, pack_root=pack_root)).report
    assert any("is also the id of concept-mini-board.md" in d.message for d in report.errors)


def test_what_cannot_be_built_at_all(tmp_path: Path, pack: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(BuildError, match="no PDSC"):
        build(Options(empty))
    (pack / "Other.Second.pdsc").write_text((pack / "Acme.Mini_BSP.pdsc").read_text())
    with pytest.raises(BuildError, match="2 PDSC files"):
        build(Options(pack))
    with pytest.raises(BuildError, match="no units folder"):
        build(Options(pack, pdsc=pack / "Acme.Mini_BSP.pdsc", units_dir=pack / "nowhere"))


def test_title_aliases_spell_identifiers_as_words() -> None:
    assert title_aliases("EventRecorderInitialize") == ["Event Recorder Initialize"]
    assert "ARM USART Send" in title_aliases("ARM_USART_Send")
    assert "set up" in title_aliases("Board setup")


def test_required_descriptions_can_be_downloaded_from_a_pack_index(pack: Path, tmp_path: Path) -> None:
    server = tmp_path / "server"
    server.mkdir()
    dfp = Path(__file__).parent / "fixtures" / "packroot" / "Acme" / "Acme_DFP" / "1.0.0" / "Acme.Acme_DFP.pdsc"
    (server / "Acme.Acme_DFP.pdsc").write_bytes(dfp.read_bytes())
    (server / "index.pidx").write_text(
        f'<index><pindex><pdsc url="{server.as_uri()}/" vendor="Acme" name="Acme_DFP" version="1.0.0"/></pindex></index>')
    result = build(Options(pack, fetch_index=(server / "index.pidx").as_uri(), strict=True))
    assert result.written and not result.report.warnings, result.report.lines()
    assert any(d.message.startswith("required pack Acme::Acme_DFP: downloaded from file:") for d in result.report.items)

    offline = build(Options(pack, fetch_index=(tmp_path / "nowhere.pidx").as_uri()), write=False).report
    assert any("cannot download its description" in d.message for d in offline.warnings)
    assert any("applies_to device 'AC12_xA': not checked, since Acme::Acme_DFP was not found" in d.message
               for d in offline.warnings)
