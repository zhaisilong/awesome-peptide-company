"""Report organizations that need evidence verification, without I/O."""
from datetime import date

from .resolve import resolve


def stale_report(tables, as_of=None, days=365):
    """Return review records in entity-ID order from already-loaded tables.

    Active entities are overdue when their last verification is strictly more
    than ``days`` old. Full entities with no usable day-precision verification
    date are reported regardless of their current status. Parent stubs are
    excluded because they have no standalone profile to maintain.
    """
    if isinstance(days, bool) or not isinstance(days, int) or days < 0:
        raise ValueError("days must be a non-negative integer")
    if as_of is None:
        as_of = date.today()
    elif isinstance(as_of, str):
        as_of = date.fromisoformat(as_of)
    if not isinstance(as_of, date):
        raise ValueError("as_of must be an ISO date")
    entries = []
    for entity in resolve(tables, as_of):
        if entity.get("inclusion") != "full":
            continue
        last = entity.get("last_verified", "")
        age = None
        if not last:
            reason = "missing_verification_date"
        else:
            try:
                verified = date.fromisoformat(last)
            except ValueError:
                reason = "incomplete_verification_date"
            else:
                age = (as_of - verified).days
                if entity.get("current_status") != "active" or age <= days:
                    continue
                reason = "overdue"
        entries.append({
            "entity_id": entity["entity_id"],
            "name": entity.get("name", ""),
            "current_status": entity.get("current_status", "unknown"),
            "last_verified": last,
            "age_days": age,
            "reason": reason,
        })
    return entries
