import shutil
from pathlib import Path

from awepep_co.cli import main

ROOT = Path(__file__).resolve().parents[1]


def project(tmp_path):
    for directory in ('data', 'vocab', 'templates'):
        shutil.copytree(ROOT / directory, tmp_path / directory)
    shutil.copy(ROOT / 'README.md', tmp_path / 'README.md')
    return tmp_path


def test_build_check_detects_changes_and_does_not_write(tmp_path, capsys):
    root = project(tmp_path)
    args = ['build', '--root', str(root), '--as-of', '2026-11-17']
    assert main(args) == 0
    assert main(args + ['--check']) == 0
    card = root / 'cards/anew-labs/README.md'
    card.write_text('edited manually\n', encoding='utf-8')
    assert main(args + ['--check']) == 1
    assert card.read_text(encoding='utf-8') == 'edited manually\n'
    assert 'Generated file differs' in capsys.readouterr().err
    assert main(args) == 0
    assert main(args + ['--check']) == 0


def test_strict_validation_fails_on_warnings(tmp_path):
    root = project(tmp_path)
    args = ['validate', '--root', str(root), '--as-of', '2026-11-17']
    assert main(args) == 0
    assert main(args + ['--strict']) == 1


def test_build_with_git_baseline_writes_change_preview(tmp_path):
    import subprocess

    root = project(tmp_path)
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
    subprocess.run(['git', 'add', 'data'], cwd=root, check=True)
    subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.org', 'commit', '-qm', 'baseline'], cwd=root, check=True)
    tags = root / 'data/tags.csv'
    tags.write_text(tags.read_text(encoding='utf-8') + 'anew-labs,dry,docking,anew-labs-dpsa\n', encoding='utf-8')
    assert main(['build', '--root', str(root), '--as-of', '2026-11-17', '--base-ref', 'HEAD']) == 0
    preview = (root / 'build/CHANGES_PREVIEW.md').read_text(encoding='utf-8')
    assert 'tags' in preview and 'anew-labs / dry / docking' in preview
