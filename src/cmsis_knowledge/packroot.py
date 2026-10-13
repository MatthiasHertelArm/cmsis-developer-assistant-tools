# Copyright (c) 2026 Arm Limited (or its affiliates). All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Finding the PDSC of a pack another pack requires, in a CMSIS pack root as cpackget lays it out.

Looked for in this order: an installed version that meets the requirement (``<root>/<Vendor>/<Name>/<version>/``),
a pack registered from a folder (``.Local/local_repository.pidx``), and the description cpackget keeps for every
pack of the public index (``.Web/<Vendor>.<Name>.pdsc``). On request, ``Fetcher`` downloads it from the public pack
index instead, for a CI run without a pack root.
"""

from __future__ import annotations

import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

#: The public pack index cpackget reads by default.
DEFAULT_INDEX_URL = "https://www.keil.com/pack/index.pidx"
_TIMEOUT_S = 60


def default_pack_root() -> Path | None:
    """``CMSIS_PACK_ROOT``, else the default of cpackget on this platform; None if it does not exist."""
    if os.environ.get("CMSIS_PACK_ROOT"):
        root = Path(os.environ["CMSIS_PACK_ROOT"]).expanduser()
    elif sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Arm" / "Packs"
    else:
        root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "arm" / "packs"
    return root if root.is_dir() else None


def version_key(version: str) -> tuple[tuple[int, ...], int, str]:
    """Order of semantic versions: ``6.0.0-0`` before ``6.0.0``, numbers compared as numbers."""
    core, _, pre = version.strip().partition("-")
    numbers = tuple(int(n) if n.isdigit() else 0 for n in re.split(r"[.+]", core)[:3])
    numbers += (0,) * (3 - len(numbers))
    return numbers, 0 if pre else 1, pre


def meets(version: str, requirement: str | None) -> bool:
    """Does ``version`` meet a PDSC requirement: ``min``, or ``min:max``?"""
    if not requirement:
        return True
    low, _, high = requirement.partition(":")
    if low and version_key(version) < version_key(low):
        return False
    if high and version_key(version) > version_key(high):
        return False
    return True


def find_pdsc(root: Path, vendor: str, name: str, requirement: str | None) -> tuple[Path, str] | None:
    """The PDSC of ``vendor.name`` and where it came from (``installed 8.44.1``, ``local``, ``index``), or None."""
    file_name = f"{vendor}.{name}.pdsc"
    pack_dir = root / vendor / name
    if pack_dir.is_dir():
        versions = [d.name for d in pack_dir.iterdir() if d.is_dir() and (d / file_name).is_file()]
        fitting = sorted((v for v in versions if meets(v, requirement)), key=version_key)
        if fitting:
            return pack_dir / fitting[-1] / file_name, f"installed {fitting[-1]}"
    pidx = root / ".Local" / "local_repository.pidx"
    if pidx.is_file():
        try:
            for entry in ET.parse(pidx).getroot().iter("pdsc"):
                if entry.get("vendor") == vendor and entry.get("name") == name:
                    folder = unquote(re.sub(r"^file://", "", entry.get("url", "")))
                    if re.match(r"^/[A-Za-z]:", folder):
                        folder = folder[1:]
                    candidate = Path(folder) / file_name
                    if candidate.is_file():
                        return candidate, "local"
        except ET.ParseError:
            pass
    web = root / ".Web" / file_name
    if web.is_file():
        return web, "index"
    return None


class Fetcher:
    """Downloads the PDSC of a pack from a pack index (``.pidx``): the index once, then one file per pack."""

    def __init__(self, index_url: str, folder: Path) -> None:
        self.index_url = index_url
        self.folder = folder
        self._entries: dict[tuple[str, str], str] | None = None

    def _read(self, url: str) -> bytes:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_S) as response:
            return response.read()

    def _index(self) -> dict[tuple[str, str], str]:
        if self._entries is None:
            root = ET.fromstring(self._read(self.index_url))
            self._entries = {(e.get("vendor", ""), e.get("name", "")): e.get("url", "") for e in root.iter("pdsc")}
        return self._entries

    def fetch(self, vendor: str, name: str) -> Path | None:
        """The downloaded PDSC, or None when the index does not list the pack. Raises OSError on network failures."""
        url = self._index().get((vendor, name))
        if not url:
            return None
        target = self.folder / f"{vendor}.{name}.pdsc"
        target.write_bytes(self._read(url.rstrip("/") + f"/{vendor}.{name}.pdsc"))
        return target
