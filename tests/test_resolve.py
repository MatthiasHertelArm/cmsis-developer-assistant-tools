# Copyright (c) 2026 Arm Limited (or its affiliates). All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""``applies_to`` resolution: the ids a project yields, suggestions for names that are no device, and never a
silently dropped target."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmsis_knowledge.packroot import find_pdsc, meets, version_key
from cmsis_knowledge.pdsc import read_pdsc
from cmsis_knowledge.resolve import Resolver

from conftest import FIXTURES, PACK_ROOT

BSP = read_pdsc(FIXTURES / "minipack" / "Acme.Mini_BSP.pdsc")
DFP = read_pdsc(PACK_ROOT / "Acme" / "Acme_DFP" / "1.0.0" / "Acme.Acme_DFP.pdsc")


@pytest.fixture
def resolver() -> Resolver:
    return Resolver(BSP, [DFP])


@pytest.mark.parametrize(("key", "value", "ids"), [
    ("board", "mini-board", ["board:Acme::mini-board"]),
    ("board", "Acme::mini-board:Rev.B", ["board:Acme::mini-board"]),
    ("device", "AC12_xA", ["device:AC12_xA"]),
    ("device", "Acme::AC2_xA_LP", ["device:AC2_xA_LP"]),
    ("device", "AC12_xA:cm33", ["device:AC12_xA"]),
    ("family", "AC1 Series", ["family:Acme::AC1 Series"]),
    ("core", "Cortex-M33", ["core:Cortex-M33"]),
    ("compiler", "ac6", ["toolchain:AC6"]),
    ("tool", "pyOCD", ["tool:pyocd"]),
    ("pack", "Acme.Acme_DFP", ["pack:Acme::Acme_DFP"]),
    ("component", "Board Support:LED", ["component:Acme::Board Support:LED"]),
    ("component", "Acme::Device:Startup", ["component:Acme::Device:Startup"]),
    ("part", "STMicroelectronics::LSM6DSO", ["part:LSM6DSO"]),
    ("api", "CMSIS Driver:VIO", ["api:CMSIS Driver:VIO"]),
])
def test_known_names_become_verified_ids(resolver: Resolver, key: str, value: str, ids: list[str]) -> None:
    target = resolver.resolve(key, value)
    assert target.ids == ids
    if key != "api":  # the fixture defines no <api>
        assert target.verified and target.problem is None, target.problem


def test_a_version_range_is_kept_as_qualifier(resolver: Resolver) -> None:
    target = resolver.resolve("pack", "Acme::Acme_DFP@>=1.0.0")
    assert target.ids == ["pack:Acme::Acme_DFP"] and target.qual == {"range": ">=1.0.0"}


def test_a_subfamily_or_a_prefix_is_no_device(resolver: Resolver) -> None:
    sub = resolver.resolve("device", "AC12")
    assert sub.ids == [] and sub.problem == ("error", "applies_to device 'AC12' is a subfamily; name its devices (AC12_xA, AC12_xB)")
    prefix = resolver.resolve("device", "AC2")
    assert prefix.ids == [] and prefix.problem == ("error", "applies_to device 'AC2' is no device; the devices are named AC2_xA, AC2_xA_LP")
    family = resolver.resolve("device", "AC1 Series")
    assert family.problem and "write 'family: Acme::AC1 Series'" in family.problem[1]


def test_unknown_names_are_written_unchecked_never_dropped(resolver: Resolver) -> None:
    for key, value, nid in [("board", "other-board", "board:other-board"), ("board", "V::b", "board:V::b"),
                            ("device", "XYZ123", "device:XYZ123"), ("family", "V::F", "family:V::F"),
                            ("tool", "cmsis_action", "tool:cmsis_action"), ("core", "Pentium", "core:Pentium"),
                            ("pack", "Other::Pack", "pack:Other::Pack"), ("part", "BMI270", "part:BMI270")]:
        target = resolver.resolve(key, value)
        assert target.ids == [nid] and not target.verified and target.problem and target.problem[0] == "warning", (key, value)


def test_names_that_cannot_match_a_project_are_errors(resolver: Resolver) -> None:
    assert resolver.resolve("board", "FRDM-*").problem == (
        "error", "applies_to board 'FRDM-*': wildcards are not supported, list the names")
    assert resolver.resolve("family", "Unknown Series").problem[0] == "error"
    assert resolver.resolve("component", "RTOS2:Keil RTX5").problem[0] == "error"
    assert resolver.resolve("device", " ").problem[0] == "error"


def test_a_missing_required_pack_is_named_in_the_warning() -> None:
    lonely = Resolver(BSP, [], missing=["Acme::Acme_DFP"])
    target = lonely.resolve("device", "AC12_xA")
    assert target.ids == ["device:AC12_xA"]
    assert target.problem == ("warning", "applies_to device 'AC12_xA': not checked, since Acme::Acme_DFP was not found")


def test_versions_order_and_requirements() -> None:
    assert version_key("6.0.0-0") < version_key("6.0.0") < version_key("6.0.1") < version_key("10.0.0")
    assert meets("8.44.1", "8.44.1") and not meets("8.44.0", "8.44.1")
    assert meets("1.5.0", "1.0.0:2.0.0") and not meets("2.1.0", "1.0.0:2.0.0") and meets("0.1.0", None)


def test_required_packs_are_found_installed_registered_or_in_the_index_cache(tmp_path: Path) -> None:
    hit = find_pdsc(PACK_ROOT, "Acme", "Acme_DFP", "0.9.0")
    assert hit and hit[1] == "installed 1.0.0"
    old = find_pdsc(PACK_ROOT, "Acme", "Acme_DFP", "0.9.0:0.9.9")
    assert old and old[1] == "installed 0.9.0"
    assert find_pdsc(PACK_ROOT, "Acme", "Missing", None) is None

    root = tmp_path / "root"
    local = tmp_path / "work" / "my pack"
    local.mkdir(parents=True)
    (local / "V.Local.pdsc").write_text("<package/>")
    (root / ".Local").mkdir(parents=True)
    (root / ".Local" / "local_repository.pidx").write_text(
        f'<index><pindex><pdsc url="file://{local.as_posix().replace(" ", "%20")}/" vendor="V" name="Local" version="1.0.0"/>'
        "</pindex></index>")
    assert find_pdsc(root, "V", "Local", None) == (local / "V.Local.pdsc", "local")
    (root / ".Web").mkdir()
    (root / ".Web" / "V.Web.pdsc").write_text("<package/>")
    assert find_pdsc(root, "V", "Web", "1.0.0") == (root / ".Web" / "V.Web.pdsc", "index")


def test_the_pdsc_yields_devices_with_inherited_cores() -> None:
    assert DFP.devices["AC12_xA"].cores == ["Cortex-M33"] and DFP.devices["AC12_xA"].subfamily == "AC12"
    assert DFP.devices["AC2_xA"].cores == ["Cortex-M55"] and DFP.devices["AC2_xA_LP"].cores == ["Cortex-M55"]
    graph = DFP.entities()
    assert ("device:AC12_xA", "part_of", "subfamily:AC12") in graph.edges
    assert ("subfamily:AC12", "part_of", "family:Acme::AC1 Series") in graph.edges
    assert ("device:AC2_xA_LP", "part_of", "device:AC2_xA") in graph.edges
    assert ("device:AC2_xA", "has_core", "core:Cortex-M55") in graph.edges
    assert BSP.version == "0.2.0" and BSP.license == "Apache-2.0"
    assert [(r.pack_id, r.version) for r in BSP.requirements] == [("Acme::Acme_DFP", "1.0.0")]
