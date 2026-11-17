import csv
import random
from pathlib import Path

from awepep_co.resolve import resolve
from awepep_co.render import render

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    tables = {}
    for path in (ROOT / "tests/fixtures").glob("*.csv"):
        with path.open(encoding="utf-8", newline="") as stream:
            tables[path.stem] = list(csv.DictReader(stream))
    return tables


def test_status_evidence_and_supersession():
    tables = fixture()
    result = {r["entity_id"]: r for r in resolve(tables, "2026-11-17")}
    for eid in ("anew-labs", "bytedance-ai4s-team", "astrazeneca-molecular-ai", "syneron-bio"):
        assert result[eid]["current_status"] == "active"
    assert result["anew-labs"]["status_since"] == "2021"
    assert result["astrazeneca-molecular-ai"]["status_since"] == ""
    assert result["bytedance-ai4s-team"]["pending_flags"] == ["bytedance-ai4s-team~2026-06-10~merged_into"]
    assert not result["anew-labs"]["pending_flags"]
    assert result["anew-labs"]["superseded"] == ["anew-labs~2026-06-10~spin_off_reported"]
    assert result["syneron-bio"]["pending_flags"] == ["syneron-bio~2022-04~founded"]
    assert result["bytedance"]["successors"] == ["anew-labs"]


def test_render_is_stable_and_preserves_manual_readme():
    tables = fixture()
    fixed = "2026-11-17"
    readme = "# Manual\n\n<!-- BEGIN:INDEX -->\nold\n<!-- END:INDEX -->\n\nManual footer\n"
    output = render(tables, resolve(tables, fixed), fixed, readme, ROOT)
    shuffled = {key: list(value) for key, value in tables.items()}
    for rows in shuffled.values():
        random.Random(7).shuffle(rows)
    second = render(shuffled, resolve(shuffled, fixed), fixed, readme, ROOT)
    assert output == second
    assert output["README.md"].startswith(b"# Manual\n")
    assert output["README.md"].endswith(b"\n\nManual footer\n")
    assert "cards/bytedance/README.md" not in output
    assert "cards/astrazeneca/README.md" not in output
    assert "Reported, unconfirmed" in output["cards/bytedance-ai4s-team/README.md"].decode()
    assert "Not assessed" in output["cards/astrazeneca-molecular-ai/README.md"].decode()
    assert "parent-level relationships" in output["cards/astrazeneca-molecular-ai/README.md"].decode()
    assert "Superseded" in output["cards/anew-labs/README.md"].decode()
    assert "pending review" in output["index/by-loop-level.md"].decode()
    assert "L3" not in output["README.md"].decode()
    assert b"-.->" in output["index/lineage.md"]
    assert b"-->" in output["index/lineage.md"]
    assert b"2026-09-16" in output["index/changes.md"]
    assert output["build/peploop.sqlite"].startswith(b"SQLite format 3")


def test_state_transitions_dates_and_stale_boundary():
    entity = {"entity_id": "example", "name": "Example", "inclusion": "full"}
    ev = {"evidence_id": "source", "accessed": "2025-11-17"}
    def event(day, event_type, confidence="confirmed"):
        return {"event_id": f"example~{day}~{event_type}", "entity_id": "example", "date": day,
                "event_type": event_type, "confidence": confidence, "evidence_ids": "source"}
    tables = {"entities": [entity], "evidence": [ev], "events": [event("2025-01", "first_public"), event("2025-12", "ceased", "reported"), event("2026-12", "ceased")]}
    before = resolve(tables, "2026-11-17")[0]
    assert before["current_status"] == "active"
    assert before["status_since"] == "2025-01"
    assert len(before["pending_flags"]) == 1
    assert not before["needs_review"]
    stale = resolve(tables, "2026-11-18")[0]
    assert stale["needs_review"]
    assert resolve(tables, "2027-01-01")[0]["current_status"] == "closed"


def test_fixture_renders_competing_maintainers_and_parent_scope():
    tables = fixture()
    outputs = render(tables, resolve(tables, "2026-11-17"), "2026-11-17",
                     "# Fixture\n<!-- BEGIN:INDEX -->\n<!-- END:INDEX -->\n", ROOT)
    asset_page = outputs["index/assets.md"].decode()
    protenix = asset_page.split("## [Protenix]", 1)[1].split("\n## ", 1)[0]
    assert "ByteDance AI4S team" in protenix and "confirmed" in protenix
    assert "Anew Labs" in protenix and "Reported, unconfirmed" in protenix
    card = outputs["cards/bytedance-ai4s-team/README.md"].decode()
    assert "maintainer — Anew Labs (Reported, unconfirmed" in card
    assert "maintainer — ByteDance AI4S team (confirmed" in card
    team_card = outputs["cards/astrazeneca-molecular-ai/README.md"].decode()
    before_parent, remainder = team_card.split("<summary>Parent organization relationships</summary>", 1)
    parent_section, after_parent = remainder.split("</details>", 1)
    assert "do not imply participation by this team" in parent_section
    assert "AstraZeneca gets access to Synova" in parent_section
    assert "AstraZeneca gets access to Synova" not in before_parent + after_parent
    assert "AstraZeneca gets access to Synova" in outputs["cards/syneron-bio/README.md"].decode()


def test_related_events_remain_attributed_and_mark_original_supersession():
    tables = fixture()
    for row in tables["entities"]:
        if row["entity_id"] in {"astrazeneca", "bytedance"}:
            row["inclusion"] = "full"
    outputs = render(tables, resolve(tables, "2026-11-17"), "2026-11-17",
                     "# Fixture\n<!-- BEGIN:INDEX -->\n<!-- END:INDEX -->\n", ROOT)
    group = outputs["cards/astrazeneca/README.md"].decode()
    timeline = group.split("## Timeline", 1)[1].split("## Related papers", 1)[0]
    assert "Related record (subject: Syneron Bio) · Confirmed: AstraZeneca gets access to Synova" in timeline
    assert "Value is the upfront and near-term part only." in timeline
    assert "[prnewswire-20250321-syneron-astrazeneca]" in timeline
    owner = outputs["cards/syneron-bio/README.md"].decode()
    owner_timeline = owner.split("## Timeline", 1)[1].split("## Related papers", 1)[0]
    assert "Related record (subject: Syneron Bio)" not in owner_timeline
    team = outputs["cards/astrazeneca-molecular-ai/README.md"].decode()
    team_timeline = team.split("## Timeline", 1)[1].split("<summary>Parent organization relationships</summary>", 1)[0]
    assert "AstraZeneca gets access to Synova" not in team_timeline
    bytedance = outputs["cards/bytedance/README.md"].decode()
    line = next(line for line in bytedance.splitlines() if "First public report that ByteDance" in line)
    assert "Related record (subject: Anew Labs)" in line and "Superseded." in line


def test_fixture_contains_no_prohibited_commercial_content():
    import re
    tables = fixture()
    outputs = render(tables, resolve(tables, "2026-11-17"), "2026-11-17",
                     "# Fixture\n<!-- BEGIN:INDEX -->\n<!-- END:INDEX -->\n", ROOT)
    for path, content in outputs.items():
        if path.endswith(".md"):
            assert not re.search(r"\b(?:buy|discount|dose)\b", content.decode(), re.I), path


def test_fixture_cli_build_check_and_drift_detection(tmp_path, capsys):
    import shutil
    from awepep_co.cli import main
    from awepep_co.validation import validate

    shutil.copytree(ROOT / "tests/fixtures", tmp_path / "data")
    shutil.copytree(ROOT / "vocab", tmp_path / "vocab")
    shutil.copytree(ROOT / "templates", tmp_path / "templates")
    (tmp_path / "README.md").write_text("# Fixture\n\n<!-- BEGIN:INDEX -->\n<!-- END:INDEX -->\n", encoding="utf-8")
    options = ["--root", str(tmp_path), "--as-of", "2026-11-17"]
    assert main(["build", *options]) == 0
    assert main(["build", *options, "--check"]) == 0
    # A source change should produce a non-zero check without changing generated files.
    source = tmp_path / "data/events.csv"
    with source.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        events = list(reader)
    events[0]["summary"] = "Buy this product for a discount dose."
    with source.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(events)
    assert "W07" in {issue.code for issue in validate(tmp_path, as_of="2026-11-17")}
    assert main(["build", *options, "--check"]) == 1
    assert "Generated file differs" in capsys.readouterr().err
