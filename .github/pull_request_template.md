## Changes

Describe the change and its evidence.

## Checklist

- [ ] Factual claims cite sources that support them; conflicting or uncertain information is clearly marked.
- [ ] Source text is paraphrased and does not contain rankings, purchase links, discount codes, or dosing instructions.
- [ ] Existing entity and event IDs are preserved; agent-authored loop assessments remain proposed.
- [ ] I ran `awepep-co validate`, regenerated pages with `awepep-co build --as-of "$(cat .build-date)"`, and ran `python -m pytest`.
- [ ] I reviewed the generated cards and indexes and updated `.build-date` if the published snapshot advanced.
