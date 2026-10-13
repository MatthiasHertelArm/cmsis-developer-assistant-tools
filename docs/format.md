# Pack knowledge: layout, unit format and index (version 1)

This is the contract between pack authors, `cmsis-knowledge` and the readers of the
index, first of all the CMSIS Developer Assistant
(`src/core/knowledge/store.ts`, `packIndexes.ts` and `search.ts` there).

## Layout

A pack carries its knowledge in the folder `.knowledge` next to its PDSC:

| Path | What |
| ---- | ---- |
| `.knowledge/units/**/*.md` | The units, one per file. Sub-folders are allowed; `README.md` files and hidden folders are not units |
| `.knowledge/knowledge.db` | The index `cmsis-knowledge build` writes from the units and the PDSC |
| `.knowledge/README.md` | Optional, for people |

The pack ships both: the index for the knowledge tools, the units for people (the
assistant's knowledge browser opens the file a unit came from). Nothing in the PDSC
refers to the folder.

## Units

YAML frontmatter between a first line `---` and a closing `---`, then the text in
Markdown. A value with `: ` in it needs quotes.

| Field | Required | Meaning |
| ----- | -------- | ------- |
| `id` | yes | Unique id: lower-case letters, digits, `-`, `_`, `.`. By convention `concept-`, `proc-`, `rule-`, `pattern-` or `ts-` and a name. An id that the base index also has is shadowed by it: choose names specific to the pack |
| `type` | yes | `concept`, `procedure`, `rule`, `pattern` or `troubleshooting` |
| `title` | yes | One line |
| `summary` | yes | At most 40 words (a warning above): a search returns summaries within the agent's token budget |
| `status` | yes | `draft` or `reviewed` |
| `domain` | no | Topic: `board`, `debug`, `project`, `pack`, ... |
| `applies_to` | no | Where the unit holds, see below |
| `requires`, `refines`, `conflicts_with`, `supersedes`, `constrains`, `produces`, `consumes`, `references` | no | Lists of unit ids. A unit that `refines` another replaces it where both apply |
| `symptoms` | no | The messages of a troubleshooting unit, verbatim |
| `symptom_regex` | no | A pattern that finds the message in tool output. It must be valid in Python and in JavaScript: no `(?P<name>)`, no inline flags, no `\A` or `\Z`. Matched without case |
| `triggers` | no | Phrases of a task the unit is for; searched like the title |
| `license` | no, warned | SPDX identifier of the unit's text |
| `source` | no | Where the knowledge comes from |

Any other field is kept and shown with the unit (`tool`, `severity`, `confidence`,
`preconditions`, `stop_conditions`, ...).

A troubleshooting unit has the sections `## Symptom`, `## Cause` and `## Fix`. A
unit whose text, or whose `## Cause`, is only a placeholder such as `_to be
written_` is left out of search.

### `applies_to`

Each key takes one name or a list. Within a key one name has to match, across keys
all of them (a key the project says nothing about leaves the unit in, marked
unverified). Names become entity ids as the assistant derives them from a project:

| Key | Name | Id |
| --- | ---- | -- |
| `board` | `MyBoard`, `Vendor::MyBoard`, `Vendor::MyBoard:Rev.B` | `board:Vendor::MyBoard` |
| `device` | `nRF52833_xxAA`, also with `Vendor::` or `:Pname` | `device:nRF52833_xxAA` |
| `family` | `Vendor::Family`, or `Family` when a description knows it | `family:Vendor::Family` |
| `part` | `LSM303AGR`, also `Vendor::LSM303AGR` (`<mountedPart Hname>`) | `part:LSM303AGR` |
| `core` | `Cortex-M33` (`Dcore`) | `core:Cortex-M33` |
| `toolchain`, `compiler` | `AC6`, `GCC`, `CLANG`, `IAR` | `toolchain:GCC` |
| `pack` | `Vendor::Name` or `Vendor.Name` | `pack:Vendor::Name` |
| `component` | `Cvendor::Cclass:Cgroup[:Csub]`, or without the vendor when a description knows it | `component:...` |
| `api` | `Cclass:Cgroup` | `api:Cclass:Cgroup` |
| `tool` | `pyocd`, `csolution`, ... | `tool:pyocd` |

`@range` after a name (`pack: [ARM::CMSIS@>=6.0.0]`) is kept as a qualifier.

The build checks names against the PDSC of the pack and of the packs it requires.
A name it cannot confirm is written as given, with a warning: dropping it would
make the unit hold for every project. A wildcard, a subfamily or prefix given as a
device, and a component or family without the vendor that no description knows are
errors, since no project yields such an id. The `tool` key filters only when a
question names tools; MCP tool names such as `cmsis_action` are no tools.

### Scope

Every unit of a pack is scoped to that pack: the build adds the relation
`scoped_to` from each unit to `pack:<Vendor>::<Name>`, and `info.scope` is `pack`.
A reader offers such a unit only when the active project uses the pack. This is
stricter than `applies_to`: without a project, the units are not offered.

## Index (schema 1)

One SQLite file.

| Table | Columns |
| ----- | ------- |
| `nodes` | `id` (primary key), `kind` (`knowledge` or `entity`), `type`, `domain`, `title`, `summary`, `body`, `meta` (JSON: the other frontmatter fields, and `path`, the unit's file relative to the pack folder with `/`) |
| `edges` | `src`, `rel`, `dst`, `qual` (JSON or NULL); primary key `(src, rel, dst)` |
| `nodes_fts` | FTS5, `tokenize='porter unicode61'`: `id` (unindexed), `title`, `summary`, `body`, `symptoms`, `triggers` (with the `description` field and the title's words spelled apart) |
| `unresolved` | `src`, `key`, `value`: the `applies_to` names the build could not confirm |
| `info` | `key`, `value` |

`info` rows: `schema_version` (`1`; readers refuse another major version),
`format_version` (`1`), `builder` (`cmsis-knowledge`), `builder_version`, `pack`
(`Vendor::Name@version`), `scope` (`pack`), `units` (count), and `built_at` (UTC)
when `SOURCE_DATE_EPOCH` is set. Without it the same input gives the same file.

Relations:

| Relation | From → to |
| -------- | --------- |
| `applies_to` | unit → entity |
| `scoped_to` | unit → its pack |
| `requires`, `refines`, ... | unit → unit, as in the frontmatter |
| `part_of` | device → subfamily → family → pack; board, component, api → pack |
| `has_core` | device → core |
| `mounted_on` | board → device |
| `has_part` | board → part |
| `implements` | component → api |
| `documents` | document → board, device or family |

The index holds the entities of the pack's own PDSC (and the tools its units name).
Those of required packs are read for checking only.
