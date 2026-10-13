# Changelog

## 0.1.0

First release.

- `cmsis-knowledge check`, `build` and `info`: check the knowledge units of a CMSIS pack
  (`.knowledge/units/*.md`) and write the index the CMSIS Developer Assistant reads
  (`.knowledge/knowledge.db`, schema 1).
- Every problem with its file and line, also as GitHub Actions annotations; `--strict`
  for CI.
- `applies_to` names checked against the PDSC of the pack and of the packs it requires
  (pack root, local repository, index cache, or downloaded with `--fetch`); a name that
  cannot be checked is written with a warning, never dropped.
- Every unit scoped to its pack (`scoped_to`, `info.scope = pack`); parts mounted on a
  board as `part:` entities.
- The same input gives the same file; `SOURCE_DATE_EPOCH` dates a build.
