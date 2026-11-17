---
name: curate-peptide-companies
description: Add or update a specified company or organizational team in the awesome-peptide-company directory using verified sources and evidence-linked CSV records. Use when curating an identified organization, not for unsolicited discovery or personal profiles.
---

# Curate peptide companies

Work from the `awesome-peptide-company` repository root. This skill handles a user-identified organization, including a named pharma or technology-company team. Only work on the requested entities and facts; do not prospect for additional companies. A normal editing request authorizes local source-data edits and regeneration, not a commit, push, PR, message, archive submission, or unrelated external write.

## Identify and research

1. Read `AGENTS.md`, sections 3–4 of `plan/awesome-ai4peptide-companies — Implementation Plan.md`, `docs/inclusion-policy.md`, `docs/evidence-policy.md`, `docs/taxonomy.md`, `schema/tables.json`, and `vocab/terms.csv`. Record the existing worktree state; preserve all pre-existing edits, including generated files.
2. Search `data/entities.csv` and `data/aliases.csv` for the requested name and variants before creating an ID. Inspect relevant entity, parent, aliases, events, evidence, assets and roles, tags, assessments and paper links. Ask only when the identity is genuinely ambiguous. Keep existing `entity_id` and all historical event IDs.
3. Research the requested facts using public sources. Prefer official materials, papers, filings and official repositories; open sources and check what each one actually says. Record `accessed` only for sources actually opened; an unreachable or search-snippet-only source is a lead, not a verified fact. Do not bypass paywalls, copy articles or silently resolve conflicts. Use conservative confidence, shared `origin_key` for reports derived from the same original, and evidence whose content supports the specific fact. If a source is unavailable or insufficient, leave the unsupported value empty or the existing value unchanged and report the gap.

## Model changes

- Reuse a matching entity; create a lowercase kebab-case ID only for a truly new entity. Do not delete entities or rewrite/delete existing events. Record organizational changes with new evidence-backed events and aliases, preserving uncertainty; model parent-level relationships on the parent. If a correction cannot be represented without changing an old event, report it for maintainer review rather than silently rewriting history.
- For inclusion, require evidence connecting the organization itself to peptides. An `adjacent` or `infrastructure` full entry needs qualifying `relevance_evidence_ids`; otherwise use a stub only if justified, or leave it out. Mere use of an asset by others does not prove an entity owns or maintains it.
- Use existing columns and controlled vocabulary. Write candidate CSVs as UTF-8 without BOM, with LF line endings and rows sorted by the schema primary key. Each evidence-bearing association cites supporting IDs. Entity and asset fields lack general evidence columns: ensure each new factual value has traceable supporting evidence through a genuinely relevant event, association, or curator note; never invent an event merely to attach a source. If this is not possible, leave it unset and report the limitation. A successful validator cannot establish factual support.
- Store free text in English, paraphrase sources, and keep titles in the source language. Use the source-supported occurrence date and original precision; if only disclosure date is known, record that date and say so in `note`. Do not infer a precise date. Only confirmed state events affect status. Label agent-drafted loop assessments `proposed` and omit a level when evidence is insufficient.

## Apply and verify

Before editing, run `awepep-co validate --base-ref origin/main` when that baseline exists; report pre-existing failures rather than hiding them. Prepare a unique, nonexistent workspace path outside the repository and use the helper:

```bash
python .codex/skills/curate-peptide-companies/scripts/transaction.py prepare --root . --workspace /tmp/UNIQUE-WORKSPACE
# Edit /tmp/UNIQUE-WORKSPACE/data/*.csv and notes/<entity_id>.md as appropriate.
```

Before applying, advance `.build-date` in the candidate if needed to include newly verified facts or their access dates, following `CONTRIBUTING.md`; never set it beyond the actual current date. Preview the fixed-date build in the candidate workspace. The helper snapshots data, vocabulary, notes, translations and schema; copy the current `README.md`, `CONTRIBUTING.md`, `LICENSE`, `pyproject.toml`, `docs/`, `templates/`, `assets/`, `cards/`, `index/`, `tests/`, `.codex/`, and complete `awepep_co/` there for the preview. From that workspace run `python -m pytest`, `python -m awepep_co build --as-of "$(cat .build-date)"`, and then the same build command with `--check`, ensuring the copied package is used rather than an editable install pointing at the real checkout.

Before accepting that preview, run `git status --porcelain -- README.md cards index` to identify pre-existing staged, unstaged, and untracked generated paths. Inspect both `git diff --cached -- README.md cards index` and `git diff -- README.md cards index`, including untracked file contents, then compare with the candidate-generated files and any candidate deletions. If the build would overwrite or delete pre-existing user content, including staged changes or untracked files, stop and preserve it. In a checkout without Git, compare each existing README/generated file with its candidate output and preserve any content that would change when ownership is unclear. The later `guard` checks changes since preparation; it does not identify or authorize overwriting edits that existed beforehand.

```bash
python .codex/skills/curate-peptide-companies/scripts/transaction.py apply --root . --workspace /tmp/UNIQUE-WORKSPACE --file data/entities.csv --file data/evidence.csv
```

Replace the example workspace and `--file` arguments with the actual path and every intentionally changed source file, including `.build-date` if changed. The helper snapshots current data (including user edits), validates the candidate, protects old events and entity IDs, checks for concurrent changes, and attempts rollback on failure without overwriting another edit. Multi-file atomicity cannot be guaranteed against external writers; inspect and report any unresolved conflict. For a single new row `awepep-co add` is also available, but it is not a multi-table transaction.

For source changes, after successful application run `awepep-co validate --base-ref origin/main` when the baseline exists and `python -m pytest`. Immediately before generating the real checkout, check that its generated files and rendering inputs have not changed since the preview:

```bash
python .codex/skills/curate-peptide-companies/scripts/transaction.py guard --root . --workspace /tmp/UNIQUE-WORKSPACE
```

If the guard fails, stop before building and report the conflict. After it succeeds, run `awepep-co build --as-of "$(cat .build-date)"` followed by `awepep-co build --as-of "$(cat .build-date)" --check`. The check cannot eliminate every race with an external writer between guard and build. Generate `cards/`, `index/` and the README index section only through `build`, not by hand.

Review the resulting diff and report what changed, evidence and source tiers for status changes, unresolved claims, checks and warnings. If no qualifying evidence was found, do not fabricate a minimal entry just to finish.
