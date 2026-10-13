# Copyright (c) 2026 Arm Limited (or its affiliates). All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""What a pack description (PDSC) says that a knowledge index needs: the pack's identity and requirements, and
its devices, boards, parts, components and APIs as entities.

Entity ids follow the csolution notation, as the CMSIS Developer Assistant forms them from a project:

====================================  ===========================================
``pack:ARM::CMSIS``                   a pack, without version
``family:Vendor::Family``             a device family; ``subfamily:Name`` below it
``device:STM32U585AIIx``              a device or variant (``Dname``/``Dvariant``)
``core:Cortex-M33``                   a processor core (``Dcore``)
``board:Vendor::Name``                a board
``part:LSM303AGR``                    a part mounted on a board (``Hname``)
``component:Vendor::Class:Group[:Sub]``  a component
``api:Class:Group``                   an API
``doc:<hash>``                        a document a ``<book>`` names
====================================  ===========================================
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .schema import PART_RELATION


class PdscError(Exception):
    """A PDSC that cannot be read or lacks its vendor or name."""


def vendor_of(value: str | None) -> str:
    """``Nordic Semiconductor:54`` → ``Nordic Semiconductor``: the enumeration suffix of the schema goes."""
    return re.sub(r":\d+$", "", (value or "").strip())


@dataclass
class Device:
    name: str
    vendor: str
    family: str
    subfamily: str | None
    cores: list[str]


@dataclass
class Board:
    vendor: str
    name: str
    revision: str | None
    mounted_devices: list[str]
    #: ``(vendor, name, variant)`` of each ``<mountedPart>``.
    mounted_parts: list[tuple[str, str, str | None]]

    @property
    def id(self) -> str:
        return f"board:{self.vendor}::{self.name}"


@dataclass
class Component:
    vendor: str
    cclass: str
    cgroup: str
    csub: str | None
    api_version: str | None

    @property
    def id(self) -> str:
        return f"component:{self.vendor}::{self.cclass}:{self.cgroup}" + (f":{self.csub}" if self.csub else "")


@dataclass
class Requirement:
    vendor: str
    name: str
    version: str | None

    @property
    def pack_id(self) -> str:
        return f"{self.vendor}::{self.name}"


@dataclass
class Graph:
    """Entity nodes by id, and edges ``(src, rel, dst)``."""

    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: set[tuple[str, str, str]] = field(default_factory=set)

    def node(self, nid: str, kind: str, title: str, **meta: Any) -> str:
        entry = self.nodes.setdefault(nid, {"id": nid, "type": kind, "title": title, "meta": {}})
        entry["meta"].update({k: v for k, v in meta.items() if v not in (None, "", [])})
        return nid

    def edge(self, src: str, rel: str, dst: str) -> None:
        self.edges.add((src, rel, dst))


@dataclass
class PackDescription:
    file: Path
    vendor: str
    name: str
    version: str | None
    description: str
    license: str | None
    requirements: list[Requirement]
    families: dict[str, str]
    subfamilies: dict[str, str]
    devices: dict[str, Device]
    boards: list[Board]
    components: list[Component]
    apis: list[tuple[str, str, str | None]]
    root: ET.Element = field(repr=False)

    @property
    def pack_id(self) -> str:
        return f"{self.vendor}::{self.name}"

    def entities(self) -> Graph:
        """The pack's own entities and their relations."""
        graph = Graph()
        pid = graph.node(f"pack:{self.pack_id}", "pack", self.pack_id, version=self.version,
                         description=self.description[:300])
        _devices(graph, self.root, pid)
        for board in self.boards:
            bid = graph.node(board.id, "board", board.name, vendor=board.vendor, revision=board.revision, pack=pid)
            graph.edge(bid, "part_of", pid)
            for device in board.mounted_devices:
                graph.edge(bid, "mounted_on", f"device:{device}")
            for vendor, name, variant in board.mounted_parts:
                part = graph.node(f"part:{name}", "part", name, vendor=vendor, variant=variant)
                graph.edge(bid, PART_RELATION, part)
        for element in self.root.findall("boards/board"):
            vendor = element.get("vendor") or self.vendor
            _books(graph, element, f"board:{vendor}::{element.get('name')}", pid)
        for cclass, cgroup, version in self.apis:
            aid = graph.node(f"api:{cclass}:{cgroup}", "api", f"{cclass}:{cgroup}", version=version)
            graph.edge(aid, "part_of", pid)
        for component in self.components:
            title = component.id.split("::", 1)[1]
            cid = graph.node(component.id, "component", title, vendor=component.vendor, pack=pid)
            graph.edge(cid, "part_of", pid)
            if component.api_version:
                graph.edge(cid, "implements", f"api:{component.cclass}:{component.cgroup}")
        return graph


def _strip_namespaces(root: ET.Element) -> ET.Element:
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    return root


def _books(graph: Graph, element: ET.Element, target: str, pid: str) -> None:
    for book in element.findall("book") + element.findall("documentation"):
        name = book.get("name") or book.get("title") or ""
        if name:
            did = "doc:" + hashlib.sha1(f"{pid}|{name}".encode()).hexdigest()[:12]
            graph.node(did, "docsection", book.get("title") or name, path=name, category=book.get("category"), pack=pid)
            graph.edge(did, "documents", target)


def _cores_here(element: ET.Element) -> list[str]:
    return sorted({p.get("Dcore") for p in element.findall("processor") if p.get("Dcore")})


def _walk_devices(element: ET.Element, family: str, vendor: str, subfamily: str | None, cores: list[str],
                  found: dict[str, Device], subfamilies: dict[str, str]) -> None:
    for child in element:
        if child.tag == "subFamily" and child.get("DsubFamily"):
            name = child.get("DsubFamily")
            subfamilies[name] = family
            _walk_devices(child, family, vendor, name, _cores_here(child) or cores, found, subfamilies)
        elif child.tag in ("device", "variant"):
            name = child.get("Dname") or child.get("Dvariant")
            if name:
                here = _cores_here(child) or cores
                found[name] = Device(name, vendor, family, subfamily, here)
                _walk_devices(child, family, vendor, subfamily, here, found, subfamilies)


def _devices(graph: Graph, root: ET.Element, pid: str) -> None:
    """Families, subfamilies, devices and variants with their cores, each part of the level above."""

    def walk(element: ET.Element, parent: str, cores: list[str]) -> None:
        for child in element:
            here = _cores_here(child) or cores
            if child.tag == "subFamily" and child.get("DsubFamily"):
                nid = graph.node(f"subfamily:{child.get('DsubFamily')}", "subfamily", child.get("DsubFamily"))
            elif child.tag in ("device", "variant") and (child.get("Dname") or child.get("Dvariant")):
                name = child.get("Dname") or child.get("Dvariant")
                nid = graph.node(f"device:{name}", "device", name, pack=pid)
                for core in here:
                    graph.node(f"core:{core}", "core", core)
                    graph.edge(nid, "has_core", f"core:{core}")
            else:
                continue
            graph.edge(nid, "part_of", parent)
            _books(graph, child, nid, pid)
            walk(child, nid, here)

    for family in root.findall("devices/family"):
        vendor = vendor_of(family.get("Dvendor"))
        fid = graph.node(f"family:{vendor}::{family.get('Dfamily')}", "family", family.get("Dfamily") or "", vendor=vendor)
        graph.edge(fid, "part_of", pid)
        _books(graph, family, fid, pid)
        walk(family, fid, _cores_here(family))


def read_pdsc(path: Path) -> PackDescription:
    """The pack description in ``path``."""
    try:
        root = _strip_namespaces(ET.parse(path).getroot())
    except (ET.ParseError, OSError) as exc:
        raise PdscError(f"{path}: cannot be read: {exc}") from exc
    vendor = (root.findtext("vendor") or "").strip()
    name = (root.findtext("name") or "").strip()
    if not vendor or not name:
        raise PdscError(f"{path}: no <vendor> or <name>")
    releases = root.findall("releases/release")
    version = releases[0].get("version") if releases else None
    description = re.sub(r"\s+", " ", root.findtext("description") or "").strip()
    license_set = root.find("licenseSets/licenseSet/license")
    spdx = license_set.get("spdx") if license_set is not None else None

    requirements = [Requirement(p.get("vendor", ""), p.get("name", ""), p.get("version"))
                    for p in root.findall("requirements/packages/package") if p.get("vendor") and p.get("name")]

    families: dict[str, str] = {}
    subfamilies: dict[str, str] = {}
    devices: dict[str, Device] = {}
    for family in root.findall("devices/family"):
        fvendor = vendor_of(family.get("Dvendor"))
        fname = family.get("Dfamily") or ""
        families[fname] = fvendor
        _walk_devices(family, fname, fvendor, None, _cores_here(family), devices, subfamilies)

    boards = []
    for element in root.findall("boards/board"):
        if not element.get("name"):
            continue
        boards.append(Board(
            vendor=element.get("vendor") or vendor,
            name=element.get("name", ""),
            revision=element.get("revision"),
            mounted_devices=[md.get("Dname", "") for md in element.findall("mountedDevice") if md.get("Dname")],
            mounted_parts=[(mp.get("Hvendor", ""), mp.get("Hname", ""), mp.get("Hvariant"))
                           for mp in element.findall("mountedPart") if mp.get("Hname")],
        ))

    for bundle in root.findall("components/bundle"):
        for component in bundle.findall("component"):
            component.attrib.setdefault("Cclass", bundle.get("Cclass", ""))
            if bundle.get("Cvendor"):
                component.attrib.setdefault("Cvendor", bundle.get("Cvendor", ""))
    components = []
    for element in root.findall("components/component") + root.findall("components/bundle/component"):
        if element.get("Cclass") and element.get("Cgroup"):
            components.append(Component(element.get("Cvendor") or vendor, element.get("Cclass", ""),
                                        element.get("Cgroup", ""), element.get("Csub"), element.get("Capiversion")))
    apis = [(a.get("Cclass", ""), a.get("Cgroup", ""), a.get("Capiversion"))
            for a in root.findall("apis/api") if a.get("Cclass") and a.get("Cgroup")]

    return PackDescription(path, vendor, name, version, description, spdx, requirements, families, subfamilies,
                           devices, boards, components, apis, root)
