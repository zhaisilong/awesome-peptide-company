"""Behavioral checks for the public Markdown presentation and exports."""
import csv
import html
import io
import json
import posixpath
import re
import sqlite3
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from awepep_co.resolve import resolve
from awepep_co.render import render
from awepep_co.validation import load_tables

ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-11-17"


def presentation(tables=None):
    tables = tables if tables is not None else load_tables(ROOT)
    source_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    return render(tables, resolve(tables, AS_OF), AS_OF, source_readme, ROOT)


def test_homepage_lists_every_full_entity_in_stable_order():
    tables = load_tables(ROOT)
    output = presentation(tables)
    home = output["README.md"].decode()
    index = home.split("<!-- BEGIN:INDEX -->", 1)[1].split("<!-- END:INDEX -->", 1)[0]
    full = sorted((row for row in tables["entities"] if row["inclusion"] == "full"),
                  key=lambda row: row["entity_id"])
    positions = []
    for row in full:
        link = f"cards/{row['entity_id']}/README.md"
        assert index.count(link) == 1
        assert row["name"] in index and row["one_liner"] in index
        positions.append(index.index(link))
    assert positions == sorted(positions)
    assert "| Name | Summary |" not in index
    assert "ai_native_biotech" not in index
    assert "AI-native biotech" in index
    for row in tables["entities"]:
        if row["inclusion"] == "stub":
            assert f"cards/{row['entity_id']}/README.md" not in index


def test_cards_and_indexes_show_readable_labels_and_navigation():
    output = presentation()
    for eid in ("anew-labs", "astrazeneca-molecular-ai", "bytedance-ai4s-team", "syneron-bio"):
        card = output[f"cards/{eid}/README.md"].decode()
        assert "../../README.md" in card
        assert "../../index/by-type.md" in card
        assert "../../index/by-status.md" in card
        assert "../../index/by-modality.md" in card
        assert "ai_native_biotech" not in card
        assert "## Sources" in card
    assert "## AI-native biotech" in output["index/by-type.md"].decode()
    assert "## Active" in output["index/by-status.md"].decode()
    assert "## Macrocyclic peptide" in output["index/by-modality.md"].decode()


def test_relationship_graph_distinguishes_group_context_and_reports_dates():
    output = presentation()
    lineage = output["index/lineage.md"].decode()
    assert 'Partnership (group context)' in lineage
    assert 'License deal (group context)' in lineage
    assert '"Partnership"' in lineage  # Syneron's direct group relationship remains direct.
    assert 'subsidiary' in lineage.lower()
    changes = output["index/changes.md"].decode()
    peptway = next(line for line in changes.splitlines() if "Peptway" in line)
    assert "Publication date" in peptway
    assert "completion date" in peptway


def test_unknown_labels_have_readable_fallback():
    tables = load_tables(ROOT)
    entity = next(row for row in tables["entities"] if row["entity_id"] == "anew-labs")
    entity["entity_type"] = "novel_institution_type"
    entity["peptide_relevance"] = "unlisted_relevance"
    output = presentation(tables)
    home = output["README.md"].decode()
    card = output["cards/anew-labs/README.md"].decode()
    assert "Novel institution type" in home and "Novel institution type" in card
    assert "Unlisted relevance" in home and "Unlisted relevance" in card


def test_all_local_markdown_links_resolve():
    output = presentation()
    for source, content in output.items():
        if not source.endswith(".md"):
            continue
        text = content.decode("utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", text):
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            relative = posixpath.normpath(posixpath.join(posixpath.dirname(source), unquote(parsed.path)))
            assert relative in output or (ROOT / relative).exists(), (source, target)


def test_data_exports_keep_machine_readable_values(tmp_path):
    output = presentation()
    csv_rows = list(csv.DictReader(io.StringIO(output["index/index.csv"].decode())))
    json_rows = json.loads(output["index/index.json"])
    expected_columns = ["entity_id", "name", "one_liner", "entity_type", "current_status", "loop_level", "peptide_relevance", "country", "last_verified"]
    assert list(csv_rows[0]) == expected_columns
    assert csv_rows == json_rows
    anew = next(row for row in csv_rows if row["entity_id"] == "anew-labs")
    assert anew["entity_type"] == "ai_native_biotech"
    assert anew["current_status"] == "active"
    assert anew["peptide_relevance"] == "infrastructure"
    sqlite_path = tmp_path / "export.sqlite"
    sqlite_path.write_bytes(output["build/peploop.sqlite"])
    with sqlite3.connect(sqlite_path) as database:
        record = database.execute("SELECT entity_type, current_status, peptide_relevance FROM entities_resolved WHERE entity_id = ?", ("anew-labs",)).fetchone()
    assert record == ("ai_native_biotech", "active", "infrastructure")


def test_homepage_badges_navigation_and_star_history():
    home = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "https://awesome.re/badge.svg" in home
    assert "github/stars/zhaisilong/awesome-peptide-company" in home
    assert "GPL-3.0" in home
    for page in ("by-type.md", "by-status.md", "by-loop-level.md", "by-modality.md", "by-region.md", "assets.md", "lineage.md", "changes.md"):
        assert f"index/{page}" in home
    star_history = "https://api.star-history.com/svg?repos=zhaisilong/awesome-peptide-company&type=Date"
    decoded_home = html.unescape(home)
    assert star_history in decoded_home
    assert f"{star_history}&theme=dark" in decoded_home
    assert 'prefers-color-scheme: dark' in home
    assert "<img" in home


def test_cover_has_file_accessible_alt_and_attribution():
    class ImageParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.images = []

        def handle_starttag(self, tag, attrs):
            if tag == "img":
                self.images.append(dict(attrs))

    home = (ROOT / "README.md").read_text(encoding="utf-8")
    parser = ImageParser()
    parser.feed(home)
    cover = next(image for image in parser.images if image.get("src") == "assets/cover.png")
    assert cover.get("alt", "").strip()
    assert (ROOT / cover["src"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    credit = (ROOT / "assets/README.md").read_text(encoding="utf-8")
    assert "assets/README.md" in home
    assert "https://commons.wikimedia.org/wiki/File:Human_calcitonin_recptor-Gs_complex_PDB_7TYO.png" in credit
    assert "https://creativecommons.org/publicdomain/zero/1.0/" in credit
    assert "CC0" in home and "CC0" in credit
