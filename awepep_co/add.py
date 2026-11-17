"""Safely append one source record after validating a complete candidate dataset."""

import csv
import io
import os
import shutil
import stat
import tempfile
from pathlib import Path

from .validation import HEADERS, PRIMARY_KEYS, validate

TABLES = {"entity": "entities", "event": "events", "evidence": "evidence", "asset": "assets"}
# These fields are the minimum needed to identify and interpret each new record;
# the common validator enforces controlled vocabulary, references, and formats.
REQUIRED = {
    "entity": ("entity_id", "name", "entity_type", "inclusion"),
    "event": ("event_id", "entity_id", "date", "date_precision", "event_type", "confidence", "evidence_ids"),
    "evidence": ("evidence_id", "url", "title", "source_type", "tier", "origin_key"),
    "asset": ("asset_id", "name", "asset_type"),
}


def _parse_fields(kind, fields):
    table = TABLES[kind]
    result = {}
    for field in fields:
        if "=" not in field:
            raise ValueError("fields must use key=value: {!r}".format(field))
        key, value = field.split("=", 1)
        if key not in HEADERS[table]:
            raise ValueError("unknown field {!r} for {}".format(key, kind))
        if key in result:
            raise ValueError("field {!r} was supplied more than once".format(key))
        if "\x00" in value:
            raise ValueError("field {!r} contains a NUL character".format(key))
        result[key] = value
    missing = [name for name in REQUIRED[kind] if not result.get(name, "").strip()]
    if missing:
        raise ValueError("missing required fields for {}: {}".format(kind, ", ".join(missing)))
    if kind == "entity" and result.get("inclusion") == "full" and not result.get("peptide_relevance", "").strip():
        raise ValueError("full entities require peptide_relevance")
    return {column: result.get(column, "") for column in HEADERS[table]}


def _errors(issues):
    return [issue for issue in issues if issue.severity == "error"]


def _error_message(issues):
    return "validation failed:\n" + "\n".join(str(issue) for issue in issues)


def _source_snapshot(root):
    """Capture all data and vocabulary used to validate a candidate."""
    paths = [Path("data") / (name + ".csv") for name in HEADERS]
    paths.append(Path("vocab/terms.csv"))
    translation = Path("i18n/zh/strings.csv")
    if (root / translation).exists():
        paths.append(translation)
    return {path: (root / path).read_bytes() for path in paths}


def add_record(root, kind, fields):
    """Append a row to one CSV; validate a snapshot and atomically replace on success.

    ``fields`` is an iterable of ``key=value`` strings. Return validation warnings;
    raise ValueError for bad input, duplicates, or an invalid candidate dataset.
    The original files remain unchanged on validation or write errors.
    """
    if kind not in TABLES:
        raise ValueError("unknown record type: {!r}".format(kind))
    root = Path(root)
    row = _parse_fields(kind, fields)
    existing_issues = validate(root)
    if _errors(existing_issues):
        raise ValueError(_error_message(_errors(existing_issues)))
    table = TABLES[kind]
    path = root / "data" / (table + ".csv")
    snapshot = _source_snapshot(root)
    original = snapshot[Path("data") / path.name]
    with io.StringIO(original.decode("utf-8"), newline="") as source:
        reader = csv.DictReader(source, strict=True)
        if reader.fieldnames != HEADERS[table]:
            raise ValueError("invalid header in {}".format(path))
        rows = list(reader)
    key_columns = PRIMARY_KEYS[table]
    new_key = tuple(row[column] for column in key_columns)
    if any(tuple(item[column] for column in key_columns) == new_key for item in rows):
        raise ValueError("duplicate primary key for {}: {}".format(table, new_key))
    rows.append(row)
    rows.sort(key=lambda item: tuple(item[column] for column in key_columns))
    with tempfile.TemporaryDirectory(prefix="awepep-co-add-") as workdir:
        candidate = Path(workdir)
        shutil.copytree(root / "data", candidate / "data")
        shutil.copytree(root / "vocab", candidate / "vocab")
        if (root / "i18n").is_dir():
            shutil.copytree(root / "i18n", candidate / "i18n")
        if _source_snapshot(candidate) != snapshot:
            raise ValueError("source data changed while preparing validation; retry the operation")
        with (candidate / "data" / path.name).open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=HEADERS[table], lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        issues = validate(candidate)
        errors = _errors(issues)
        if errors:
            raise ValueError(_error_message(errors))
        candidate_bytes = (candidate / "data" / path.name).read_bytes()
    # The temporary file must live beside the destination for os.replace to be atomic.
    # Preserve the original file mode and refuse to overwrite concurrent edits.
    mode = stat.S_IMODE(path.stat().st_mode)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", prefix=".awepep-co-add-", dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            os.chmod(temporary, mode)
            output.write(candidate_bytes)
            output.flush()
            os.fsync(output.fileno())
        if _source_snapshot(root) != snapshot:
            raise ValueError("source data changed during validation; retry the operation")
        os.replace(str(temporary), str(path))
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return [issue for issue in issues if issue.severity == "warning"]
