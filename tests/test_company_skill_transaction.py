import csv
import importlib.util
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / '.codex/skills/curate-peptide-companies/scripts/transaction.py'
spec = importlib.util.spec_from_file_location('company_transaction', SCRIPT)
tx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tx)


@pytest.fixture
def project(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    for name in ('data', 'vocab', 'schema'):
        shutil.copytree(ROOT / name, project / name)
    (project / 'awepep_co').mkdir()
    shutil.copy(ROOT / 'awepep_co/tables.json', project / 'awepep_co/tables.json')
    shutil.copy(ROOT / '.build-date', project / '.build-date')
    (project / 'notes').mkdir()
    (project / 'notes/syneron-bio.md').write_text('Existing user note.\n', encoding='utf-8')
    return project


def edit_entity(workspace):
    path = workspace / 'data/entities.csv'
    text = path.read_text(encoding='utf-8')
    text = text.replace('AI drug discovery company with peptide-related research and experimental programmes.', 'Research company with peptide-related work.')
    path.write_text(text, encoding='utf-8')


def add_evidence(workspace):
    path = workspace / 'data/evidence.csv'
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        headers, rows = reader.fieldnames, list(reader)
    row = dict(rows[0])
    row.update(evidence_id='zz-sample-source', origin_key='zz-sample-source', url='https://example.org/source')
    rows.append(row)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=headers, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def edit_source(workspace, evidence_id, **changes):
    path = workspace / 'data/evidence.csv'
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        headers, rows = reader.fieldnames, list(reader)
    row = next(row for row in rows if row['evidence_id'] == evidence_id)
    row.update(changes)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=headers, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def test_complete_curation_workflow_records_snapshot_before_validation(tmp_path):
    """A real candidate preview and apply can be validated and rebuilt with history enabled."""
    from awepep_co.cli import main

    root = tmp_path / 'project'
    root.mkdir()
    for directory in ('data', 'vocab', 'schema', 'notes', 'docs', 'templates', 'assets', 'awepep_co'):
        shutil.copytree(ROOT / directory, root / directory, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy(ROOT / 'README.md', root / 'README.md')
    shutil.copy(ROOT / 'pyproject.toml', root / 'pyproject.toml')
    test_file = Path('tests/fixtures/entities.csv')
    (root / test_file).parent.mkdir(parents=True)
    shutil.copy(ROOT / test_file, root / test_file)
    skill_script = SCRIPT.relative_to(ROOT)
    (root / skill_script).parent.mkdir(parents=True)
    shutil.copy(SCRIPT, root / skill_script)
    today = date.today().isoformat()
    (root / '.build-date').write_text(today + '\n', encoding='utf-8')
    assert main(['history', 'record', '--root', str(root), '--reason', 'baseline']) == 0
    assert main(['build', '--root', str(root), '--as-of', today]) == 0
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
    subprocess.run(['git', 'add', '.'], cwd=root, check=True)
    subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.org',
                    'commit', '-qm', 'baseline'], cwd=root, check=True)

    workspace = tmp_path / 'candidate'
    assert tx.main(['prepare', '--with-preview', '--root', str(root), '--workspace', str(workspace)]) == 0
    for file in (test_file, skill_script, Path('pyproject.toml')):
        assert (workspace / file).read_bytes() == (root / file).read_bytes()
    assert not (workspace / '.git').exists()
    assert not (workspace / 'build').exists()
    card = Path('cards/anew-labs/README.md')
    original_card = (root / card).read_bytes()
    assert (workspace / card).read_bytes() == original_card
    edit_entity(workspace)
    for args in (
        ['history', 'record', '--reason', 'preview'],
        ['history', 'check', '--require'],
        ['build', '--as-of', today],
        ['build', '--as-of', today, '--check'],
    ):
        subprocess.run([sys.executable, '-m', 'awepep_co', *args], cwd=workspace, check=True)
    assert (root / card).read_bytes() == original_card
    assert (workspace / card).read_bytes() != original_card

    # The preview copies additional files, but they may not be applied.
    with pytest.raises(ValueError, match='only source CSV'):
        tx.apply(root, workspace, ['data/entities.csv', str(card)])

    tx.apply(root, workspace, ['data/entities.csv'])
    tx.guard(root, workspace)
    assert (root / card).read_bytes() == original_card
    assert len(list((root / 'history/snapshots').iterdir())) == 1
    # The previously documented ordering failed here: changed inputs have no real snapshot yet.
    assert main(['validate', '--root', str(root), '--base-ref', 'HEAD']) == 1
    assert main(['history', 'record', '--root', str(root), '--reason', 'curation']) == 0
    assert main(['history', 'check', '--root', str(root), '--require', '--base-ref', 'HEAD']) == 0
    assert main(['validate', '--root', str(root), '--base-ref', 'HEAD']) == 0
    assert main(['build', '--root', str(root), '--as-of', today]) == 0
    assert main(['build', '--root', str(root), '--as-of', today, '--check']) == 0
    assert (root / 'cards/anew-labs/README.md').read_bytes() == (workspace / 'cards/anew-labs/README.md').read_bytes()


def test_preview_detects_changed_test_input_before_apply(project, tmp_path):
    test_file = project / 'tests/test_example.py'
    test_file.parent.mkdir()
    test_file.write_text('def test_original(): pass\n', encoding='utf-8')
    workspace = tmp_path / 'candidate'
    tx.prepare(project, workspace, with_preview=True)
    edit_entity(workspace)
    original_entities = (project / 'data/entities.csv').read_bytes()
    test_file.write_text('def test_changed(): pass\n', encoding='utf-8')
    with pytest.raises(ValueError, match='render inputs or outputs changed'):
        tx.apply(project, workspace, ['data/entities.csv'])
    assert (project / 'data/entities.csv').read_bytes() == original_entities


@pytest.mark.parametrize('field,value', [
    ('url', 'https://example.org/unrelated'),
    ('tier', 'B'),
    ('origin_key', 'another-origin'),
    ('source_type', 'news'),
])
@pytest.mark.parametrize('evidence_id', [
    'hkex-20261113-hansoh-ailsynbio',  # historical event
    'pubmed-20250416-pepinvent',  # entity relevance, not an event
])
def test_referenced_source_identity_cannot_be_replaced(project, tmp_path, field, value, evidence_id):
    workspace = tmp_path / 'candidate'
    tx.prepare(project, workspace)
    before = tx._files(project)
    edit_source(workspace, evidence_id, **{field: value})
    with pytest.raises(ValueError, match='source identity of referenced evidence'):
        tx.apply(project, workspace, ['data/evidence.csv'])
    assert tx._files(project) == before


def test_referenced_source_metadata_can_be_corrected(project, tmp_path):
    workspace = tmp_path / 'candidate'
    tx.prepare(project, workspace)
    edit_source(workspace, 'hkex-20261113-hansoh-ailsynbio',
                publisher='Corrected publisher', archive_url='https://example.org/archive')
    tx.apply(project, workspace, ['data/evidence.csv'])
    assert 'Corrected publisher' in (project / 'data/evidence.csv').read_text()


def test_new_source_may_have_any_valid_identity(project, tmp_path):
    workspace = tmp_path / 'candidate'
    tx.prepare(project, workspace)
    add_evidence(workspace)
    edit_source(workspace, 'zz-sample-source', url='https://example.org/new-location', origin_key='new-origin')
    tx.apply(project, workspace, ['data/evidence.csv'])
    assert 'https://example.org/new-location' in (project / 'data/evidence.csv').read_text()


def test_removing_referenced_source_is_rejected(project, tmp_path):
    workspace = tmp_path / 'candidate'
    tx.prepare(project, workspace)
    path = workspace / 'data/evidence.csv'
    path.write_text('\n'.join(line for line in path.read_text().splitlines()
                              if not line.startswith('hkex-20261113-hansoh-ailsynbio,')) + '\n')
    with pytest.raises(ValueError, match='source identity of referenced evidence'):
        tx.apply(project, workspace, ['data/evidence.csv'])


def test_valid_multi_table_and_new_note_preserves_dirty_inputs(project, tmp_path):
    workspace = tmp_path / 'candidate'
    user_note = (project / 'notes/syneron-bio.md').read_bytes()
    tx.prepare(project, workspace)
    edit_entity(workspace)
    add_evidence(workspace)
    (workspace / 'notes/anew-labs.md').write_text('Verified sources: https://example.org/source\n', encoding='utf-8')
    tx.apply(project, workspace, ['data/entities.csv', 'data/evidence.csv', 'notes/anew-labs.md'])
    assert 'Research company' in (project / 'data/entities.csv').read_text()
    assert 'zz-sample-source' in (project / 'data/evidence.csv').read_text()
    assert 'Verified sources' in (project / 'notes/anew-labs.md').read_text()
    assert (project / 'notes/syneron-bio.md').read_bytes() == user_note


@pytest.mark.parametrize('operation', ['event_change', 'event_remove', 'entity_remove', 'invalid_reference', 'unlisted'])
def test_invalid_candidate_leaves_project_unchanged(project, tmp_path, operation):
    workspace = tmp_path / 'candidate'
    tx.prepare(project, workspace)
    before = tx._files(project)
    name = 'data/events.csv'
    path = workspace / name
    text = path.read_text(encoding='utf-8')
    if operation == 'event_change':
        path.write_text(text.replace('Reuters reported approximately USD 290M', 'Some other claim'), encoding='utf-8')
    elif operation == 'event_remove':
        path.write_text('\n'.join(text.splitlines()[:1]) + '\n', encoding='utf-8')
    elif operation == 'entity_remove':
        name = 'data/entities.csv'
        path = workspace / name
        path.write_text('\n'.join(line for line in path.read_text().splitlines() if not line.startswith('anew-labs,')) + '\n')
    elif operation == 'invalid_reference':
        path.write_text(text + 'new-event,absent,2026,year,founded,,,,,Founded,confirmed,missing,\n', encoding='utf-8')
    else:
        edit_entity(workspace)
    with pytest.raises(ValueError):
        tx.apply(project, workspace, [name])
    assert tx._files(project) == before


def test_concurrent_user_edit_aborts_without_overwrite(project, tmp_path):
    workspace = tmp_path / 'candidate'
    tx.prepare(project, workspace)
    edit_entity(workspace)
    path = project / 'notes/syneron-bio.md'
    path.write_text('User changed the note.\n')
    before = tx._files(project)
    with pytest.raises(ValueError, match='changed since prepare'):
        tx.apply(project, workspace, ['data/entities.csv'])
    assert tx._files(project) == before


def test_write_failure_rolls_back_first_file(project, tmp_path, monkeypatch):
    workspace = tmp_path / 'candidate'
    tx.prepare(project, workspace)
    edit_entity(workspace)
    add_evidence(workspace)
    before = tx._files(project)
    original = tx._atomic_write
    calls = []
    def fail_second(path, content, mode):
        calls.append(path)
        if len(calls) == 2:
            raise OSError('simulated disk failure')
        original(path, content, mode)
    monkeypatch.setattr(tx, '_atomic_write', fail_second)
    with pytest.raises(OSError, match='simulated'):
        tx.apply(project, workspace, ['data/entities.csv', 'data/evidence.csv'])
    assert tx._files(project) == before


def test_concurrent_edit_during_apply_is_not_overwritten(project, tmp_path, monkeypatch):
    workspace = tmp_path / 'candidate'
    tx.prepare(project, workspace)
    edit_entity(workspace)
    add_evidence(workspace)
    before_entities = (project / 'data/entities.csv').read_bytes()
    original = tx._atomic_write
    def external_edit(path, content, mode):
        original(path, content, mode)
        if path.name == 'entities.csv' and content != before_entities:
            (project / 'notes/syneron-bio.md').write_text('Concurrent user change.\n')
    monkeypatch.setattr(tx, '_atomic_write', external_edit)
    with pytest.raises(ValueError, match='changed during apply'):
        tx.apply(project, workspace, ['data/entities.csv', 'data/evidence.csv'])
    assert (project / 'data/entities.csv').read_bytes() == before_entities
    assert (project / 'notes/syneron-bio.md').read_text() == 'Concurrent user change.\n'


def test_unknown_note_and_unsafe_paths_rejected(project, tmp_path):
    workspace = tmp_path / 'candidate'
    tx.prepare(project, workspace)
    (workspace / 'notes/missing.md').write_text('No entity.\n')
    with pytest.raises(ValueError, match='existing entity'):
        tx.apply(project, workspace, ['notes/missing.md'])
    with pytest.raises(ValueError, match='only source'):
        tx.apply(project, workspace, ['notes/../README.md'])


def test_date_cannot_go_back_or_into_future(project, tmp_path):
    from datetime import date, timedelta
    workspace = tmp_path / 'candidate'
    tx.prepare(project, workspace)
    previous = date.fromisoformat((project / '.build-date').read_text().strip())
    for value, message in ((previous - timedelta(days=1), 'backwards'), (date.today() + timedelta(days=1), 'future')):
        (workspace / '.build-date').write_text(value.isoformat() + '\n')
        with pytest.raises(ValueError, match=message):
            tx.apply(project, workspace, ['.build-date'])


@pytest.mark.parametrize('change', ['bom', 'crlf', 'unsorted'])
def test_changed_csv_must_be_utf8_lf_and_sorted(project, tmp_path, change):
    workspace = tmp_path / 'candidate'
    tx.prepare(project, workspace)
    before = tx._files(project)
    path = workspace / 'data/entities.csv'
    content = path.read_bytes()
    if change == 'bom':
        content = b'\xef\xbb\xbf' + content
    elif change == 'crlf':
        content = content.replace(b'\n', b'\r\n')
    else:
        lines = content.splitlines()
        content = b'\n'.join([lines[0]] + list(reversed(lines[1:]))) + b'\n'
    path.write_bytes(content)
    with pytest.raises(ValueError):
        tx.apply(project, workspace, ['data/entities.csv'])
    assert tx._files(project) == before


@pytest.mark.parametrize('target', ['README.md', 'templates/card.liquid', 'cards/new/README.md', 'index/new.md', 'awepep_co/render.py', 'docs/policy.md', 'assets/card.png', 'history/manifest.json'])
def test_render_input_change_before_apply_is_rejected(project, tmp_path, target):
    workspace = tmp_path / 'candidate'
    tx.prepare(project, workspace)
    edit_entity(workspace)
    path = project / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('New user content.\n')
    with pytest.raises(ValueError, match='render inputs or outputs changed'):
        tx.apply(project, workspace, ['data/entities.csv'])
    assert path.read_text() == 'New user content.\n'


@pytest.mark.parametrize('target', ['docs/policy.md', 'assets/card.png', 'history/manifest.json'])
@pytest.mark.parametrize('change', ['modify', 'delete'])
def test_guard_protects_knowledge_inputs_after_apply(project, tmp_path, target, change):
    path = project / target
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('Original input.\n')
    workspace = tmp_path / 'candidate'
    tx.prepare(project, workspace)
    edit_entity(workspace)
    tx.apply(project, workspace, ['data/entities.csv'])
    if change == 'modify':
        path.write_text('Concurrent input.\n')
    else:
        path.unlink()
    with pytest.raises(ValueError, match='render inputs or output files changed'):
        tx.guard(project, workspace)
    if change == 'modify':
        assert path.read_text() == 'Concurrent input.\n'
    else:
        assert not path.exists()


def test_guard_protects_generated_output_after_apply(project, tmp_path):
    workspace = tmp_path / 'candidate'
    (project / 'README.md').write_text('Original\n')
    tx.prepare(project, workspace)
    edit_entity(workspace)
    tx.apply(project, workspace, ['data/entities.csv'])
    tx.guard(project, workspace)
    (project / 'README.md').write_text('User changed this.\n')
    with pytest.raises(ValueError, match='render inputs or output files changed'):
        tx.guard(project, workspace)
    assert (project / 'README.md').read_text() == 'User changed this.\n'


def test_guard_protects_source_after_apply(project, tmp_path):
    workspace = tmp_path / 'candidate'
    tx.prepare(project, workspace)
    edit_entity(workspace)
    tx.apply(project, workspace, ['data/entities.csv'])
    (project / 'notes/syneron-bio.md').write_text('User change after apply.\n')
    with pytest.raises(ValueError, match='inputs changed since apply'):
        tx.guard(project, workspace)


def test_new_evidence_backed_organization_and_event(project, tmp_path):
    workspace = tmp_path / 'candidate'
    tx.prepare(project, workspace)
    add_evidence(workspace)
    entities = workspace / 'data/entities.csv'
    with entities.open('a', encoding='utf-8', newline='') as stream:
        csv.writer(stream, lineterminator='\n').writerow([
            'zz-test-labs', 'Z Test Labs', 'ai_native_biotech', 'full', '',
            'core', 'zz-sample-source', '', '', '', 'Test organization.',
        ])
    events = workspace / 'data/events.csv'
    with events.open('a', encoding='utf-8', newline='') as stream:
        csv.writer(stream, lineterminator='\n').writerow([
            'zz-test-labs~2026~first_public', 'zz-test-labs', '2026', 'year',
            'first_public', '', '', '', '', 'First public activity.',
            'reported', 'zz-sample-source', '',
        ])
    tx.apply(project, workspace, ['data/entities.csv', 'data/events.csv', 'data/evidence.csv'])
    tx.guard(project, workspace)
    assert 'zz-test-labs,' in (project / 'data/entities.csv').read_text(encoding='utf-8')
    assert 'zz-test-labs~2026~first_public,' in (project / 'data/events.csv').read_text(encoding='utf-8')
