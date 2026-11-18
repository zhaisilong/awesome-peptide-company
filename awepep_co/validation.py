"""Offline validation for the flat-file source of truth."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from .resolve import interval_bounds


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    severity: str = "error"

    def __str__(self):
        return f"{self.severity.upper()} {self.code}: {self.message}"


# Schema remains accessible to consumers without copying the table definitions.
_SCHEMA = json.loads((Path(__file__).resolve().parent / 'tables.json').read_text(encoding='utf-8'))
HEADERS = {name: spec['columns'] for name, spec in _SCHEMA.items()}
PRIMARY_KEYS = {name: spec['primary_key'] for name, spec in _SCHEMA.items()}
EVIDENCE_IDENTITY_FIELDS = ('url', 'tier', 'origin_key', 'source_type')


def _read_table(root, table):
    with (Path(root) / 'data' / (table + '.csv')).open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream, strict=True)
        columns = HEADERS[table]
        if reader.fieldnames != columns:
            raise ValueError(f'expected header {columns}, got {reader.fieldnames}')
        rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ValueError('malformed row width')
        return rows


def load_tables(root, table_names=HEADERS):
    """Read source tables and check their CSV structure."""
    tables = {}
    for table in table_names:
        try:
            tables[table] = _read_table(root, table)
        except (csv.Error, ValueError) as exc:
            raise ValueError(f'{table}.csv: {exc}') from exc
    return tables


def _datestr(value):
    if not value or not re.fullmatch(r'\d{4}(?:-\d{2}(?:-\d{2})?)?', value):
        return None
    try:
        parts = [int(p) for p in value.split('-')]
        return date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
    except ValueError:
        return None


def _values(value):
    return [v.strip() for v in (value or '').split(';') if v.strip()]


def evidence_identity_conflicts(before, after):
    """Return IDs whose previously referenced source identity was changed."""
    referenced = set()
    for table, rows in before.items():
        if table == 'evidence':
            continue
        for row in rows:
            for column, value in row.items():
                if column.endswith('evidence_ids'):
                    referenced.update(_values(value))
    old_sources = {row['evidence_id']: row for row in before.get('evidence', [])}
    new_sources = {row['evidence_id']: row for row in after.get('evidence', [])}
    return sorted(eid for eid in referenced if eid in old_sources and (
        eid not in new_sources or any(old_sources[eid][field] != new_sources[eid][field]
                                     for field in EVIDENCE_IDENTITY_FIELDS)))


def _vocab(root):
    result = {}
    with (Path(root) / 'vocab/terms.csv').open(encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f, strict=True)
        if reader.fieldnames != ['category', 'value']:
            raise ValueError('vocabulary header must be category,value')
        for row in reader:
            result.setdefault(row['category'], set()).add(row['value'])
    return result


def _translation_source(key, tables):
    parts = key.split(':')
    if len(parts) == 3 and parts[0] in ('entity', 'event', 'asset'):
        table, idcol, allowed = {
            'entity': ('entities', 'entity_id', {'one_liner'}),
            'event': ('events', 'event_id', {'summary', 'note'}),
            'asset': ('assets', 'asset_id', {'description'}),
        }[parts[0]]
        if parts[2] in allowed:
            return next((r[parts[2]] for r in tables[table] if r[idcol] == parts[1]), None)
    if len(parts) == 4 and parts[0] == 'loop' and parts[3] == 'rationale':
        return next((r['rationale'] for r in tables['loop_assessments'] if r['entity_id'] == parts[1] and r['as_of'] == parts[2]), None)
    return None


def validate(root, as_of=None, base_ref=None):
    """Return deterministic issues; never perform network requests or mutate inputs.

    ``base_ref`` names a Git revision for E09 entity, event, and referenced
    evidence protections. If omitted, baseline validation is skipped.
    """
    root = Path(root)
    issues = []
    def add(code, msg, severity='error'):
        issues.append(Issue(code, msg, severity))
    if as_of is None:
        today = date.today()
    elif isinstance(as_of, date):
        today = as_of
    else:
        today = _datestr(as_of)
        if today is None or len(as_of) != 10:
            raise ValueError('as_of must be YYYY-MM-DD')
    try:
        vocabulary = _vocab(root)
    except (OSError, ValueError, csv.Error) as exc:
        return [Issue('E02', f'cannot read vocabulary: {exc}')]
    tables = {}
    for table in HEADERS:
        try:
            tables[table] = _read_table(root, table)
        except (OSError, csv.Error, ValueError) as exc:
            add('E01', f'{table}.csv: {exc}')
    if len(tables) != len(HEADERS):
        return issues
    for table, rows in tables.items():
        seen = set()
        for number, row in enumerate(rows, 2):
            key = tuple(row[k] for k in PRIMARY_KEYS[table])
            if not all(key) or key in seen:
                add('E12', f'{table}.csv:{number}: missing or duplicate primary key {key}')
            seen.add(key)
    ids = {table: {r[col] for r in tables[table]} for table, col in [('entities','entity_id'),('assets','asset_id'),('evidence','evidence_id')]}
    evidence = {r['evidence_id']: r for r in tables['evidence']}
    enum_fields = {
        'entities': {'entity_type':'entity_type', 'inclusion':'inclusion', 'peptide_relevance':'peptide_relevance'},
        'aliases': {'kind':'alias_kind'},
        'events': {'date_precision':'date_precision','event_type':'event_type','confidence':'confidence','unit':'unit'},
        'evidence': {'source_type':'source_type','tier':'tier'},
        'assets': {'asset_type':'asset_type'},
        'asset_roles': {'role':'role','confidence':'confidence'},
        'loop_assessments': {'level':'level','evidence_level':'evidence_level','review_status':'review_status'},
        'paper_links': {'subject_kind':'subject_kind','relation':'relation'},
    }
    optional_enums = {('entities', 'peptide_relevance'), ('events', 'unit')}
    refs = {
        'entities': {'parent_id':'entities'}, 'aliases': {'entity_id':'entities'},
        'events': {'entity_id':'entities','related_entity_id':'entities','asset_id':'assets'},
        'asset_roles': {'entity_id':'entities','asset_id':'assets'},
        'tags': {'entity_id':'entities'}, 'loop_assessments': {'entity_id':'entities'},
    }
    datefields = {
        'aliases':['valid_from','valid_to'], 'events':['date'], 'evidence':['published','accessed'],
        'assets':['first_public_date'], 'asset_roles':['start','end'], 'loop_assessments':['as_of'],
    }
    origin_tiers = {}
    for ev in tables['evidence']:
        origin = ev['origin_key']
        if origin and origin in origin_tiers and origin_tiers[origin] != ev['tier']:
            add('E06', f"origin_key {origin!r} has conflicting tiers")
        origin_tiers[origin] = ev['tier']
        if not origin or not ev['tier']:
            add('E02', f"evidence {ev['evidence_id']}: origin_key and tier are required")
        if ev['source_type'] in {'news','paper','preprint','press_release'} and not ev['published']:
            add('W02', f"evidence {ev['evidence_id']}: published date missing", 'warning')
        for field in ('url','archive_url'):
            value = ev[field]
            if value and (urlparse(value).scheme not in {'http','https'} or not urlparse(value).netloc):
                add('W04', f"evidence {ev['evidence_id']}: invalid {field}", 'warning')
        if not ev['archive_url']:
            add('W04', f"evidence {ev['evidence_id']}: no archive URL", 'warning')
    def max_confidence(ev_ids):
        src = [evidence[eid] for eid in ev_ids if eid in evidence]
        if any(ev['tier'] == 'A' for ev in src): return 2
        b = {ev['origin_key'] for ev in src if ev['tier'] == 'B' and ev['origin_key']}
        if len(b) >= 2: return 2
        if len(b) == 1: return 1
        return 0
    for table, rows in tables.items():
        for number, row in enumerate(rows, 2):
            loc = f'{table}.csv:{number}'
            for field, category in enum_fields.get(table, {}).items():
                value = row[field]
                if (not value and (table, field) not in optional_enums) or (value and value not in vocabulary.get(category, set())):
                    add('E02', f'{loc}: invalid {field} {value!r}')
            if table == 'tags':
                if row['facet'] not in {'directory_scope','modality','dry','wet','therapeutic_area','stage_max'} or row['value'] not in vocabulary.get(row['facet'], set()):
                    add('E02', f"{loc}: invalid tag {row['facet']}:{row['value']}")
            for field, target in refs.get(table, {}).items():
                if row[field] and row[field] not in ids[target]:
                    add('E03', f'{loc}: {field} {row[field]!r} not found')
            if table == 'events' and not row['entity_id']:
                add('E03', f'{loc}: entity_id is required')
            if table == 'paper_links' and row['subject_id']:
                target = {'asset':'assets','entity':'entities'}.get(row['subject_kind'])
                if target and row['subject_id'] not in ids[target]:
                    add('E03', f"{loc}: subject {row['subject_id']!r} not found")
            evfields = [k for k in row if k in ('evidence_ids','relevance_evidence_ids')]
            for field in evfields:
                for eid in _values(row[field]):
                    if eid not in evidence:
                        add('E03', f'{loc}: evidence {eid!r} not found')
            if table in {'events', 'aliases', 'tags', 'asset_roles', 'loop_assessments'} and not _values(row['evidence_ids']):
                add('E04', f'{loc}: evidence required')
            for field in datefields.get(table, []):
                if row[field] and _datestr(row[field]) is None:
                    add('E08', f'{loc}: invalid {field} {row[field]!r}')
            for field, limit in [('one_liner',140),('summary',200),('note',200),('rationale',200)]:
                if field in row and len(row[field]) > limit:
                    add('E11', f'{loc}: {field} exceeds {limit} characters')
            if table in ('aliases','asset_roles'):
                start = row['valid_from'] if table == 'aliases' else row['start']
                end = row['valid_to'] if table == 'aliases' else row['end']
                if start and end and _datestr(start) and _datestr(end) and end < start:
                    add('E12', f'{loc}: end precedes start')
            if table in ('events','asset_roles') and row['confidence']:
                rank = {'rumor':0,'reported':1,'confirmed':2}.get(row['confidence'])
                if rank is not None and rank > max_confidence(_values(row['evidence_ids'])):
                    add('E05', f'{loc}: declared confidence exceeds evidence support')
            if table == 'events':
                req = {'merged_into':'related_entity_id', 'acquired':'related_entity_id','spin_off_reported':'related_entity_id','spun_out':'related_entity_id','ownership_disclosed':'related_entity_id','partnership':'related_entity_id','license_deal':'related_entity_id','asset_release':'asset_id','pipeline_milestone':'asset_id'}.get(row['event_type'])
                if req and not row[req]: add('E07', f'{loc}: {row["event_type"]} requires {req}')
                precision = {'year':4,'month':7,'day':10}.get(row['date_precision'])
                if not row['date'] or not precision or len(row['date']) != precision:
                    add('E08', f'{loc}: date does not match date_precision')
                published = [_datestr(evidence[e]['published']) for e in _values(row['evidence_ids']) if e in evidence and len(evidence[e]['published']) == 10]
                published = [d for d in published if d]
                if len(published) >= 2 and (max(published)-min(published)).days > 3 and not row['note'].strip():
                    add('W01', f'{loc}: evidence publication dates differ by more than 3 days without explanation', 'warning')
                if re.search(r'\b(buy|discount|dose)\b', row['summary'], re.I):
                    add('W07', f'{loc}: review potentially prohibited content', 'warning')
            if table == 'entities' and row['inclusion'] == 'full' and row['peptide_relevance'] in {'adjacent','infrastructure'} and not _values(row['relevance_evidence_ids']):
                add('E10', f'{loc}: relevance evidence required')
            if table == 'loop_assessments' and row['review_status'] == 'proposed' and _datestr(row['as_of']) and (today - _datestr(row['as_of'])).days > 30:
                add('W05', f'{loc}: proposed assessment is over 30 days old', 'warning')
    windows = {}
    for row in tables['aliases']:
        if row['kind'] != 'preferred_zh':
            continue
        eid = row['entity_id']
        if row['lang'].lower().split('-', 1)[0] != 'zh':
            add('E02', f'entity {eid}: preferred_zh alias requires Chinese language (zh)')
        start, end = row['valid_from'], row['valid_to']
        if (start and _datestr(start) is None) or (end and _datestr(end) is None):
            continue  # The row already has a date error.
        lower, upper = interval_bounds(start, end)
        if lower > upper:
            add('E12', f'entity {eid}: preferred_zh alias has no effective dates')
            continue
        windows.setdefault(eid, []).append((lower, upper))
    for eid, intervals in sorted(windows.items()):
        ordered = sorted(intervals)
        if any(previous[1] >= current[0] for previous, current in zip(ordered, ordered[1:])):
            add('E12', f'entity {eid}: overlapping preferred_zh aliases')

    scope_counts = {}
    landscape_entities = set()
    clinical_landscape = set()
    for row in tables['tags']:
        eid = row['entity_id']
        if row['facet'] == 'directory_scope':
            scope_counts[eid] = scope_counts.get(eid, 0) + 1
            if row['value'] == 'peptide_landscape':
                landscape_entities.add(eid)
        if row['facet'] == 'stage_max' and row['value'] in {'phase1', 'phase2', 'phase3', 'approved'}:
            refs = (evidence[source_id] for source_id in _values(row['evidence_ids']) if source_id in evidence)
            if any(source['tier'] == 'A' and source['accessed'] for source in refs):
                clinical_landscape.add(eid)
    for entity in tables['entities']:
        eid = entity['entity_id']
        if scope_counts.get(eid, 0) > 1:
            add('E12', f'entity {eid}: multiple directory scope values')
        if entity['inclusion'] != 'full':
            continue
        kind = entity['entity_type']
        if kind == 'pharma_company' and not scope_counts.get(eid):
            add('E10', f'entity {eid}: pharmaceutical company requires a directory scope with evidence')
        if eid not in landscape_entities:
            continue
        if kind not in {'pharma_company', 'peptide_therapeutics'}:
            add('E10', f'entity {eid}: peptide landscape scope requires pharma_company or peptide_therapeutics type')
        elif kind == 'peptide_therapeutics' and eid not in clinical_landscape:
            add('E10', f'entity {eid}: peptide landscape entry requires clinical-stage evidence from an accessed A-tier source')
    # Use the same resolver as rendering; skip W03 if invalid data would be resolved.
    if not any(issue.severity == 'error' for issue in issues):
        from .resolve import resolve
        for entity in resolve(tables, today):
            if entity['needs_review']:
                add('W03', f"{entity['entity_id']}: active entity has not been verified for over 365 days", 'warning')
    translation = root / 'i18n/zh/strings.csv'
    if translation.exists():
        try:
            with translation.open(encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f, strict=True)
                if reader.fieldnames != ['key','zh_text','source_hash','status','translator','updated']:
                    add('E01', 'i18n/zh/strings.csv: invalid header')
                else:
                    for row in reader:
                        source = _translation_source(row['key'], tables)
                        digest = hashlib.sha256(' '.join(source.split()).encode()).hexdigest()[:12] if source is not None else None
                        if digest != row['source_hash']:
                            add('W06', f"translation {row['key']}: source missing or hash is stale", 'warning')
        except (OSError, csv.Error, UnicodeError) as exc:
            add('E01', f'translation CSV: {exc}')
    if base_ref:
        revision = subprocess.run(['git','rev-parse','--verify',f'{base_ref}^{{commit}}'], cwd=root, capture_output=True, text=True)
        if revision.returncode:
            add('E09', f'cannot read Git baseline {base_ref}: {revision.stderr.strip()}')
            return issues
        baseline_tables = {}
        for table in HEADERS:
            try:
                exists = subprocess.run(['git','cat-file','-e',f'{base_ref}:data/{table}.csv'], cwd=root, capture_output=True)
                if exists.returncode:
                    if table in ('entities', 'events'):
                        add('I01', f'{table}.csv does not exist at baseline; no prior rows to compare', 'info')
                    continue
                raw = subprocess.run(['git','show',f'{base_ref}:data/{table}.csv'], cwd=root, check=True, capture_output=True, text=True).stdout
                old = csv.DictReader(io.StringIO(raw), strict=True)
                if old.fieldnames != HEADERS[table]:
                    add('E01', f'baseline {table}.csv has invalid header')
                    continue
                old_rows = list(old)
                if any(None in row or any(value is None for value in row.values()) for row in old_rows):
                    add('E01', f'baseline {table}.csv has malformed row width')
                    continue
                baseline_tables[table] = old_rows
                if table in ('entities', 'events'):
                    old_rows_by_key = {tuple(row[k] for k in PRIMARY_KEYS[table]): row for row in old_rows}
                    new_rows_by_key = {tuple(row[k] for k in PRIMARY_KEYS[table]): row for row in tables[table]}
                    for key in sorted(old_rows_by_key.keys() - new_rows_by_key.keys()):
                        add('E09', f'{table}.csv: removed existing key {key}')
                    if table == 'events':
                        for key in sorted(old_rows_by_key.keys() & new_rows_by_key.keys()):
                            if old_rows_by_key[key] != new_rows_by_key[key]:
                                add('E09', f'{table}.csv: modified existing event {key}')
            except (OSError, subprocess.CalledProcessError, csv.Error, KeyError) as exc:
                add('E09', f'cannot read baseline {base_ref} for {table}: {exc}')
        for evidence_id in evidence_identity_conflicts(baseline_tables, tables):
            add('E09', f'evidence.csv: removed or changed identity of referenced source {evidence_id!r}')
    else:
        add('I01', 'no Git baseline supplied; E09 historical protections skipped', 'info')
    return issues
