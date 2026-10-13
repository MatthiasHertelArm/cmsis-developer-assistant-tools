# Copyright (c) 2026 Arm Limited (or its affiliates). All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""The command line: exit status, output lines and the GitHub annotations."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from cmsis_knowledge.cli import main

from conftest import unit_text, write_unit


def test_build_and_info(pack: Path, pack_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["build", str(pack), "--pack-root", str(pack_root)]) == 0
    out = capsys.readouterr().out
    assert "Acme::Mini_BSP: 3 units (concept 1, procedure 1, troubleshooting 1)" in out
    assert "0 errors, 0 warnings" in out and f"wrote {pack / '.knowledge' / 'knowledge.db'}" in out
    assert main(["info", str(pack / ".knowledge" / "knowledge.db")]) == 0
    out = capsys.readouterr().out
    assert "  pack: Acme::Mini_BSP@0.2.0" in out and "  scope: pack" in out
    assert "relations: applies_to 9" in out
    assert "ts-mini-flash-locked · troubleshooting · draft · pyOCD: flash locked on a factory mini board" in out


def test_check_fails_on_errors_and_strict_on_warnings(pack: Path, pack_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_unit(pack, "concept-extra.md", unit_text(extra="applies_to:\n  board: [unknown-board]\n"))
    assert main(["check", str(pack), "--pack-root", str(pack_root)]) == 0
    assert main(["check", str(pack), "--pack-root", str(pack_root), "--strict"]) == 1
    out = capsys.readouterr().out
    assert ".knowledge/units/concept-extra.md:8: warning: applies_to board 'unknown-board'" in out
    write_unit(pack, "concept-extra.md", unit_text(extra="applies_to:\n  board: [FRDM-*]\n"))
    assert main(["build", str(pack), "--pack-root", str(pack_root)]) == 1
    assert "no index written: fix the errors above" in capsys.readouterr().out


def test_input_that_cannot_be_built_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", str(tmp_path)]) == 2
    assert "no PDSC" in capsys.readouterr().err
    assert main(["info", str(tmp_path / "none.db")]) == 2
    (tmp_path / "text.db").write_text("not a database")
    assert main(["info", str(tmp_path / "text.db")]) == 2


def test_github_annotations(pack: Path, pack_root: Path, monkeypatch: pytest.MonkeyPatch,
                            capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    write_unit(pack, "concept-extra.md", unit_text(summary="Too: colon."))
    main(["check", str(pack), "--pack-root", str(pack_root)])
    assert "::error file=.knowledge/units/concept-extra.md,line=5::frontmatter is not valid YAML" in capsys.readouterr().out


def test_python_dash_m(pack: Path, pack_root: Path) -> None:
    run = subprocess.run([sys.executable, "-m", "cmsis_knowledge", "check", str(pack), "--pack-root", str(pack_root)],
                         capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stderr
    assert "3 units" in run.stdout
