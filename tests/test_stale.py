from datetime import date, timedelta

import pytest

from awepep_co.stale import stale_report


AS_OF = date(2026, 11, 17)


def dataset():
    entities = []
    events = []
    evidence = []

    def add(eid, age, status="active", inclusion="full"):
        evidence_id = f"{eid}-evidence"
        entities.append({
            "entity_id": eid, "name": eid.title(), "inclusion": inclusion,
            "relevance_evidence_ids": evidence_id if age is not None else "",
        })
        if age is not None:
            evidence.append({"evidence_id": evidence_id, "accessed": (AS_OF - timedelta(days=age)).isoformat()})
        if status != "unknown":
            events.append({
                "event_id": f"{eid}~2020~founded", "entity_id": eid,
                "date": "2020", "event_type": "founded", "confidence": "confirmed", "evidence_ids": "",
            })
        if status == "inactive":
            events.append({
                "event_id": f"{eid}~2021~paused", "entity_id": eid,
                "date": "2021", "event_type": "paused", "confidence": "confirmed", "evidence_ids": "",
            })

    add("at-boundary", 365)
    add("overdue", 366)
    add("inactive-old", 600, status="inactive")
    add("inactive-missing", None, status="inactive")
    add("unknown-missing", None, status="unknown")
    add("stub-missing", None, status="unknown", inclusion="stub")
    return {"entities": entities, "events": events, "evidence": evidence}


def test_threshold_current_state_and_missing_dates():
    results = stale_report(dataset(), as_of=AS_OF, days=365)
    assert [row["entity_id"] for row in results] == ["inactive-missing", "overdue", "unknown-missing"]
    assert results[0]["reason"] == "missing_verification_date"
    assert results[0]["current_status"] == "inactive"
    assert results[1]["age_days"] == 366
    assert results[1]["reason"] == "overdue"
    assert results[2]["current_status"] == "unknown"


def test_custom_days_and_as_of_are_honored():
    results = stale_report(dataset(), as_of="2026-11-17", days=364)
    assert "at-boundary" in [row["entity_id"] for row in results]
    assert next(row for row in results if row["entity_id"] == "at-boundary")["age_days"] == 365
    previous = stale_report(dataset(), as_of="2026-11-16", days=365)
    assert "overdue" not in [row["entity_id"] for row in previous]


def test_incomplete_and_future_verification_dates_are_not_treated_as_fresh():
    tables = dataset()
    tables["entities"].append({"entity_id": "partial", "name": "Partial", "inclusion": "full", "relevance_evidence_ids": "partial-evidence"})
    tables["entities"].append({"entity_id": "future", "name": "Future", "inclusion": "full", "relevance_evidence_ids": "future-evidence"})
    tables["evidence"] += [{"evidence_id": "partial-evidence", "accessed": "2026-05"}, {"evidence_id": "future-evidence", "accessed": "2026-11-18"}]
    by_id = {row["entity_id"]: row for row in stale_report(tables, as_of=AS_OF)}
    assert by_id["partial"]["reason"] == "incomplete_verification_date"
    assert by_id["partial"]["last_verified"] == "2026-05"
    assert by_id["future"]["reason"] == "missing_verification_date"


def test_invalid_days_are_rejected():
    for value in (-1, 1.5, True, "365"):
        with pytest.raises(ValueError, match="non-negative integer"):
            stale_report(dataset(), as_of=AS_OF, days=value)
