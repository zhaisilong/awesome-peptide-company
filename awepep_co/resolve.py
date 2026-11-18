"""Resolve event-sourced entity state without network access."""
from datetime import date
from calendar import monthrange

STATUS_EVENTS = {
    "founded": "active", "first_public": "active", "reorganized": "in_transition",
    "merged_into": "merged", "acquired": "acquired", "paused": "inactive",
    "resumed": "active", "ceased": "closed",
}


def event_key(event):
    """Order partial dates by earliest possible date, then precision and ID."""
    parts = event.get("date", "").split("-")
    try:
        day = date(int(parts[0]), int(parts[1]) if len(parts) > 1 else 1,
                   int(parts[2]) if len(parts) > 2 else 1)
    except (ValueError, IndexError):
        day = date.min
    return day, len(parts), event.get("event_id", "")


def latest_date(event):
    parts = event.get("date", "").split("-")
    try:
        year = int(parts[0])
        if len(parts) == 1:
            return date(year, 12, 31)
        month = int(parts[1])
        if len(parts) == 2:
            return date(year, month, monthrange(year, month)[1])
        return date.fromisoformat(event["date"])
    except (ValueError, IndexError):
        return date.min


def interval_bounds(start, end):
    """Return the inclusive bounds for the known part of a validity window."""
    earliest = latest_date({"date": start}) if start else date.min
    latest = event_key({"date": end})[0] if end else date.max
    return earliest, latest


def interval_contains(start, end, as_of):
    """Conservatively require validity throughout any uncertain date range."""
    earliest, latest = interval_bounds(start, end)
    return earliest <= as_of <= latest


def tables_as_of(tables, as_of):
    """Filter dated rows once for resolver, markdown and all data exports."""
    if isinstance(as_of, str):
        as_of = date.fromisoformat(as_of)
    result = {name: list(rows) for name, rows in tables.items()}
    result["events"] = [r for r in result.get("events", []) if latest_date(r) <= as_of]
    result["aliases"] = [r for r in result.get("aliases", []) if interval_contains(r.get("valid_from", ""), r.get("valid_to", ""), as_of)]
    result["loop_assessments"] = [r for r in result.get("loop_assessments", []) if not r.get("as_of") or latest_date({"date": r["as_of"]}) <= as_of]
    result["assets"] = [r for r in result.get("assets", []) if not r.get("first_public_date") or latest_date({"date": r["first_public_date"]}) <= as_of]
    asset_ids = {r.get("asset_id") for r in result["assets"]}
    result["asset_roles"] = [r for r in result.get("asset_roles", []) if r.get("asset_id") in asset_ids and (not r.get("start") or latest_date({"date": r["start"]}) <= as_of)]
    result["events"] = [r for r in result["events"] if not r.get("asset_id") or r["asset_id"] in asset_ids]
    result["paper_links"] = [r for r in result.get("paper_links", []) if r.get("subject_kind") != "asset" or r.get("subject_id") in asset_ids]
    return result

def _ids(value):
    return [v.strip() for v in value.split(";") if v.strip()]


def resolve(tables, as_of):
    """Return entity dictionaries enriched with state, lineage, and freshness."""
    if isinstance(as_of, str):
        as_of = date.fromisoformat(as_of)
    evidence = {e["evidence_id"]: e for e in tables.get("evidence", [])}
    events = [e for e in tables.get("events", []) if latest_date(e) <= as_of]
    by_entity = {}
    for e in events:
        by_entity.setdefault(e["entity_id"], []).append(e)
    predecessors, successors = {}, {}
    for e in events:
        if e.get("confidence") != "confirmed" or not e.get("related_entity_id"):
            continue
        if e.get("event_type") == "spun_out":
            old, new = e["related_entity_id"], e["entity_id"]
        elif e.get("event_type") == "merged_into":
            old, new = e["entity_id"], e["related_entity_id"]
        else:
            continue
        successors.setdefault(old, set()).add(new)
        predecessors.setdefault(new, set()).add(old)
    result = []
    for entity in sorted(tables.get("entities", []), key=lambda x: x["entity_id"]):
        eid = entity["entity_id"]
        own = sorted(by_entity.get(eid, []), key=event_key)
        status, status_since = "unknown", ""
        pending, superseded = [], []
        for e in own:
            et, confidence = e.get("event_type"), e.get("confidence")
            if confidence == "confirmed" and et in STATUS_EVENTS:
                if et != "first_public" or status == "unknown":
                    status, status_since = STATUS_EVENTS[et], e.get("date", "")
            if confidence != "confirmed" and (et in STATUS_EVENTS or et == "spin_off_reported"):
                replaced = et == "spin_off_reported" and any(
                    other.get("event_type") == "spun_out"
                    and other.get("confidence") == "confirmed"
                    and other.get("related_entity_id") == e.get("related_entity_id")
                    and latest_date(other) >= event_key(e)[0] for other in own)
                (superseded if replaced else pending).append(e["event_id"])
        if status == "unknown" and any(e.get("confidence") == "confirmed" for e in own):
            status = "active"
        evidence_ids = set(_ids(entity.get("relevance_evidence_ids", "")))
        for table in ("aliases", "events", "asset_roles", "tags", "loop_assessments"):
            for row in tables.get(table, []):
                if row.get("entity_id") == eid:
                    if table == "events" and latest_date(row) > as_of:
                        continue
                    if table == "aliases" and not interval_contains(row.get("valid_from", ""), row.get("valid_to", ""), as_of):
                        continue
                    if table == "loop_assessments" and row.get("as_of", "") > as_of.isoformat():
                        continue
                    if table == "asset_roles" and row.get("start", "") > as_of.isoformat():
                        continue
                    evidence_ids.update(_ids(row.get("evidence_ids", "")))
        accessed = sorted(evidence[i].get("accessed", "") for i in evidence_ids if i in evidence
                          and evidence[i].get("accessed", "") and evidence[i]["accessed"] <= as_of.isoformat())
        last = accessed[-1] if accessed else ""
        try:
            stale = bool(last and (as_of - date.fromisoformat(last)).days > 365)
        except ValueError:
            stale = False
        result.append({**entity, "current_status": status, "status_since": status_since,
                       "pending_flags": pending, "superseded": superseded,
                       "last_verified": last, "needs_review": status == "active" and stale,
                       "predecessors": sorted(predecessors.get(eid, set())),
                       "successors": sorted(successors.get(eid, set())),
                       "evidence_ids": sorted(evidence_ids)})
    return result
