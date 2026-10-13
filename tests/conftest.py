# Copyright (c) 2026 Arm Limited (or its affiliates). All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Fixtures: a copy of the mini pack to change per test, and the fixture pack root with the DFP it requires."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
PACK_ROOT = FIXTURES / "packroot"


@pytest.fixture(autouse=True)
def _no_ambient_pack_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Tests never see the pack root of the machine they run on."""
    monkeypatch.setenv("CMSIS_PACK_ROOT", str(tmp_path / "no-pack-root"))
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


@pytest.fixture
def pack(tmp_path: Path) -> Path:
    target = tmp_path / "Mini_BSP"
    shutil.copytree(FIXTURES / "minipack", target)
    return target


@pytest.fixture
def pack_root() -> Path:
    return PACK_ROOT


def write_unit(pack: Path, name: str, text: str) -> Path:
    path = pack / ".knowledge" / "units" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def unit_text(uid: str = "concept-extra", *, type_: str = "concept", summary: str = "A short summary.",
              extra: str = "", body: str = "## Text\n\nSome text.") -> str:
    return (f"---\nid: {uid}\ntype: {type_}\ntitle: \"Extra unit\"\nsummary: {summary}\nstatus: draft\n"
            f"license: Apache-2.0\n{extra}---\n\n{body}\n")
