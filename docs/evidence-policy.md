# Evidence policy

Record source metadata in `data/evidence.csv`; reference source IDs from the records they support. A source supports only what it actually says. Preserve conflicting accounts in notes and leave unsupported details blank. Do not store copyrighted articles or bypass paywalls.

- **A:** primary institutional publications, official repositories, peer-reviewed papers, preprints, regulatory filings, patents, and official releases.
- **B:** independent reporting based on original reporting or interviews. Copies of one report share an `origin_key`.
- **C:** other material, including recruitment pages, aggregators, social media, and encyclopedias.

A claim can be `confirmed` with an A source or two independent B origins, `reported` with one B origin, and `rumor` with C sources. Curators may choose a lower confidence where a source supports only part of a claim. Only confirmed status events change the derived status. An event date represents its evidenced occurrence; if only its disclosure date is known, use that date and explain this in `note`. Never infer a precise date from a partial one.

Use `claimed`, `documented`, and `verified` to distinguish stated loop capability from detailed documentation and independently reusable public outputs. Agent-created assessments require maintainer review.

The derived `active` status means that qualifying public activity has been recorded and no confirmed terminal event supersedes it; it is not proof that an organization currently operates. `last_verified` is the latest eligible source access date, not a date on which continued operations were verified. Old evidence may trigger a review warning, but does not automatically change status.
