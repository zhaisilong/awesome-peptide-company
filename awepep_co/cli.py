"""Command line interface for validating and building the directory."""

import argparse
import csv
import io
import math
import subprocess
import sys
from datetime import date
from pathlib import Path

from . import history, render, resolve, validation


def _date(value):
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a date in YYYY-MM-DD format") from exc


def _nonnegative_int(value):
    try:
        result = int(value)
        if result < 0:
            raise ValueError
        return result
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a non-negative integer") from exc


def _timeout(value):
    try:
        result = float(value)
        if not math.isfinite(result) or result <= 0:
            raise ValueError
        return result
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a positive timeout in seconds") from exc


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
    output_root = args.output_dir.resolve() if args.output_dir else root
    has_history = bool(history._snapshot_dirs(root))
    source_root = root
    if args.output_dir:
        if output_root == root or root in output_root.parents and output_root.relative_to(root).parts[0] not in ("build",):
            raise ValueError("historical output must be outside the source tree or under build/")
        if not has_history:
            raise ValueError("historical output requires a recorded baseline")
        if not args.check and output_root.exists() and any(output_root.iterdir()):
            raise ValueError("historical output directory must be empty")
    if has_history:
        history.check(root, current=not bool(args.output_dir))
        source_root = history.select(root, args.as_of)
        if not args.output_dir and source_root != history._snapshot_dirs(root)[-1] / "files":
            raise ValueError("historical builds require --output-dir")
    if args.base_ref and source_root != root and not _diagnostics(root, args.as_of, args.base_ref):
        return 1
    if not _diagnostics(source_root, args.as_of, None if source_root != root else args.base_ref):
        return 1
    tables = resolve.tables_as_of(validation.load_tables(source_root), args.as_of)
    resolved = resolve.resolve(tables, args.as_of)
    readme = (source_root / "README.md").read_text(encoding="utf-8")
    outputs = render.render(tables, resolved, args.as_of, readme, source_root, template_root=root)
    if args.output_dir:
        for directory in ("assets", "docs"):
            source_dir = source_root / directory
            if source_dir.is_dir():
                for file in source_dir.rglob("*"):
                    if file.is_file():
                        outputs[file.relative_to(source_root).as_posix()] = file.read_bytes()
    if args.base_ref:
        outputs["build/CHANGES_PREVIEW.md"] = _preview(root, args.base_ref)
    tracked_outputs = {name for name in outputs if name == "README.md" or name.startswith(("cards/", "index/")) or (args.output_dir and name.startswith(("assets/", "docs/")))}
    stale = _managed_files(output_root) - tracked_outputs
    differences = sorted(name for name in tracked_outputs if not (output_root / name).is_file() or (output_root / name).read_bytes() != outputs[name])
    if args.check:
        for name in differences:
            print("Generated file differs: {}".format(name), file=sys.stderr)
        for name in sorted(stale):
            print("Unexpected generated file: {}".format(name), file=sys.stderr)
        return int(bool(differences or stale))
    for name in sorted(stale):
        (output_root / name).unlink()
    for name, content in sorted(outputs.items()):
        path = output_root / name
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
    build.add_argument("--output-dir", type=Path, help="Write historical snapshot to an empty, independent directory")
    build.add_argument("--base-ref", help="Compare records and generate a change preview against this revision")
    build.add_argument("--root", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    archive = sub.add_parser("history", help="Record and validate knowledge snapshots")
    archive_sub = archive.add_subparsers(dest="history_command", required=True)
    archive_record = archive_sub.add_parser("record")
    archive_record.add_argument("--reason", required=True)
    archive_record.add_argument("--root", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    archive_check = archive_sub.add_parser("check")
    archive_check.add_argument("--require", action="store_true")
    archive_check.add_argument("--base-ref")
    archive_check.add_argument("--root", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    add = sub.add_parser("add", help="Validate and append a source record")
    add.add_argument("kind", choices=("entity", "event", "evidence", "asset"))
    add.add_argument("--field", action="append", required=True, metavar="NAME=VALUE")
    add.add_argument("--root", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    links = sub.add_parser("check-links", help="Check evidence URLs without changing records")
    links.add_argument("--timeout", type=_timeout, default=10.0, help="Timeout per request in seconds")
    links.add_argument("--root", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    stale = sub.add_parser("stale", help="Report stale or unverified entities")
    stale.add_argument("--days", type=_nonnegative_int, default=365)
    stale.add_argument("--as-of", type=_date, default=date.today())
    stale.add_argument("--root", type=Path, default=Path.cwd(), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            history.check(args.root.resolve(), base_ref=args.base_ref)
            return 0 if _diagnostics(args.root.resolve(), args.as_of, args.base_ref, args.strict) else 1
        if args.command == "history":
            if args.history_command == "record":
                if not _diagnostics(args.root.resolve(), date.today(), None):
                    return 1
                print("Recorded knowledge snapshot {}.".format(history.record(args.root.resolve(), args.reason)))
            else:
                history.check(args.root.resolve(), base_ref=args.base_ref, require=args.require)
                print("Knowledge snapshot history is consistent.")
            return 0
        if args.command == "add":
            from .add import add_record
            issues = add_record(args.root.resolve(), args.kind, args.field)
            for issue in issues:
                print(str(issue))
            print("Added {} record.".format(args.kind))
            return 0
        if args.command == "check-links":
            from .linkcheck import check_links
            results = check_links(args.root.resolve(), timeout=args.timeout)
            for result in results:
                print("{} | {} | {} | {} | {}".format(result.status.upper(), result.evidence_id, result.field, result.url, result.detail))
            print("Checked {} links; {} broken, {} unknown.".format(len(results), sum(r.status == "broken" for r in results), sum(r.status == "unknown" for r in results)))
            return int(any(r.status == "broken" for r in results))
        if args.command == "stale":
            from .stale import stale_report
            issues = validation.validate(args.root.resolve(), as_of=args.as_of)
            errors = [issue for issue in issues if issue.severity == "error"]
            for issue in errors:
                print(str(issue), file=sys.stderr)
            if errors:
                return 1
            records = stale_report(validation.load_tables(args.root.resolve()), as_of=args.as_of, days=args.days)
            for record in records:
                print("{} | {} | {} | {} | {}".format(record["entity_id"], record["current_status"], record["last_verified"] or "Unknown", record["reason"], record["age_days"] if record["age_days"] is not None else "Unknown"))
            if not records:
                print("No organizations need review.")
            return 0
        return _build(args)
    except (OSError, ValueError, csv.Error) as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
