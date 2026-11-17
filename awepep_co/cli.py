"""Command line interface for validating and building the directory."""

import argparse
import csv
import io
import subprocess
import sys
from datetime import date
from pathlib import Path

from . import render, resolve, validation


def _date(value):
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a date in YYYY-MM-DD format") from exc


def _diagnostics(root, as_of, base_ref, strict=False):
    issues = validation.validate(root, as_of=as_of, base_ref=base_ref)
    for issue in issues:
        print(str(issue), file=sys.stderr if issue.severity == "error" else sys.stdout)
    return not any(item.severity == "error" or (strict and item.severity == "warning") for item in issues)


def _preview(root, base_ref):
    """Compare records against an explicit Git revision; never affect rendering."""
    lines = ["# Changes preview", "", "Compared with `{}`.".format(base_ref), ""]
    tables = validation.load_tables(root)
    for name, current in sorted(tables.items()):
        result = subprocess.run(["git", "show", "{}:data/{}.csv".format(base_ref, name)], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            exists = subprocess.run(["git", "rev-parse", "--verify", "{}^{{commit}}".format(base_ref)], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if exists.returncode:
                raise ValueError("Git baseline does not exist: {}".format(base_ref))
            before = []
        else:
            before = list(csv.DictReader(io.StringIO(result.stdout)))
        keys = validation.PRIMARY_KEYS[name]
        def indexed(rows):
            return {tuple(row.get(key, "") for key in keys): row for row in rows}
        old, new = indexed(before), indexed(current)
        for key in sorted(new.keys() - old.keys()):
            lines.append("- `{}` added `{}`".format(name, " / ".join(key)))
        for key in sorted(old.keys() - new.keys()):
            lines.append("- `{}` removed `{}`".format(name, " / ".join(key)))
        for key in sorted(new.keys() & old.keys()):
            if new[key] != old[key]:
                lines.append("- `{}` changed `{}`".format(name, " / ".join(key)))
    if len(lines) == 4:
        lines.append("No record changes.")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _managed_files(root):
    found = set()
    for directory in ("cards", "index"):
        path = root / directory
        if path.exists():
            found.update(p.relative_to(root).as_posix() for p in path.rglob("*") if p.is_file())
    return found


def _build(args):
    root = args.root.resolve()
    if not _diagnostics(root, args.as_of, args.base_ref):
        return 1
    tables = validation.load_tables(root)
    resolved = resolve.resolve(tables, args.as_of)
    readme = (root / "README.md").read_text(encoding="utf-8")
    outputs = render.render(tables, resolved, args.as_of, readme, root)
    if args.base_ref:
        outputs["build/CHANGES_PREVIEW.md"] = _preview(root, args.base_ref)
    tracked_outputs = {name for name in outputs if name == "README.md" or name.startswith(("cards/", "index/"))}
    stale = _managed_files(root) - tracked_outputs
    differences = sorted(name for name in tracked_outputs if not (root / name).is_file() or (root / name).read_bytes() != outputs[name])
    if args.check:
        for name in differences:
            print("Generated file differs: {}".format(name), file=sys.stderr)
        for name in sorted(stale):
            print("Unexpected generated file: {}".format(name), file=sys.stderr)
        return int(bool(differences or stale))
    for name in sorted(stale):
        (root / name).unlink()
    for name, content in sorted(outputs.items()):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    print("Built {} files as of {}.".format(len(outputs), args.as_of.isoformat()))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="awepep-co")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Validate source data")
    validate.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    validate.add_argument("--base-ref", help="Compare IDs against this Git revision")
    validate.add_argument("--root", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    validate.add_argument("--as-of", type=_date, default=date.today(), help="Reference date for warnings")
    build = sub.add_parser("build", help="Validate, resolve and render")
    build.add_argument("--as-of", type=_date, default=date.today())
    build.add_argument("--check", action="store_true", help="Compare generated files without writing")
    build.add_argument("--base-ref", help="Compare records and generate a change preview against this revision")
    build.add_argument("--root", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            return 0 if _diagnostics(args.root.resolve(), args.as_of, args.base_ref, args.strict) else 1
        return _build(args)
    except (OSError, ValueError, csv.Error) as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
