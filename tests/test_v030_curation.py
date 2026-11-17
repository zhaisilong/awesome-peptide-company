"""Regression checks for the first user-requested company curation."""
from pathlib import Path

from awepep_co.validation import load_tables

ROOT = Path(__file__).resolve().parents[1]


def _by_id(rows, key):
    return {row[key]: row for row in rows}


def test_ailsynbio_agreement_keeps_payment_conditional_and_currency_clear():
    tables = load_tables(ROOT)
    events = _by_id(tables['events'], 'event_id')
    event = events['ailsynbio~2026-11-13~license_deal']
    assert event['confidence'] == 'confirmed'
    assert event['related_entity_id'] == 'hansoh-pharma'
    assert 'may reach RMB 317 million' in event['summary']
    assert not event['value'] and not event['unit']
    assert 'not received revenue' in event['note']
    assert 'hkex-20261113-hansoh-ailsynbio' in event['evidence_ids'].split(';')


def test_peptway_financing_retains_reported_status_and_disclosure_date():
    tables = load_tables(ROOT)
    events = _by_id(tables['events'], 'event_id')
    event = events['peptway~2026-11-09~funding_round']
    assert event['confidence'] == 'reported'
    assert not event['value'] and not event['unit']
    assert 'Publication date' in event['note']
    assert event['evidence_ids'] == 'pharmcircle-20261109-peptway-financing'


def test_protenix_record_does_not_claim_one_license_for_all_weights():
    tables = load_tables(ROOT)
    protenix = _by_id(tables['assets'], 'asset_id')['protenix']
    assert not protenix['license']
    assert 'weights' not in protenix['description'].lower()
    note = (ROOT / 'notes/bytedance-ai4s-team.md').read_text(encoding='utf-8')
    assert 'conflicting license' in note and 'https://github.com/bytedance/Protenix' in note


def test_peptway_and_ailsynbio_keep_sources_and_organization_names():
    tables = load_tables(ROOT)
    entities = _by_id(tables['entities'], 'entity_id')
    assert entities['ailsynbio']['inclusion'] == entities['peptway']['inclusion'] == 'full'
    aliases = {(a['entity_id'], a['alias']) for a in tables['aliases']}
    assert ('ailsynbio', '昂心生物有限公司') in aliases
    assert ('peptway', '杭州肽为生物科技有限公司') in aliases
    names = {r['evidence_id'] for r in tables['evidence']}
    assert {'hkex-20261113-hansoh-ailsynbio', 'peptway-about', 'pubmed-20250416-pepinvent'} <= names
