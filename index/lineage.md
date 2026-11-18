# Lineage

[← Home](../README.md) · [Names](by-name.md) · [Scope](by-scope.md) · [Types](by-type.md) · [Status](by-status.md) · [Modalities](by-modality.md)

Group context edges point to a parent group; see the company timeline for the signing subsidiary.

```mermaid
flowchart LR
    e0["AilsynBio"]
    e1["AIMEDORIG"]
    e2["Anew Labs"]
    e3["AstraZeneca"]
    e4["AstraZeneca Molecular AI"]
    e5["Bristol Myers Squibb"]
    e6["ByteDance"]:::stub
    e7["ByteDance AI4S team"]
    e8["China Resources Pharmaceutical Group"]:::stub
    e9["CSPC Pharmaceutical Group"]
    e10["Eli Lilly and Company"]
    e11["Gan & Lee Pharmaceuticals"]
    e12["Gilead Sciences"]
    e13["Hansoh Pharmaceutical Group"]
    e14["Jiangsu Hengrui Pharmaceuticals"]
    e15["HitGen"]
    e16["Huadong Medicine"]
    e17["Hybio Pharmaceutical"]
    e18["LigIT"]
    e19["Novartis"]
    e20["Novo Nordisk"]
    e21["PepStar Therapeutics Limited"]
    e22["PeptiOrigin"]
    e23["Peptway"]
    e24["Beijing QL Biopharmaceutical"]
    e25["Shanghai Pharmaceuticals Holding"]
    e26["Syneron Bio"]
    e27["碳云智肽"]
    e28["Viva Biotech"]
    e29["XtalPi Holdings"]
    a0["AnewDDE"]:::asset
    a1["PepINVENT"]:::asset
    a2["Protenix"]:::asset
    a3["REINVENT 4"]:::asset
    a4["Synova"]:::asset
    e0 -->|"Partnership (group context)"| e8
    e0 -->|"License deal (group context)"| e13
    e2 -.->|"Spun out"| e6
    e3 -->|"Parent"| e4
    e6 -->|"Parent"| e7
    e9 -->|"License deal"| e3
    e17 -->|"Partnership"| e27
    e26 -->|"Partnership"| e3
    e29 -->|"License deal"| e11
    e2 -->|"Developer"| a0
    e3 -->|"Licensee"| a4
    e4 -->|"Developer"| a1
    e4 -->|"Developer"| a3
    e7 -->|"Developer"| a2
    e7 -->|"Maintainer"| a2
    e26 -->|"Owner"| a4
    classDef stub stroke-dasharray: 5 5
    classDef asset fill:#eeeeee
```
