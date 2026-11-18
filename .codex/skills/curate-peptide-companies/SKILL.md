---
name: curate-peptide-companies
description: Research and curate peptide-related companies or organizational teams with verified sources and evidence-linked records. Discover candidates only when explicitly requested; do not create personal profiles.
---

# Curate peptide companies

Work from the `awesome-peptide-company` repository root. This skill handles a user-identified organization, including a named pharma or technology-company team. Discover and evaluate additional organizations only when the user explicitly requests discovery, and stay within the requested scope. A normal editing request authorizes local source-data edits and regeneration, not a commit, push, PR, message, archive submission, or unrelated external write.

## Identify and research

1. Read `AGENTS.md`, sections 3–4 of `plan/awesome-ai4peptide-companies — Implementation Plan.md`, `docs/inclusion-policy.md`, `docs/evidence-policy.md`, `docs/taxonomy.md`, `schema/tables.json`, and `vocab/terms.csv`. Record the existing worktree state; preserve all pre-existing edits, including generated files.
2. Run `python -m awepep_co lookup 'NAME OR ID'` for the known Chinese and English names before creating an ID. Review every match, including relationship stubs. Distinguish the legal entity, parent, subsidiary, research team, and project using the cited records. Preserve existing entity and event IDs.
3. Research the requested facts using public sources. Prefer official materials, papers, filings and official repositories; open sources and check what each one actually says. Record `accessed` only for sources actually opened; an unreachable or search-snippet-only source is a lead, not a verified fact. Do not bypass paywalls, copy articles or silently resolve conflicts. Match supplied articles against existing evidence before adding sources or events; a repost or the same article is not an independent confirmation. Use conservative confidence, shared `origin_key` for reports derived from the same original, and evidence whose content supports the specific fact. If a source is unavailable or insufficient, leave the unsupported value empty or the existing value unchanged and report the gap.
4. For requested discovery, assess each candidate against the inclusion policy before preparing a batch. Record which entity the source describes, its peptide activity, and any specific AI connection. Use `docs/candidate-review.md` to capture the source, verification date and open question for leads requiring follow-up. Treat the announced agreement, confirmed closing, and subsequent project progress as distinct facts. Use each organization's disclosed role in joint work.

## Model changes

- Reuse a matching entity; create a lowercase kebab-case ID only for a truly new entity. Do not delete entities or rewrite/delete existing events. Record organizational changes with new evidence-backed events and aliases, preserving uncertainty; model parent-level relationships on the parent. If a correction cannot be represented without changing an old event, report it for maintainer review rather than silently rewriting history.
- Use an evidence-linked `directory_scope` tag for each qualifying full entry. `ai_peptide` requires a source connecting AI to peptide work by the organization or a named collaborator. `peptide_landscape` covers eligible established pharma and clinical-stage peptide biotechs whose AI connection remains unverified. For a clinical-stage biotech, verify the specific peptide and its development stage with a first-party source such as a trial registry, regulatory filing or sponsor disclosure. A trial authorization by itself establishes permission to start and a registry entry can still describe a planned trial. See `docs/inclusion-policy.md` for eligibility and `relevance_evidence_ids` requirements.
- Use an evidence-backed `preferred_zh` alias with `lang=zh` for the public Chinese display name. Observe any known validity dates, keep other names as aliases, and assign a single preferred name at any given date. Use the documented name when an official English rendering is unavailable.
- Use existing columns and controlled vocabulary. Write candidate CSVs as UTF-8 without BOM, with LF line endings and rows sorted by the schema primary key. Each evidence-bearing association cites supporting IDs. Entity and asset fields lack general evidence columns: ensure each new factual value has traceable supporting evidence through a genuinely relevant event, association, or curator note; never invent an event merely to attach a source. If this is not possible, leave it unset and report the limitation. A successful validator cannot establish factual support.
- Store free text in English, paraphrase sources, and keep titles in the source language. Use the source-supported occurrence date and original precision; if only disclosure date is known, record that date and say so in `note`. Do not infer a precise date. Only confirmed state events affect status. Label agent-drafted loop assessments `proposed` and omit a level when evidence is insufficient.
- Verify the actual contracting entities, scope and stage of each deal: an announced agreement is not evidence of a completed transaction, and a purchase of a program is not automatically a purchase of the company. Keep group-level relationships distinguishable from subsidiary signatories.
- Keep the identity of referenced evidence (`url`, `tier`, `origin_key`, `source_type`) stable. Correct non-identity metadata when supported; for a different source or a URL migration add a new evidence ID and document the correction, leaving historic event references intact. Escalate a correction that cannot be represented without rewriting history.
- Include an image only when it improves the card and its creator, provenance, reuse permission and depicted organization's identity are established; credit it as required. Do not copy images with unclear rights. Preserve the generated-file rule and review any source asset separately from the transaction helper's supported paths.

## Apply and verify

Before editing, run `awepep-co validate --base-ref origin/main` when that baseline exists. Report pre-existing failures. Put any intended candidate-review documentation updates in the project before preparing the batch so the preview captures them. Use a unique, nonexistent workspace path outside the repository.

```bash
python .codex/skills/curate-peptide-companies/scripts/transaction.py prepare --with-preview --root . --workspace /tmp/UNIQUE-WORKSPACE
# Edit /tmp/UNIQUE-WORKSPACE/data/*.csv and notes/<entity_id>.md as appropriate.
```

`--with-preview` copies the local build and test inputs together with the source tables, existing outputs and history. In the candidate set `.build-date` to the actual intended recording date. From inside that directory, run the following commands so Python imports the candidate package. Keep the preview snapshot in the candidate workspace.

```bash
python -m awepep_co history record --reason 'Describe the research change'
python -m awepep_co history check --require
python -m pytest
python -m awepep_co build --as-of "$(cat .build-date)"
python -m awepep_co build --as-of "$(cat .build-date)" --check
```

Before accepting that preview, run `git status --porcelain -- README.md cards index` to identify pre-existing staged, unstaged, and untracked generated paths. Inspect both `git diff --cached -- README.md cards index` and `git diff -- README.md cards index`, including untracked file contents, then compare with the candidate-generated files and any candidate deletions. If the build would overwrite or delete pre-existing user content, including staged changes or untracked files, stop and preserve it. In a checkout without Git, compare each existing README/generated file with its candidate output and preserve any content that would change when ownership is unclear. The later `guard` checks changes since preparation; it does not identify or authorize overwriting edits that existed beforehand.

```bash
python .codex/skills/curate-peptide-companies/scripts/transaction.py apply --root . --workspace /tmp/UNIQUE-WORKSPACE --file data/entities.csv --file data/evidence.csv
```

Replace the example workspace and `--file` arguments with the actual path and every intentionally changed source file, including `.build-date` if changed. The helper snapshots current data (including user edits), validates the candidate, protects old events, entity IDs and referenced source identities, checks for concurrent changes, and attempts rollback on failure without overwriting another edit. Multi-file atomicity cannot be guaranteed against external writers; inspect and report any unresolved conflict. For a single new row `awepep-co add` is also available, but it is not a multi-table transaction.

After successful application and immediately before recording the real snapshot, check that generated files and rendering inputs, including `docs/`, `assets/`, and `history/`, have not changed since the preview:

```bash
python .codex/skills/curate-peptide-companies/scripts/transaction.py guard --root . --workspace /tmp/UNIQUE-WORKSPACE
```

If the guard fails, stop before recording or building and report the conflict. After it succeeds, record the actual changed sources with `python -m awepep_co history record --reason 'Describe the research change'` and run `python -m awepep_co history check --require`. Only then run `awepep-co validate --base-ref origin/main` when the baseline exists, `python -m pytest`, and `awepep-co build --as-of "$(cat .build-date)"` followed by the same command with `--check`: validation before recording would reject the intentional source changes. Snapshot dates reflect actual recording, not retroactive knowledge; `--as-of` before the history baseline cannot reconstruct earlier states. The guard cannot eliminate every race with an external writer between checking, recording and building. Generate `cards/`, `index/` and the README index section only through `build`, not by hand.

Review the resulting diff and report what changed, evidence and source tiers for status changes, unresolved claims, checks and warnings. If no qualifying evidence was found, do not fabricate a minimal entry just to finish.
