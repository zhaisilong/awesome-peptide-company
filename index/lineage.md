# Lineage

[← Home](../README.md) · [Types](by-type.md) · [Status](by-status.md) · [Modalities](by-modality.md)

```mermaid
flowchart LR
    e0["Anew Labs"]
    e1["AstraZeneca"]:::stub
    e2["AstraZeneca Molecular AI"]
    e3["ByteDance"]:::stub
    e4["ByteDance AI4S team"]
    e5["Syneron Bio"]
    a0["AnewDDE"]:::asset
    a1["PepINVENT"]:::asset
    a2["Protenix"]:::asset
    a3["REINVENT 4"]:::asset
    a4["Synova"]:::asset
    e0 -.->|"Spun out"| e3
    e1 -->|"Parent"| e2
    e3 -->|"Parent"| e4
    e5 -->|"Partnership"| e1
    e0 -->|"Developer"| a0
    e1 -->|"Licensee"| a4
    e2 -->|"Developer"| a1
    e2 -->|"Developer"| a3
    e4 -->|"Developer"| a2
    e4 -->|"Maintainer"| a2
    e5 -->|"Owner"| a4
    classDef stub stroke-dasharray: 5 5
    classDef asset fill:#eeeeee
```
