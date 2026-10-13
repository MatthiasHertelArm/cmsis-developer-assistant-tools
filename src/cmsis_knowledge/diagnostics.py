# Copyright (c) 2026 Arm Limited (or its affiliates). All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""What a check finds: errors, which fail every build, warnings, which fail a ``--strict`` one, and notes."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Diagnostic:
    """One finding, with the file and line it is about when there is one."""

    severity: str
    message: str
    file: Path | None = None
    line: int | None = None


class Report:
    """The findings of one run, in the order they were made."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.items: list[Diagnostic] = []

    def error(self, message: str, file: Path | None = None, line: int | None = None) -> None:
        self.items.append(Diagnostic("error", message, file, line))

    def warning(self, message: str, file: Path | None = None, line: int | None = None) -> None:
        self.items.append(Diagnostic("warning", message, file, line))

    def note(self, message: str, file: Path | None = None, line: int | None = None) -> None:
        self.items.append(Diagnostic("note", message, file, line))

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.items if d.severity == "warning"]

    def failed(self, strict: bool) -> bool:
        """True when the run must not produce an index: any error, or with ``strict`` any warning."""
        return bool(self.errors) or (strict and bool(self.warnings))

    def where(self, item: Diagnostic) -> str:
        """``path:line`` relative to the pack, as editors and CI logs link it."""
        if item.file is None:
            return ""
        try:
            name = item.file.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            name = str(item.file)
        return f"{name}:{item.line}" if item.line else name

    def ordered(self) -> list[Diagnostic]:
        """The findings without a file first, then by file and line."""
        return sorted(self.items, key=lambda d: (d.file is not None, self.where(d).rsplit(":", 1)[0], d.line or 0))

    def lines(self) -> list[str]:
        """Each finding as ``path:line: severity: message``."""
        out = []
        for item in self.ordered():
            where = self.where(item)
            out.append(f"{where}: {item.severity}: {item.message}" if where else f"{item.severity}: {item.message}")
        return out

    def annotations(self) -> list[str]:
        """GitHub Actions workflow commands, so that errors and warnings show on the changed files."""
        out = []
        for item in self.ordered():
            if item.severity == "note":
                continue
            props = []
            if item.file is not None:
                props.append(f"file={self.where(item).rsplit(':', 1)[0] if item.line else self.where(item)}")
                if item.line:
                    props.append(f"line={item.line}")
            message = item.message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
            out.append(f"::{item.severity}{' ' + ','.join(props) if props else ''}::{message}")
        return out


def in_github_actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"
