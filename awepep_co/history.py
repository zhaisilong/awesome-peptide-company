"""Append-only, day-granularity snapshots of the directory's knowledge inputs."""
import csv
import hashlib
import io
import json
import shutil
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

SOURCE_DIRS = ("data", "vocab", "notes", "i18n", "schema", "docs", "assets")
HISTORY = Path("history/snapshots")


def _digest(content):
    return hashlib.sha256(content).hexdigest()


def source_files(root):
    root = Path(root)
    result = {}
    for directory in SOURCE_DIRS:
        path = root / directory
        if path.is_dir():
            for file in sorted(path.rglob("*")):
                if file.is_file():
                    if file.is_symlink():
                        raise ValueError("snapshot inputs must not be symlinks: {}".format(file))
                    result[file.relative_to(root).as_posix()] = file.read_bytes()
    readme = root / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        begin, end = "<!-- BEGIN:INDEX -->", "<!-- END:INDEX -->"
        if text.count(begin) == 1 and text.count(end) == 1 and text.index(begin) < text.index(end):
            text = text[:text.index(begin) + len(begin)] + "\n" + text[text.index(end):]
        result["README.md"] = text.encode("utf-8")
    return result


def _snapshot_dirs(root):
    path = Path(root) / HISTORY
    return sorted(p for p in path.iterdir() if p.is_dir()) if path.exists() else []


def _manifest(path):
    return json.loads((path / "manifest.json").read_text(encoding="utf-8"))


def check(root, base_ref=None, require=False, current=True):
    """Verify snapshots, append-only Git baseline and (optionally) current inputs."""
    root = Path(root)
    snapshots = _snapshot_dirs(root)
    if not snapshots:
        if require:
            raise ValueError("no knowledge snapshot exists; record a baseline first")
        return
    previous = ""
    for path in snapshots:
        metadata = _manifest(path)
        day = date.fromisoformat(metadata["date"])
        if not path.name.startswith(day.isoformat() + "-") or len(path.name) != 15 or not path.name[-4:].isdigit():
            raise ValueError("invalid snapshot directory {}".format(path.name))
        if metadata.get("previous") != previous or not metadata.get("reason", "").strip():
            raise ValueError("snapshot chain or reason invalid: {}".format(path.name))
        files = source_files(path / "files")
        hashes = {key: _digest(value) for key, value in files.items()}
        archived = {f.relative_to(path).as_posix() for f in path.rglob("*") if f.is_file()}
        expected = {"manifest.json"} | {"files/" + name for name in hashes}
        if hashes != metadata.get("files") or archived != expected:
            raise ValueError("snapshot content does not match its manifest: {}".format(path.name))
        previous = _digest((path / "manifest.json").read_bytes())
    if current and source_files(root) != source_files(snapshots[-1] / "files"):
        raise ValueError("knowledge inputs differ from latest snapshot; run history record")
    if base_ref:
        result = subprocess.run(["git", "diff", "--name-status", "--no-renames", base_ref, "--", HISTORY.as_posix()], cwd=root, text=True, capture_output=True)
        if result.returncode:
            raise ValueError("cannot compare snapshot history with {}".format(base_ref))
        old = subprocess.run(["git", "ls-tree", "--name-only", base_ref + ":history/snapshots"], cwd=root, text=True, capture_output=True)
        old_names = set(old.stdout.splitlines()) if old.returncode == 0 else set()
        for line in result.stdout.splitlines():
            status, _, name = line.partition("\t")
            parts = Path(name).parts
            if status != "A" or (len(parts) > 2 and parts[2] in old_names):
                raise ValueError("existing snapshots are append-only: {}".format(line))


def record(root, reason, day=None):
    """Record the complete current knowledge state as one immutable revision."""
    root = Path(root)
    if not reason.strip():
        raise ValueError("a snapshot reason is required")
    day = day or date.today()
    if day > date.today():
        raise ValueError("snapshot date cannot be in the future")
    check(root, current=False)
    previous = _snapshot_dirs(root)
    if previous and day.isoformat() < _manifest(previous[-1])["date"]:
        raise ValueError("cannot backdate a snapshot")
    before = source_files(root)
    if not before or not any(k.startswith("data/") for k in before):
        raise ValueError("source data is missing")
    # A snapshot cannot honestly contain a source not yet published or accessed.
    for evidence in csv.DictReader(io.StringIO(before["data/evidence.csv"].decode("utf-8"))):
        for field in ("published", "accessed"):
            value = evidence.get(field, "")
            if value:
                parts = [int(part) for part in value.split("-")]
                earliest = date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
                if earliest > day:
                    raise ValueError("source {} has a future {} date".format(evidence.get("evidence_id"), field))
    base = root / HISTORY
    base.mkdir(parents=True, exist_ok=True)
    sequence = 1
    while (base / (day.isoformat() + "-{:04d}".format(sequence))).exists():
        sequence += 1
    path = base / (day.isoformat() + "-{:04d}".format(sequence))
    path.mkdir()
    try:
        for name, content in before.items():
            dest = path / "files" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
        if source_files(root) != before:
            raise ValueError("knowledge inputs changed during snapshot; retry")
        metadata = {"date": day.isoformat(), "created_at": datetime.now(timezone.utc).isoformat(),
                    "reason": reason.strip(), "previous": _digest((previous[-1] / "manifest.json").read_bytes()) if previous else "",
                    "files": {key: _digest(value) for key, value in before.items()}}
        (path / "manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(path)
        raise
    return path


def select(root, as_of):
    """Return the latest snapshot no later than the requested calendar day."""
    check(root, current=False)
    matching = [p for p in _snapshot_dirs(root) if _manifest(p)["date"] <= as_of.isoformat()]
    if not matching:
        raise ValueError("historical knowledge is unavailable before the snapshot baseline")
    return matching[-1] / "files"
