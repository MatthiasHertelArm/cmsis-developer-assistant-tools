# Copyright (c) 2026 Arm Limited (or its affiliates). All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""The contract with the readers of a pack's knowledge: where it lives in a pack, what a unit may say, and the
layout of the index file.

The CMSIS Developer Assistant reads the index with Node's SQLite (``src/core/knowledge/store.ts``). A change here
that a reader would notice raises ``SCHEMA_VERSION``; readers refuse an index of another major version.
"""

#: Major version of the index layout (``info.schema_version``).
SCHEMA_VERSION = 1
#: Version of the unit format and the ``.knowledge`` layout (``info.format_version``).
FORMAT_VERSION = 1

#: The folder of a pack that holds its knowledge, next to the PDSC.
KNOWLEDGE_DIR = ".knowledge"
#: The units, one Markdown file each, below ``KNOWLEDGE_DIR``.
UNITS_DIR = "units"
#: The built index, below ``KNOWLEDGE_DIR``.
INDEX_NAME = "knowledge.db"

KNOWLEDGE_TYPES = ("concept", "procedure", "rule", "pattern", "troubleshooting")
STATUSES = ("draft", "reviewed")
#: Relations a unit names in its frontmatter, each a list of unit ids.
RELATIONS = ("requires", "refines", "conflicts_with", "supersedes", "constrains", "produces", "consumes", "references")
#: Keys of ``applies_to``. ``compiler`` is another name for ``toolchain``.
APPLIES_KEYS = ("device", "family", "board", "part", "core", "component", "api", "pack", "toolchain", "compiler", "tool")
TOOLCHAINS = ("AC6", "GCC", "CLANG", "IAR")
#: Tools a unit usually names; another name is allowed with a warning, since a typo would never match.
KNOWN_TOOLS = (
    "csolution", "cbuild", "cpackget", "cbridge", "cbuild2cmake", "packchk", "svdconv", "packgen", "vcpkg",
    "gen-pack", "cmsis-solution", "cmsis-debugger", "pyocd", "jlink", "openocd", "gdb", "daplink", "fvp", "west", "vela",
    "uv2csolution",
)
#: A summary is what a search returns; longer ones eat the agent's token budget.
SUMMARY_MAX_WORDS = 40

#: Frontmatter fields that are columns of ``nodes``; every other field is kept in ``nodes.meta``.
COLUMN_FIELDS = ("id", "type", "domain", "title", "summary")

#: Relation of every unit of a pack to that pack: the unit is offered only to projects that use the pack.
SCOPE_RELATION = "scoped_to"
#: Relation of a board to a part mounted on it (``<mountedPart>``).
PART_RELATION = "has_part"

#: Info keys every index carries.
INFO_KEYS = ("schema_version", "format_version", "builder", "builder_version", "pack", "scope", "units")

DDL = """
CREATE TABLE nodes(id TEXT PRIMARY KEY, kind TEXT, type TEXT, domain TEXT, title TEXT,
                   summary TEXT, body TEXT, meta JSON);
CREATE TABLE edges(src TEXT, rel TEXT, dst TEXT, qual JSON, PRIMARY KEY(src, rel, dst));
CREATE TABLE unresolved(src TEXT, key TEXT, value TEXT);
CREATE TABLE info(key TEXT PRIMARY KEY, value TEXT);
CREATE VIRTUAL TABLE nodes_fts USING fts5(id UNINDEXED, title, summary, body, symptoms, triggers,
                                          tokenize='porter unicode61');
CREATE INDEX edges_dst ON edges(dst, rel);
"""
