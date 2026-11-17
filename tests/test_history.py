import csv
import shutil
import sqlite3
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

from awepep_co import history
from awepep_co.cli import main
from awepep_co.resolve import interval_contains, resolve, tables_as_of

ROOT = Path(__file__).resolve().parents[1]


def project(tmp_path):
    for directory in ('data', 'vocab', 'templates', 'notes', 'schema'):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    shutil.copy(ROOT / 'README.md', tmp_path / 'README.md')
    # These are synthetic historical fixtures, not a claim about real access dates.
    evidence = tmp_path / 'data/evidence.csv'
    with evidence.open(encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    cutoff = (date.today() - timedelta(days=3)).isoformat()
    for row in rows:
        for field in ('published', 'accessed'):
            if row[field] and row[field] > cutoff:
                row[field] = cutoff
    with evidence.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    return tmp_path


def test_history_snapshots_restore_notes_and_data_without_current_leaks(tmp_path, capsys):
    root = project(tmp_path)
    first = date.today() - timedelta(days=2)
    second = date.today() - timedelta(days=1)
    note = root / 'notes/peptway.md'
    (root / 'assets').mkdir()
    (root / 'assets/cover.png').write_bytes(b'baseline image')
    (root / 'docs').mkdir()
    (root / 'docs/research.md').write_text('baseline research', encoding='utf-8')
    note.write_text('Baseline note.\n', encoding='utf-8')
    history.record(root, 'baseline', first)
    original = (root / 'data/entities.csv').read_text(encoding='utf-8')
    (root / 'data/entities.csv').write_text(original.replace('Peptway', 'Peptway New Name'), encoding='utf-8')
    note.write_text('Later note.\n', encoding='utf-8')
    (root / 'assets/cover.png').write_bytes(b'new image')
    (root / 'docs/research.md').write_text('later research', encoding='utf-8')
    history.record(root, 'update', second)
    output = root / 'build/old'
    assert main(['build', '--root', str(root), '--as-of', first.isoformat(), '--output-dir', str(output)]) == 0
    card = (output / 'cards/peptway/README.md').read_text(encoding='utf-8')
    assert 'Baseline note.' in card and 'Later note.' not in card
    assert 'Peptway New Name' not in card
    assert (output / 'assets/cover.png').read_bytes() == b'baseline image'
    assert (output / 'docs/research.md').read_text() == 'baseline research'
    assert main(['build', '--root', str(root), '--as-of', first.isoformat(), '--output-dir', str(output), '--check']) == 0
    with sqlite3.connect(output / 'build/peploop.sqlite') as connection:
        names = [row[0] for row in connection.execute('select name from entities')]
    assert 'Peptway New Name' not in names
    (output / 'assets/cover.png').write_bytes(b'tampered')
    assert main(['build', '--root', str(root), '--as-of', first.isoformat(), '--output-dir', str(output), '--check']) == 1
    assert main(['build', '--root', str(root), '--as-of', (first - timedelta(days=1)).isoformat(), '--output-dir', str(root / 'build/missing')]) == 1
    assert 'unavailable before' in capsys.readouterr().err
    assert main(['build', '--root', str(root), '--as-of', first.isoformat()]) == 1
    assert 'require --output-dir' in capsys.readouterr().err
    note.write_text('unrecorded change', encoding='utf-8')
    assert main(['history', 'check', '--root', str(root), '--require']) == 1
    # A historical build remains tied to its archive, even with dirty current inputs.
    assert main(['build', '--root', str(root), '--as-of', first.isoformat(), '--output-dir', str(root / 'build/old2')]) == 0


def test_same_day_last_snapshot_and_tamper_detection(tmp_path):
    root = project(tmp_path)
    day = date.today()
    history.record(root, 'baseline')
    note = root / 'notes/peptway.md'
    note.write_text('revision two', encoding='utf-8')
    latest = history.record(root, 'second revision')
    assert (history.select(root, day) / 'notes/peptway.md').read_text() == 'revision two'
    (latest / 'files/notes/peptway.md').write_text('tampered', encoding='utf-8')
    with pytest.raises(ValueError, match='does not match'):
        history.check(root)


def test_existing_snapshot_files_are_append_only_even_for_additions(tmp_path):
    root = project(tmp_path)
    history.record(root, 'baseline')
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
    subprocess.run(['git', 'add', '.'], cwd=root, check=True)
    subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.org', 'commit', '-qm', 'baseline'], cwd=root, check=True)
    snapshot = history._snapshot_dirs(root)[0]
    (snapshot / 'extra').write_text('unexpected', encoding='utf-8')
    with pytest.raises(ValueError, match='does not match'):
        history.check(root, base_ref='HEAD')


def test_partial_dates_and_alias_bounds_are_conservative():
    tables = {'entities': [{'entity_id': 'company'}], 'evidence': [],
              'events': [{'entity_id': 'company', 'event_id': 'found', 'event_type': 'founded', 'date': '2024', 'confidence': 'confirmed'}],
              'aliases': [{'entity_id': 'company', 'alias': 'New', 'valid_from': '2024-04', 'valid_to': '2025'}]}
    assert resolve(tables, '2024-01-01')[0]['current_status'] == 'unknown'
    assert resolve(tables, '2024-12-31')[0]['current_status'] == 'active'
    assert not interval_contains('2024-04', '', date(2024, 4, 1))
    assert interval_contains('2024-04', '2025', date(2024, 4, 30))
    assert not interval_contains('2024-04', '2025', date(2025, 1, 2))
    assert not tables_as_of(tables, '2024-04-01')['aliases']
