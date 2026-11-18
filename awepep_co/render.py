"""Deterministic Liquid-based Markdown and data exports."""
import csv
import io
import json
import re
import sqlite3
import tempfile
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from liquid import Template

from .names import active_aliases, display_name, name_key
from .resolve import event_key, latest_date

BEGIN, END = "<!-- BEGIN:INDEX -->", "<!-- END:INDEX -->"
INDEX_NAV = "[← Home](../README.md) · [Names](by-name.md) · [Scope](by-scope.md) · [Types](by-type.md) · [Status](by-status.md) · [Modalities](by-modality.md)"
RESOLVED_COLUMNS = ["entity_id", "name", "entity_type", "inclusion", "parent_id", "peptide_relevance", "relevance_evidence_ids", "country", "hq_city", "website", "one_liner", "current_status", "status_since", "pending_flags", "last_verified", "needs_review", "successors", "predecessors"]
INDEX_COLUMNS = ["entity_id", "name", "one_liner", "entity_type", "current_status", "loop_level", "peptide_relevance", "country", "last_verified"]

# Presentation labels are separate from source vocabulary and data exports.
DISPLAY_LABELS = {
    "entity_type": {
        "ai_native_biotech": "AI-native biotech", "pharma_ai_team": "Pharmaceutical AI team", "pharma_company": "Pharmaceutical company",
        "bigtech_ai_team": "Technology company AI team", "peptide_therapeutics": "Peptide therapeutics",
        "platform_vendor": "Platform vendor", "cdmo": "CDMO", "parent_org": "Parent organization",
    },
    "status": {
        "active": "Active", "in_transition": "In transition", "inactive": "Inactive",
        "closed": "Closed", "acquired": "Acquired", "merged": "Merged", "unknown": "Not assessed",
    },
    "relevance": {"core": "Core", "adjacent": "Adjacent", "infrastructure": "Infrastructure"},
    "facet": {
        "modality": "Modality", "dry": "Computational methods", "wet": "Experimental capabilities",
        "therapeutic_area": "Therapeutic area", "stage_max": "Development stage", "directory_scope": "Directory scope",
    },
    "tag": {
        "macrocyclic_peptide": "Macrocyclic peptide", "linear_peptide": "Linear peptide",
        "stapled_peptide": "Stapled peptide", "bicyclic_peptide": "Bicyclic peptide",
        "peptide_drug_conjugate": "Peptide–drug conjugate", "incretin": "Incretin",
        "antimicrobial_peptide": "Antimicrobial peptide", "spps_inhouse": "In-house SPPS",
        "dna_encoded_library": "DNA-encoded library", "in_vivo": "In vivo",
        "foundation_model_inhouse": "In-house foundation model",
        "cmc": "CMC", "llm_agent": "LLM agent", "phase1": "Phase 1",
        "phase2": "Phase 2", "phase3": "Phase 3", "na": "Not applicable",
        "ai_peptide": "AI–peptide work", "peptide_landscape": "Peptide landscape · AI link unverified",
        "unassessed": "Scope pending review",
    },
    "review": {"proposed": "pending review", "reviewed": "reviewed"},
}


def _display(category, value):
    if not value:
        return "Not specified"
    return DISPLAY_LABELS.get(category, {}).get(value, str(value).replace("_", " ").capitalize())


def _list(value):
    return [x.strip() for x in value.split(';') if x.strip()]


def _cell(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def _csv(rows, fields):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ';'.join(row.get(k, [])) if isinstance(row.get(k), list)
                         else str(row.get(k, "")).lower() if isinstance(row.get(k), bool)
                         else row.get(k, "") for k in fields})
    return output.getvalue().encode("utf-8")


def _table(rows, headers, cols):
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    out.extend("| " + " | ".join(_cell(row.get(c, "")) for c in cols) + " |" for row in rows)
    return "\n".join(out) + "\n"


def _anchor_link(eid, entities, prefix="../cards", label=None):
    entity = entities.get(eid)
    if entity is None:
        return eid
    name = label or entity.get("name") or eid
    return f"[{name}]({prefix}/{eid}/README.md)" if entity.get("inclusion") == "full" else f"{name} (stub)"


def _sqlite(tables, resolved, root):
    # New database, fixed table and row ordering, no journal or timestamps.
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "export.sqlite"
        con = sqlite3.connect(path)
        try:
            for name in sorted(tables):
                rows = tables[name]
                source = Path(root) / "data" / (name + ".csv")
                if source.exists():
                    with source.open(encoding="utf-8", newline="") as stream:
                        fields = next(csv.reader(stream), [])
                else:
                    fields = sorted({k for row in rows for k in row})
                if not fields:
                    continue
                if not re.fullmatch(r"[a-z_]+", name) or not all(re.fullmatch(r"[a-z_]+", f) for f in fields):
                    raise ValueError("invalid table or column name")
                con.execute(f'CREATE TABLE "{name}" (' + ', '.join('"' + x + '" TEXT' for x in fields) + ')')
                ordered = sorted(rows, key=lambda row: tuple(row.get(field, "") for field in fields))
                con.executemany(f'INSERT INTO "{name}" VALUES (' + ','.join('?' for _ in fields) + ')',
                                [tuple(row.get(field, "") for field in fields) for row in ordered])
            con.execute('CREATE TABLE entities_resolved (' + ', '.join('"' + x + '" TEXT' for x in RESOLVED_COLUMNS) + ')')
            for row in resolved:
                values = [';'.join(row.get(k, [])) if isinstance(row.get(k), list) else str(row.get(k, "")).lower() if isinstance(row.get(k), bool) else row.get(k, "") for k in RESOLVED_COLUMNS]
                con.execute('INSERT INTO entities_resolved VALUES (' + ','.join('?' for _ in values) + ')', values)
            con.commit()
            con.execute("VACUUM")
        finally:
            con.close()
        return path.read_bytes()


def render(tables, resolved, as_of, readme, root, template_root=None):
    """Return relative paths mapped to bytes, leaving all writes to the caller."""
    root = Path(root)
    if isinstance(as_of, str):
        as_of = date.fromisoformat(as_of)
    entities = {row["entity_id"]: row for row in resolved}
    evidence = {row["evidence_id"]: row for row in tables.get("evidence", [])}
    asset_map = {row["asset_id"]: row for row in tables.get("assets", [])}
    full = sorted((e for e in resolved if e.get("inclusion") == "full"), key=lambda e: e["entity_id"])
    aliases_by_entity = active_aliases(tables.get("aliases", []), as_of)
    labels = {eid: display_name(entity, aliases_by_entity.get(eid, [])) for eid, entity in entities.items()}
    scope_tags = {r["entity_id"]: r for r in sorted(tables.get("tags", []), key=lambda r: (r.get("entity_id", ""), r.get("value", ""))) if r.get("facet") == "directory_scope"}
    scope_rows = [{"entity_id": e["entity_id"], "name": e.get("name", ""),
                   "directory_scope": scope_tags.get(e["entity_id"], {}).get("value", "unassessed"),
                   "evidence_ids": scope_tags.get(e["entity_id"], {}).get("evidence_ids", "")} for e in full]
    scopes = {r["entity_id"]: r["directory_scope"] for r in scope_rows}
    events = sorted([e for e in tables.get("events", []) if latest_date(e) <= as_of], key=event_key)
    loops = defaultdict(list)
    for row in tables.get("loop_assessments", []):
        if row.get("as_of", "") <= as_of.isoformat():
            loops[row["entity_id"]].append(row)
    latest_loop = {eid: max(rows, key=lambda r: r.get("as_of", "")) for eid, rows in loops.items()}
    reviewed = {eid: row.get("level", "") for eid, row in latest_loop.items() if row.get("review_status") == "reviewed"}
    rows = [{**e, "loop_level": reviewed.get(e["entity_id"], "Not assessed")} for e in full]
    out = {}
    out["build/entities_resolved.csv"] = _csv(resolved, RESOLVED_COLUMNS)
    out["index/index.csv"] = _csv(rows, INDEX_COLUMNS)
    out["index/index.json"] = (json.dumps([{k: row.get(k, "") for k in INDEX_COLUMNS} for row in rows], ensure_ascii=False, indent=2) + "\n").encode()
    scope_columns = ["entity_id", "name", "directory_scope", "evidence_ids"]
    out["index/scopes.csv"] = _csv(scope_rows, scope_columns)
    out["index/scopes.json"] = (json.dumps(scope_rows, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    out["build/peploop.sqlite"] = _sqlite(tables, resolved, root)
    indexlines = []
    for scope in ("ai_peptide", "peptide_landscape", "unassessed"):
        group = [row for row in rows if scopes[row["entity_id"]] == scope]
        if not group:
            continue
        indexlines.extend(["### " + _display("tag", scope), ""])
        for row in group:
            metadata = [
                _display("entity_type", row.get("entity_type")),
                _display("status", row.get("current_status")),
                _display("relevance", row.get("peptide_relevance")) + " relevance",
            ]
            if row.get("country"):
                metadata.append(row["country"])
            if row.get("pending_flags"):
                metadata.append("⚠ Report pending confirmation")
            eid = row["entity_id"]
            indexlines.append("- **" + _anchor_link(eid, entities, "cards", labels[eid]) + "**<br>")
            if row.get("one_liner"):
                indexlines.append("  " + row["one_liner"] + "<br>")
            indexlines.append("  " + " · ".join(metadata))
            indexlines.append("")
    indextext = "\n".join(indexlines).rstrip() + "\n" if indexlines else "No organizations recorded.\n"
    if readme.count(BEGIN) != 1 or readme.count(END) != 1 or readme.index(BEGIN) > readme.index(END):
        raise ValueError("README must contain one ordered BEGIN:INDEX and END:INDEX marker")
    readme = readme[:readme.index(BEGIN) + len(BEGIN)] + "\n\n" + indextext + "\n" + readme[readme.index(END):]
    out["README.md"] = readme.replace("\r\n", "\n").encode("utf-8")
    template = Template(((Path(template_root) if template_root else root) / "templates/card.liquid").read_text(encoding="utf-8"))
    for e in full:
        eid = e["entity_id"]
        own_events = [ev for ev in events if ev.get("entity_id") == eid]
        aliases = [row["alias"] for row in aliases_by_entity.get(eid, [])]
        loop = latest_loop.get(eid)
        banner = ""
        if e["pending_flags"] or e["current_status"] not in {"active", "unknown"}:
            flags = [ev for ev in own_events if ev.get("event_id") in e["pending_flags"]]
            banner = "> ⚠ Status: " + _display("status", e["current_status"]) + ". " + " ".join(("Rumor, unconfirmed: " if ev.get("confidence") == "rumor" else "Reported, unconfirmed: ") + ev.get("summary", "") for ev in flags) + "\n"
        elif e["current_status"] == "unknown":
            banner = "> Status not assessed: no confirmed status event has been recorded.\n"
        parent = entities.get(e.get("parent_id"), {})
        info = [("Headquarters", ", ".join(filter(None, [e.get("hq_city"), e.get("country")]))), ("Parent", parent.get("name", "")), ("Website", e.get("website", "")), ("Aliases", ", ".join(aliases)), ("Last verified", e.get("last_verified", ""))]
        overview = _table([{"key": key, "value": value or "—"} for key, value in info], ["Field", "Value"], ["key", "value"])
        tags = sorted((r.get("facet", ""), r.get("value", "")) for r in tables.get("tags", []) if r.get("entity_id") == eid)
        relevance_sources = ' '.join(f"[{i}]({evidence[i].get('url', '')})" for i in _list(e.get("relevance_evidence_ids", "")) if i in evidence)
        scope_refs = " ".join(f"[{i}]({evidence[i].get('url', '')})" for i in _list(scope_tags.get(eid, {}).get("evidence_ids", "")) if i in evidence)
        scope_line = "**Directory scope:** " + _display("tag", scopes[eid]) + (" " + scope_refs if scope_refs else "")
        relevance = scope_line + "\n\n**Relevance:** " + _display("relevance", e.get("peptide_relevance")) + "." + (" " + relevance_sources if relevance_sources else "") + "\n\n" + ("\n".join(f"- **{_display('facet', facet)}:** {_display('tag', value)}" for facet, value in tags if facet != "directory_scope") or "No other tags.")
        looptext = f"**{loop.get('level')} · {loop.get('evidence_level')} · {_display('review', loop.get('review_status'))}** ({loop.get('as_of')})\n\n{loop.get('rationale', '')}" if loop else "Not assessed."
        roles = [r for r in tables.get("asset_roles", []) if r.get("entity_id") == eid and r.get("start", "") <= as_of.isoformat()]
        # Show all competing claims for each asset, including claims by other entities.
        asset_ids = {r.get("asset_id") for r in roles}
        relevant_roles = sorted((r for r in tables.get("asset_roles", []) if r.get("asset_id") in asset_ids and r.get("start", "") <= as_of.isoformat()), key=lambda r: (r.get("asset_id", ""), r.get("entity_id", ""), r.get("role", ""), r.get("start", "")))
        asset_lines = []
        for role in relevant_roles:
            asset = asset_map.get(role.get("asset_id"), {})
            flag = "Reported, unconfirmed" if role.get("confidence") == "reported" else role.get("confidence", "")
            asset_name = asset.get("name", role.get("asset_id", ""))
            if asset.get("url"):
                asset_name = f"[{asset_name}]({asset['url']})"
            refs = " ".join(f"[{x}]({evidence[x].get('url', '')})" for x in _list(role.get("evidence_ids", "")) if x in evidence)
            asset_lines.append(f"- {asset_name}: {role.get('role', '')} — {entities.get(role.get('entity_id'), {}).get('name', role.get('entity_id'))} ({flag}; {role.get('start', '')}–{role.get('end') or 'present'}). {refs}".rstrip())
        timeline = []
        timeline_events = [ev for ev in events if ev.get("entity_id") == eid or ev.get("related_entity_id") == eid]
        for ev in reversed(timeline_events):
            label = {"reported": "Reported, unconfirmed", "rumor": "Rumor, unconfirmed", "confirmed": "Confirmed"}.get(ev.get("confidence"), ev.get("confidence", ""))
            subject_id = ev.get("entity_id", "")
            subject = entities.get(subject_id, {})
            related = f"Related record (subject: {subject.get('name') or subject_id}) · " if subject_id != eid else ""
            suffix = " Superseded." if ev.get("event_id") in subject.get("superseded", []) else ""
            note = f" — {ev['note']}" if ev.get("note") else ""
            ids = " ".join(f"[{x}]({evidence[x].get('url', '')})" for x in _list(ev.get("evidence_ids", "")) if x in evidence)
            timeline.append(f"- **{ev.get('date', '')}** · {related}{label}: {ev.get('summary', '')}{note}{suffix} {ids}".rstrip())
        parenttext = ""
        if e.get("entity_type") in {"pharma_ai_team", "bigtech_ai_team"} and parent:
            parent_events = [ev for ev in events if ev.get("event_type") in {"partnership", "license_deal", "ownership_disclosed", "funding_round"} and (ev.get("entity_id") == parent["entity_id"] or ev.get("related_entity_id") == parent["entity_id"])]
            parenttext = "<details>\n<summary>Parent organization relationships</summary>\n\nThese are parent-level relationships and do not imply participation by this team.\n\n" + ("\n".join(f"- {ev['date']}: {ev['summary']} ({ev['confidence']})" for ev in parent_events) or "No recorded relationships.") + "\n\n</details>\n\n"
        paper_rows = sorted((r for r in tables.get("paper_links", []) if (r.get("subject_kind") == "entity" and r.get("subject_id") == eid) or (r.get("subject_kind") == "asset" and r.get("subject_id") in asset_ids)), key=lambda r: (r.get("subject_id", ""), r.get("doi", "")))
        papers = []
        for p in paper_rows:
            link = f"https://doi.org/{p.get('doi', '')}"
            awe = f" · [awesome-peptide](https://github.com/zhaisilong/awesome-peptide#{{}})".format(p['awepep_id']) if p.get('awepep_id') else ''
            papers.append(f"- [{p.get('doi', '')}]({link}) ({p.get('relation', '')}){awe}")
        cited = set(e.get("evidence_ids", []))
        for ev in timeline_events:
            cited.update(_list(ev.get("evidence_ids", "")))
        for role in relevant_roles:
            cited.update(_list(role.get("evidence_ids", "")))
        sources = []
        for key in sorted(cited, key=lambda k: (evidence.get(k, {}).get("tier", "Z"), k)):
            if key not in evidence:
                continue
            src = evidence[key]
            archive = f" · [archive]({src['archive_url']})" if src.get("archive_url") else ""
            sources.append(f"- **{src.get('tier', '')}** [{src.get('title') or key}]({src.get('url', '')}) · {src.get('publisher', '')} · accessed {src.get('accessed', '')}{archive}")
        note_path = root / "notes" / (eid + ".md")
        notes = "## Curator notes\n\n*Editorial opinion.*\n\n" + note_path.read_text(encoding="utf-8").strip() if note_path.is_file() else ""
        badges = " · ".join(filter(None, [
            "**Type:** " + _display("entity_type", e.get("entity_type")),
            "**Status:** " + _display("status", e.get("current_status")),
            "**Relevance:** " + _display("relevance", e.get("peptide_relevance")),
            "**Loop:** " + (loop.get("level", "") + " · " + loop.get("evidence_level", "") + " · " + _display("review", loop.get("review_status")) if loop else "Not assessed"),
            ("**Region:** " + e["country"]) if e.get("country") else "",
        ]))
        content = template.render(name=labels[eid], one_liner=e.get("one_liner", ""), badges=badges, banner=banner, overview=overview, relevance=relevance, loop=looptext, assets="\n".join(asset_lines) or "No assets recorded.", timeline="\n".join(timeline) or "No events recorded.", parent_relations=parenttext, papers="\n".join(papers) or "No papers linked.", sources="\n".join(sources) or "No sources recorded.", notes=notes)
        out[f"cards/{eid}/README.md"] = (content.rstrip() + "\n").encode("utf-8")
    def grouped(filename, title, group_rows, category=None):
        lines = [f"# {title}", "", INDEX_NAV, ""]
        for key in sorted(group_rows):
            label = _display(category, key) if category else (key or 'Not specified')
            lines.extend([f"## {label}", ""])
            lines.extend(f"- {_anchor_link(eid, entities, label=labels[eid])}" for eid in sorted(group_rows[key]))
            lines.append("")
        out["index/" + filename] = ("\n".join(lines).rstrip() + "\n").encode("utf-8")

    name_rows = []
    for entity in sorted(full, key=lambda row: (name_key(row.get("name") or ""), row["entity_id"])):
        eid = entity["entity_id"]
        aliases = [row["alias"] for row in aliases_by_entity.get(eid, []) if row.get("kind") != "preferred_zh"]
        name_rows.append({"name": _anchor_link(eid, entities, label=labels[eid]), "aliases": ", ".join(aliases), "id": f"`{eid}`"})
    name_table = _table(name_rows, ["Organization", "Other names", "Entity ID"], ["name", "aliases", "id"])
    out["index/by-name.md"] = (f"# By name / 按名称\n\n{INDEX_NAV}\n\n" + name_table).encode("utf-8")

    groups = defaultdict(set)
    for e in full:
        groups[scopes[e["entity_id"]]].add(e["entity_id"])
    grouped("by-scope.md", "By directory scope", groups, "tag")

    for filename, title, field in [("by-type.md", "By type", "entity_type"), ("by-status.md", "By status", "current_status"), ("by-region.md", "By region", "country")]:
        groups = defaultdict(set)
        for e in full:
            groups[e.get(field, "")].add(e["entity_id"])
        grouped(filename, title, groups, {"entity_type": "entity_type", "current_status": "status"}.get(field))
    groups = defaultdict(set)
    for e in full:
        loop = latest_loop.get(e["entity_id"])
        label = (loop.get("level", "") if loop.get("review_status") == "reviewed" else f"{loop.get('level')} · {loop.get('evidence_level')} · pending review") if loop else "Not assessed"
        groups[label].add(e["entity_id"])
    grouped("by-loop-level.md", "By loop level", groups)
    groups = defaultdict(set)
    tagged = set()
    for r in tables.get("tags", []):
        if r.get("facet") == "modality" and r.get("entity_id") in entities and entities[r["entity_id"]].get("inclusion") == "full":
            groups[r.get("value", "")].add(r["entity_id"])
            tagged.add(r["entity_id"])
    for e in full:
        if e["entity_id"] not in tagged:
            groups["Not specified"].add(e["entity_id"])
    grouped("by-modality.md", "By modality", groups, "tag")
    lines = ["# Assets", "", INDEX_NAV, ""]
    for aid, asset in sorted(asset_map.items()):
        title = f"[{asset.get('name', aid)}]({asset['url']})" if asset.get("url") else asset.get("name", aid)
        lines += [f"## {title}", "", asset.get("description", ""), ""]
        roles = sorted((r for r in tables.get("asset_roles", []) if r.get("asset_id") == aid and r.get("role") == "maintainer" and (not r.get("end") or r["end"] >= as_of.isoformat()) and (not r.get("start") or r["start"] <= as_of.isoformat())), key=lambda r: (r.get("entity_id", ""), r.get("start", "")))
        lines += [f"- {_anchor_link(r.get('entity_id', ''), entities)}: {'Reported, unconfirmed' if r.get('confidence') == 'reported' else r.get('confidence', '')}" for r in roles] or ["No current maintainer recorded."]
        lines.append("")
    out["index/assets.md"] = ("\n".join(lines).rstrip() + "\n").encode("utf-8")
    # Include all full entities and only referenced stub nodes.
    edges = set()
    for e in full:
        if e.get("parent_id") in entities:
            edges.add((e["parent_id"], e["entity_id"], "parent", "confirmed"))
    for ev in events:
        if ev.get("event_type") in {"spun_out", "spin_off_reported", "merged_into", "acquired", "partnership", "license_deal"} and ev.get("related_entity_id") in entities:
            a, b = ev.get("entity_id"), ev.get("related_entity_id")
            if a not in entities or (entities[a].get("inclusion") != "full" and entities[b].get("inclusion") != "full"):
                continue
            if ev.get("event_id") in entities[a].get("superseded", []):
                continue
            label = ev.get("event_type")
            # An event's subsidiary attribution does not change if its parent
            # group is promoted from a stub to a full directory entry.
            if (label in {"partnership", "license_deal"}
                    and "subsidiary" in (ev.get("summary", "") + " " + ev.get("note", "")).lower()):
                label = _display("event", label) + " (group context)"
            edges.add((a, b, label, ev.get("confidence", "")))
    asset_edges = set()
    for r in tables.get("asset_roles", []):
        if r.get("entity_id") in entities and r.get("asset_id") in asset_map and r.get("start", "") <= as_of.isoformat():
            asset_edges.add((r["entity_id"], r["asset_id"], r.get("role", ""), r.get("confidence", "")))
    nodes = {e["entity_id"] for e in full}
    for a, b, _, _ in edges:
        nodes.update((a, b))
    for eid, _, _, _ in asset_edges:
        nodes.add(eid)
    ids = {eid: f"e{i}" for i, eid in enumerate(sorted(nodes))}
    aids = {aid: f"a{i}" for i, aid in enumerate(sorted({a for _, a, _, _ in asset_edges}))}
    def mermaid(value):
        return str(value).replace('"', "'").replace("\n", " ")
    diagram = ["# Lineage", "", INDEX_NAV, "", "Group context edges point to a parent group; see the company timeline for the signing subsidiary.", "", "```mermaid", "flowchart LR"]
    for eid in sorted(nodes):
        entity = entities[eid]
        diagram.append(f'    {ids[eid]}["{mermaid(entity.get("name") or eid)}"]' + (":::stub" if entity.get("inclusion") == "stub" else ""))
    for aid in sorted(aids):
        diagram.append(f'    {aids[aid]}["{mermaid(asset_map[aid].get("name") or aid)}"]:::asset')
    for a, b, label, confidence in sorted(edges):
        arrow = "-->" if confidence == "confirmed" else "-.->"
        display = label if label.endswith(" (group context)") else _display("event", label)
        diagram.append(f'    {ids[a]} {arrow}|"{mermaid(display)}"| {ids[b]}')
    for eid, aid, role, confidence in sorted(asset_edges):
        arrow = "-->" if confidence == "confirmed" else "-.->"
        diagram.append(f'    {ids[eid]} {arrow}|"{mermaid(_display("role", role))}"| {aids[aid]}')
    diagram += ["    classDef stub stroke-dasharray: 5 5", "    classDef asset fill:#eeeeee", "```", ""]
    out["index/lineage.md"] = "\n".join(diagram).encode("utf-8")
    recent = [ev for ev in events if as_of - timedelta(days=90) <= event_key(ev)[0] <= as_of]
    lines = ["# Recent changes", "", INDEX_NAV, "", f"Events within 90 days of {as_of.isoformat()}.", ""]
    for ev in reversed(recent):
        if ev.get("entity_id") not in entities:
            continue
        note = f" — {ev['note']}" if ev.get("note") else ""
        lines.append(f"- **{ev.get('date', '')}** {_anchor_link(ev['entity_id'], entities)} · {ev.get('confidence', '')}: {ev.get('summary', '')}{note}")
    if not recent:
        lines.append("No recent events.")
    out["index/changes.md"] = ("\n".join(lines).rstrip() + "\n").encode("utf-8")
    return out
