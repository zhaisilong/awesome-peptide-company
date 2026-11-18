"""Bilingual labels and offline lookups against source and historical tables."""
import csv
import json
import shutil
from pathlib import Path

from awepep_co.cli import main
from awepep_co.render import render
from awepep_co.resolve import resolve
from awepep_co.validation import HEADERS, load_tables, validate


ROOT = Path(__file__).resolve().parents[1]
BASELINE = '2026-11-17'
V032 = ROOT / 'history/snapshots/2026-11-17-0002'


def alias(entity, name, kind='preferred_zh', start='', end='', lang='zh', refs='peptway-about'):
    return dict(entity_id=entity, alias=name, kind=kind, lang=lang, valid_from=start, valid_to=end, evidence_ids=refs)


def write_table(root, name, rows):
    with (root / f'data/{name}.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADERS[name], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def project(tmp_path):
    for revision in ('2026-11-17-0001', V032.name):
        shutil.copytree(V032.parent / revision, tmp_path / 'history/snapshots' / revision)
    shutil.copytree(V032 / 'files/data', tmp_path / 'data')
    shutil.copytree(ROOT / 'vocab', tmp_path / 'vocab')
    return tmp_path


def test_preferred_name_flows_into_markdown_with_conservative_dates():
    source = V032 / 'files'
    tables = load_tables(source)
    tables['aliases'] = [row for row in tables['aliases'] if row['entity_id'] != 'peptway']
    tables['aliases'] += [alias('peptway', '测试肽为旧名', end='2026-11-29'), alias('peptway', '测试肽为新名', start='2026-11')]
    readme = (source / 'README.md').read_text(encoding='utf-8')
    old_date, new_date = '2026-11-29', '2026-11-30'
    old = render(tables, resolve(tables, old_date), old_date, readme, source, template_root=ROOT)
    new = render(tables, resolve(tables, new_date), new_date, readme, source, template_root=ROOT)
    for path in ('README.md', 'cards/peptway/README.md', 'index/by-name.md', 'index/by-scope.md', 'index/by-region.md'):
        assert 'Peptway (测试肽为旧名)' in old[path].decode()
        assert 'Peptway (测试肽为新名)' in new[path].decode()
        assert '测试肽为旧名' not in new[path].decode()
    assert next(row for row in json.loads(new['index/index.json']) if row['entity_id'] == 'peptway')['name'] == 'Peptway'


def test_lookup_prefers_exact_matches_and_uses_snapshot(tmp_path, capsys):
    root = project(tmp_path)
    tables = load_tables(root)
    tables['aliases'] += [alias('bytedance', '重名样例'), alias('peptway', '重名样例'), alias('anew-labs', '重名样例扩展'),
                          alias('peptway', '过期样例', kind='former_name', end='2025-01-01')]
    write_table(root, 'aliases', tables['aliases'])

    def lookup(term, *options):
        assert main(['lookup', term, '--root', str(root), *options]) == 0
        return capsys.readouterr().out.splitlines()

    assert lookup('重名样例') == ['bytedance | ByteDance (重名样例) | stub', 'peptway | Peptway (重名样例) | full']
    assert len(lookup('重名')) == 3
    assert lookup('ＰＥＰＴＷＡＹ') == ['peptway | Peptway (重名样例) | full']
    assert lookup('过期样例') == ['No matching organizations.']
    assert lookup('重名样例', '--as-of', BASELINE) == ['No matching organizations.']
    assert lookup('肽为生物', '--as-of', BASELINE) == ['peptway | Peptway | full']
    assert main(['lookup', '  ', '--root', str(root)]) == 1
    assert 'cannot be blank' in capsys.readouterr().err


def test_preferred_chinese_names_cannot_overlap(tmp_path):
    root = project(tmp_path)
    rows = load_tables(root)['aliases']
    rows += [alias('peptway', '测试甲', end='2025-06-30'), alias('peptway', '测试乙', start='2025-07', lang='zh-Hans')]
    write_table(root, 'aliases', rows)
    assert not any(issue.severity == 'error' for issue in validate(root, as_of=BASELINE))
    rows[-1].update(valid_from='2025-06', lang='en', evidence_ids='')
    write_table(root, 'aliases', rows)
    issues = validate(root, as_of=BASELINE)
    assert any(issue.code == 'E12' and 'overlapping preferred_zh aliases' in issue.message for issue in issues)
    assert any(issue.code == 'E02' and 'requires Chinese language' in issue.message for issue in issues)
    assert any(issue.code == 'E04' and 'evidence required' in issue.message for issue in issues)


def test_lookup_distinguishes_missing_history_and_malformed_csv(tmp_path, capsys):
    data = tmp_path / 'data'
    data.mkdir()
    for table in ('entities', 'aliases'):
        shutil.copy(V032 / f'files/data/{table}.csv', data)
    args = ['lookup', 'Peptway', '--root', str(tmp_path)]
    assert main(args) == 0
    assert capsys.readouterr().out == 'peptway | Peptway | full\n'
    assert main(args + ['--as-of', BASELINE]) == 1
    assert 'requires a recorded knowledge snapshot' in capsys.readouterr().err
    with (data / 'aliases.csv').open('a', encoding='utf-8') as stream:
        stream.write('peptway,broken\n')
    assert main(args) == 1
    assert 'aliases.csv: malformed row width' in capsys.readouterr().err


def test_peptide_biotech_landscape_requires_accessed_primary_clinical_evidence(tmp_path):
    root = project(tmp_path)
    tables = load_tables(root)
    entity = next(row for row in tables['entities'] if row['entity_id'] == 'peptway')
    next(row for row in tables['tags'] if row['entity_id'] == 'peptway' and row['facet'] == 'directory_scope')['value'] = 'peptide_landscape'
    stage = dict(entity_id='peptway', facet='stage_max', value='preclinical', evidence_ids='peptway-about')
    tables['tags'].append(stage)

    write_table(root, 'tags', tables['tags'])
    assert any(issue.code == 'E10' and 'peptide landscape scope requires' in issue.message for issue in validate(root, as_of=BASELINE))
    entity['entity_type'] = 'peptide_therapeutics'
    write_table(root, 'entities', tables['entities'])

    def clinical_stage_error():
        write_table(root, 'tags', tables['tags'])
        return any(issue.code == 'E10' and 'clinical-stage evidence' in issue.message for issue in validate(root, as_of=BASELINE))

    assert clinical_stage_error()
    stage.update(value='phase1', evidence_ids='cls-20260518-syneron-ai')
    assert clinical_stage_error()
    stage['evidence_ids'] = 'biorxiv-20250313-protein-peptide-benchmark'
    assert clinical_stage_error()
    stage['evidence_ids'] = 'peptway-about'
    assert not clinical_stage_error()
