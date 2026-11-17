"""Scope classifications stay distinct and are evidence-linked."""
import csv
import io
import json
import shutil
from pathlib import Path

from awepep_co.cli import main
from awepep_co.render import render
from awepep_co.resolve import resolve
from awepep_co.validation import HEADERS, load_tables, validate

ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-11-17"


def test_scope_sections_exports_and_unassessed_legacy():
    tables = load_tables(ROOT)
    tables["tags"] = [row for row in tables["tags"] if row["facet"] != "directory_scope"]
    tables["tags"].extend([
        {"entity_id": "ailsynbio", "facet": "directory_scope", "value": "ai_peptide", "evidence_ids": "hkex-20261113-hansoh-ailsynbio"},
        {"entity_id": "peptway", "facet": "directory_scope", "value": "peptide_landscape", "evidence_ids": "peptway-about"},
    ])
    out = render(tables, resolve(tables, AS_OF), AS_OF, (ROOT / "README.md").read_text(), ROOT)
    home = out["README.md"].decode()
    ai, rest = home.split("### AI–peptide work", 1)[1].split("### Peptide landscape · AI link unverified", 1)
    landscape, pending = rest.split("### Scope pending review", 1)
    assert "cards/ailsynbio/README.md" in ai and "cards/ailsynbio/README.md" not in landscape
    assert "cards/peptway/README.md" in landscape and "cards/peptway/README.md" not in ai
    assert "cards/anew-labs/README.md" in pending
    assert "AI link unverified" in out["cards/peptway/README.md"].decode()
    assert "[peptway-about](https://www.peptway.com/about.html)" in out["cards/peptway/README.md"].decode()
    assert "Scope pending review" in out["cards/anew-labs/README.md"].decode()
    assert "AI–peptide work" in out["index/by-scope.md"].decode()
    scopes = json.loads(out["index/scopes.json"])
    assert scopes == list(csv.DictReader(io.StringIO(out["index/scopes.csv"].decode())))
    assert next(row for row in scopes if row["entity_id"] == "anew-labs")["directory_scope"] == "unassessed"
    assert next(row for row in scopes if row["entity_id"] == "peptway")["evidence_ids"] == "peptway-about"
    assert "directory_scope" not in json.loads(out["index/index.json"])[0]


def _write(root, table, rows):
    with (root / "data" / (table + ".csv")).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADERS[table], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_scope_validation_enforces_one_evidence_backed_category(tmp_path):
    shutil.copytree(ROOT / "data", tmp_path / "data")
    shutil.copytree(ROOT / "vocab", tmp_path / "vocab")
    tables = load_tables(tmp_path)
    entity = next(row for row in tables["entities"] if row["entity_id"] == "peptway")
    entity["entity_type"] = "pharma_company"
    _write(tmp_path, "entities", tables["entities"])
    tables["tags"] = [row for row in tables["tags"] if row["entity_id"] != "peptway" or row["facet"] != "directory_scope"]
    _write(tmp_path, "tags", tables["tags"])
    assert any(issue.code == "E10" and "directory scope" in issue.message for issue in validate(tmp_path, as_of=AS_OF))
    scope = {"entity_id": "peptway", "facet": "directory_scope", "value": "peptide_landscape", "evidence_ids": ""}
    tables["tags"].append(scope)
    _write(tmp_path, "tags", tables["tags"])
    assert any(issue.code == "E04" for issue in validate(tmp_path, as_of=AS_OF))
    scope["evidence_ids"] = "peptway-about"
    _write(tmp_path, "tags", tables["tags"])
    assert not any(issue.severity == "error" for issue in validate(tmp_path, as_of=AS_OF))
    tables["tags"].append({**scope, "value": "ai_peptide"})
    _write(tmp_path, "tags", tables["tags"])
    assert any(issue.code == "E12" and "multiple directory scope" in issue.message for issue in validate(tmp_path, as_of=AS_OF))


def test_original_v031_snapshot_stays_buildable_with_unassessed_legacy_scope(tmp_path):
    snapshot = "2026-11-17-0001"
    shutil.copytree(ROOT / "history/snapshots" / snapshot, tmp_path / "history/snapshots" / snapshot)
    shutil.copytree(ROOT / "templates", tmp_path / "templates")
    output = tmp_path / "build/legacy"
    options = ["build", "--root", str(tmp_path), "--as-of", AS_OF, "--output-dir", str(output)]
    assert main(options) == 0
    assert main(options + ["--check"]) == 0
    with (output / "index/scopes.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 6
    assert {row["directory_scope"] for row in rows} == {"unassessed"}
    assert all(not row["evidence_ids"] for row in rows)
