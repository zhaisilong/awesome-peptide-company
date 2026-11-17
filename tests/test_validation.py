import csv
import hashlib
import shutil
import subprocess
from pathlib import Path

from awepep_co.validation import HEADERS, validate


def write(path, rows):
    with path.open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=HEADERS[path.stem], lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def dataset(tmp_path):
    root = Path(__file__).resolve().parents[1]
    shutil.copytree(root / 'vocab', tmp_path / 'vocab')
    (tmp_path / 'data').mkdir()
    for name in HEADERS:
        write(tmp_path / 'data' / f'{name}.csv', [])
    write(tmp_path / 'data/entities.csv', [{'entity_id':'x','name':'X','entity_type':'ai_native_biotech','inclusion':'full','peptide_relevance':'core'}])
    write(tmp_path / 'data/evidence.csv', [
        {'evidence_id':'b1','url':'https://example.org/1','source_type':'news','tier':'B','origin_key':'o1','published':'2025-01-01','accessed':'2025-01-02'},
        {'evidence_id':'b2','url':'https://example.org/2','source_type':'news','tier':'B','origin_key':'o2','published':'2025-01-05','accessed':'2025-01-05'},
    ])
    write(tmp_path / 'data/events.csv', [{'event_id':'x~2025~founded','entity_id':'x','date':'2025','date_precision':'year','event_type':'founded','summary':'Founded','confidence':'confirmed','evidence_ids':'b1;b2'}])
    return tmp_path


def codes(root, **kwargs):
    return [i.code for i in validate(root, as_of='2025-01-06', **kwargs)]


def test_confidence_origin_dedup_and_date_warning(tmp_path):
    root = dataset(tmp_path)
    assert 'E05' not in codes(root)
    assert 'W01' in codes(root)
    write(root / 'data/evidence.csv', [
        {'evidence_id':'b1','source_type':'news','tier':'B','origin_key':'same','published':'2025-01-01'},
        {'evidence_id':'b2','source_type':'news','tier':'B','origin_key':'same','published':'2025-01-04'},
    ])
    assert 'E05' in codes(root)
    assert 'W01' not in codes(root)


def test_w01_three_and_four_day_boundaries_and_explanation(tmp_path):
    root = dataset(tmp_path)
    evidence = [
        {'evidence_id':'b1','source_type':'news','tier':'B','origin_key':'o1','published':'2025-01-01'},
        {'evidence_id':'b2','source_type':'news','tier':'B','origin_key':'o2','published':'2025-01-04'},
    ]
    write(root / 'data/evidence.csv', evidence)
    assert 'W01' not in codes(root)
    evidence[1]['published'] = '2025-01-05'
    write(root / 'data/evidence.csv', evidence)
    assert 'W01' in codes(root)
    write(root / 'data/events.csv', [{'event_id':'e','entity_id':'x','date':'2025','date_precision':'year','event_type':'founded','confidence':'confirmed','evidence_ids':'b1;b2','note':'Sources published four days apart.'}])
    assert 'W01' not in codes(root)


def test_w02_publication_date_required_only_for_specified_sources(tmp_path):
    root = dataset(tmp_path)
    sources = ('news', 'paper', 'preprint', 'press_release', 'repo', 'aggregator', 'job_post')
    write(root / 'data/evidence.csv', [{'evidence_id':source,'source_type':source,'tier':'A','origin_key':source} for source in sources])
    issues = validate(root, as_of='2025-01-06')
    warnings = [issue.message for issue in issues if issue.code == 'W02']
    for source in sources[:4]:
        assert any('evidence ' + source + ':' in message for message in warnings)
    for source in sources[4:]:
        assert not any('evidence ' + source + ':' in message for message in warnings)


def test_w07_warns_about_prohibited_terms_without_rejecting_case_insensitively(tmp_path):
    root = dataset(tmp_path)
    for term in ('buy', 'Discount', 'DOSE'):
        write(root / 'data/events.csv', [{'event_id':'e','entity_id':'x','date':'2025','date_precision':'year','event_type':'founded','summary':'Please ' + term,'confidence':'reported','evidence_ids':'b1'}])
        issues = validate(root, as_of='2025-01-06')
        assert any(issue.code == 'W07' and issue.severity == 'warning' for issue in issues)


def test_foreign_keys_required_fields_and_relevance(tmp_path):
    root = dataset(tmp_path)
    write(root / 'data/entities.csv', [{'entity_id':'x','entity_type':'ai_native_biotech','inclusion':'full','peptide_relevance':'adjacent'}])
    write(root / 'data/events.csv', [{'event_id':'e','entity_id':'missing','date':'2025-01','date_precision':'day','event_type':'acquired','confidence':'reported'}])
    assert {'E03','E04','E07','E08','E10'} <= set(codes(root))


def test_missing_entity_and_evidence_on_factual_rows(tmp_path):
    root = dataset(tmp_path)
    write(root / 'data/events.csv', [{'event_id':'e','date':'2025','date_precision':'year','event_type':'founded','confidence':'rumor','evidence_ids':'b1'}])
    write(root / 'data/aliases.csv', [{'entity_id':'x','alias':'Example','kind':'variant'}])
    write(root / 'data/tags.csv', [{'entity_id':'x','facet':'dry','value':'docking'}])
    write(root / 'data/asset_roles.csv', [{'asset_id':'a','entity_id':'x','role':'developer','start':'2025','confidence':'rumor'}])
    write(root / 'data/loop_assessments.csv', [{'entity_id':'x','as_of':'2025-01-01','level':'L0','evidence_level':'claimed','review_status':'proposed'}])
    issues = validate(root, as_of='2025-01-06')
    assert any(i.code == 'E03' and 'entity_id is required' in i.message for i in issues)
    for table in ('aliases', 'tags', 'asset_roles', 'loop_assessments'):
        assert any(i.code == 'E04' and i.message.startswith(table + '.csv:') for i in issues)


def test_tier_conflicts_header_dates_and_duplicates(tmp_path):
    root = dataset(tmp_path)
    write(root / 'data/evidence.csv', [
        {'evidence_id':'e','tier':'A','origin_key':'same','source_type':'paper'},
        {'evidence_id':'e','tier':'B','origin_key':'same','source_type':'paper'},
    ])
    assert {'E06','E12','W02'} <= set(codes(root))
    (root / 'data/aliases.csv').write_text('alias,entity_id\n')
    assert 'E01' in codes(root)


def test_baseline_compares_primary_keys(tmp_path):
    root = dataset(tmp_path)
    subprocess.run(['git','init','-q'], cwd=root, check=True)
    subprocess.run(['git','add','data'], cwd=root, check=True)
    subprocess.run(['git','-c','user.name=Tester','-c','user.email=test@example.org','commit','-qm','baseline'], cwd=root, check=True)
    write(root / 'data/events.csv', [])
    assert 'E09' in codes(root, base_ref='HEAD')
    assert 'E09' not in codes(root)


def test_baseline_without_tables_allows_new_tables(tmp_path):
    root = dataset(tmp_path)
    subprocess.run(['git','init','-q'], cwd=root, check=True)
    (root / 'initial').write_text('initial\n')
    subprocess.run(['git','add','initial'], cwd=root, check=True)
    subprocess.run(['git','-c','user.name=Tester','-c','user.email=test@example.org','commit','-qm','baseline'], cwd=root, check=True)
    assert 'E09' not in codes(root, base_ref='HEAD')
    assert 'E09' in codes(root, base_ref='missing-revision')


def test_packaged_schema_stays_in_sync():
    root = Path(__file__).resolve().parents[1]
    assert (root / 'awepep_co/tables.json').read_bytes() == (root / 'schema/tables.json').read_bytes()


def test_translation_staleness(tmp_path):
    root = dataset(tmp_path)
    directory = root / 'i18n/zh'
    directory.mkdir(parents=True)
    digest = hashlib.sha256(b'Founded').hexdigest()[:12]
    path = directory / 'strings.csv'
    path.write_text('key,zh_text,source_hash,status,translator,updated\nevent:x~2025~founded:summary,成立,'+digest+',reviewed,me,2025-01-01\n', encoding='utf-8')
    assert 'W06' not in codes(root)
    path.write_text(path.read_text().replace(digest,'123456789abc'))
    assert 'W06' in codes(root)
