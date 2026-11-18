# Contributing

Use Python 3.9 or newer:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
```

The CSV files in `data/` are the authoritative records. Add sources to `evidence.csv` and cite source IDs from relevant records. Consult the [inclusion](docs/inclusion-policy.md), [evidence](docs/evidence-policy.md), and [taxonomy](docs/taxonomy.md) policies before editing. Preserve IDs and existing entities and events; request maintainer review for exceptions. Findings with incomplete or conflicting evidence must be described conservatively. Preserve the original test fixtures: production source verification is tracked separately in [source review](docs/source-review.md).

For Codex-assisted work on a specified organization, the repo-local [`$curate-peptide-companies` skill](.codex/skills/curate-peptide-companies/SKILL.md) guides source verification, safe multi-table changes, and review. It does not imply permission to commit or push.

## Adding records

Before adding an organization, use `awepep-co lookup '质肽生物'` with its known names or ID. Lookup includes relationship stubs and searches the current source tables. An explicit `--as-of YYYY-MM-DD` selects the historical snapshot for that date. Exact normalized matches take precedence over substring matches. Review all matches before deciding whether a record is new.

Edit the source CSVs, or use `awepep-co add` with repeated `--field name=value` arguments for an `entity`, `event`, `evidence`, or `asset`. Field names and required values are defined by `schema/tables.json` and the controlled vocabulary in `vocab/`. For example, use `awepep-co add evidence --field evidence_id=... --field url=...` with the remaining required fields. All values must describe verified sources or conservatively identified reports. The command validates the resulting dataset, checks keys and references, and writes a sorted CSV only if validation succeeds. It does not generate pages.

## Review and generation

Use the curation transaction for changes that span multiple tables, such as adding a company together with its required scope and evidence tags. Run the skill's `prepare --with-preview` command to create a self-contained preview workspace and inspect its generated output before applying changes.

After changing knowledge inputs, record a new snapshot with the actual current date before validating or generating pages. Review the snapshot alongside the source changes; see [historical snapshots](docs/history.md) for scope and historical builds.

```bash
awepep-co history record --reason "Describe the verified changes"
awepep-co history check --require --base-ref origin/main
awepep-co validate
awepep-co validate --base-ref origin/main
awepep-co build --as-of "$(cat .build-date)"
awepep-co build --as-of "$(cat .build-date)" --check
python -m pytest
```

Generated files under `cards/`, `index/`, and the marked README section must be updated by the build, not edited manually. Include regenerated pages with source changes in the pull request. `build/` contains local artifacts and is ignored. A build is deterministic for the same input and `--as-of` date; source research is a separate, network-enabled activity. The committed `.build-date` sets the view checked by CI. When adding later events or advancing the published view, update this date and regenerate the pages in the same change. Review all changed records and generated pages.

## Source maintenance

```bash
awepep-co check-links
awepep-co stale --days 365 --as-of "$(cat .build-date)"
```

`check-links` performs read-only network requests for source and existing archive URLs. It reports `ok`, `broken`, or `unknown`; access restrictions, rate limits, and network failures are not proof of a broken link. It never creates archives or edits records. `stale` lists active entities past the age threshold, plus full entries without a verification date. Review a source before manually updating its `accessed` date. The default age is 365 days; both commands leave data unchanged. Routine `validate` and `build` remain offline.
