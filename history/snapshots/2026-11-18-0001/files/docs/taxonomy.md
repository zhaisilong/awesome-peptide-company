# Taxonomy

`vocab/` contains the machine-readable controlled vocabulary. Entities may be pharmaceutical companies, AI-native biotech companies, named pharmaceutical or technology-company AI teams, peptide therapeutics companies, platform vendors, CDMOs, or parent-organization stubs. Relevance is `core`, `adjacent`, or `infrastructure`. See the [inclusion policy](inclusion-policy.md).

Loop levels range from L0 (computational only) to L4 (a documented L3 design–synthesis–test–learn loop plus dedicated large-scale training data and clinical pipeline). L1 indicates external wet validation, L2 an in-house laboratory with data feedback, and L3 a continuous loop with high-throughput or automated synthesis and testing. A level is not assigned without supporting public information, and the overall index shows only reviewed assessments.

Tags group modalities, computational methods, experimental capabilities, therapeutic areas, and development stages. Add any needed term to the controlled vocabulary before using it.

The evidence-linked `directory_scope` tag separates `ai_peptide` (a documented AI–peptide connection, including a clearly attributed collaboration) from `peptide_landscape` (peptide work is documented, but a direct AI connection is not established). An untagged existing entry is shown as **Scope pending review**; absence of the tag does not establish either classification. A full `pharma_company` requires exactly one directory scope tag. Scope describes the documented connection, not the company's size, ownership of an AI platform, or proof that an announced project is complete.

Use `preferred_zh` for a sourced Chinese display name in the aliases table. An entity can have one such name at a time. Use validity dates when known, and use `zh_name` for other documented Chinese names. The index adds the current Chinese display name to the canonical name when they differ.
