# Copyright (c) 2026 Arm Limited (or its affiliates). All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""What an index holds, for a CI log or a review: its info rows, counts, unchecked targets and units."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path


def describe(file: Path) -> list[str]:
    """The lines ``cmsis-knowledge info`` prints for an index file."""
    if not file.is_file():
        raise FileNotFoundError(f"{file}: no such index")
    with closing(sqlite3.connect(f"{file.resolve().as_uri()}?mode=ro", uri=True)) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
        missing = [t for t in ("nodes", "edges", "nodes_fts") if t not in tables]
        if missing:
            raise ValueError(f"{file}: not a knowledge index (no {', '.join(missing)} table)")
        lines = [f"{file}"]
        if "info" in tables:
            for key, value in db.execute("SELECT key, value FROM info ORDER BY key"):
                lines.append(f"  {key}: {value}")
        units = db.execute("SELECT type, count(*) FROM nodes WHERE kind='knowledge' GROUP BY type ORDER BY type").fetchall()
        lines.append("units: " + (", ".join(f"{t} {n}" for t, n in units) or "none"))
        entities = db.execute("SELECT type, count(*) FROM nodes WHERE kind='entity' GROUP BY type ORDER BY type").fetchall()
        lines.append("entities: " + (", ".join(f"{t} {n}" for t, n in entities) or "none"))
        relations = db.execute("SELECT rel, count(*) FROM edges GROUP BY rel ORDER BY rel").fetchall()
        lines.append("relations: " + (", ".join(f"{r} {n}" for r, n in relations) or "none"))
        if "unresolved" in tables:
            rows = db.execute("SELECT src, key, value FROM unresolved ORDER BY src, key, value").fetchall()
            if rows:
                lines.append(f"unchecked targets: {len(rows)}")
                lines.extend(f"  {src}: {key} {value}" for src, key, value in rows)
        lines.append("")
        for nid, kind, status, title in db.execute(
                "SELECT id, type, json_extract(meta, '$.status'), title FROM nodes WHERE kind='knowledge' ORDER BY type, id"):
            lines.append(f"{nid} · {kind} · {status or 'draft'} · {title}")
    return lines
