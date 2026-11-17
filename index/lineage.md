# Lineage

[← Home](../README.md) · [Scope](by-scope.md) · [Types](by-type.md) · [Status](by-status.md) · [Modalities](by-modality.md)

Group context edges point to a parent group; see the company timeline for the signing subsidiary.

```mermaid
flowchart LR
    e0["AilsynBio"]
    e1["Anew Labs"]
    e2["AstraZeneca"]
    e3["AstraZeneca Molecular AI"]
    e4["Bristol Myers Squibb"]
    e5["ByteDance"]:::stub
    e6["ByteDance AI4S team"]
    e7["China Resources Pharmaceutical Group"]:::stub
    e8["Eli Lilly and Company"]
    e9["Gan & Lee Pharmaceuticals"]
    e10["Gilead Sciences"]
    e11["Hansoh Pharmaceutical Group"]
    e12["Novartis"]
    e13["Novo Nordisk"]
    e14["Peptway"]
    e15["Syneron Bio"]
    a0["AnewDDE"]:::asset
    a1["PepINVENT"]:::asset
    a2["Protenix"]:::asset
    a3["REINVENT 4"]:::asset
    a4["Synova"]:::asset
    e0 -->|"Partnership (group context)"| e7
    e0 -->|"License deal (group context)"| e11
    e1 -.->|"Spun out"| e5
    e2 -->|"Parent"| e3
    e5 -->|"Parent"| e6
    e15 -->|"Partnership"| e2
    e1 -->|"Developer"| a0
    e2 -->|"Licensee"| a4
    e3 -->|"Developer"| a1
    e3 -->|"Developer"| a3
    e6 -->|"Developer"| a2
    e6 -->|"Maintainer"| a2
    e15 -->|"Owner"| a4
    classDef stub stroke-dasharray: 5 5
    classDef asset fill:#eeeeee
```
