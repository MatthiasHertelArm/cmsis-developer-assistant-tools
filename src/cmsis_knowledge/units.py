# Copyright (c) 2026 Arm Limited (or its affiliates). All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Knowledge units: one Markdown file each, YAML frontmatter between two ``---`` lines, then the text.

Reading reports every problem with its file and line and goes on with the next file, so one run lists them all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .diagnostics import Report
from .schema import APPLIES_KEYS, KNOWLEDGE_TYPES, RELATIONS, STATUSES, SUMMARY_MAX_WORDS

_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)(.*)\Z", re.S)
_KEY_LINE = re.compile(r"^([A-Za-z_][\w-]*)[ \t]*:")
_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
# Python regular expression syntax that a JavaScript RegExp (the reader's) does not take.
_NOT_JAVASCRIPT = (
    (re.compile(r"\(\?P[<=]"), "named groups are written (?<name>...) and \\k<name> in JavaScript"),
    (re.compile(r"\(\?[aiLmsux]+[):]"), "inline flags such as (?i) are not JavaScript; the reader matches without case anyway"),
    (re.compile(r"\\[AZ]"), "\\A and \\Z are not JavaScript; use ^ and $"),
)
_PLACEHOLDER = re.compile(r"^_[^_\n]+_$")


@dataclass
class Unit:
    """One unit as read from its file."""

    path: Path
    #: The path relative to the pack root, with forward slashes: what the index records.
    rel_path: str
    meta: dict[str, Any]
    body: str
    #: The line of each top-level frontmatter key, for messages.
    lines: dict[str, int] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return str(self.meta.get("id") or "")

    @property
    def type(self) -> str:
        return str(self.meta.get("type") or "")

    def line(self, key: str) -> int:
        return self.lines.get(key, 1)


def unit_files(units_dir: Path) -> list[Path]:
    """The Markdown files below ``units_dir``, sorted; ``README.md`` and hidden folders are not units."""
    found = []
    for path in units_dir.rglob("*.md"):
        rel = path.relative_to(units_dir)
        if any(part.startswith(".") for part in rel.parts[:-1]) or path.name.lower() == "readme.md":
            continue
        found.append(path)
    return sorted(found, key=lambda p: p.relative_to(units_dir).as_posix())


def as_list(value: Any) -> list[Any]:
    """A frontmatter value that may be one item or a list, as a list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def read_unit(path: Path, pack_dir: Path, report: Report) -> Unit | None:
    """The unit in ``path``, or None after reporting why it cannot be read."""
    try:
        text = path.read_text(encoding="utf-8").lstrip("﻿")
    except UnicodeDecodeError as exc:
        report.error(f"not UTF-8 text: {exc.reason} at byte {exc.start}", path)
        return None
    match = _FRONTMATTER.match(text)
    if not match:
        report.error("no frontmatter: a unit starts with a line '---', its YAML fields, and another '---'", path, 1)
        return None
    head = match.group(1)
    try:
        meta = yaml.safe_load(head)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 2 if mark is not None else 1
        problem = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        hint = ""
        if "mapping values are not allowed" in str(exc):
            hint = "; a ': ' inside an unquoted value starts a new field, so put the value in double quotes"
        report.error(f"frontmatter is not valid YAML: {problem}{hint}", path, line)
        return None
    if not isinstance(meta, dict):
        report.error("frontmatter is not a set of 'key: value' fields", path, 2)
        return None
    lines = {}
    for number, raw in enumerate(head.splitlines(), start=2):
        key = _KEY_LINE.match(raw)
        if key and key.group(1) not in lines:
            lines[key.group(1)] = number
    try:
        rel_path = path.resolve().relative_to(pack_dir.resolve()).as_posix()
    except ValueError:
        rel_path = path.as_posix()
    return Unit(path=path, rel_path=rel_path, meta=meta, body=match.group(2).strip(), lines=lines)


def _is_text_list(value: Any) -> bool:
    return all(isinstance(item, str) and item.strip() for item in as_list(value))


def lint(unit: Unit, report: Report) -> bool:
    """Check one unit against the unit format; False when it cannot go into an index at all."""
    meta, path = unit.meta, unit.path
    usable = True
    for key in ("id", "type", "title", "summary", "status"):
        value = meta.get(key)
        if not isinstance(value, str) or not value.strip():
            report.error(f"'{key}' is missing or not a text", path, unit.line(key) if key in unit.lines else 2)
            usable = False
    if not usable:
        return False
    if not _ID.match(unit.id):
        report.error(f"id '{unit.id}': use lower-case letters, digits, '-', '_' and '.'", path, unit.line("id"))
        usable = False
    if unit.type not in KNOWLEDGE_TYPES:
        report.error(f"type '{unit.type}' is none of {', '.join(KNOWLEDGE_TYPES)}", path, unit.line("type"))
        usable = False
    if meta["status"] not in STATUSES:
        report.error(f"status '{meta['status']}' is none of {', '.join(STATUSES)}", path, unit.line("status"))
    words = len(meta["summary"].split())
    if words > SUMMARY_MAX_WORDS:
        report.warning(f"summary has {words} words; at most {SUMMARY_MAX_WORDS} keep search results within the "
                       "agent's token budget, the details belong in the text", path, unit.line("summary"))
    if "domain" in meta and not isinstance(meta["domain"], str):
        report.error("'domain' is not a text", path, unit.line("domain"))

    applies = meta.get("applies_to")
    if applies is not None and not isinstance(applies, dict):
        report.error("'applies_to' is not a set of 'key: [values]' fields", path, unit.line("applies_to"))
    for key, values in (applies or {}).items() if isinstance(applies, dict) else ():
        if key not in APPLIES_KEYS:
            report.error(f"applies_to key '{key}' is none of {', '.join(APPLIES_KEYS)}", path, unit.line("applies_to"))
        elif not all(isinstance(v, (str, int, float)) for v in as_list(values)):
            report.error(f"applies_to {key}: each value is a name", path, unit.line("applies_to"))

    for relation in RELATIONS:
        if relation in meta and not _is_text_list(meta[relation]):
            report.error(f"'{relation}' is not a list of unit ids", path, unit.line(relation))
    for key in ("symptoms", "triggers"):
        if key in meta and not _is_text_list(meta[key]):
            report.error(f"'{key}' is not a list of texts", path, unit.line(key))

    pattern = meta.get("symptom_regex")
    if pattern is not None:
        if not isinstance(pattern, str):
            report.error("'symptom_regex' is not a text", path, unit.line("symptom_regex"))
        else:
            try:
                re.compile(pattern)
            except re.error as exc:
                report.error(f"symptom_regex does not compile: {exc}", path, unit.line("symptom_regex"))
            for syntax, why in _NOT_JAVASCRIPT:
                if syntax.search(pattern):
                    report.error(f"symptom_regex: {why}", path, unit.line("symptom_regex"))
    if unit.type == "troubleshooting" and not meta.get("symptoms") and not pattern:
        report.warning("a troubleshooting unit without 'symptoms' or 'symptom_regex' is never found by its message",
                       path, unit.line("type"))

    if not meta.get("license"):
        report.warning("no 'license': name the licence of the unit's text (an SPDX identifier)", path, 2)
    if not unit.body or _PLACEHOLDER.match(unit.body):
        report.warning("the unit has no text yet and is left out of search", path)
    elif unit.type == "troubleshooting":
        cause = section(unit.body, "Cause")
        if cause is not None and (not cause or _PLACEHOLDER.match(cause)):
            report.warning("the '## Cause' section is empty, so the unit is left out of search", path)
    return usable


def section(body: str, heading: str) -> str | None:
    """The text of a ``## heading`` section, or None without one."""
    lines = body.splitlines()
    for start, line in enumerate(lines):
        if line.strip().lower() == f"## {heading.lower()}":
            rest = lines[start + 1:]
            end = next((i for i, text in enumerate(rest) if re.match(r"^##? ", text)), len(rest))
            return "\n".join(rest[:end]).strip()
    return None
