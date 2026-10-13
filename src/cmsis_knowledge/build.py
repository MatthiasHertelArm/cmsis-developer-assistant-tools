# Copyright (c) 2026 Arm Limited (or its affiliates). All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Building a pack's knowledge index: units and PDSC in, ``.knowledge/knowledge.db`` out.

Steps: read the pack's PDSC and those of the packs it requires; read and check every unit; resolve what each
applies to; write nodes, edges and the full-text index into a new file and move it over the old one, so a reader
never sees half an index. The same input gives the same file.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sqlite3
import tempfile
import xml.etree.ElementTree as ET
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .diagnostics import Report
from .packroot import Fetcher, default_pack_root, find_pdsc
from .pdsc import PackDescription, PdscError, read_pdsc
from .resolve import Resolver
from .schema import (APPLIES_KEYS, COLUMN_FIELDS, DDL, FORMAT_VERSION, INDEX_NAME, KNOWLEDGE_DIR, RELATIONS, SCHEMA_VERSION,
                     SCOPE_RELATION, UNITS_DIR)
from .units import Unit, as_list, lint, read_unit, unit_files


class BuildError(Exception):
    """The input cannot be built at all: no PDSC, no units folder, no FTS5 in this Python's SQLite."""


@dataclass
class Options:
    pack_dir: Path
    units_dir: Path | None = None
    out: Path | None = None
    pdsc: Path | None = None
    with_pdsc: list[Path] = field(default_factory=list)
    pack_root: Path | None = None
    #: Other indexes whose ids are valid relation targets, such as the base index.
    known: list[Path] = field(default_factory=list)
    strict: bool = False
    #: Download the PDSC of a required pack that no pack root has from this pack index.
    fetch_index: str | None = None


@dataclass
class Result:
    report: Report
    pack: PackDescription | None = None
    out: Path | None = None
    written: bool = False
    counts: dict[str, Any] = field(default_factory=dict)


def _check_fts5() -> None:
    try:
        sqlite3.connect(":memory:").execute("CREATE VIRTUAL TABLE t USING fts5(a)")
    except sqlite3.OperationalError as exc:
        raise BuildError(f"the SQLite of this Python ({sqlite3.sqlite_version}) has no FTS5: {exc}; "
                         "use a Python from python.org, Homebrew or your distribution") from exc


def _own_pdsc(options: Options) -> Path:
    if options.pdsc is not None:
        if not options.pdsc.is_file():
            raise BuildError(f"{options.pdsc}: no such PDSC")
        return options.pdsc
    found = sorted(options.pack_dir.glob("*.pdsc"))
    if len(found) != 1:
        what = "no PDSC" if not found else f"{len(found)} PDSC files"
        raise BuildError(f"{options.pack_dir}: {what}; name the pack's description with --pdsc")
    return found[0]


def title_aliases(title: str) -> list[str]:
    """Words of the title as a person writes them: ``EventRecorderInitialize`` → ``Event Recorder Initialize``,
    ``ARM_USART_Send`` → ``ARM USART Send``; ``setup`` ↔ ``set up``."""
    out = []
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_]*", title):
        parts = [p for p in re.split(r"_|(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", word) if p]
        if len(parts) > 1:
            out.append(" ".join(parts))
    for one, two in (("setup", "set up"), ("timestamp", "time stamp"), ("bootloader", "boot loader"),
                     ("startup", "start up"), ("pinout", "pin out"), ("workspace", "work space")):
        if re.search(rf"(?i)\b{one}", title):
            out.append(two)
        elif re.search(rf"(?i)\b{two}\b", title):
            out.append(one)
    return out


def _known_ids(files: list[Path], report: Report) -> set[str]:
    ids: set[str] = set()
    for file in files:
        try:
            with closing(sqlite3.connect(f"{file.resolve().as_uri()}?mode=ro", uri=True)) as db:
                ids.update(row[0] for row in db.execute("SELECT id FROM nodes"))
        except sqlite3.Error as exc:
            report.error(f"--known {file}: not a knowledge index ({exc})")
    return ids


def _required(pack: PackDescription, options: Options, report: Report) -> tuple[list[PackDescription], list[str]]:
    """The descriptions of the packs ``pack`` requires, and the ids of those not found."""
    given: dict[str, PackDescription] = {}
    for file in options.with_pdsc:
        try:
            description = read_pdsc(file)
            given[description.pack_id] = description
        except PdscError as exc:
            report.error(str(exc))
    root = options.pack_root or default_pack_root()
    found, missing = [], []
    with tempfile.TemporaryDirectory(prefix="cmsis-knowledge-") as downloads:
        fetcher = Fetcher(options.fetch_index, Path(downloads)) if options.fetch_index else None
        for requirement in pack.requirements:
            if requirement.pack_id in given:
                found.append(given.pop(requirement.pack_id))
                continue
            hit = find_pdsc(root, requirement.vendor, requirement.name, requirement.version) if root else None
            if hit is None and fetcher is not None:
                try:
                    fetched = fetcher.fetch(requirement.vendor, requirement.name)
                    hit = (fetched, f"downloaded from {options.fetch_index}") if fetched else None
                except (OSError, ET.ParseError) as exc:
                    report.warning(f"required pack {requirement.pack_id}: cannot download its description: {exc}")
            if hit is None:
                missing.append(requirement.pack_id)
                continue
            try:
                found.append(read_pdsc(hit[0]))
                where = hit[1] if hit[1].startswith("downloaded") else f"{hit[1]}, {hit[0]}"
                report.note(f"required pack {requirement.pack_id}: {where}")
            except PdscError as exc:
                report.warning(str(exc))
                missing.append(requirement.pack_id)
    found.extend(given.values())
    if missing:
        where = f"in the pack root {root}" if root else "(no pack root: set CMSIS_PACK_ROOT, pass --pack-root, or --fetch)"
        report.note(f"required pack{'s' if len(missing) > 1 else ''} {', '.join(missing)} not found {where}; "
                    "targets defined there are written unchecked")
    return found, missing


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def build(options: Options, write: bool = True) -> Result:
    """Check the units of a pack and, with ``write`` and no failure, write its index."""
    _check_fts5()
    pack_dir = options.pack_dir
    report = Report(pack_dir)
    result = Result(report)
    if not pack_dir.is_dir():
        raise BuildError(f"{pack_dir}: no such folder")
    try:
        pack = read_pdsc(_own_pdsc(options))
    except PdscError as exc:
        raise BuildError(str(exc)) from exc
    result.pack = pack
    units_dir = options.units_dir or pack_dir / KNOWLEDGE_DIR / UNITS_DIR
    if not units_dir.is_dir():
        raise BuildError(f"{units_dir}: no units folder; a pack keeps its units in {KNOWLEDGE_DIR}/{UNITS_DIR}/")
    out = options.out or pack_dir / KNOWLEDGE_DIR / INDEX_NAME
    result.out = out

    others, missing = _required(pack, options, report)
    resolver = Resolver(pack, others, missing)
    entities = pack.entities()
    pack_node = f"pack:{pack.pack_id}"

    units: list[Unit] = []
    seen: dict[str, Path] = {}
    for path in unit_files(units_dir):
        unit = read_unit(path, pack_dir, report)
        if unit is None or not lint(unit, report):
            continue
        if unit.id in seen:
            report.error(f"id '{unit.id}' is also the id of {seen[unit.id].name}", path, unit.line("id"))
            continue
        seen[unit.id] = path
        units.append(unit)
    if not units and not report.errors:
        report.warning(f"{units_dir}: no units")

    known = _known_ids(options.known, report)
    for unit in units:
        if unit.id in known:
            report.warning(f"id '{unit.id}' is also in a --known index, which a reader asks first; rename the unit",
                           unit.path, unit.line("id"))

    edges: dict[tuple[str, str, str], str | None] = {}
    unresolved: list[tuple[str, str, str]] = []
    tools: set[str] = set()
    for unit in units:
        edges[(unit.id, SCOPE_RELATION, pack_node)] = None
        applies = unit.meta.get("applies_to")
        for key, values in (applies.items() if isinstance(applies, dict) else ()):
            if key not in APPLIES_KEYS:
                continue  # reported by lint
            for value in as_list(values):
                if not isinstance(value, (str, int, float)):
                    continue  # reported by lint
                target = resolver.resolve(key, value)
                if target.problem:
                    severity, message = target.problem
                    getattr(report, severity)(message, unit.path, unit.line("applies_to"))
                if target.ids and not target.verified:
                    unresolved.append((unit.id, key, str(value)))
                for nid in target.ids:
                    edges[(unit.id, "applies_to", nid)] = _json(target.qual) if target.qual else None
                    if nid.startswith("tool:"):
                        tools.add(nid)
        for relation in RELATIONS:
            for dst in as_list(unit.meta.get(relation)):
                if not isinstance(dst, str):
                    continue  # reported by lint
                if dst == unit.id:
                    report.error(f"'{relation}' names the unit itself", unit.path, unit.line(relation))
                    continue
                if dst not in seen and dst not in known:
                    note = "not a unit of this pack" + ("" if options.known else "; pass --known <base index> to check it")
                    report.warning(f"{relation} '{dst}': {note}", unit.path, unit.line(relation))
                edges[(unit.id, relation, dst)] = None
    for src, rel, dst in entities.edges:
        edges.setdefault((src, rel, dst), None)
    for tool in tools:
        entities.node(tool, "tool", tool.split(":", 1)[1])

    counts: dict[str, Any] = {"units": len(units), "entities": len(entities.nodes), "edges": len(edges),
                              "unresolved": len(unresolved)}
    by_type: dict[str, int] = {}
    for unit in units:
        by_type[unit.type] = by_type.get(unit.type, 0) + 1
    counts["types"] = dict(sorted(by_type.items()))
    result.counts = counts

    if not write or report.failed(options.strict):
        _write(":memory:", pack, units, entities.nodes, edges, unresolved)
        return result

    out.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=".knowledge-", suffix=".db", dir=out.parent)
    os.close(handle)
    try:
        _write(temp, pack, units, entities.nodes, edges, unresolved)
        os.replace(temp, out)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    result.written = True
    return result


def _write(target: str, pack: PackDescription, units: list[Unit], nodes: dict[str, dict[str, Any]],
           edges: dict[tuple[str, str, str], str | None], unresolved: list[tuple[str, str, str]]) -> None:
    if target != ":memory:" and os.path.exists(target):
        os.unlink(target)
    db = sqlite3.connect(target)
    try:
        db.executescript(DDL)
        with db:
            for nid in sorted(nodes):
                node = nodes[nid]
                db.execute("INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?)",
                           (nid, "entity", node["type"], None, node["title"], None, None, _json(node["meta"])))
            for unit in sorted(units, key=lambda u: u.id):
                meta = {k: v for k, v in unit.meta.items() if k not in COLUMN_FIELDS}
                meta["path"] = unit.rel_path
                db.execute("INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?)",
                           (unit.id, "knowledge", unit.type, unit.meta.get("domain"), unit.meta["title"],
                            unit.meta.get("summary", ""), unit.body, _json(meta)))
                triggers = [str(t) for t in as_list(unit.meta.get("triggers"))]
                if unit.meta.get("description"):
                    triggers.append(str(unit.meta["description"]))
                db.execute("INSERT INTO nodes_fts VALUES(?,?,?,?,?,?)",
                           (unit.id, unit.meta["title"], unit.meta.get("summary", ""), unit.body,
                            " ".join(str(s) for s in as_list(unit.meta.get("symptoms"))),
                            " ".join(triggers + title_aliases(unit.meta["title"]))))
            for (src, rel, dst) in sorted(edges):
                db.execute("INSERT INTO edges VALUES(?,?,?,?)", (src, rel, dst, edges[(src, rel, dst)]))
            db.executemany("INSERT INTO unresolved VALUES(?,?,?)", sorted(unresolved))
            info = {
                "schema_version": str(SCHEMA_VERSION), "format_version": str(FORMAT_VERSION),
                "builder": "cmsis-knowledge", "builder_version": __version__,
                "pack": f"{pack.pack_id}@{pack.version}" if pack.version else pack.pack_id,
                "scope": "pack", "units": str(len(units)),
            }
            epoch = os.environ.get("SOURCE_DATE_EPOCH")
            if epoch and epoch.isdigit():
                info["built_at"] = _dt.datetime.fromtimestamp(int(epoch), _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            db.executemany("INSERT INTO info VALUES(?,?)", sorted(info.items()))
        db.execute("VACUUM")
    finally:
        db.close()
