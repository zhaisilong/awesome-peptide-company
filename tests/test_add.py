import csv
import shutil
from pathlib import Path

import pytest

from awepep_co.add import add_record
from awepep_co.validation import PRIMARY_KEYS

ROOT = Path(__file__).resolve().parents[1]


def project(tmp_path):
    for name in ("data", "vocab"):
        shutil.copytree(ROOT / name, tmp_path / name)
    return tmp_path


def records(root, table):
    with (root / "data" / (table + ".csv")).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def snapshot(root):
    return {p.name: p.read_bytes() for p in (root / "data").glob("*.csv")}


@pytest.mark.parametrize("kind,table,fields,key", [
    ("entity", "entities", ["entity_id=example-org", "name=Example 中文", "entity_type=ai_native_biotech", "inclusion=full", "peptide_relevance=core"], "entity_id"),
    ("event", "events", ["event_id=syneron-bio~2026-02~first_public", "entity_id=syneron-bio", "date=2026-02", "date_precision=month", "event_type=first_public", "confidence=confirmed", "evidence_ids=prnewswire-20250321-syneron-astrazeneca", "summary=A quoted, concise statement"], "event_id"),
    ("evidence", "evidence", ["evidence_id=example-source", "url=https://example.org/page?x=1&y=2", "title=A source, with comma", "publisher=Example", "source_type=official", "tier=A", "origin_key=example-source"], "evidence_id"),
    ("asset", "assets", ["asset_id=example-asset", "name=Example asset", "asset_type=software", "description=An example, with comma"], "asset_id"),
])
def test_adds_record_and_sorts_preserving_other_tables(tmp_path, kind, table, fields, key):
    root = project(tmp_path)
    before = snapshot(root)
    source_path = root / "data" / (table + ".csv")
    source_path.chmod(0o640)
    warnings = add_record(root, kind, fields)
    rows = records(root, table)
    expected = fields[0].split("=", 1)[1]
    assert expected in [item[key] for item in rows]
    keys = [tuple(row[column] for column in PRIMARY_KEYS[table]) for row in rows]
    assert keys == sorted(keys)
    assert source_path.stat().st_mode & 0o777 == 0o640
    assert b'\r\n' not in source_path.read_bytes()
    assert all(p.read_bytes() == before[p.name] for p in (root / "data").glob("*.csv") if p.name != source_path.name)
    assert all(w.severity == "warning" for w in warnings)
    if kind == "evidence":
        saved = next(item for item in rows if item[key] == expected)
        assert saved["url"] == "https://example.org/page?x=1&y=2"
        assert saved["title"] == "A source, with comma"
    if kind == "entity":
        assert next(item for item in rows if item[key] == expected)["name"] == "Example 中文"


@pytest.mark.parametrize("kind,fields", [
    ("entity", ["entity_id=syneron-bio", "name=Duplicate", "entity_type=ai_native_biotech", "inclusion=full", "peptide_relevance=core"]),
    ("entity", ["entity_id=new", "name=New", "entity_type=ai_native_biotech", "inclusion=full", "peptide_relevance=adjacent"]),
    ("entity", ["entity_id=new", "name=New", "entity_type=unknown", "inclusion=full", "peptide_relevance=core"]),
    ("event", ["event_id=e", "entity_id=missing", "date=2026", "date_precision=year", "event_type=founded", "confidence=rumor", "evidence_ids=liepin-syneron-profile"]),
    ("event", ["event_id=e", "entity_id=syneron-bio", "date=2026", "date_precision=year", "event_type=founded", "confidence=rumor"]),
    ("asset", ["asset_id=x", "name=X", "asset_type=software", "surprise=value"]),
    ("asset", ["asset_id=x", "name=X", "asset_type=software", "name=duplicate"]),
    ("asset", ["asset_id=x", "name=X", "asset_type=software", "badfield"]),
    ("unknown", ["id=x"]),
])
def test_invalid_add_does_not_change_any_csv(tmp_path, kind, fields):
    root = project(tmp_path)
    before = snapshot(root)
    with pytest.raises(ValueError):
        add_record(root, kind, fields)
    assert snapshot(root) == before


def test_missing_required_asset_and_evidence_fields_fail(tmp_path):
    root = project(tmp_path)
    before = snapshot(root)
    for kind, fields in [("asset", ["asset_id=a", "asset_type=model"]), ("evidence", ["evidence_id=e", "source_type=repo", "tier=A", "origin_key=e"])]:
        with pytest.raises(ValueError, match="missing required fields"):
            add_record(root, kind, fields)
    assert snapshot(root) == before


def test_write_failure_preserves_source_and_removes_temporary(tmp_path, monkeypatch):
    root = project(tmp_path)
    before = snapshot(root)
    def fail(*args):
        raise OSError("replace failed")
    monkeypatch.setattr("awepep_co.add.os.replace", fail)
    with pytest.raises(OSError, match="replace failed"):
        add_record(root, "asset", ["asset_id=x", "name=X", "asset_type=software"])
    assert snapshot(root) == before
    assert not list((root / "data").glob(".awepep-co-add-*"))


def test_concurrent_referenced_data_change_aborts_without_overwrite(tmp_path, monkeypatch):
    from importlib import import_module

    root = project(tmp_path)
    target = root / "data/assets.csv"
    evidence = root / "data/evidence.csv"
    target_before = target.read_bytes()
    evidence_before = evidence.read_bytes()
    module = import_module("awepep_co.add")
    real_validate = module.validate

    def validate_with_concurrent_change(path, *args, **kwargs):
        result = real_validate(path, *args, **kwargs)
        if Path(path) != root:
            evidence.write_bytes(evidence_before + b"\n")
        return result

    monkeypatch.setattr(module, "validate", validate_with_concurrent_change)
    with pytest.raises(ValueError, match="source data changed during validation"):
        add_record(root, "asset", ["asset_id=x", "name=X", "asset_type=software"])
    assert target.read_bytes() == target_before
    assert evidence.read_bytes() == evidence_before + b"\n"
    assert not list((root / "data").glob(".awepep-co-add-*"))


def test_cli_add_success_and_invalid_input(tmp_path, capsys):
    from awepep_co.cli import main

    root = project(tmp_path)
    args = ["add", "asset", "--root", str(root), "--field", "asset_id=cli-test", "--field", "name=CLI example", "--field", "asset_type=software"]
    assert main(args) == 0
    assert "Added asset record." in capsys.readouterr().out
    saved = (root / "data/assets.csv").read_bytes()
    assert main(args) == 1
    assert "duplicate primary key" in capsys.readouterr().err
    assert (root / "data/assets.csv").read_bytes() == saved
