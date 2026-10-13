# Copyright (c) 2026 Arm Limited (or its affiliates). All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""``applies_to`` values to entity ids, checked against the pack's own description and the packs it requires.

A value is never dropped: one that no description confirms is still written, in the form the CMSIS Developer
Assistant derives from a project, with a warning. Dropping it would leave the unit without that target, and a unit
without targets holds for every project.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .pdsc import Board, PackDescription
from .schema import KNOWN_TOOLS, TOOLCHAINS

_WILDCARD = re.compile(r"[*?\[]")
_CORE = re.compile(r"^(Cortex-[AMR]\d+[A-Z+]*|SC000|SC300|Star-MC\d+|ARMV\d+[A-Z]*|ARMV\d+\.?\d*[A-Z]*)$")


@dataclass
class Target:
    """What one ``applies_to`` value became."""

    ids: list[str]
    qual: dict[str, str] | None = None
    #: A pack description confirms the id.
    verified: bool = False
    #: ``(severity, message)`` when there is something to say.
    problem: tuple[str, str] | None = None


@dataclass
class Resolver:
    own: PackDescription
    others: list[PackDescription] = field(default_factory=list)
    #: Required packs whose description was not found.
    missing: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        descriptions = [self.own, *self.others]
        self.boards: dict[str, list[Board]] = {}
        self.devices: dict[str, str] = {}
        self.subfamilies: dict[str, list[str]] = {}
        self.families: dict[str, list[str]] = {}
        self.components: set[str] = set()
        self.component_tails: dict[str, list[str]] = {}
        self.parts: set[str] = set()
        self.cores: set[str] = set()
        self.packs = {self.own.pack_id, *(r.pack_id for r in self.own.requirements), *(d.pack_id for d in self.others)}
        self.apis: set[str] = set()
        for description in descriptions:
            for board in description.boards:
                self.boards.setdefault(board.name, []).append(board)
                self.parts.update(name for _, name, _ in board.mounted_parts)
            for name, device in description.devices.items():
                self.devices[name] = name
                self.cores.update(device.cores)
                if device.subfamily:
                    self.subfamilies.setdefault(device.subfamily, []).append(name)
            for family, vendor in description.families.items():
                self.families.setdefault(family, []).append(f"family:{vendor}::{family}")
            for component in description.components:
                self.components.add(component.id)
                self.component_tails.setdefault(component.id.split("::", 1)[1], []).append(component.id)
            self.apis.update(f"api:{c}:{g}" for c, g, _ in description.apis)

    def _unchecked(self) -> str:
        if not self.missing:
            return "it is not in this pack or the packs it requires"
        return f"not checked, since {', '.join(self.missing)} was not found"

    def resolve(self, key: str, raw: Any) -> Target:
        value = str(raw).strip()
        if not value:
            return Target([], problem=("error", f"applies_to {key}: an empty value"))
        if _WILDCARD.search(value):
            return Target([], problem=("error", f"applies_to {key} '{value}': wildcards are not supported, list the names"))
        qual = None
        if "@" in value:
            value, version_range = value.split("@", 1)
            qual = {"range": version_range}
        key = "toolchain" if key == "compiler" else key
        target = getattr(self, f"_{key}")(value)
        target.qual = qual
        return target

    def _board(self, value: str) -> Target:
        vendor, _, name = value.rpartition("::")
        name = name.split(":")[0]
        found = [b for b in self.boards.get(name, []) if not vendor or b.vendor == vendor]
        if found:
            return Target(sorted({b.id for b in found}), verified=True)
        nid = f"board:{vendor}::{name}" if vendor else f"board:{name}"
        return Target([nid], problem=("warning", f"applies_to board '{value}': {self._unchecked()}"))

    def _device(self, value: str) -> Target:
        name = value.split("::")[-1].split(":")[0]
        if name in self.devices:
            return Target([f"device:{name}"], verified=True)
        if name in self.subfamilies:
            devices = sorted(self.subfamilies[name])
            listed = ", ".join(devices[:6]) + (", ..." if len(devices) > 6 else "")
            return Target([], problem=("error", f"applies_to device '{value}' is a subfamily; name its devices ({listed})"))
        if name in self.families:
            ids = self.families[name]
            return Target([], problem=("error", f"applies_to device '{value}' is a device family; write "
                                                f"'family: {ids[0].split(':', 1)[1]}'"))
        similar = sorted(d for d in self.devices if d.startswith(name))
        if similar:
            listed = ", ".join(similar[:6]) + (", ..." if len(similar) > 6 else "")
            return Target([], problem=("error", f"applies_to device '{value}' is no device; the devices are named {listed}"))
        return Target([f"device:{name}"], problem=("warning", f"applies_to device '{value}': {self._unchecked()}"))

    def _family(self, value: str) -> Target:
        vendor, _, name = value.rpartition("::")
        ids = [i for i in self.families.get(name, []) if not vendor or i == f"family:{vendor}::{name}"]
        if ids:
            return Target(ids, verified=True)
        if vendor:
            return Target([f"family:{vendor}::{name}"], problem=("warning", f"applies_to family '{value}': {self._unchecked()}"))
        return Target([], problem=("error", f"applies_to family '{value}': give the vendor, 'Vendor::{name}', "
                                            f"since {self._unchecked()}"))

    def _part(self, value: str) -> Target:
        name = value.split("::")[-1]
        if name in self.parts:
            return Target([f"part:{name}"], verified=True)
        return Target([f"part:{name}"], problem=("warning", f"applies_to part '{value}': no board of this pack mounts it"))

    def _core(self, value: str) -> Target:
        if value in self.cores or _CORE.match(value):
            return Target([f"core:{value}"], verified=True)
        return Target([f"core:{value}"], problem=("warning", f"applies_to core '{value}' is not a Dcore name such as Cortex-M33"))

    def _toolchain(self, value: str) -> Target:
        name = value.upper()
        if name in TOOLCHAINS:
            return Target([f"toolchain:{name}"], verified=True)
        return Target([f"toolchain:{name}"], problem=("warning", f"applies_to toolchain '{value}' is none of {', '.join(TOOLCHAINS)}"))

    def _tool(self, value: str) -> Target:
        name = value.lower()
        if name in KNOWN_TOOLS:
            return Target([f"tool:{name}"], verified=True)
        return Target([f"tool:{name}"], problem=("warning", f"applies_to tool '{value}' is not a known tool (a program "
                                                            "such as pyocd or csolution); a search names tools by those names"))

    def _pack(self, value: str) -> Target:
        if "::" not in value and "." in value:
            value = value.replace(".", "::", 1)
        if value in self.packs:
            return Target([f"pack:{value}"], verified=True)
        return Target([f"pack:{value}"], problem=("warning", f"applies_to pack '{value}' is neither this pack nor one it requires"))

    def _component(self, value: str) -> Target:
        if "::" in value:
            nid = f"component:{value}"
            if nid in self.components:
                return Target([nid], verified=True)
            return Target([nid], problem=("warning", f"applies_to component '{value}': {self._unchecked()}"))
        ids = self.component_tails.get(value)
        if ids:
            return Target(sorted(set(ids)), verified=True)
        return Target([], problem=("error", f"applies_to component '{value}': give the vendor, 'Cvendor::{value}', "
                                            f"since {self._unchecked()}"))

    def _api(self, value: str) -> Target:
        nid = f"api:{value}"
        if nid in self.apis:
            return Target([nid], verified=True)
        return Target([nid], problem=("warning", f"applies_to api '{value}': {self._unchecked()}"))
