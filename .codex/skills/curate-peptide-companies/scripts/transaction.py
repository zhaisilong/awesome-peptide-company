#!/usr/bin/env python3
"""Prepare and apply validated source changes with best-effort rollback.

Multiple files cannot be atomically replaced as a group; concurrent writers
that ignore this tool can still race. The tool never overwrites a changed file
while rolling back.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from awepep_co.validation import HEADERS, PRIMARY_KEYS, validate  # noqa: E402

MANIFEST = '.company-edit-snapshot.json'
TABLES = tuple('data/' + name + '.csv' for name in HEADERS)
EDITABLE = set(TABLES) | {'.build-date'}
NOTE = re.compile(r'notes/[a-z0-9]+(?:-[a-z0-9]+)*\.md\Z')


def _digest(content):
    return hashlib.sha256(content).hexdigest()


def _render_files(root):
    """Snapshot user-editable render inputs and generated targets."""
    result = {}
    readme = root / 'README.md'
    if readme.is_symlink():
        raise ValueError('symlink render input: README.md')
    if readme.is_file():
        result['README.md'] = readme.read_bytes()
    for dirname in ('templates', 'cards', 'index', 'awepep_co'):
        base = root / dirname
        if base.is_symlink():
            raise ValueError('symlink render directory: ' + dirname)
        if not base.exists():
            continue
        if not base.is_dir():
            raise ValueError('not a render directory: ' + dirname)
        for path in sorted(base.rglob('*')):
            if path.is_symlink():
                raise ValueError('symlink render input: ' + str(path.relative_to(root)))
            if path.is_file() and (dirname != 'awepep_co' or path.suffix in ('.py', '.json')):
                result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def _hashes(files):
    return {name: _digest(value) for name, value in files.items()}


def _files(root):
    result = {}
    for directory in ('data', 'vocab', 'schema', 'i18n', 'notes'):
        base = root / directory
        if base.is_symlink():
            raise ValueError('symlink source directory: ' + directory)
        if base.exists():
            if not base.is_dir():
                raise ValueError('not a source directory: ' + directory)
            for path in sorted(base.rglob('*')):
                if path.is_symlink():
                    raise ValueError('symlink source file: ' + str(path.relative_to(root)))
                if path.is_file():
                    result[path.relative_to(root).as_posix()] = path.read_bytes()
    for name in ('.build-date', 'awepep_co/tables.json'):
        path = root / name
        if path.is_symlink():
            raise ValueError('symlink source file: ' + name)
        if path.is_file():
            result[name] = path.read_bytes()
    return result


def _paths(root, workspace):
    root, workspace = Path(root).resolve(), Path(workspace).resolve()
    if workspace == root or root in workspace.parents or workspace in root.parents:
        raise ValueError('workspace must be outside the project and its ancestors')
    return root, workspace


def prepare(root, workspace):
    root, workspace = _paths(root, workspace)
    snapshot = _files(root)
    for name in TABLES + ('.build-date', 'awepep_co/tables.json'):
        if name not in snapshot:
            raise ValueError('missing source file: ' + name)
    if not (root / 'vocab').is_dir():
        raise ValueError('missing vocab directory')
    workspace.mkdir(parents=True, exist_ok=False)
    try:
        for name, content in snapshot.items():
            path = workspace / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        manifest = {'root': str(root), 'files': _hashes(snapshot), 'render_files': _hashes(_render_files(root))}
        (workspace / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    except BaseException:
        shutil.rmtree(workspace)
        raise


def _csv_rows(content, table):
    reader = csv.DictReader(io.StringIO(content.decode('utf-8'), newline=''), strict=True)
    if reader.fieldnames != HEADERS[table]:
        raise ValueError('invalid header in ' + table)
    rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError('malformed row in ' + table)
    return rows


def _protected(before, after):
    old_entities = _csv_rows(before['data/entities.csv'], 'entities')
    new_entities = _csv_rows(after['data/entities.csv'], 'entities')
    old_ids = {row['entity_id'] for row in old_entities}
    new_ids = {row['entity_id'] for row in new_entities}
    if not old_ids <= new_ids:
        raise ValueError('cannot delete or change an existing entity ID')
    old_events = _csv_rows(before['data/events.csv'], 'events')
    new_events = _csv_rows(after['data/events.csv'], 'events')
    by_id = {row['event_id']: row for row in new_events}
    if any(by_id.get(row['event_id']) != row for row in old_events):
        raise ValueError('existing events must not be deleted or modified')
    return new_ids


def _atomic_write(path, content, mode):
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.company-edit-', delete=False) as stream:
            temp = Path(stream.name)
            os.chmod(temp, mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temp), str(path))
        temp = None
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def apply(root, workspace, files):
    root, workspace = _paths(root, workspace)
    if not files or len(set(files)) != len(files):
        raise ValueError('specify each changed file exactly once with --file')
    if any(name not in EDITABLE and not NOTE.fullmatch(name) for name in files):
        raise ValueError('only source CSV tables, entity notes, and .build-date may be changed')
    manifest = json.loads((workspace / MANIFEST).read_text(encoding='utf-8'))
    if manifest.get('root') != str(root) or not isinstance(manifest.get('files'), dict):
        raise ValueError('invalid snapshot or workspace belongs to a different project')
    before = _files(root)
    if _hashes(before) != manifest['files']:
        raise ValueError('project inputs changed since prepare; create a fresh workspace')
    if _hashes(_render_files(root)) != manifest.get('render_files'):
        raise ValueError('render inputs or outputs changed since prepare; create a fresh workspace')
    after = _files(workspace)
    if set(before) - set(after) or any(name not in before and not NOTE.fullmatch(name) for name in after):
        raise ValueError('source files were removed or unsupported files were added')
    changed = {name for name in after if before.get(name) != after[name]}
    if changed != set(files):
        raise ValueError('the explicit file list must match all changed inputs')
    for name in sorted(changed & set(TABLES)):
        content = after[name]
        if content.startswith(b'\xef\xbb\xbf') or b'\r' in content or not content.endswith(b'\n'):
            raise ValueError(name + ': expected UTF-8 without BOM and LF line endings')
        table = Path(name).stem
        rows = _csv_rows(content, table)
        keys = [tuple(row[col] for col in PRIMARY_KEYS[table]) for row in rows]
        if keys != sorted(keys):
            raise ValueError(name + ': rows must be sorted by primary key')
    if '.build-date' in changed:
        try:
            raw = after['.build-date'].decode('utf-8')
            proposed = date.fromisoformat(raw.strip())
            previous = date.fromisoformat(before['.build-date'].decode('utf-8').strip())
            if raw != proposed.isoformat() + '\n':
                raise ValueError
        except (ValueError, UnicodeError):
            raise ValueError('.build-date must be YYYY-MM-DD followed by LF')
        if proposed < previous:
            raise ValueError('.build-date cannot move backwards')
        if proposed > date.today():
            raise ValueError('.build-date cannot be in the future')
    entity_ids = _protected(before, after)
    for name in changed:
        if NOTE.fullmatch(name):
            if Path(name).stem not in entity_ids:
                raise ValueError('note must refer to an existing entity: ' + name)
            after[name].decode('utf-8')
    issues = validate(workspace)
    errors = [issue for issue in issues if issue.severity == 'error']
    if errors:
        raise ValueError('candidate validation failed:\n' + '\n'.join(map(str, errors)))
    if _files(root) != before or _hashes(_render_files(root)) != manifest['render_files']:
        raise ValueError('project inputs changed during validation; retry')
    written = []
    try:
        for name in sorted(changed):
            if (_files(root) != {**before, **{key: after[key] for key in written}}
                    or _hashes(_render_files(root)) != manifest['render_files']):
                raise ValueError('project inputs changed during apply; retry')
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
            _atomic_write(path, after[name], mode)
            written.append(name)
        expected = {**before, **{key: after[key] for key in written}}
        if _files(root) != expected or _hashes(_render_files(root)) != manifest['render_files']:
            raise ValueError('project inputs changed during apply; retry')
        manifest['applied_files'] = _hashes(expected)
        manifest_path = workspace / MANIFEST
        _atomic_write(manifest_path, (json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode('utf-8'), 0o600)
    except BaseException as exc:
        errors = []
        for name in reversed(written):
            path = root / name
            try:
                if not path.is_symlink() and path.read_bytes() == after[name]:
                    if name in before:
                        _atomic_write(path, before[name], stat.S_IMODE(path.stat().st_mode))
                    else:
                        path.unlink()
                else:
                    errors.append(name + ': changed concurrently; not overwritten')
            except OSError as error:
                errors.append(name + ': ' + str(error))
        if errors:
            raise RuntimeError('apply failed; rollback incomplete: ' + '; '.join(errors)) from exc
        raise
    return [issue for issue in issues if issue.severity == 'warning']


def guard(root, workspace):
    """Abort before build if source inputs or output targets changed since apply."""
    root, workspace = _paths(root, workspace)
    manifest = json.loads((workspace / MANIFEST).read_text(encoding='utf-8'))
    if manifest.get('root') != str(root) or not isinstance(manifest.get('applied_files'), dict):
        raise ValueError('workspace has not applied changes to this project')
    if _hashes(_files(root)) != manifest['applied_files']:
        raise ValueError('project inputs changed since apply; do not build')
    if _hashes(_render_files(root)) != manifest.get('render_files'):
        raise ValueError('render inputs or output files changed since prepare; do not build')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('prepare', 'apply', 'guard'):
        command = sub.add_parser(action)
        command.add_argument('--root', type=Path, default=Path.cwd())
        command.add_argument('--workspace', type=Path, required=True)
        if action == 'apply':
            command.add_argument('--file', action='append', required=True, dest='files')
    args = parser.parse_args(argv)
    try:
        if args.action == 'prepare':
            prepare(args.root, args.workspace)
            print('Prepared candidate workspace:', args.workspace)
        elif args.action == 'apply':
            issues = apply(args.root, args.workspace, args.files)
            for issue in issues:
                print(issue)
            print('Applied validated source files:', ', '.join(sorted(args.files)))
        else:
            guard(args.root, args.workspace)
            print('Source inputs and generated output targets are unchanged since apply.')
    except (OSError, ValueError, RuntimeError, csv.Error, UnicodeError) as exc:
        print('Error:', exc, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
