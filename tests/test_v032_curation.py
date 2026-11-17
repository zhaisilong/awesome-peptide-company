"""Check evidence boundaries and identity preservation for the pharma survey."""
import csv
from pathlib import Path

from awepep_co.validation import load_tables
from awepep_co.render import render
from awepep_co.resolve import resolve

ROOT = Path(__file__).resolve().parents[1]


def test_pharma_scope_is_evidence_linked_and_legacy_uncertainty_is_visible():
    tables = load_tables(ROOT)
    scopes = {row['entity_id']: row for row in tables['tags'] if row['facet'] == 'directory_scope'}
    ai = {'astrazeneca', 'hansoh-pharma', 'gan-and-lee', 'novartis', 'bristol-myers-squibb'}
    landscape = {'novo-nordisk', 'eli-lilly', 'gilead-sciences'}
    assert all(scopes[eid]['value'] == 'ai_peptide' and scopes[eid]['evidence_ids'] for eid in ai)
    assert all(scopes[eid]['value'] == 'peptide_landscape' and scopes[eid]['evidence_ids'] for eid in landscape)
    assert 'bytedance-ai4s-team' not in scopes
    syneron = scopes['syneron-bio']
    sources = {row['evidence_id']: row for row in tables['evidence']}
    assert syneron['value'] == 'ai_peptide'
    assert sources[syneron['evidence_ids']]['tier'] == 'B'
    assert 'not an independent validation' in (ROOT / 'notes/syneron-bio.md').read_text()


def test_transaction_scope_and_existing_history_remain_distinct():
    tables = load_tables(ROOT)
    entities = {row['entity_id']: row for row in tables['entities']}
    assert entities['astrazeneca']['inclusion'] == entities['hansoh-pharma']['inclusion'] == 'full'
    assert entities['astrazeneca-molecular-ai']['parent_id'] == 'astrazeneca'
    assert 'subject to closing' in entities['gilead-sciences']['one_liner']
    hansoh = (ROOT / 'notes/hansoh-pharma.md').read_text()
    assert 'subsidiary' in hansoh and 'signatory' in hansoh
    baseline = ROOT / 'history/snapshots/2026-11-17-0001/files/data/events.csv'
    with baseline.open(encoding='utf-8', newline='') as stream:
        original = {row['event_id']: row for row in csv.DictReader(stream)}
    current = {row['event_id']: row for row in tables['events']}
    assert all(current.get(eid) == row for eid, row in original.items())


def test_unassessed_status_is_explained_without_a_warning():
    tables = load_tables(ROOT)
    day = '2026-11-17'
    output = render(tables, resolve(tables, day), day, (ROOT / 'README.md').read_text(), ROOT)
    card = output['cards/gilead-sciences/README.md'].decode()
    assert '**Status:** Not assessed' in card
    assert 'no confirmed status event has been recorded' in card
    assert '> ⚠ Status:' not in card
