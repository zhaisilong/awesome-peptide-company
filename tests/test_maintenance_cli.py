"""CLI integration tests for v0.2 maintenance commands."""

import csv
import shutil
from pathlib import Path

import pytest

from awepep_co.cli import main

ROOT = Path(__file__).resolve().parents[1]


def project(tmp_path):
    for name in ("data", "vocab"):
        shutil.copytree(ROOT / name, tmp_path / name)
    return tmp_path


def test_add_command_success_and_duplicate_failure_are_atomic(tmp_path, capsys):
    root = project(tmp_path)
    args = ["add", "asset", "--root", str(root), "--field", "asset_id=sample-asset", "--field", "name=Sample, Inc.", "--field", "asset_type=software"]
    assert main(args) == 0
    output = capsys.readouterr()
    assert "Added asset record." in output.out
    path = root / "data/assets.csv"
    with path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert next(row for row in rows if row["asset_id"] == "sample-asset")["name"] == "Sample, Inc."
    before = path.read_bytes()
    assert main(args) == 1
    assert "duplicate primary key" in capsys.readouterr().err
    assert path.read_bytes() == before


def test_add_invalid_arguments_return_error_without_writing(tmp_path, capsys):
    root = project(tmp_path)
    path = root / "data/assets.csv"
    before = path.read_bytes()
    assert main(["add", "asset", "--root", str(root), "--field", "bad"]) == 1
    assert "key=value" in capsys.readouterr().err
    assert path.read_bytes() == before
    with pytest.raises(SystemExit) as caught:
        main(["add", "unsupported", "--root", str(root), "--field", "x=y"])
    assert caught.value.code == 2


def test_stale_cli_uses_threshold_as_of_and_readonly_data(tmp_path, capsys):
    root = project(tmp_path)
    before = {p.name: p.read_bytes() for p in (root / "data").glob("*.csv")}
    assert main(["stale", "--root", str(root), "--as-of", "2026-11-17", "--days", "365"]) == 0
    assert "No organizations need review." in capsys.readouterr().out
    assert main(["stale", "--root", str(root), "--as-of", "2027-11-18", "--days", "365"]) == 0
    output = capsys.readouterr().out
    assert "syneron-bio | active | 2026-11-17 | overdue | 366" in output
    assert "astrazeneca |" not in output
    assert {p.name: p.read_bytes() for p in (root / "data").glob("*.csv")} == before
    with pytest.raises(SystemExit) as caught:
        main(["stale", "--root", str(root), "--days", "-1"])
    assert caught.value.code == 2


def test_check_links_cli_statuses_exit_codes_and_readonly(tmp_path, capsys, monkeypatch):
    root = project(tmp_path)
    before = (root / "data/evidence.csv").read_bytes()
    requested = []
    def fake_check(url, timeout):
        requested.append((url, timeout))
        if "liepin" in url:
            raise AssertionError("unexpected link")
        return ("ok", "HTTP 200")
    monkeypatch.setattr("awepep_co.linkcheck.check_url", fake_check)
    assert main(["check-links", "--root", str(root), "--timeout", "3"]) == 0
    output = capsys.readouterr().out
    assert "OK |" in output and "0 broken, 0 unknown." in output
    assert requested and all(timeout == 3 for _, timeout in requested)
    assert (root / "data/evidence.csv").read_bytes() == before
    first_url = requested[0][0]
    def inaccessible(url, timeout):
        return ("broken", "HTTP 404") if url == first_url else ("unknown", "HTTP 403")
    monkeypatch.setattr("awepep_co.linkcheck.check_url", inaccessible)
    assert main(["check-links", "--root", str(root)]) == 1
    output = capsys.readouterr().out
    assert "BROKEN |" in output and "UNKNOWN |" in output
    assert (root / "data/evidence.csv").read_bytes() == before
    monkeypatch.setattr("awepep_co.linkcheck.check_url", lambda url, timeout: ("unknown", "HTTP 429"))
    assert main(["check-links", "--root", str(root)]) == 0
    assert "UNKNOWN |" in capsys.readouterr().out
    with pytest.raises(SystemExit) as caught:
        main(["check-links", "--root", str(root), "--timeout", "0"])
    assert caught.value.code == 2
