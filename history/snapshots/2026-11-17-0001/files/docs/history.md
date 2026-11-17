# Historical knowledge snapshots

The CSV files remain the source of truth. Snapshots preserve what this directory recorded, starting with the v0.3.1 migration baseline. Earlier knowledge states cannot be reconstructed reliably and a historical build before that baseline fails. A snapshot is not proof of when the underlying event actually occurred or when the world first knew it.

After completing a set of source changes, validate the candidate, then record the current knowledge before building and committing:

```bash
python -m awepep_co history record --reason "Describe the verified changes"
python -m awepep_co history check --require
python -m awepep_co build --as-of "$(cat .build-date)"
```

Snapshots include source CSVs, notes, vocabulary, schema, translations, project research documentation, assets, and the manually maintained README text. Each revision stores its reason, date, content hashes, and previous manifest hash. Do not edit or remove an existing snapshot. A changed source file without a new snapshot fails validation. CI compares snapshots against the pull request base to detect changes to already recorded revisions. Same-day revisions are ordered, and a date-only query selects the last revision recorded that day; intraday reconstruction is not provided.

Build a historical view into a new empty directory without touching the current pages:

```bash
python -m awepep_co build --as-of 2026-11-17 --output-dir build/history-review
```

The date selects the last snapshot on or before that day. The historical knowledge content comes from that snapshot; page templates and renderer behavior use the current version and are not a byte-for-byte reconstruction of an old website. Events with only a year or month become visible only after the entire possible date range has passed. Alias validity is likewise conservative. Sources accessed or added later cannot enter an earlier snapshot.
