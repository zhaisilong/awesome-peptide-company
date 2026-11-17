# Agent instructions

- Read sections 3 and 4 of `plan/awesome-ai4peptide-companies — Implementation Plan.md` and the policies in `docs/` before changing records.
- The CSV files in `data/` are the source of truth. Edit data, vocabularies, notes, templates, translations, and code as appropriate; never manually edit generated `cards/`, `index/`, or `build/`.
- Link factual claims to evidence. Leave unsupported fields empty, and do not promote uncertain events to confirmed. Keep conflicting source claims visible in notes.
- Use controlled vocabulary and preserve entity and event IDs. Do not delete entity or event records without maintainer approval.
- Paraphrase sources; do not paste articles or bypass paywalls. No rankings, purchase links, discount codes, dosing instructions, gray-market suppliers, or personal profiles.
- Agent-drafted loop assessments are `proposed`. For status changes, describe the supporting source tiers.
- Run the tests and validation, then regenerate pages when data or rendering changes. Use a fixed `--as-of` for reproducible comparisons.
