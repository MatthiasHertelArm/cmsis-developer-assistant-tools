# How to add a knowledge database to your pack

This guide is for CMSIS partners who make a BSP or a DFP pack. It uses Simplified Technical English
(ASD-STE100). It uses the pack
[MicroBit::MicroBit_V2_BSP](https://github.com/Open-CMSIS-Pack/MicroBit_V2_BSP) as a complete example.

When you add knowledge to your pack, the CMSIS Developer Assistant gets the facts of your board. An AI agent can
then find your procedures, rules and fixes for known error messages. The assistant shows your units only in
projects that use your pack.

## What the example contains

The knowledge is in the `.knowledge/` folder of the pack source. The example has 12 units. Each unit is one
Markdown file.

| Item | Location in the example | Function |
|:-----|:------------------------|:---------|
| Knowledge units | `.knowledge/units/*.md` | One concept, procedure, rule or problem in each file |
| List of units | `.knowledge/README.md` | Lists each unit with its type and topic (optional, not a unit) |
| Build step | `gen_pack.sh`, function `preprocess` | Runs `cmsis-knowledge build . --strict --fetch` before packaging |
| CI setup | `.github/workflows/pack.yml`, `build.yml` | Installs `cmsis-knowledge` before the gen-pack step |

The file name starts with the prefix of the unit type:

| Prefix | Type | Example |
|:-------|:-----|:--------|
| `ts-` | `troubleshooting` | `ts-daplink-maintenance-mode.md`: the board shows a MAINTENANCE drive |
| `concept-` | `concept` | `concept-microbit-v2-hardware.md`: parts and pin map |
| `proc-` | `procedure` | `proc-microbit-v2-bring-up.md`: build, download and verify |
| `rule-` | `rule` | `rule-drag-and-drop-when-pyocd-erase-fails.md` |
| `pattern-` | `pattern` | (not used in the example) |

## Tools

| Tool | Used by | Function |
|:-----|:--------|:---------|
| `cmsis-knowledge check` | Pack author | Checks the units. Writes nothing |
| `cmsis-knowledge build` | Pack author, CI | Checks the units and writes `.knowledge/knowledge.db` |
| `cmsis-knowledge info` | Pack author | Shows what an index contains |
| `knowledge_search` | AI agent | Finds units from two or three words or from an error message |
| `knowledge_get` | AI agent | Reads the full text of one unit |
| `knowledge_expand` | AI agent | Follows the relations from one unit to related units |

The data moves in this sequence:

1. You write the units in `.knowledge/units/`.
2. `cmsis-knowledge build` makes `.knowledge/knowledge.db`.
3. `gen_pack.sh` puts the units and `knowledge.db` in the pack.
4. The user installs the pack.
5. The AI agent reads `knowledge.db` with the `knowledge_*` tools.

## Procedure: make your knowledge database

1. Install the tool. Refer to [Install](../README.md#install).
2. Make the folder `.knowledge/units/` in the pack folder (the folder with the PDSC).
3. Write down each problem that you solve during pack development. Write the error text exactly as the tool
   shows it.
4. Make one Markdown file for each problem, concept, procedure or rule. Use the type prefix in the file name.
5. Add the YAML frontmatter at the top of each file. The fields `id`, `type`, `title`, `summary` and `status`
   are mandatory. Also add `applies_to`, `source` and `license`.
6. For a troubleshooting unit, add `symptoms` and, if possible, `symptom_regex`. Copy the error messages into
   `symptoms`.
7. For a procedure unit, add `triggers`. Use `references` to name the units that the procedure uses.
8. Write the text below the frontmatter in sections. Example for a troubleshooting unit: Symptom, Cause, Fix.
9. Run `cmsis-knowledge check .` in the pack folder. Correct all errors and warnings.
10. In `gen_pack.sh`, add `.knowledge` to `PACK_DIRS`.
11. In `gen_pack.sh`, add `cmsis-knowledge build . --strict --fetch || exit 1` to the function `preprocess`.
12. Add `.knowledge/knowledge.db` to `.gitignore`. The units are the source.
13. In your GitHub workflow, install `cmsis-developer-assistant-tools` before the gen-pack step.

> **CAUTION:** Put the pack folder `.` before `--fetch`. If you put it after `--fetch`, the tool uses `.` as
> the index URL.

> **NOTE:** gen-pack ignores the return value of `preprocess`. Thus `|| exit 1` is necessary to stop the
> pack build when the units have errors.

## Rules for good units

- Write one topic in each unit. Keep units short.
- Write the `summary` as one sentence that gives the answer. Use 40 words or less. The search shows the summary
  first.
- Copy error messages exactly. The agent compares them with the error text that the user gets.
- Write only data that you tested. Record the test setup in `source` (board revision, tool versions).
- Use `status: draft` for a new unit. Change it to `reviewed` after a second person checks the unit.
- Use `applies_to` to limit the unit to your board, device, part, component or tool. This prevents wrong
  matches in other projects. Use the names from your PDSC.
- Give each unit an `id` that is specific to your pack. An `id` that the base index also has is not used.
- Refer to other units by their `id`. Do not copy their text.
- In a procedure, tell the agent to use the assistant tools (for example `cmsis_action`). Do not tell it to run
  debug tools from a shell.
- Give a license for each unit, for example `Apache-2.0`.

## Check the result

1. Run `./gen_pack.sh`. Make sure that the build step shows no errors.
2. Make sure that the `.pack` file contains `.knowledge/units/` and `.knowledge/knowledge.db`.
3. Run `cmsis-knowledge info .knowledge/knowledge.db`. Make sure that all your units are in the index.
4. Install the pack with `cpackget add`.
5. Open a project that uses the pack in VS Code.
6. Tell the agent to call `knowledge_search` with an error text from one of your troubleshooting units.
7. Make sure that the search finds your unit. If not, change `symptoms`, `triggers` or `summary`.
8. Open a project that does not use your pack. Make sure that the search does not show your units.

## Related documents

- [format.md](format.md): all fields of a unit, the names of `applies_to` and the index format.
- [MicroBit_V2_BSP](https://github.com/Open-CMSIS-Pack/MicroBit_V2_BSP): the complete example.
