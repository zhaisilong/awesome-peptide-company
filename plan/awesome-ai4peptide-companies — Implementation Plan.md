# awesome-ai4peptide-companies — Implementation Plan

Nov 17, 2026 · @Silong Zhai

## 1. 目标与范围

本项目以一组 CSV 作为唯一数据源，自动生成每个机构一张 README 名片和多种索引；收录 AI × 多肽（尤其是干湿结合）的公司、药企 AI 团队和大厂 AI 团队，并用带证据的事件流追踪它们的状态变化。

**收录对象（`entity_type`）**

- `ai_native_biotech`：以 AI 平台加自有湿实验为核心的公司（案例：元思生肽）
- `pharma_ai_team`：大药厂内部有公开署名的 AI 团队（案例：AstraZeneca Molecular AI）
- `bigtech_ai_team`：互联网或科技大厂的 AI4Science 团队（案例：字节 Seed AI4S 团队，后拆分）
- `peptide_therapeutics`、`platform_vendor`、`cdmo`：按需补充
- `parent_org`：只作母公司占位的 stub（如 AstraZeneca、ByteDance），不生成名片，只承载母公司层面的关系

**不做的事**

- 不排名、不放购买链接或折扣码、不收灰色市场的研究肽商家目录
- 默认不建个人（人员）档案，只记录机构
- 不替代 awesome-peptide：两个仓库并列，用 DOI 和条目 ID 互链

**给执行 agent 的工作规则**

1. 先读第 3、4 节（schema 与规则），再读第 5 节（三个真实案例，直接作为测试 fixture）。
2. 只修改 `data/`、`vocab/`、`templates/`、`i18n/` 和代码；不要手改 `cards/` 与 `index/`，它们由 `awepep-co build` 生成。
3. 每一条事实都必须挂 `evidence_id`；查不到来源就留空，不要凭印象填写。
4. 先写校验器和测试，再写生成器。

## 2. 设计原则

状态不是一个字段，而是由带证据的事件流推导出来的结果；下面每条原则都有对应的校验规则或测试。

1. **事件驱动**：`events.csv` 只追加、不改写；当前状态、谱系、名片时间线都由它推导。
2. **ID 永不改、实体永不删**：更名、重组、拆分、解散都是事件。
3. **一个事实一条证据**：状态类事件必须有符合等级要求的证据，否则只显示为“有报道称…”。
4. **自称与证据分开**：干湿闭环等级标注 `claimed`（自述）、`documented`（有细节的论文、专利、报告）、`verified`（可复核的公开数据）。
5. **派生值不存储**：当前状态、最近核实日期、索引行全部在 build 时计算。
6. **生成确定且幂等**：行按主键排序、UTF-8、LF，相同输入必得相同输出。
7. **英文为主、翻译另表**：翻译用哈希绑定英文原文，原文一改即标记为过期。

**已采纳的默认决策（可修改）**

- 状态变化、融资、合作等都放进同一张 `events.csv`，用 `event_type` 区分。
- 生成物由 main 分支上的 Action 自动提交，贡献者只改 `data/`。
- 不建人员表；团队负责人只在公开报道中出现时写进 `summary`。
- 长文本不进 CSV，放在可选的 `notes/<entity_id>.md`。

## 3. 数据模型（CSV）

9 张 CSV 加 `vocab/` 目录构成一个平面文件数据库；下表“列”的顺序就是表头顺序，校验器必须强制。

| 文件 | 主键 | 列 |
| --- | --- | --- |
| `entities.csv` | `entity_id` | `entity_id`, `name`, `entity_type`, `inclusion`, `parent_id`, `peptide_relevance`, `relevance_evidence_ids`, `country`, `hq_city`, `website`, `one_liner` |
| `aliases.csv` | `entity_id`+`alias` | `entity_id`, `alias`, `lang`, `kind`, `valid_from`, `valid_to`, `evidence_ids` |
| `events.csv` | `event_id` | `event_id`, `entity_id`, `date`, `date_precision`, `event_type`, `related_entity_id`, `asset_id`, `value`, `unit`, `summary`, `confidence`, `evidence_ids`, `note` |
| `evidence.csv` | `evidence_id` | `evidence_id`, `url`, `archive_url`, `title`, `publisher`, `source_type`, `tier`, `origin_key`, `published`, `accessed`, `language` |
| `assets.csv` | `asset_id` | `asset_id`, `name`, `asset_type`, `url`, `license`, `first_public_date`, `description` |
| `asset_roles.csv` | `asset_id`+`entity_id`+`role`+`start` | `asset_id`, `entity_id`, `role`, `start`, `end`, `confidence`, `evidence_ids` |
| `tags.csv` | `entity_id`+`facet`+`value` | `entity_id`, `facet`, `value`, `evidence_ids` |
| `loop_assessments.csv` | `entity_id`+`as_of` | `entity_id`, `as_of`, `level`, `evidence_level`, `review_status`, `rationale`, `evidence_ids` |
| `paper_links.csv` | `subject_id`+`doi` | `subject_id`, `subject_kind`, `doi`, `awepep_id`, `relation` |

**格式约定**

- UTF-8 无 BOM、LF 换行、RFC 4180 引号；行按主键升序。
- 日期用 ISO 8601：`YYYY`、`YYYY-MM`、`YYYY-MM-DD`，`date_precision` 分别为 `year`/`month`/`day`。
- 多值字段用 `;` 分隔（如 `evidence_ids`）；空值留空，不写 N/A。
- ID 一律是小写 ASCII kebab-case，由英文名生成且永不改；`event_id` = `{entity_id}~{date}~{event_type}`，重名时加 `~2`。
- 长度上限：`one_liner` ≤ 140 字符，`summary`、`note`、`rationale` ≤ 200 字符；不得粘贴文章段落，转述自己的话。

**完整性规则**（校验器报错）：所有 `*_id` 必须存在；`events.csv` 每行至少 1 条 `evidence_ids`；`entities.csv` 和 `events.csv` 不允许删行（PR 的 diff 中出现删行即失败，维护者可豁免）。

**派生但不存储的值**（build 时计算，写入 `build/entities_resolved.csv`）：`current_status`、`status_since`、`pending_flags`、`last_verified`、`needs_review`、`successors`、`predecessors`。

**三个案例倒逼出的设计**

- `peptide_relevance`（`core` / `adjacent` / `infrastructure`）：Anew Labs 的主业务不是多肽，AstraZeneca Molecular AI 的多肽工作只是其中一部分，需要显式标注相关度，避免收录理由被质疑。
- `evidence.origin_key`：多家媒体转述同一条路透报道时不算多条独立证据，需用 `origin_key` 去重。
- `events.value` + `unit`：融资额（`usd_m`）、持股比例（`pct`）等数值不塞进 `summary`，方便汇总。

## 4. 受控词表、状态规则、证据等级

状态由“已确认的状态类事件”推导，而事件能否生效取决于证据等级；下面的词表写入 `vocab/*.csv`，校验器从那里读取。

### 4.1 证据等级与置信度

| 等级 | 来源 | 例子 |
| --- | --- | --- |
| A | 机构自身发布的一手材料 | 公司新闻稿（PR Newswire）、官网、官方 GitHub 仓库与更新说明、同行评审论文、预印本、监管文件、专利 |
| B | 有自主采访的媒体与行业媒体 | Reuters、SCMP、36氪、pharmaphorum；只转述、没有新增报道的不算新来源 |
| C | 其他 | 招聘页、数据聚合站、社交媒体、百科类页面（含百度百科）、匿名博客 |

- `origin_key` = 原始报道的唯一标识，格式 `{publisher}-{yyyymmdd}-{slug}`，如 `reuters-20260916-anew-labs-funding`。转载同一条报道的条目共用同一个 `origin_key`。
- `confirmed`：至少 1 条 A 级证据，或至少 2 条 B 级证据且 `origin_key` 不同。
- `reported`：只有 1 个 B 级 `origin_key`。
- `rumor`：只有 C 级。
- 校验器根据证据计算“允许的最高置信度”，行上声明的 `confidence` 不得高于它。
- 一条证据只证明它自己写了的内容：公司新闻稿能证明“公司宣布了融资”，不能证明它没写的估值。
- 事件 `date` 取证据支持的最早公开披露日；各证据的日期相差超过 3 天时，校验器告警（不报错），并要求在 `note` 里写明差异。

### 4.2 状态与事件类型

| 状态 | 含义 |
| --- | --- |
| `active` | 有公开活动，且没有已确认的终止类事件 |
| `in_transition` | 重组或拆分进行中，身份或归属在变化 |
| `inactive` | 暂停或长期无活动（仅在有证据时标注） |
| `closed` / `acquired` / `merged` | 解散 / 被收购 / 并入其他机构 |
| `unknown` | 没有任何已确认事件时的占位 |

| `event_type` | 改变状态 | 生效后状态 | 必填关联列 | 说明 |
| --- | --- | --- | --- | --- |
| `founded` | 是 | `active` | — | 正式成立或首次官宣成立 |
| `first_public` | 仅当无状态时 | `active` | — | 首次公开露面（官网、论文、开源仓库） |
| `renamed` | 否 | — | — | 同时新增 `aliases` 行 |
| `reorganized` | 是 | `in_transition` | — | 重组开始 |
| `merged_into` | 是 | `merged` | `related_entity_id`（幸存方） | 写在被合并方 |
| `acquired` | 是 | `acquired` | `related_entity_id`（收购方） | 写在被收购方 |
| `paused` / `resumed` | 是 | `inactive` / `active` | — | 需有公开证据 |
| `ceased` | 是 | `closed` | — | 解散 |
| `spin_off_reported` | 否 | — | `related_entity_id`（原机构） | 只有报道的拆分，生成“待证实”标记 |
| `spun_out` | 否 | — | `related_entity_id`（原机构） | 写在新实体，建立谱系边 |
| `funding_round` | 否 | — | — | `value` + `unit=usd_m`；轮次写入 `note` |
| `ownership_disclosed` | 否 | — | `related_entity_id`（股东） | `value` + `unit=pct` |
| `partnership` / `license_deal` | 否 | — | `related_entity_id` | 金额写 `value` + `unit` |
| `asset_release` | 否 | — | `asset_id` | 模型、软件、数据集发布 |
| `pipeline_milestone` | 否 | — | — | 管线进展，需指明资产 |

**状态推导算法**（`build` 实现，需有单元测试）

1. 取该实体所有“改变状态”且 `confidence=confirmed` 的事件，按日期（精度感知）、再按 `event_id` 排序，最后一条的“生效后状态”即当前状态。
2. `reported` / `rumor` 的状态类事件只生成 `pending_flags`，名片显示“⚠ 有报道称…（待证实）”，不改变状态。
3. 没有状态类事件时，只要有至少一条已确认事件，状态为 `active`；否则为 `unknown`。
4. `active` 且 `last_verified` 距今超过 365 天 → `needs_review=true`，不自动改状态。
5. `last_verified` = 该实体名下所有行引用的证据中最大的 `accessed` 日期。

**补充规则（status\_since 与取代）**：`status_since` 取引起当前状态的那条 confirmed 事件的 `date`；实体没有任何状态类事件时状态为 `active`，`status_since` 取 `founded` 或 `first_public` 的日期，两者都没有则留空。若同一实体后来出现了同一事实的 confirmed 版本（如 `spin_off_reported` 之后出现 `spun_out`），前者不再产生 pending flag，时间线里标为已被取代。无论事件是否 confirmed，同一事件的证据发布日期相差超过 3 天时触发 W01。

### 4.3 干湿闭环等级与多肽相关度

| 等级 | 含义 | 判定所需的最低公开信息 |
| --- | --- | --- |
| L0 | 纯干实验 | 仅有软件或模型发布 |
| L1 | 干实验 + 外包湿实验验证 | 论文或公告提到外部实验验证 |
| L2 | 自有湿实验，定期回传数据 | 自有实验室，且描述了实验数据用于改进模型 |
| L3 | 设计–合成–测试–学习持续闭环 | 公开描述端到端流程，并有高通量或自动化合成与测定的证据 |
| L4 | L3 + 为训练模型专门大规模产数据 + 临床管线 | 公开的数据规模、专有数据集或临床阶段资产 |

- `evidence_level`：`claimed`（仅自述）、`documented`（论文、专利、会议报告给出细节）、`verified`（有可复核的公开产出，如开源模型、数据集、临床登记）。
- `review_status`：agent 草拟的为 `proposed`，维护者确认后为 `reviewed`；总索引只显示 `reviewed` 的等级，`proposed` 在名片上带“待审核”标记。
- 没有公开信息就不评级，名片显示“未评估”，不要猜。

| `peptide_relevance` | 含义 | 案例 |
| --- | --- | --- |
| `core` | 多肽是主要分子形式或业务 | 元思生肽 |
| `adjacent` | 多肽是多项业务之一，有公开的多肽工作 | AstraZeneca Molecular AI |
| `infrastructure` | 通用模型或平台，被用于多肽任务 | Protenix / Anew Labs（待证据） |

`adjacent` 和 `infrastructure` 必须在 `relevance_evidence_ids` 里引用至少一篇论文、基准或官方文档证明“用于多肽”，否则 `inclusion` 只能是 `stub`。

**标签词表**（`tags.csv` 的 `facet`）：

- `modality`：`macrocyclic_peptide`、`linear_peptide`、`stapled_peptide`、`bicyclic_peptide`、`peptide_drug_conjugate`、`incretin`、`antimicrobial_peptide`、`other`
- `dry`：`generative_design`、`structure_prediction`、`docking`、`property_prediction`、`protein_language_model`、`active_learning`、`reinforcement_learning`、`foundation_model_inhouse`、`llm_agent`
- `wet`：`spps_inhouse`、`high_throughput_synthesis`、`display_screening`、`dna_encoded_library`、`binding_assay`、`permeability_assay`、`stability_assay`、`in_vivo`、`automation`、`cmc`
- `therapeutic_area`：`oncology`、`autoimmune`、`metabolic`、`rare_disease`、`infection`、`other`
- `stage_max`：`discovery`、`preclinical`、`phase1`、`phase2`、`phase3`、`approved`、`na`

## 5. 三个案例（验收用的真实 fixture）

三个案例分别覆盖“团队拆分与资产归属不明”“药企内部团队与母公司的关系”“公司干湿闭环的自述与证据差距”；以下事实截至 2026-11-17，只在搜索结果中见过摘要、没有打开原页的条目，已列入 5.8 的待核实清单。

| 案例 | 实体 | 检验的设计点 |
| --- | --- | --- |
| Protenix | `bytedance-ai4s-team`、`anew-labs`、`bytedance`（占位） | 团队拆分、资产维护者变更、“待证实”标记、报道日期与实际日期不同、名称变体 |
| MolecularAI | `astrazeneca-molecular-ai`、`astrazeneca`（占位） | 药企内部团队、母公司占位、`adjacent` 相关度、无状态变化时默认 `active`、未评估闭环 |
| 元思生肽 | `syneron-bio`、`astrazeneca` | 干湿闭环的自述与证据、日期冲突、总部冲突留空、跨实体的合作与投资链接 |

### 5.1 Protenix 与 Anew Labs

- Protenix 是 AlphaFold 3 风格的开源复现模型，代码与模型参数均为 Apache-2.0；更新日志显示 v1 发布于 2026-02-05、v2 发布于 2026-04-08（[GitHub](https://github.com/bytedance/Protenix)）；技术报告发布在 [bioRxiv](https://www.biorxiv.org/content/10.1101/2025.01.08.631967.full.pdf)。
- 2026-06-10，36氪独家报道称字节的 AI 药物发现业务已开始拆分，字节保留控股，核心团队、算法、平台和管线资产转入新公司；信息来自未署名人士，文中没有字节官方确认（[36Kr](https://eu.36kr.com/en/p/3846956646124036)）。同一篇文章还说负责蛋白结构预测模型的团队此前已并入 AI 药物发现团队，但没有给出具体来源。
- 2026-09-16，路透引用两位匿名人士报道，拆分后的 Anew Labs 完成约 2.9 亿美元首轮外部融资，估值约 15 亿美元，字节保留 56% 股权（[WOWTALE](https://en.wowtale.net/2026/09/17/235139/)，页面抓取失败，仅见搜索摘要）。另一家媒体称公司已自行宣布并列出投资方（[36Kr](https://eu.36kr.com/en/p/3986744042765062)）；《经济观察报》则称截至 2026-10-12 没有收到公司官方回复（[36Kr](https://eu.36kr.com/en/p/4022199830187911)）。
- 名称变体：SCMP 称该机构也被称为 Anew Therapeutics 或 ByteDance AI Drug Discovery（[SCMP](https://scmp.com/tech/article/3352032/bytedances-drug-unit-presents-ai-designed-therapies-global-conferences)）；Protenix 仓库的引用块署名为 “ByteDance AML AI4Science Team”。
- **维护者尚未确认转移**：截至 2026-11-17，仓库仍在 `github.com/bytedance` 下，联系地址是 bytedance.com 域，页面没有提到 Anew Labs；但 36氪称拆分实体承接了算法平台。因此建模为“已确认：ByteDance AI4S 团队”加“待证实：Anew Labs”两行。
- 多肽相关度：没有找到 Anew Labs 或 Protenix 的多肽专项产品，但第三方预印本把 Protenix 用于蛋白–多肽复合物预测基准测试（[bioRxiv](https://www.biorxiv.org/content/10.1101/2025.03.09.642277)，其中 Protenix 在严格标准下准确率最高），因此标为 `infrastructure`。

### 5.2 AstraZeneca Molecular AI

- GitHub 组织的简介是“来自 AstraZeneca R&D Molecular AI 部门的软件”，共 54 个仓库，REINVENT4 为 Apache-2.0（[GitHub](https://github.com/MolecularAI)）。
- PepINVENT 是 REINVENT 的多肽扩展，可设计含非天然氨基酸的肽（[Chem. Sci. 2025](https://doi.org/10.1039/d4sc07642g)，发表于 2025-04-16；预印本 [arXiv 2409.14040](https://arxiv.org/pdf/2409.14040)）。仓库为 Apache-2.0，预训练模型包括大环肽渗透性预测模型（[GitHub](https://github.com/MolecularAI/PepINVENT)）。
- 论文署名为“Molecular AI, Discovery Sciences, BioPharmaceuticals R&D, AstraZeneca, Gothenburg”，据此记录国家与城市。
- 状态：2026-11-17 的搜索没有找到重组或解散的报道，按规则默认 `active`。另有一则招聘页提到 AstraZeneca 设有“AI for Science Innovation Unit”（C 级来源），与 Molecular AI 的关系不明，列入继续观察。
- AstraZeneca 是元思生肽的合作方和投资方，这是**母公司层面**的关系，名片上不得写成 Molecular AI 团队参与。

### 5.3 元思生肽 Syneron Bio

- 2025-03-21 与 AstraZeneca 达成合作：AstraZeneca 获得 Synova 平台使用权，预付款加近期里程碑共 7500 万美元，另有最高 34 亿美元的开发与商业化里程碑、分层版税和股权投资（[PR Newswire via BioSpace](https://www.biospace.com/press-releases/syneron-bio-announces-strategic-collaboration-with-astrazeneca)）。新闻稿把 Synova 称为“智能化高通量”平台，没有写它是 AI 平台，也没有描述闭环。
- A/A+ 轮近 1 亿美元：中文媒体在 2025-12-11 报道，并称由 AstraZeneca 及其中国联合基金领投（[新浪财经](https://finance.sina.com.cn/roll/2025-12-11/doc-inhamxqc6402996.shtml)）；PR Newswire 稿的日期是 2025-12-18（[BioSpace](https://www.biospace.com/press-releases/syneron-bio-closes-nearly-100m-in-series-a-and-a-rounds)），相差 7 天。
- B 轮 1.5 亿美元：中文公告为 2026-03-31（[投资界](https://news.pedaily.cn/202603/562257.shtml)），英文稿为 2026-04-03（[PR Newswire Asia](https://tirto.id/syneron-bio-announces-completion-of-150-million-series-b-financing-htHD)）；德诚资本与鼎晖 VGC 共同领投。
- 闭环证据：创新工场的投资人在中文转载稿中称其为“干湿闭环技术平台”（[搜狐](https://www.sohu.com/a/874262272_198516)）；公司招聘页称 AI 赋能设计、筛选、合成、表征、优化全链条，并在招多肽数据治理岗位（[猎聘](https://m.liepin.com/company/13183827/)，C 级）。没有找到描述该闭环的论文或专利，因此只能评为 `claimed`。
- 成立时间：2022 年 4 月仅见于招聘页和聚合站（[猎聘](https://m.liepin.com/company/13183827/)、[Dealroom](https://dealroom.co/companies/syneron-bio/)），新闻稿没有给出日期（只说 2025 年 3 月时“不到三年”），因此只能记为 `rumor`。
- 总部：新闻稿只提到北京（研发中心），Dealroom 写广州总部，两者冲突，`hq_city` 留空。

### 5.4 `evidence.csv`（22 行）

证据表先行，其它表都引用它的 ID；行按 `evidence_id` 升序。`archive_url` 全部留空，由 `awepep-co check-links --archive` 填充 Wayback 链接。`wowtale-*` 两行共用同一个 `origin_key`（路透的原始报道），校验器必须把它们算作一个独立来源。

```csv
evidence_id,url,archive_url,title,publisher,source_type,tier,origin_key,published,accessed,language
36kr-20260610-bytedance-spinoff,https://eu.36kr.com/en/p/3846956646124036,,"Exclusive | ByteDance's AI drug discovery unit spins off for financing, AI4S enters industrialization phase",36Kr,news,B,intelligentemergence-20260610-bytedance-spinoff,2026-06-10,2026-11-17,en
36kr-20260917-anew-labs-round,https://eu.36kr.com/en/p/3986744042765062,,ByteDance Spin-off AI Pharmaceutical Division Secures Massive 2 Billion Yuan First-Round Financing,36Kr (via VCBeat),news,B,vcbeat-20260917-anew-labs-round,2026-09-17,2026-11-17,en
arxiv-202409-pepinvent,https://arxiv.org/pdf/2409.14040,,PepINVENT: Generative peptide design beyond the natural amino acids,arXiv,preprint,A,arxiv-202409-pepinvent,2024-09,2026-11-17,en
biorxiv-20250108-protenix,https://www.biorxiv.org/content/10.1101/2025.01.08.631967.full.pdf,,Protenix - Advancing Structure Prediction Through a Comprehensive AlphaFold3 Reproduction,bioRxiv,preprint,A,biorxiv-20250108-protenix,2025-01,2026-11-17,en
biorxiv-20250313-protein-peptide-benchmark,https://www.biorxiv.org/content/10.1101/2025.03.09.642277,,Benchmarking AlphaFold3-like Methods for Protein-Peptide Complex Prediction,bioRxiv,preprint,A,biorxiv-20250313-protein-peptide-benchmark,2025-03-13,2026-11-17,en
dealroom-syneron-profile,https://dealroom.co/companies/syneron-bio/,,Syneron Bio company profile,Dealroom,aggregator,C,dealroom-syneron-profile,,2026-11-17,en
economicobserver-20261012-anew-labs,https://eu.36kr.com/en/p/4022199830187911,,Unfamiliar Newcomer in the AI Pharmaceutical Industry,36Kr (Economic Observer),news,B,economicobserver-20261012-anew-labs,2026-10-12,2026-11-17,en
github-bytedance-protenix,https://github.com/bytedance/Protenix,,Protenix: Protein + X (README and update log),GitHub,repo,A,github-bytedance-protenix,,2026-11-17,en
github-molecularai-org,https://github.com/MolecularAI,,AstraZeneca - Molecular AI (GitHub organization),GitHub,repo,A,github-molecularai-org,,2026-11-17,en
github-molecularai-pepinvent,https://github.com/MolecularAI/PepINVENT,,MolecularAI/PepINVENT (repository README),GitHub,repo,A,github-molecularai-pepinvent,,2026-11-17,en
jcheminf-2024-reinvent4,https://doi.org/10.1186/s13321-024-00812-5,,REINVENT 4 (Journal of Cheminformatics),Journal of Cheminformatics,paper,A,jcheminf-2024-reinvent4,2024,2026-11-17,en
liepin-syneron-profile,https://m.liepin.com/company/13183827/,,元思生肽 company profile (recruiting page),Liepin,job_post,C,liepin-syneron-profile,,2026-11-17,zh
pedaily-20260331-syneron-series-b,https://news.pedaily.cn/202603/562257.shtml,,元思生肽（Syneron Bio）完成1.5亿美元B轮融资,Pedaily,news,B,syneron-company-release-cn-20260331,2026-03-31,2026-11-17,zh
prnewswire-20250321-syneron-astrazeneca,https://www.biospace.com/press-releases/syneron-bio-announces-strategic-collaboration-with-astrazeneca,,Syneron Bio Announces Strategic Collaboration with AstraZeneca,PR Newswire (via BioSpace),press_release,A,prnewswire-20250321-syneron-astrazeneca,2025-03-21,2026-11-17,en
prnewswire-20251218-syneron-series-a,https://www.biospace.com/press-releases/syneron-bio-closes-nearly-100m-in-series-a-and-a-rounds,,Syneron Bio Closes Nearly $100M in Series A and A+ Rounds,PR Newswire (via BioSpace),press_release,A,prnewswire-20251218-syneron-series-a,2025-12-18,2026-11-17,en
prnewswire-20260403-syneron-series-b,https://tirto.id/syneron-bio-announces-completion-of-150-million-series-b-financing-htHD,,Syneron Bio Announces Completion of $150 Million Series B Financing,PR Newswire Asia (via Tirto EN),press_release,A,prnewswire-20260403-syneron-series-b,2026-04-03,2026-11-17,en
rsc-20250416-pepinvent,https://doi.org/10.1039/d4sc07642g,,PepINVENT: generative peptide design beyond natural amino acids,Chemical Science,paper,A,rsc-20250416-pepinvent,2025-04-16,2026-11-17,en
scmp-undated-bytedance-drug-unit,https://scmp.com/tech/article/3352032/bytedances-drug-unit-presents-ai-designed-therapies-global-conferences,,bytedances drug unit presents ai designed therapies global conferences,SCMP,news,B,scmp-undated-bytedance-drug-unit,,2026-11-17,en
sina-20251211-syneron-series-a,https://finance.sina.com.cn/roll/2025-12-11/doc-inhamxqc6402996.shtml,,元思生肽完成A轮及A+轮近亿美元融资,Sina Finance,news,B,syneron-company-briefing-20251211,2025-12-11,2026-11-17,zh
sohu-20250321-syneron-astrazeneca-zh,https://www.sohu.com/a/874262272_198516,,元思生肽（Syneron Bio）与阿斯利康达成战略合作｜创新事,Sohu (reprint),news,B,sinovation-20250321-syneron-astrazeneca,2025-03-21,2026-11-17,zh
wowtale-20260917-anew-labs-round,https://en.wowtale.net/2026/09/17/235139/,,"ByteDance's AI Drug Spin-Off Anew Labs Closes $290M Round, Sources Say",WOWTALE,news,B,reuters-20260916-anew-labs-funding,2026-09-17,2026-11-17,en
wowtale-ko-20260917-anew-labs-round,https://wowtale.net/2026/09/17/264879/,,"바이트댄스발 AI 신약 에뉴랩스, 2억9000만 달러 투자유치",WOWTALE (Korean),news,B,reuters-20260916-anew-labs-funding,2026-09-17,2026-11-17,ko
```

说明：`scmp-undated-bytedance-drug-unit` 的标题取自搜索结果里的 URL 标题字段，尚未核对原页的正式标题和发布日期，由 agent 在任务 E 中核实；`published` 留空时校验器只告警，不报错。

### 5.5 实体与资产侧的表

`entities.csv`（`bytedance` 与 `astrazeneca` 是只作母公司占位的 `stub`，不生成名片）：

```csv
entity_id,name,entity_type,inclusion,parent_id,peptide_relevance,relevance_evidence_ids,country,hq_city,website,one_liner
anew-labs,Anew Labs,ai_native_biotech,full,,infrastructure,biorxiv-20250313-protein-peptide-benchmark,CN,Shanghai,,AI drug discovery company spun out of ByteDance's AI drug discovery unit in 2026.
astrazeneca,AstraZeneca,parent_org,stub,,,,,,,
astrazeneca-molecular-ai,AstraZeneca Molecular AI,pharma_ai_team,full,astrazeneca,adjacent,github-molecularai-pepinvent;rsc-20250416-pepinvent,SE,Gothenburg,https://github.com/MolecularAI,Molecular AI department of AstraZeneca R&D with open-source generative design tools including PepINVENT.
bytedance,ByteDance,parent_org,stub,,,,,,,
bytedance-ai4s-team,ByteDance AI4S team,bigtech_ai_team,full,bytedance,infrastructure,biorxiv-20250313-protein-peptide-benchmark,,,https://github.com/bytedance/Protenix,AI for Science team at ByteDance that developed the Protenix structure prediction model.
syneron-bio,Syneron Bio,ai_native_biotech,full,,core,,CN,,,Macrocyclic peptide company with the Synova platform and an AstraZeneca collaboration.
```

`aliases.csv`（中文名和名称变体都在这里，为后续中文翻译层和搜索所用）：

```csv
entity_id,alias,lang,kind,valid_from,valid_to,evidence_ids
anew-labs,Anew Therapeutics,en,variant,,,scmp-undated-bytedance-drug-unit
anew-labs,ByteDance AI Drug Discovery,en,variant,,,scmp-undated-bytedance-drug-unit
anew-labs,新生实验室,zh,zh_name,,,wowtale-ko-20260917-anew-labs-round
astrazeneca-molecular-ai,MolecularAI,en,variant,,,github-molecularai-org
bytedance-ai4s-team,ByteDance AML AI4Science Team,en,variant,,,github-bytedance-protenix
syneron-bio,元思生肽,zh,zh_name,,,sina-20251211-syneron-series-a
```

`assets.csv`：

```csv
asset_id,name,asset_type,url,license,first_public_date,description
pepinvent,PepINVENT,software,https://github.com/MolecularAI/PepINVENT,Apache-2.0,2024-09,Generative peptide design framework with natural and non-natural amino acids built on the REINVENT ecosystem.
protenix,Protenix,model,https://github.com/bytedance/Protenix,Apache-2.0,2025-01,Open-source AlphaFold 3-style biomolecular structure prediction model with code and weights.
reinvent4,REINVENT 4,software,https://github.com/MolecularAI/REINVENT4,Apache-2.0,2024,Open-source generative AI framework for small-molecule design.
synova,Synova,platform,,,2025-03,Syneron Bio's proprietary macrocyclic peptide discovery platform.
```

`asset_roles.csv`（`role` 词表：`developer`、`maintainer`、`owner`、`licensee`；`end` 留空表示仍在任。Protenix 的维护者一行已确认、一行待证实，正是这个案例要检验的地方）：

```csv
asset_id,entity_id,role,start,end,confidence,evidence_ids
pepinvent,astrazeneca-molecular-ai,developer,2024-09,,confirmed,arxiv-202409-pepinvent;rsc-20250416-pepinvent
protenix,anew-labs,maintainer,2026-06,,reported,36kr-20260610-bytedance-spinoff;36kr-20260917-anew-labs-round
protenix,bytedance-ai4s-team,developer,2025-01,,confirmed,biorxiv-20250108-protenix;github-bytedance-protenix
protenix,bytedance-ai4s-team,maintainer,2025-01,,confirmed,github-bytedance-protenix
reinvent4,astrazeneca-molecular-ai,developer,2024,,confirmed,github-molecularai-org;jcheminf-2024-reinvent4
synova,astrazeneca,licensee,2025-03,,confirmed,prnewswire-20250321-syneron-astrazeneca
synova,syneron-bio,owner,2025-03,,confirmed,prnewswire-20250321-syneron-astrazeneca
```

第 2 行的 `confidence` 记为 `reported`，即使证据计算出的上限是 `confirmed`（两个独立的 B 级来源），原因是一手来源 GitHub 仍然显示维护者在字节一侧；校验器只禁止“声明高于证据上限”，允许策展人主动降低。

`tags.csv`：

```csv
entity_id,facet,value,evidence_ids
anew-labs,dry,structure_prediction,36kr-20260917-anew-labs-round
astrazeneca-molecular-ai,dry,generative_design,rsc-20250416-pepinvent
astrazeneca-molecular-ai,dry,property_prediction,github-molecularai-pepinvent
astrazeneca-molecular-ai,dry,reinforcement_learning,github-molecularai-pepinvent
astrazeneca-molecular-ai,modality,macrocyclic_peptide,github-molecularai-pepinvent
bytedance-ai4s-team,dry,structure_prediction,biorxiv-20250108-protenix
syneron-bio,modality,macrocyclic_peptide,prnewswire-20250321-syneron-astrazeneca
syneron-bio,therapeutic_area,autoimmune,prnewswire-20250321-syneron-astrazeneca
syneron-bio,therapeutic_area,metabolic,prnewswire-20250321-syneron-astrazeneca
syneron-bio,therapeutic_area,oncology,prnewswire-20251218-syneron-series-a
syneron-bio,therapeutic_area,rare_disease,prnewswire-20250321-syneron-astrazeneca
```

`loop_assessments.csv`（只有一行：AstraZeneca Molecular AI 和 ByteDance/Anew 没有公开的湿实验信息，按规则不评级，名片显示“未评估”）：

```csv
entity_id,as_of,level,evidence_level,review_status,rationale,evidence_ids
syneron-bio,2026-11-17,L3,claimed,proposed,Company calls Synova an intelligent high-throughput platform; an investor calls it a dry-wet closed-loop platform; no paper or patent detail found.,prnewswire-20250321-syneron-astrazeneca;sohu-20250321-syneron-astrazeneca-zh;liepin-syneron-profile
```

`paper_links.csv`（`awepep_id` 留空，由任务 F 用 DOI 去匹配 awesome-peptide 的条目）：

```csv
subject_id,subject_kind,doi,awepep_id,relation
pepinvent,asset,10.1039/d4sc07642g,,authored
protenix,asset,10.1101/2025.01.08.631967,,authored
protenix,asset,10.1101/2025.03.09.642277,,benchmarked
reinvent4,asset,10.1186/s13321-024-00812-5,,authored
```

### 5.6 `events.csv`（16 行）

这张表会把前面所有“报道与确认不同步”的情况写进数据：注意 `confidence` 列、`date_precision` 列和 `note` 列。所有文字都是我自己的转述，没有摘抄原文。

```csv
event_id,entity_id,date,date_precision,event_type,related_entity_id,asset_id,value,unit,summary,confidence,evidence_ids,note
anew-labs~2021~founded,anew-labs,2021,year,founded,,,,,AI drug discovery team formed inside ByteDance; legal incorporation date not found.,confirmed,36kr-20260917-anew-labs-round;wowtale-20260917-anew-labs-round,Two independent B origins: VCBeat and Reuters.
anew-labs~2026-06-10~spin_off_reported,anew-labs,2026-06-10,day,spin_off_reported,bytedance,,,,First public report that ByteDance would spin off its AI drug discovery business and keep a controlling stake.,reported,36kr-20260610-bytedance-spinoff,Unnamed sources; no official ByteDance statement found. Superseded by the spun_out event below.
anew-labs~2026-06~spun_out,anew-labs,2026-06,month,spun_out,bytedance,,,,Spun out of ByteDance as a separate company.,confirmed,36kr-20260917-anew-labs-round;wowtale-20260917-anew-labs-round,Month inferred from 'about three months before 2026-09-17'; no A-tier source found.
anew-labs~2026-09-16~funding_round,anew-labs,2026-09-16,day,funding_round,,,290,usd_m,First external round reported at about USD 290M with a valuation of about USD 1.5B.,reported,economicobserver-20261012-anew-labs;36kr-20260917-anew-labs-round;wowtale-20260917-anew-labs-round,Reuters cites two unnamed sources; one outlet says the company announced it; Economic Observer got no official reply by 2026-10-12.
anew-labs~2026-09-16~ownership_disclosed,anew-labs,2026-09-16,day,ownership_disclosed,bytedance,,56,pct,ByteDance reportedly keeps a 56% stake after the round.,reported,36kr-20260917-anew-labs-round;wowtale-20260917-anew-labs-round,Figure originates with Reuters; VCBeat repeats it.
astrazeneca-molecular-ai~2024-09~asset_release,astrazeneca-molecular-ai,2024-09,month,asset_release,,pepinvent,,,PepINVENT preprint posted to arXiv.,confirmed,arxiv-202409-pepinvent,Journal version published 2025-04-16.
astrazeneca-molecular-ai~2024~asset_release,astrazeneca-molecular-ai,2024,year,asset_release,,reinvent4,,,REINVENT 4 described in the Journal of Cheminformatics.,confirmed,jcheminf-2024-reinvent4,Month not captured.
astrazeneca-molecular-ai~2025-04-16~asset_release,astrazeneca-molecular-ai,2025-04-16,day,asset_release,,pepinvent,,,PepINVENT published in Chemical Science.,confirmed,github-molecularai-pepinvent;rsc-20250416-pepinvent,
bytedance-ai4s-team~2025-01~asset_release,bytedance-ai4s-team,2025-01,month,asset_release,,protenix,,,Protenix technical report posted on bioRxiv.,confirmed,biorxiv-20250108-protenix,DOI suggests a 2025-01-08 submission; confirm the posting date.
bytedance-ai4s-team~2026-02-05~asset_release,bytedance-ai4s-team,2026-02-05,day,asset_release,,protenix,,,Protenix-v1 released.,confirmed,github-bytedance-protenix,
bytedance-ai4s-team~2026-04-08~asset_release,bytedance-ai4s-team,2026-04-08,day,asset_release,,protenix,,,Protenix-v2 released.,confirmed,github-bytedance-protenix,
bytedance-ai4s-team~2026-06-10~merged_into,bytedance-ai4s-team,2026-06-10,day,merged_into,anew-labs,,,,Reported: the protein structure prediction team had earlier merged into the AI drug discovery team.,reported,36kr-20260610-bytedance-spinoff,Date is the report date; actual merge date unknown ('previously'); single unnamed source.
syneron-bio~2022-04~founded,syneron-bio,2022-04,month,founded,,,,,Founding date taken from a recruiting page and an aggregator only.,rumor,dealroom-syneron-profile;liepin-syneron-profile,No press release states a founding date; a March 2025 release says rounds in less than three years.
syneron-bio~2025-03-21~partnership,syneron-bio,2025-03-21,day,partnership,astrazeneca,synova,75,usd_m,AstraZeneca gets access to Synova; USD 75M upfront and near-term plus up to USD 3.4B in milestones; royalties and an equity investment.,confirmed,prnewswire-20250321-syneron-astrazeneca,Value is the upfront and near-term part only.
syneron-bio~2025-12-11~funding_round,syneron-bio,2025-12-11,day,funding_round,astrazeneca,,100,usd_m,Series A and A+ reported as close to USD 100M with AstraZeneca and its China joint fund leading.,confirmed,prnewswire-20251218-syneron-series-a;sina-20251211-syneron-series-a,Chinese media 2025-12-11 vs PR Newswire 2025-12-18; amount stated as 'close to'. Lead investors per Sina Finance.
syneron-bio~2026-03-31~funding_round,syneron-bio,2026-03-31,day,funding_round,,,150,usd_m,Series B of USD 150M co-led by Decheng Capital and CDH VGC with an unnamed international life-sciences fund.,confirmed,pedaily-20260331-syneron-series-b;prnewswire-20260403-syneron-series-b,Chinese announcement 2026-03-31; English PR Newswire 2026-04-03.
```

实现上要注意的三点：

- `anew-labs~2026-06-10~spin_off_reported` 被同一机构、同 `related_entity_id` 的后续 `spun_out`（已确认）取代，其“待证实”标记在 build 时自动消失，但事件本身保留在时间线里。
- `bytedance-ai4s-team~2026-06-10~merged_into` 的 `confidence` 是 `reported`，所以该团队的状态不变，只生成一条待证实标记。
- `syneron-bio~2022-04~founded` 只有 C 级证据，所以是 `rumor`，不进入状态推导；该公司的“active”来自已确认的合作与融资事件（推导规则第 3 条）。

### 5.7 预期的生成结果

三个案例构建后应得到下面的状态、标记和页面，它们就是 `tests/test_fixtures.py` 的断言来源。

&#91;embedded content: case lineage · 7 nodes, 7 links, 2 reported\]

实线是已确认的关系，虚线是只有报道的关系；两条虚线（团队合并、Protenix 维护者）在名片上都要带“待证实”标记，字节的 56% 持股也只是报道。AstraZeneca 与 Syneron 的合作、投资是母公司层面的已确认关系，不属于 Molecular AI 团队。

| 实体 | 派生状态 | 待证实标记 | 名片上必须出现的内容 |
| --- | --- | --- | --- |
| `bytedance-ai4s-team` | `active`（始于 2025-01） | 合并入 Anew Labs（报道，2026-06-10） | Protenix 的维护者两行：已确认（本团队）与待证实（Anew Labs）；别名 ByteDance AML AI4Science Team |
| `anew-labs` | `active`（始于 2021） | 无（`spin_off_reported` 已被 `spun_out` 取代） | “2026-06 从 ByteDance 拆分（月精度）”；融资与持股标 reported，并注明有媒体称公司未回应；相关度 `infrastructure` 及证据链接；别名“新生实验室”等 |
| `astrazeneca-molecular-ai` | `active`（始于 2024） | 无 | 母公司 AstraZeneca；资产 REINVENT 4、PepINVENT；闭环“未评估”；折叠区“母公司层面的关系”只列 AstraZeneca–Syneron，并注明非本团队 |
| `syneron-bio` | `active`（始于 2025-03-21） | 无 | 闭环“L3 · claimed · 待审核”；成立时间只作为未证实条目；总部城市留空；AstraZeneca 合作与投资；Synova 资产（Syneron 所有，AstraZeneca 获使用权） |

索引页的预期：

- `index/by-status.md`：四个实体都在 `active`；没有实体在 `in_transition`。
- `index/by-loop-level.md`：Syneron Bio 列在“claimed（待审核）”，其余三个列在“未评估”。
- `index/changes.md`（以 2026-11-17 为构建日、近 90 天）：只有 2026-09-16 的两条 Anew Labs 事件，都带 reported 标记。
- `index/lineage.md`：由 Mermaid 生成上图的关系。
- **禁止项**：Anew Labs 名片不得把 `spun_out` 写成“完全独立”；Molecular AI 名片不得把 AstraZeneca 的对外合作写成该团队的工作。

### 5.8 待核实清单（任务 E）

下表每一项都是我没有亲自打开原页、或者来源之间有冲突的地方；agent 核实前不得把相应行的 `confidence` 提高。

| # | 条目 | 为什么要核实 | 怎么做 |
| --- | --- | --- | --- |
| 1 | `wowtale-20260917-anew-labs-round` | 页面抓取失败，只见过搜索摘要 | 重新打开；仍失败则改用路透原文或 Straits Times 作为来源，并更新 `origin_key` |
| 2 | `prnewswire-20260403-syneron-series-b` | 只通过 Tirto 转载的搜索摘要见过 | 打开 PR Newswire 原稿并替换 URL，核对发布日期 |
| 3 | `scmp-undated-bytedance-drug-unit` | 标题、发布日期都没有核对 | 打开原文，填入 `published`，把 `undated` 从 `origin_key` 里去掉 |
| 4 | Anew Labs 官网与官方公告 | 目前只有 B 级来源；还有媒体称公司未回应过融资 | 找 A 级来源，填 `entities.website`；若有官方公告，把 `spun_out`、`funding_round` 的置信度证据换成 A 级 |
| 5 | Protenix 的维护者 | 仓库仍在 `github.com/bytedance`，而 36氪称算法平台已转入 Anew Labs | 每次 build 前检查仓库组织、README 的联系方式和作者署名；若变化，给旧的 `maintainer` 行填 `end`，并将 Anew Labs 的行升级为 `confirmed` |
| 6 | Syneron Bio 的总部与成立时间 | 新闻稿只提北京研发中心，Dealroom 写广州总部，成立时间只有 C 级来源 | 用工商登记或公司官网核对；核实前 `hq_city` 留空 |
| 7 | Syneron Bio 的闭环证据 | 目前只有自述和投资人表述，一份第三方分析提到过一个口服 pan-KRAS 的 AACR 摘要（仅是线索） | 查找会议摘要、专利、论文；找到后把 `evidence_level` 升为 `documented` |
| 8 | AstraZeneca Molecular AI 的隐性重组 | 一则 C 级招聘页提到“AI for Science Innovation Unit”，与 Molecular AI 的关系不明 | 找 A 级来源（AstraZeneca 官网、公告）；没找到就不写入事件 |
| 9 | 百度百科关于 Seed AI4S 团队管理权转移的说法 | 仅见搜索摘要，且百科为 C 级 | 不入库，只作线索，找到 A/B 级佐证再记录 |
| 10 | `awepep_id` 回填 | `paper_links.csv` 中该列为空 | 用 DOI 匹配 awesome-peptide 的 CSV 条目，匹配不到的保持空 |

## 6. 构建流程、命令行与生成物

`awepep-co build` 要是一个纯函数：读取 `data/`、`vocab/`、`templates/`、`i18n/`，输出 `cards/`、`index/`、`build/`，相同输入必须得到字节相同的输出。

**流水线**

1. **读取**：严格解析 CSV（列名与顺序必须与表头定义一致）。
2. **校验**：见下表；有报错即停止。
3. **解析**：连接各表，计算状态、待证实标记、谱系、最近核实日期，写入 `build/entities_resolved.csv`。
4. **渲染**：用模板生成 `cards/<entity_id>/README.md`（只对 `inclusion=full`）、所有 `index/*.md`、根 `README.md` 的索引段。
5. **导出**：`index/index.csv`、`index/index.json`，以及不入库的 `build/peploop.sqlite`（作为 Release 附件）。
6. **变更预览**：`build/CHANGES_PREVIEW.md` 列出相对上一次提交新增或改变的行，用于 PR 评论。

为了可测试，时间相关的计算一律用参数 `--as-of YYYY-MM-DD`（默认今天），输出里不写入时间戳；fixture 的预期结果全部以 `--as-of 2026-11-17` 为准。

| 命令 | 作用 |
| --- | --- |
| `awepep-co validate [--strict]` | 校验；有报错退出码 1，告警仅在 `--strict` 时失败 |
| `awepep-co build [--as-of D]` | 校验 → 解析 → 渲染 |
| `awepep-co build --check` | 重新生成并与工作区比较，有差异则失败（CI 用） |
| `awepep-co add entity\|event\|evidence\|asset` | 交互式或用参数追加一行，自动按主键排序并检查外键 |
| `awepep-co check-links [--archive]` | 检查链接是否失效；加 `--archive` 时提交 Wayback 存档并回填 `archive_url` |
| `awepep-co stale [--days N]` | 列出 `needs_review` 的实体和超期未核实的条目 |
| `awepep-co export sqlite\|json` | 导出供分析使用的数据库或 JSON |

**校验规则**

| 编号 | 级别 | 规则 |
| --- | --- | --- |
| E01 | 报错 | 列名或列顺序与表头定义不符 |
| E02 | 报错 | 枚举值不在 `vocab/` 中 |
| E03 | 报错 | 外键不存在（含 `evidence_ids`、`related_entity_id`、`asset_id`、`parent_id`） |
| E04 | 报错 | `events.csv` 的行没有 `evidence_ids` |
| E05 | 报错 | 声明的 `confidence` 高于证据计算出的上限（规则见 4.1） |
| E06 | 报错 | 同一 `origin_key` 在不同行里写了不同的 `tier` |
| E07 | 报错 | 事件类型要求的 `related_entity_id` 或 `asset_id` 缺失 |
| E08 | 报错 | 日期格式与 `date_precision` 不一致 |
| E09 | 报错 | PR 里 `entities.csv` 或 `events.csv` 有行被删除 |
| E10 | 报错 | `peptide_relevance` 为 `adjacent` 或 `infrastructure`，但 `inclusion=full` 且没有 `relevance_evidence_ids` |
| E11 | 报错 | 文本列超过长度上限 |
| E12 | 报错 | `end` 早于 `start`；主键重复 |
| W01 | 告警 | 同一事件的证据发布日期相差超过 3 天（且 `note` 未说明） |
| W02 | 告警 | `news`、`paper`、`preprint`、`press_release` 类证据的 `published` 为空（`repo`、`aggregator`、`job_post` 豁免） |
| W03 | 告警 | `active` 实体超过 365 天未核实 |
| W04 | 告警 | 链接失效，或没有 `archive_url` |
| W05 | 告警 | `review_status=proposed` 超过 30 天 |
| W06 | 告警 | 翻译的 `source_hash` 过期（v0.3 起） |

**名片的结构**（`templates/card.liquid`，英文，章节顺序固定）

1. 抬头：名称、`one_liner`、徽章（类型、状态、相关度、闭环等级与证据等级、国家）。
2. 状态横幅：有待证实标记或状态不是 `active` 时显示。
3. 基本信息表：总部、母机构、网站、别名、最近核实日期。
4. 相关度与标签：多肽相关度和证据、`modality`、`dry`、`wet`、`therapeutic_area`。
5. 干湿闭环：等级、证据等级、审核状态、依据；没有记录时写“Not assessed”。
6. 资产与角色：每行带置信度标记，`reported` 的行写“⁠Reported, unconfirmed”。
7. 时间线：事件按时间倒序，`reported`、`rumor` 用不同样式，显示 `note`。
8. 母公司层面的关系（折叠，仅团队类实体）：列出母公司的对外关系，并声明不代表本团队的工作。
9. 相关论文：链接到 awesome-peptide 的条目。
10. 来源：按等级列出证据，带访问日期和存档链接。
11. （可选）Curator notes：渲染 `notes/<entity_id>.md`，并标注为编者观点。

模板引擎应与 awesome-peptide 现有流程保持一致（它用 Liquid 模板从 CSV 生成 README）。我没能读到那个仓库的 `CONTRIBUTING.md` 全文，所以 agent 开工前必须先阅读 `awepep` 包的现有实现，复用其约定而不是重写。

**索引与其它生成物**

- 根 `README.md`：顶部摘要、总索引表（名称、一句话、类型、状态、闭环等级、相关度、地区、最近核实），用 `<!-- BEGIN:INDEX -->` 标记圈出生成区，标记外的内容不得被 build 覆盖。
- `index/by-type.md`、`by-status.md`、`by-loop-level.md`、`by-modality.md`、`by-region.md`、`assets.md`（资产及当前维护者）。
- `index/lineage.md`：Mermaid 图，节点是 `inclusion=full` 实体加被引用的 stub，实线表示已确认的关系（母机构、`spun_out`、`partnership`），虚线表示 `reported` 的关系（如 `merged_into`、未确认的 `asset_roles`）。
- `index/changes.md`：`--as-of` 前 90 天的事件，按日期倒序，带置信度标记和名片链接。

## 7. 国际化：英文为主，中文后续

v0.1 只生成英文，但表结构和哈希机制从第一天就位，后续补中文翻译不需要改数据模型。

- **英文是唯一源**：CSV 里所有自由文本列（`one_liner`、`summary`、`note`、`rationale`、`description`）一律用英文。
- **中文名与别名**写在 `aliases.csv`（`kind=zh_name`）；中文版页面在英文名后用括号注明中文名，搜索也用它。
- **翻译表** `i18n/zh/strings.csv`：`key`、`zh_text`、`source_hash`、`status`、`translator`、`updated`。`key` 格式：`entity:<id>:one_liner`、`event:<event_id>:summary`、`event:<event_id>:note`、`asset:<id>:description`、`loop:<entity_id>:<as_of>:rationale`。
- **哈希绑定原文**：`source_hash` 是翻译时英文原文（规范化空白后）的 SHA-256 前 12 位。build 时比对，不一致即触发 W06，并在中文页面回退到英文。
- **状态**：`draft`（机器或初翻）、`reviewed`（人工审过）。默认只渲染 `reviewed`；`--include-draft` 才渲染草稿，并加“机器翻译”标记。
- **界面标签**（如“Status”“Loop level”）放在 `i18n/zh/ui.yml`，模板里用 `{{ 'status' | t }}` 取值；枚举值（如 `in_transition`）也在这里映射显示名。
- **不翻译**：ID、证据标题（保留原文）、实体名称（用别名表）。翻译不得引入英文里没有的事实。
- **输出**：根和每张名片各多一个 `README.zh.md`，索引页多一个 `*.zh.md`；英文页顶部放语言切换链接。

**v0.1 验收**：没有 `i18n/zh/` 时 build 不报错且不生成中文页；写入一条 `reviewed` 翻译后再改英文原文，`validate` 报 W06。

## 8. 仓库结构

仓库独立于 awesome-peptide，与它并列；代码默认放在独立包 `awepep_co` 中，若现有 `awepep` 包的工具函数稳定，可以导入复用，但不要把两者耦合成一个包。

```
awesome-ai4peptide-companies/
├── README.md                     # 手写说明 + 生成的索引区
├── CONTRIBUTING.md              # 贡献流程（只改 data/）
├── CHANGELOG.md
├── AGENTS.md                     # agent 工作规则（来自本计划第 1、10 节）
├── LICENSE
├── pyproject.toml
├── data/                         # 9 张 CSV，唯一数据源
├── vocab/                        # 受控词表 CSV（实体类型、事件类型、状态、标签、角色）
├── schema/                       # 表结构定义：列、类型、长度上限
├── notes/                       # 可选：<entity_id>.md 人工分析笔记
├── i18n/zh/                      # strings.csv、ui.yml（v0.3 起启用）
├── templates/                    # card / index / lineage / changes / assets (.liquid)
├── cards/<entity_id>/README.md   # 生成
├── index/                        # 生成
├── build/                        # 生成，gitignore（sqlite、resolved csv、预览）
├── awepep_co/                    # Python 包：CLI、校验、解析、渲染
├── tests/
│   ├── fixtures/                 # 第 5 节的 CSV 原样放这里
│   └── expected/                 # --as-of 2026-11-17 下的预期输出
├── docs/                         # taxonomy.md、inclusion-policy.md、evidence-policy.md
└── .github/workflows/            # validate.yml、build.yml、stale.yml
```

`docs/` 下三份文档直接来自本计划：`taxonomy.md`（第 1、4.3 节）、`inclusion-policy.md`（第 1 节与相关度规则）、`evidence-policy.md`（第 4.1 节）。所有规则只在一处定义，其他地方引用。

## 9. CI 与贡献流程

贡献者只改 `data/`、`notes/` 和 `i18n/`，生成物一律由 main 上的 Action 重新生成并提交，所以 PR 里不会出现生成文件的冲突。

| 工作流 | 触发 | 做什么 |
| --- | --- | --- |
| `validate.yml` | PR | 运行 `validate`，报错即失败；把告警和 `CHANGES_PREVIEW.md` 以评论发到 PR；在评论里附上受影响名片的渲染预览 |
| `build.yml` | push 到 main | 运行 `build`，用 bot 账号提交 `cards/`、`index/`，提交信息带 `[skip ci]`；打 tag 时把 `peploop.sqlite` 和 `index.json` 作为 Release 附件 |
| `stale.yml` | 每周 | 运行 `stale` 和 `check-links`，把结果开成一个 issue，不自动改数据 |

**PR 模板的检查清单**（由人勾选）

- [ ] 每一行都有 `evidence_ids`，证据都在 `evidence.csv` 中
- [ ] 状态类事件有 A 级证据，或至少两个独立的 B 级 `origin_key`；否则标为 `reported`
- [ ] 没有整段粘贴文章文字，摘要都是自己的转述
- [ ] 没有排名、购买链接、折扣码或用法用量信息
- [ ] 来源之间有冲突时，已在 `note` 里写明，且没有挑一个答案抽掉另一个

**规则**

- 分支保护：`validate` 必须通过，维护者审核后才能合并；E09（删行）需维护者豁免。
- agent 只能提 PR，不能直接推 main；它草拟的闭环评估一律 `review_status=proposed`。
- 不抓取付费墙内容，不保存文章全文，只保存 URL、存档链接和自己写的摘要。
- v0.4 起，由定时任务搜索新闻和 GitHub 变化，生成候选事件行并开 PR，不自动合并。

## 10. 验收测试

所有测试以第 5 节的 fixture 为输入，固定 `--as-of 2026-11-17`，预期输出放在 `tests/expected/`。通过标准：`pytest` 全绿，且 `build --check` 在 fixture 上无差异。

| 编号 | 测试 | 通过条件 |
| --- | --- | --- |
| T01 | 状态推导 | `anew-labs`、`bytedance-ai4s-team`、`astrazeneca-molecular-ai`、`syneron-bio` 的当前状态都是 `active`；`astrazeneca`、`bytedance` 作为 stub 不生成名片 |
| T02 | 待证实标记 | `bytedance-ai4s-team` 出现一条 `merged_into anew-labs` 的 pending flag，状态仍为 `active`，名片顶部显示状态横幅 |
| T03 | 事件取代 | `spin_off_reported` 在同一实体出现 confirmed 的 `spun_out` 后不再显示为待证实，时间线里标为已被取代 |
| T04 | 置信度上限 | 把某条 `reported` 事件改成 `confirmed` 但证据不够时，`validate` 报 E05；把 `confirmed` 降为 `reported` 不报错 |
| T05 | 来源去重 | 两条证据 `origin_key` 相同时只算一个来源；`anew-labs~2026-06~spun_out` 因有两个不同 `origin_key` 才是 confirmed |
| T06 | 日期差告警 | 同一事件证据发布日期相差 3 天以内不告警，4 天以上（且 `note` 未说明）报 W01；Syneron 的 12 月 11 日与 12 月 18 日应触发告警或在 `note` 中已说明 |
| T07 | 空发布日期 | `news`/`paper`/`preprint`/`press_release` 类证据 `published` 为空报 W02；`repo`、`aggregator`、`job_post` 不报 |
| T08 | 不得删除 | 删掉 `events.csv` 或 `entities.csv` 的一行，E09 触发 |
| T09 | 双维护者渲染 | Protenix 在资产页和名片里显示两行：`bytedance-ai4s-team` 为 confirmed，`anew-labs` 带“Reported, unconfirmed” |
| T10 | 母公司层级 | AZ 与 Syneron 的合作只出现在 `astrazeneca` 一层；`astrazeneca-molecular-ai` 名片的折叠区声明该关系不代表本团队 |
| T11 | 相关度规则 | `anew-labs` 为 `infrastructure` 且有论文证据；去掉 `relevance_evidence_ids` 后 E10 触发 |
| T12 | 幂等 | 连续两次 `build` 的输出字节相同；打乱 CSV 行顺序后输出不变 |
| T13 | 生成区保护 | 在根 README 的标记之外加入的手写内容，`build` 之后保持不变 |
| T14 | 禁止项 | 渲染结果中不出现排名、购买链接、折扣码、用法用量；`validate` 对包含 `buy`、`discount`、`dose` 等关键词的 `summary` 发出告警 |
| T15 | 无中文目录 | 没有 `i18n/zh/` 时 `build` 成功且不生成 `*.zh.md`（见第 7 节） |
| T16 | 血缘图 | `index/lineage.md` 中，已确认关系是实线，`reported` 关系是虚线，stub 有单独样式；与 5.7 的 SVG 示意一致 |

测试里的 `expected/` 文件只在有意改变格式时更新，更新必须单独提交并在 PR 描述里说明。

## 11. Agent 任务拆分与路线图

任务按依赖顺序排列。每个任务以一个 PR 交付，并附上对应的验收编号（第 10 节）。A 是其余任务的前提；B、C、D 可在 A 完成后并行。

| 任务 | 内容 | 依赖 | 验收 |
| --- | --- | --- | --- |
| A | 创建仓库骨架（第 8 节）；`schema/` 与 `vocab/`；把第 5 节 CSV 原样放入 `tests/fixtures/`；先读 awesome-peptide 的 `awepep` 包，记录可复用部分 | 无 | 目录与 CI 空跑通过 |
| B | 校验器：E01–E12、W01–W05；`validate` 命令 | A | T04–T08、T11 |
| C | 解析器：状态推导、pending flags、谱系、`last_verified`，输出 `entities_resolved.csv` | A | T01–T03、T05 |
| D | 模板与渲染：名片、总索引、各分面索引、`lineage.md`、`changes.md` | A、C | T09、T10、T12、T13、T16 |
| E | 核实 5.8 的 10 条待核实项，逐条以 PR 提交，改动只涉及 `data/` | A | 每条有证据行或在 `note` 中说明无法核实 |
| F | 与 awesome-peptide 对接：回填 `paper_links.awepep_id`，生成反向链接清单（不改动对方仓库，仅给出 issue 草稿） | A | 回填后 `validate` 通过 |
| G | `add` 与 `check-links`、`stale` 命令 | B、C | 命令行行为测试 |
| H | CI：`validate.yml`、`build.yml`、`stale.yml`；PR 模板与 `CONTRIBUTING.md` | B、D | PR 上能看到预览评论 |
| I | 扩充数据：按第 1 节的纳入范围，每类先收 5–10 家，仅 `inclusion=full` 且有证据者；其余为 stub | D | 无校验报错 |
| J | 中文：`i18n/zh/`、模板中的 `t` 过滤器、`*.zh.md` 输出 | D | T15 与第 7 节验收 |

**路线图**

- **v0.1**：A–D、E，加 fixture 的全部验收。仓库公开。
- **v0.2**：G、H，开始扩充数据（I），首批 20–30 家。
- **v0.3**：J，中文翻译，W06 生效。
- **v0.4**：定时的新闻和 GitHub 监测，生成候选事件的 PR（第 9 节）。
- **v0.5**：SQLite 与 JSON 的 Release 附件，数据版本号与变更日志。

**给 agent 的工作规则**（同时写入 `AGENTS.md`）

1. 只改 `data/`、`notes/`、`i18n/`、`vocab/` 和代码；绝不手改 `cards/`、`index/`、`build/`。
2. 每个事实性字段都要有 `evidence_ids`；找不到证据就不写，或写成 `rumor`。
3. 不确定时降低 `confidence`，不要提高；来源冲突写在 `note`，不要挑一个。
4. 摘要只能用自己的话改写，不整段复制来源；单个来源的直接引用不得超过十五个词。
5. 不添加排名、购买链接、折扣码、用法用量、灰色市场的研究肽供应商，也不建立人员表。
6. 状态类变更必须引用证据；改状态的 PR 描述里写明证据等级。
7. 开工前先阅读本计划的第 3、4 节，不得自创枚举值，需要新值时先提 PR 改 `vocab/`。

## 12. 未决问题与来源

**需要你拍板的问题**（我没有等你回复，已按下列默认值设计；如要改，请在文档里评论）

1. **事件表**：采用单一 `events.csv`（含状态、融资、合作、发布等所有类型），而不是按类型分表。理由是时间线渲染和审计更简单；代价是列中有些字段对部分事件类型为空。
2. **生成物是否提交到 main**：采用由机器人在 main 上提交生成的 `cards/`、`index/`，让 GitHub 上直接可浏览。代价是提交历史里有机器人噪音，可通过 `[skip ci]` 和只在 push 到 main 时生成来控制。
3. **人员表**：不建。人名只出现在公开报道过的事件摘要中，避免形成个人档案。
4. **仓库名**：暂定 `awesome-ai4peptide-companies`，命令行前缀 `awepep-co`；如果要改名，需要同步 `pyproject.toml`、包名与文档。
5. **许可证**：数据（CC BY 4.0 或 CC0）与代码（MIT）是否分开授权，由你决定。
6. **A 级证据的认定**：目前定义为公司官方公告、监管或交易所文件、同行评审论文、官方代码仓库。是否把创始人本人的公开账号也算 A 级，需要你定。

**已知局限**

- Anew Labs 的分拆目前只有两个独立的 B 级来源，没有找到官方公告，所以是 confirmed 但没有 A 级支持；融资额和持股比例仍为 reported。
- 一篇 Wowtale 英文文章无法抓取全文，仅凭搜索摘要入库，已列入 5.8 第 1 项重新核实。
- 元思生肽的总部城市来源冲突，`hq_city` 留空；其闭环等级是 `proposed`，目前缺乏公司自己对 AI 或闭环流程的描述。
- 我没能读到 awesome-peptide 仓库的 `CONTRIBUTING.md` 与 `awepep` 包的内部实现，所以模板和命令行风格需要 agent 先对齐。

**来源**

本计划中案例的全部来源 URL、证据等级和发布日期见 5.4 的 `evidence.csv`（22 行）；事实核对以该表为准，核对时请以原始页面而不是本文为准。

- [awesome-peptide](https://github.com/zhaisilong/awesome-peptide)：本项目的姊妹仓库，`awepep_id` 回填与模板约定的参照。
