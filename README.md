# CMSIS Developer Assistant tools

Tools for authors of CMSIS packs who want their pack to carry knowledge for the
[CMSIS Developer Assistant](https://github.com/Open-CMSIS-Pack/CMSIS-Developer-Assistant):
the procedures, rules, concepts and fixes of known error messages that an AI agent
looks up with the assistant's knowledge tools while it works on a project that uses
the pack.

Version 0.1.0 has one command, `cmsis-knowledge`. It checks the knowledge units of a
pack and builds the index the assistant reads.

## Install

```sh
pip install cmsis-developer-assistant-tools
```

Python 3.10 or later. The only dependency is PyYAML; the index is written with the
SQLite that comes with Python (it needs FTS5, which the builds of python.org,
Homebrew and the Linux distributions have).

## A pack with knowledge

```txt
MyVendor.MyBoard_BSP.pdsc
.knowledge/
  README.md                 optional, not a unit
  units/
    proc-myboard-bring-up.md
    ts-flash-locked.md
    ...
  knowledge.db              built by cmsis-knowledge build
```

Each unit is one Markdown file: YAML frontmatter, then the text.

```markdown
---
id: ts-myboard-flash-locked
type: troubleshooting
title: "pyOCD: flash erase fails on a factory MyBoard"
summary: The factory image locks the flash; erase it once with the vendor's mass erase.
domain: debug
status: draft
symptoms:
  - "flash erase sector failure (address 0x00000000; result code 0x67)"
symptom_regex: "flash erase sector failure \\(address 0x[0-9A-Fa-f]+; result code 0x67\\)"
applies_to:
  board: [MyBoard]
  tool: [pyocd]
license: Apache-2.0
---

## Symptom
...
## Cause
...
## Fix
...
```

[docs/format.md](docs/format.md) describes every field, the names `applies_to`
takes, and the index the build writes.

## Commands

```sh
cmsis-knowledge check [PACK]     # check the units, write nothing
cmsis-knowledge build [PACK]     # check, then write PACK/.knowledge/knowledge.db
cmsis-knowledge info [INDEX]     # what an index holds
```

`PACK` is the folder with the PDSC, the current folder by default. Options of
`check` and `build`:

| Option | Meaning |
| ------ | ------- |
| `--strict` | Fail on warnings too; use it in CI |
| `--pack-root DIR` | Where the packs this pack requires are installed; default `CMSIS_PACK_ROOT`, else cpackget's default |
| `--fetch [INDEX_URL]` | Download the description of a required pack that no pack root has from the public pack index (`https://www.keil.com/pack/index.pidx`), for a CI run without installed packs |
| `--with-pdsc FILE` | The description of a required pack, when no pack root has it (repeatable) |
| `--known DB` | Another knowledge index whose unit ids your units may name in `requires`, `refines` and the other relations (repeatable) |
| `--pdsc FILE` | The pack's description, when the folder holds more than one |
| `--units DIR`, `--out FILE` | Other places for the units and the index |

Messages read `path:line: severity: text`. Errors always fail; warnings fail with
`--strict`. In GitHub Actions they also appear as annotations on the files.
Exit status: 0 done, 1 errors (or warnings with `--strict`), 2 the input cannot be
built at all.

The build reads the PDSC of the pack and of the packs it requires, so that a unit
that names a board, device, part or component is checked against the descriptions.
A name it cannot check is still written, with a warning; one that can never match
a project (a wildcard, a subfamily used as a device) is an error.

## In the pack build

With [gen-pack](https://github.com/Open-CMSIS-Pack/gen-pack), list the folder and
build the index before the pack is put together:

```sh
PACK_DIRS="
  Board
  Documents
  .knowledge
"

function preprocess() {
  # gen-pack ignores the return value of preprocess: stop the script on failure
  cmsis-knowledge build --strict --fetch . || exit 1
}
```

Keep `.knowledge/knowledge.db` out of version control (`.gitignore`); the units are
the source. In a GitHub workflow, install the tool before gen-pack runs:

```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
- run: pip install cmsis-developer-assistant-tools==0.1.0
```

## What the assistant does with it

The CMSIS Developer Assistant (2.7.0 or later, with the experimental setting
`cmsis-developer-assistant.knowledge.enabled` on) reads `.knowledge/knowledge.db` of
every installed pack. A pack's units are offered only in projects that use the
pack, and within those only where their `applies_to` fits the active target. The
knowledge browser of the assistant opens a unit's Markdown file from the installed
pack.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
