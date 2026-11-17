# Contributing

Use Python 3.9 or newer:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
```

The CSV files in `data/` are the authoritative records. Add sources to `evidence.csv` and cite their IDs from relevant records. Consult the [inclusion](docs/inclusion-policy.md), [evidence](docs/evidence-policy.md), and [taxonomy](docs/taxonomy.md) policies before editing. Preserve IDs and existing entities and events; request maintainer review for exceptions. Findings with incomplete or conflicting evidence must be described conservatively. Preserve the original test fixtures: production source verification is tracked separately in [source review](docs/source-review.md).

```bash
awepep-co validate
awepep-co validate --base-ref origin/main
awepep-co build --as-of "$(cat .build-date)"
python -m pytest
```

Generated files under `cards/`, `index/`, and the marked README section must be updated by the build, not edited manually. `build/` contains local artifacts and is ignored. A build is deterministic for the same input and `--as-of` date; source research is a separate, network-enabled activity. The committed `.build-date` sets the snapshot checked by CI. When adding later events or advancing the published snapshot, update this date and regenerate the pages in the same change. Review all changed records and generated pages. Automated commits, scheduled checks, and release publication are future work.
