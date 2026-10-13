# Copyright (c) 2026 Arm Limited (or its affiliates). All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""The ``cmsis-knowledge`` command: ``check``, ``build`` and ``info``.

Exit status: 0 done, 1 the units have errors (or warnings with ``--strict``), 2 the input cannot be built at all.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from . import __version__
from .build import BuildError, Options, Result, build
from .diagnostics import in_github_actions
from .info import describe
from .packroot import DEFAULT_INDEX_URL


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cmsis-knowledge",
        description="Check and build the knowledge a CMSIS pack ships in its .knowledge folder.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    def pack_options(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("pack", nargs="?", default=".", type=Path,
                         help="the pack folder: its PDSC and the .knowledge folder (default: the current folder)")
        sub.add_argument("--pdsc", type=Path, help="the pack's description, when the folder holds several")
        sub.add_argument("--units", type=Path, help="the units folder (default: <pack>/.knowledge/units)")
        sub.add_argument("--pack-root", type=Path,
                         help="where to find the packs this pack requires (default: CMSIS_PACK_ROOT, else cpackget's)")
        sub.add_argument("--with-pdsc", type=Path, action="append", default=[], metavar="PDSC",
                         help="the description of a required pack, instead of looking in the pack root (repeatable)")
        sub.add_argument("--fetch", nargs="?", const=DEFAULT_INDEX_URL, metavar="INDEX_URL",
                         help="download the description of a required pack that no pack root has, from the public "
                              f"pack index (default {DEFAULT_INDEX_URL}) or the index given")
        sub.add_argument("--known", type=Path, action="append", default=[], metavar="DB",
                         help="another knowledge index whose ids units may name in their relations (repeatable)")
        sub.add_argument("--strict", action="store_true", help="fail on warnings too")

    check = commands.add_parser("check", help="check the units without writing an index")
    pack_options(check)
    build_cmd = commands.add_parser("build", help="check the units and write .knowledge/knowledge.db")
    pack_options(build_cmd)
    build_cmd.add_argument("--out", type=Path, help="the index file (default: <pack>/.knowledge/knowledge.db)")
    info = commands.add_parser("info", help="show what an index holds")
    info.add_argument("index", nargs="?", default=Path(".knowledge/knowledge.db"), type=Path,
                      help="the index file (default: .knowledge/knowledge.db)")
    return parser


def _print_report(result: Result) -> None:
    for line in result.report.lines():
        print(line)
    if in_github_actions():
        for line in result.report.annotations():
            print(line)


def _summary(result: Result, strict: bool, building: bool) -> list[str]:
    counts = result.counts
    types = ", ".join(f"{t} {n}" for t, n in counts.get("types", {}).items()) or "none"
    errors, warnings = len(result.report.errors), len(result.report.warnings)
    lines = [f"{result.pack.pack_id if result.pack else '?'}: {counts.get('units', 0)} units ({types}), "
             f"{counts.get('entities', 0)} entities, {counts.get('edges', 0)} relations; "
             f"{errors} error{'s' if errors != 1 else ''}, {warnings} warning{'s' if warnings != 1 else ''}"]
    if result.written:
        lines.append(f"wrote {result.out}")
    elif building and result.report.failed(strict):
        lines.append(f"no index written: fix the {'errors' if errors else 'warnings (--strict)'} above")
    return lines


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "info":
        try:
            print("\n".join(describe(args.index)))
        except (OSError, ValueError, sqlite3.Error) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0

    options = Options(pack_dir=args.pack, units_dir=args.units, out=getattr(args, "out", None), pdsc=args.pdsc,
                      with_pdsc=args.with_pdsc, pack_root=args.pack_root, known=args.known, strict=args.strict,
                      fetch_index=args.fetch)
    try:
        result = build(options, write=args.command == "build")
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _print_report(result)
    print("\n".join(_summary(result, args.strict, args.command == "build")))
    return 1 if result.report.failed(args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
