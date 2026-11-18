"""Display and search evidence-backed organization names."""
from collections import defaultdict
from unicodedata import normalize

from .resolve import interval_contains


def name_key(value):
    return " ".join(normalize("NFKC", value).casefold().split())


def active_aliases(rows, as_of):
    by_entity = defaultdict(list)
    for row in rows:
        if row.get("alias") and interval_contains(row.get("valid_from", ""), row.get("valid_to", ""), as_of):
            by_entity[row["entity_id"]].append(row)
    for aliases in by_entity.values():
        aliases.sort(key=lambda row: (name_key(row["alias"]), row["alias"]))
    return by_entity


def display_name(entity, aliases):
    name = entity.get("name") or entity["entity_id"]
    chinese = next((row["alias"] for row in aliases if row.get("kind") == "preferred_zh"), "")
    if chinese and name_key(chinese) != name_key(name):
        return f"{name} ({chinese})"
    return name


def lookup(tables, term, as_of):
    query = name_key(term)
    if not query:
        raise ValueError("lookup term cannot be blank")
    aliases = active_aliases(tables.get("aliases", []), as_of)
    exact, partial = [], []
    for entity in sorted(tables.get("entities", []), key=lambda row: row["entity_id"]):
        eid = entity["entity_id"]
        entity_aliases = aliases.get(eid, [])
        candidates = [eid, entity.get("name") or ""] + [row["alias"] for row in entity_aliases]
        match_keys = {name_key(name) for name in candidates}
        result = (eid, display_name(entity, entity_aliases), entity.get("inclusion", ""))
        if query in match_keys:
            exact.append(result)
        elif any(query in key for key in match_keys):
            partial.append(result)
    return exact or partial
