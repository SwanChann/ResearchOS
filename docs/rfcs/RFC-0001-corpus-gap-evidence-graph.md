# RFC-0001：CorpusGap + EvidenceGraph

- 状态：Implemented and locally accepted；真实项目迁移仍需逐项目授权
- 日期：2026-09-05
- 目标版本：ResearchFlow 0.6.0
- 影响范围：项目 workspace、JSON Schema、ID 分配、`rf evidence` CLI、迁移器、doctor/status/Knowledge 投影与测试
- 不影响：独立研究代码仓、Zotero 数据库、现有 PAPER/REPO/HYP/EXP/RUN/OBS/DEC/ARTIFACT 的可读性

## 1. 摘要

本 RFC 建议在 ResearchFlow 中增加两个互补模块：

1. **CorpusGap**：冻结一个已核验论文语料快照，把逐篇抽取转换为可追溯的结构元组，再用确定性 motif 规则生成“候选缺口”。候选缺口只是待审查对象，不能自动成为研究假设。
2. **EvidenceGraph**：用跨记录引用表达 `Problem -> Gap -> Hypothesis -> Experiment -> Finding -> Claim` 的证据链，并将论文、代码、运行与 Artifact 作为来源或执行证据。图索引可以重建；节点正文不复制；语义审查和科学结论保持分离。

核心决策如下：

- 不引入图数据库，也不把 NetworkX 序列化文件设为事实源。
- 新增的人类可读记录和关系账本是权威数据；`index.json` 只是可删除、可重建的派生索引。
- Agent/LLM 只能产出待导入草稿；写入前必须经过 schema、引用、指纹和路径检查。
- 结构验证是确定性的；语义审查是带审查者与输入指纹的独立记录。审查服务不可用、超时或解析失败时不得记为通过。
- 不自动将 Gap 提升为 Hypothesis，不自动改写证据链，不自动把负结果判为失败。
- 任何 `supported` 都只表示“当前证据链在限定范围内支持”，不表示论文主张已经被独立复现或科学成立。

## 2. 来源审查与证据边界

### 2.1 固定审查对象

| 对象 | 固定版本 | 当前可核验范围 | 结论边界 |
|---|---|---|---|
| SGHA | [`09f92147`](https://github.com/SarveshVGharat/structural-gap-hypothesis-agent/tree/09f92147f07482f8ae8ed4adf4cec258c124e4ba)，论文 [arXiv:2608.17501](https://arxiv.org/abs/2608.17501) | 完整公开源码、schema、CLI、离线演示与测试；隔离环境中 24 项测试通过 | 可以审查实现；其演示仍是 synthetic/offline contract evidence，不是论文结果复现 |
| EviGraph | 论文 [arXiv:2608.04738](https://arxiv.org/abs/2608.04738)，本地 TeX 包 SHA-256 `38706d089eda52500d6294fba04e4755461513827335d05f047751e390494443` | TeX、算法伪代码、提示词、数据结构和附录 trace | 未发现公开实现；只能做“论文设计级”审查，不能声称做过实现审查 |
| ABE-Ralph | [`67ada1c0`](https://github.com/Flavorfish/AutoRepro/tree/67ada1c0cfc3aa3b0304b1bf1a83786daf18ee27)，论文 [arXiv:2608.26753](https://arxiv.org/abs/2608.26753) | 公开 audit modules、自包含 demo、历史实验 Artifact；核心模块可编译，demo 在 UTF-8 环境下跑通 | 主 8 步 orchestrator `ralph_github.py` 未公开，完整流水线不可复核；历史 Artifact 不等于当前科学结果 |

补充限制：ABE-Ralph 根目录未见明确 LICENSE，因此本 RFC 只借鉴可描述的设计思想，不复制其源码。EviGraph 的论文示例没有实际触发 rollback 或长期记忆检索，二者只能作为待实现假设。

### 2.2 可采用、需改造、暂不采用

| 来源 | 可采用 | 必须改造 | v1 不采用 |
|---|---|---|---|
| SGHA | typed corpus graph、稳定 ID、motif 驱动缺口、counterevidence-first、多阶段产物 | 启发式分数必须标成 heuristic；gap 版本不可原位覆盖；图只能是派生索引 | 自动检索供应商编排、自动 Gap→Hypothesis、把 LLM 评分当科学判定 |
| EviGraph | `H->E->F->C` 最小证据链、限定范围 Claim、负结果保留、最早弱节点定位、checkpoint hash | rollback 先降级为诊断与建议；语义检查必须外置、可审计、fail-closed | 自动 repair、自动 rollback、未经实证的长期 memory policy |
| ABE-Ralph | 实验 fidelity contract、M1–M5 失败分类、定量/定性/代码三层核验 | metric 必须精确 ID/别名映射；审查失败不得默认通过；完成状态不能只看文件存在 | 依赖未公开 orchestrator 的完整 pipeline、硬编码外部 CLI、模糊键匹配作决定性证据 |

### 2.3 源码审查发现的具体风险

1. SGHA 的 `candidate_gaps.json` 会在 novelty filter 阶段被覆盖。ResearchFlow 必须保留旧版本，以 `supersedes` 建立谱系。
2. SGHA 当前 novelty/feasibility/impact 计算包含固定启发式常数。ResearchFlow 可以保存该分数用于排序，但字段必须包含 `kind: heuristic` 和算法版本，不能显示成已验证的“顶会潜力”。
3. ABE-Ralph 的代码对齐检查在缺少 `critical_modules`、blueprint 不存在或 LLM 解析失败时存在宽松通过路径；最终 `overall_pass` 主要由模块是否存在决定。ResearchFlow 的阻断性检查必须 fail-closed，语义意见只能是 advisory。
4. ABE-Ralph demo 在普通 Windows 默认代码页下读取 UTF-8 文本会触发 `UnicodeDecodeError`，设置 `PYTHONUTF8=1` 后才能跑通。ResearchFlow 必须延续显式 UTF-8 I/O 合同。
5. EviGraph 的“修复、回滚、长期记忆”主要由论文算法和提示词描述，缺少公开实现证据；本 RFC 不把它们纳入 v1 验收承诺。

## 3. 问题定义

ResearchFlow 0.5.0 已能保存论文、代码证据、假设、实验、运行、观察、决策和 Artifact，但还缺少以下可验证连接：

- “这批论文的边界是什么”没有冻结语料对象；后续新增论文会让旧缺口的来源范围变得含糊。
- 从论文限制到候选缺口的抽取过程没有结构化中间层，Agent 总结难以逐边回查。
- HYP、EXP、RUN、OBS 之间虽有引用，但没有 Claim 及完整证据链的统一验证器。
- 现有 `status` 能检查项目完整性，却不能回答“这项 Claim 的最早薄弱节点在哪里”。
- 缺少 source fingerprint 变化后的定向失效规则，容易把旧审查结论继续显示为当前事实。

因此，新模块的目标不是替研究者自动想出并认定一个好 idea，而是让“从语料到缺口、从假设到主张”的每一步都可定位、可失效、可审查。

## 4. 设计目标与非目标

### 4.1 目标

- 一个 Corpus 对象精确固定 PAPER 列表、PAPER 指纹、matrix 指纹、查询范围与排除规则。
- 抽取结果能定位到 paper、claim/section/page 等来源位置，并保留抽取器与人工审查状态。
- Gap 候选由版本化 motif 规则确定性生成；相同输入得到相同候选指纹。
- EvidenceGraph 能检查端点类型、悬空引用、依赖环、来源指纹、运行值和 Claim 范围。
- 找到最早弱节点，但 v1 只输出修复计划，不自动改数据。
- 所有新 CLI 支持显式 `--project`；写操作遵循原子写、文件锁、dry-run、snapshot 和幂等合同。
- 旧项目不迁移也能继续使用 0.5.0 功能。

### 4.2 非目标

- 不在 core 中实现论文搜索、PDF 下载、LLM provider、向量库或联网爬虫。
- 不自动评判论文新颖性、顶会潜力或科学真伪。
- 不把 smoke/mock/demo 结果升级为科学结果。
- 不替代 Git、Artifact registry、Zotero 或独立代码仓。
- v1 不实现自动 repair、自动 rollback、跨项目全局知识图谱或图形化 Web UI。

## 5. 架构决策

### 5.1 两层图，而不是一个万能图

```text
PAPER + LiteratureMatrix + reviewed extraction
                    |
                    v
          CorpusGraph（派生、可重建）
                    |
          deterministic motifs
                    v
             GAP（正式草稿记录）
                    |
              human approval
                    v
PROBLEM -> GAP -> HYP -> EXP -> OBS(Finding) -> CLAIM
                         |      ^               ^
                         v      |               |
                        RUN ----+          PAPER / ARTIFACT

上面核心链 + 关系账本 = EvidenceGraph
```

- **CorpusGraph** 服务于跨论文结构比较，节点包括 Paper、Method、Task、Dataset、Metric、Assumption、Result、Limitation、FailureCondition；其 index 完全可由 Corpus 与 extraction 重建。
- **EvidenceGraph** 服务于研究论证。核心链节点使用正式 ResearchFlow 记录；论文、Repo、Run、Artifact 是来源和执行证据。
- 两图通过 GAP 的 `derivation` 连接，但不共享一份可变 JSON 事实源。

### 5.2 权威数据与派生数据

| 类型 | 权威性 | 说明 |
|---|---|---|
| PAPER、REPO、HYP、EXP、RUN、OBS、DEC、ARTIFACT | 既有权威记录 | 保持 0.5.0 路径和语义 |
| CORPUS、extraction、PROBLEM、GAP、CLAIM | 新增权威记录 | 普通 YAML/Markdown，可 Git diff |
| `edges.yaml` | 权威关系账本 | 只存关系、来源引用和状态，不复制节点正文 |
| review/audit records | 权威审查记录 | 绑定对象指纹；对象变化后变 stale，不覆盖旧审查 |
| CorpusGraph/EvidenceGraph `index.json` | 派生 | 可删除重建，不进入科学证据判断 |
| Agent 原始输出 | 非权威草稿 | 只有 preflight/import 后才成为权威记录 |

### 5.3 不引入 NetworkX 运行时依赖

v1 用标准库的 adjacency map、DFS/Kahn 算法完成端点、环、可达性和最早弱节点检查。理由：ResearchFlow 当前仅依赖 PyYAML 与 jsonschema；本模块的数据规模以个人项目的数十至数百篇论文为主，引入图数据库或 NetworkX 会扩大恢复面而没有必要。

## 6. 文件布局与 ID

### 6.1 新目录

```text
<workspace>/
  evidence/
    corpora/CORPUS-0001.yaml
    corpus-extractions/CORPUS-0001/PAPER-0001.yaml
  memory/
    problems/PROB-0001.md
    gaps/GAP-0001.md
    claims/CLAIM-0001.md
  .research/
    evidence-graph/
      edges.yaml
      audits/EGAUDIT-000001.yaml
      index.json
    corpus-gap/
      runs/CGAPRUN-000001/
        manifest.yaml
        motifs.jsonl
        candidates.jsonl
        audit.jsonl
```

`runs/CGAPRUN-*` 是语料分析 run，不是模型训练 `RUN-*`；其结果只能产生候选 Gap。大型 PDF、模型权重和数据集仍不进入 workspace。

### 6.2 新 ID 前缀

| 前缀 | 宽度 | 含义 |
|---|---:|---|
| `CORPUS` | 4 | 冻结语料快照 |
| `PROB` | 4 | 研究问题与边界 |
| `GAP` | 4 | 候选/已审查研究缺口 |
| `CLAIM` | 4 | 有范围限定的研究主张 |
| `CGAPRUN` | 6 | CorpusGap 派生运行 |
| `EGAUDIT` | 6 | EvidenceGraph 审查 |

ID 继续由 ResearchFlow 全局计数器原子分配。用户提供旧 ID 时只能登记映射，不能复用已分配 ID。

## 7. 数据结构

所有 schema 使用 JSON Schema Draft 2020-12，`additionalProperties: false`。所有时间为带时区 ISO 8601；所有路径为 workspace/repo 内的规范化相对路径；文本以 UTF-8 读取和原子写入。

### 7.1 Corpus

```yaml
schema_version: 1
id: CORPUS-0001
title: Embodied navigation inspection corpus 2026-09-05
scope:
  research_area: embodied navigation
  application_context: inspection
  included_years: [2024, 2025, 2026]
  inclusion_rules: [peer-reviewed or clearly versioned preprint]
  exclusion_rules: [no accessible primary text]
source_matrix:
  id: LITMATRIX-0001
  sha256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
papers:
  - id: PAPER-0001
    source_fingerprint: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
    review_status: verified
created_at: 2026-09-05T12:00:00+08:00
created_by: agent
corpus_fingerprint: cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
```

`corpus_fingerprint` 由 canonical JSON 的 scope、matrix hash、排序后的 paper ID 与 source fingerprint 计算。Corpus 创建后不可原位增删 PAPER；变化生成新 CORPUS，并用 `supersedes` 连接。

### 7.2 Corpus extraction

每个 PAPER 一个 extraction 文件，便于独立审查和失效：

```yaml
schema_version: 1
corpus_id: CORPUS-0001
paper_id: PAPER-0001
paper_fingerprint: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
extractor:
  kind: agent
  name: codex
  version: recorded-runtime-version
tuples:
  - id: TUPLE-<stable-hash>
    subject: {type: Method, key: method/canonical-name}
    relation: fails_under
    object: {type: FailureCondition, key: condition/canonical-name}
    evidence:
      paper_claim_ids: [C3]
      locators: [{kind: page, value: "7"}]
      exact_text_sha256: dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd
    epistemic_status: paper_reported
review:
  status: pending
  reviewer: null
  reviewed_fingerprint: null
```

允许的 subject/object 类型为 `Paper, Method, Task, Dataset, Metric, Assumption, Result, Limitation, FailureCondition`。允许的 relation 为版本化词表，例如 `proposes, evaluated_on, uses_dataset, measured_by, improves_over, fails_under, assumes, limited_by, contradicts`。

`exact_text_sha256` 证明抽取对应的原始文本片段，但默认不把长引文重复写入图。需要查看原文时由 PAPER 的受控 PDF/分析记录解析。

### 7.3 Problem

PROB 使用带 YAML front matter 的 Markdown：

```yaml
schema_version: 1
id: PROB-0001
title: 巡检环境中的具身导航可靠性
objective: 在限定巡检环境中识别并验证导航失效机制
scope: 双足或四足机器人在可复现实验协议下的视觉导航
constraints: [双卡 RTX 4090, Lite3, TRON1]
application_context: 工业巡检
status: active
created_at: 2026-09-05T12:00:00+08:00
supersedes: null
```

Problem 是当前研究问题的稳定锚点；`memory/current-state.md` 只投影 active PROB，不再充当唯一机器可读来源。

### 7.4 Gap

```yaml
schema_version: 1
id: GAP-0001
title: 视觉退化条件下的恢复决策缺口
problem_id: PROB-0001
statement: 现有语料尚未覆盖短时视觉失效后的可验证恢复决策
mechanism_missing: 显式失败检测与恢复策略联动
remaining_scope: 已排除只处理静态遮挡且不执行恢复动作的方法
boundary_conditions: [短时遮挡, 低照度, 计算预算固定]
known_counterevidence:
  - ref: PAPER-0008
    effect: partially_addresses
    rationale: 该工作检测遮挡，但没有验证恢复动作
falsification: 若已核验工作在相同边界内完成检测、恢复并报告可复现结果，则该缺口关闭
derivation:
  corpus_id: CORPUS-0001
  corpus_fingerprint: cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
  cgap_run_id: CGAPRUN-000001
  motif_id: MISSING_EDGE
  tuple_ids: [TUPLE-a4c3e11d]
scores:
  novelty: {value: 0.71, kind: heuristic, algorithm: motif-score-v1}
  feasibility: {value: 0.65, kind: heuristic, algorithm: motif-score-v1}
review:
  status: pending
  reviewer: null
  reviewed_fingerprint: null
state: candidate
supersedes: null
```

`state` 允许 `candidate, approved, rejected, superseded`。`approved` 只表示人类允许把它作为研究输入，不表示 Gap 已被证明开放。审查必须回答：语料覆盖是否足够、反例是否搜索、剩余范围是否具体、能否被证伪、资源约束是否可行。

### 7.5 Claim

```yaml
schema_version: 1
id: CLAIM-0001
title: 限定条件下的 SPL 改善
statement: 在指定 TEST 数据集和三次种子运行中，方法 A 的平均 SPL 高于基线 B
scope:
  datasets: [TEST-DATASET-01]
  platforms: [simulation]
  seeds: [1, 2, 3]
  conditions: [固定传感器输入, 固定推理预算]
qualifiers: [只适用于登记的数据版本和实验协议]
supporting_findings: [OBS-0004]
counter_findings: [OBS-0005]
metric_evidence:
  - run_id: RUN-0003
    artifact_id: ARTIFACT-0012
    artifact_sha256: eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
    json_pointer: /metrics/spl/mean
    metric_id: spl
    value: 0.62
    unit: ratio
status: draft
review:
  structural: pending
  semantic: pending
  reproduction: not_checked
scientific_establishment: not_established
supersedes: null
```

`status` 允许 `draft, evidence_ready, contradicted, superseded, retracted`。不提供无范围的 `true/verified`。负结果必须保存为 OBS，可形成否定 Claim，或把原 Claim 标为 `contradicted`；不得因为假设未通过就删除运行和 Finding。

### 7.6 Edge ledger

```yaml
schema_version: 1
graph_id: project-evidence-graph
edges:
  - id: EDGE-<stable-hash>
    from: PROB-0001
    relation: identifies
    to: GAP-0001
    provenance_refs: [CORPUS-0001, EGAUDIT-000001]
    status: active
    source_fingerprints:
      PROB-0001: ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
      GAP-0001: 1111111111111111111111111111111111111111111111111111111111111111
    created_at: 2026-09-05T12:00:00+08:00
    supersedes: null
```

边 ID 由 `from + relation + to + source_fingerprints` 计算。对象更新后创建新边或重新审查，旧边标为 `stale/superseded`，不原位伪装成当前证据。

### 7.7 Audit

```yaml
schema_version: 1
id: EGAUDIT-000001
target: CLAIM-0001
target_fingerprint: 2222222222222222222222222222222222222222222222222222222222222222
mode: full_chain
deterministic_checks:
  status: pass
  checks: [schema_valid, refs_resolve, metric_value_matches]
semantic_review:
  status: pending
  reviewer: null
  rationale: null
fidelity_review:
  status: fail
  failures: [M2]
earliest_weak_node: EXP-0002
repair_plan:
  allowed_actions: [revise_protocol, rerun_experiment, narrow_claim]
  automatic_mutation: false
created_at: 2026-09-05T12:00:00+08:00
```

审查状态统一为 `pass, fail, pending, unavailable, stale`。只有 `pass` 是通过；其余均不能被聚合成通过。

## 8. EvidenceGraph 类型系统与验证

### 8.1 核心关系

| from | relation | to | 确定性最低要求 |
|---|---|---|---|
| PROB | `identifies` | GAP | Gap 的 `problem_id` 完全相同 |
| GAP | `motivates` | HYP | Gap 已 approved；HYP 明确引用 GAP |
| HYP | `tested_by` | EXP | EXP 的 hypothesis ID 完全相同；有 falsification criterion |
| EXP | `produces` | OBS | OBS 引用已完成 RUN，RUN 引用该 EXP |
| OBS | `supports` / `weakens` / `contradicts` | CLAIM | OBS 是 `experimental_result`；Claim 明确列出该 OBS |
| PAPER | `supports_gap` / `weakens_gap` | GAP | paper fingerprint 与 gap derivation/review 一致 |
| ARTIFACT | `substantiates` | OBS/CLAIM | registry 中存在且 hash、路径、lineage 均有效 |

依赖边 `identifies/motivates/tested_by/produces` 必须构成 DAG。`supports/weakens/contradicts` 不参与依赖拓扑，但仍禁止自环和重复 active 边。

### 8.2 三层验证

1. **L1 结构与定量（阻断）**：schema、ID、端点、路径、hash、JSON Pointer、metric ID、值、scope、环和 staleness；完全确定性。
2. **L2 语义一致性（建议性但 fail-closed）**：Gap 是否落在 Problem 范围、实验是否可区分预测与反证、Claim 是否超出 Finding。它不自动修改记录；不可用时为 `unavailable`，不是 pass。
3. **L3 实现与复现（阻断或明确未检查）**：Git HEAD、dirty 状态、关键模块、命令、环境、数据/权重指纹、运行 Artifact。`not_checked` 不等于 fail，也不等于 pass。

Evidence-ready 的最低门槛是：L1 pass、L2 pass、所有支持 Finding 对应的 RUN 成功且 Artifact 可解析、L3 至少记录状态、Claim scope 不宽于 Finding。`scientific_establishment` 始终由更高层人工决策维护。

### 8.3 M1–M5 失败分类

- `M1 method_integrity_collapse`：关键机制缺失或被替代。
- `M2 silent_protocol_degradation`：数据、步数、seed、模型规模或评估协议静默降级。
- `M3 scale_driven_conclusion_inversion`：缩放后方向可能翻转。
- `M4 quantitative_key_mismatch`：metric 身份、键、单位、聚合或值不一致。
- `M5 incomplete_execution`：必要阶段或 Artifact 缺失。

分类是诊断标签，不直接等价于 Claim 为假。一个 audit 可以命中多类。

### 8.4 精确指标合同

- metric 使用 canonical ID；别名必须来自版本化 alias map，并记录映射来源。
- 值必须来自 registry 中已登记 Artifact 的 `json_pointer`，同时校验 Artifact hash。
- 禁止用字符串包含、编辑距离或“最像的键”决定通过。
- CSV 必须固定列名、行选择键和聚合方式；浮点容差必须在实验卡中预先声明。
- 文件存在只证明输出存在，不证明运行完成、协议一致或数值可信。

### 8.5 失效传播

| 变化 | 必须失效 | 不自动失效 |
|---|---|---|
| PAPER source fingerprint 变化 | 对应 extraction、Corpus verify、相关 Gap 文献审查与边 | 已完成 RUN 的原始 Artifact |
| LiteratureMatrix fingerprint 变化 | 由该 matrix 创建的新 Corpus 建议、未审查 gap scan | 已冻结 CORPUS 本身；它仍代表旧快照 |
| GAP 内容变化 | Gap review、GAP→HYP 边 | 已保存的旧 HYP；但显示 source stale |
| EXP 协议变化 | preflight、后续 RUN/OBS/CLAIM 链 | 旧 RUN Artifact；它仍对应旧 EXP 指纹 |
| RUN/Artifact hash 变化 | OBS 和 Claim audit | PAPER/Gap 审查 |
| CLAIM scope/statement 变化 | Claim 的 L1/L2/L3 audit | Finding 本身 |

## 9. CLI 设计

CLI 延续 `对象 + 动作` 风格，并默认在当前项目操作；所有命令支持根级 `--project`。

### 9.1 Corpus 与 extraction

```powershell
rf --project embodied-nav evidence corpus create `
  --matrix LITMATRIX-0001 --title "inspection navigation corpus" `
  --scope-file corpus-scope.yaml --dry-run

rf --project embodied-nav evidence corpus show CORPUS-0001
rf --project embodied-nav evidence corpus verify CORPUS-0001

rf --project embodied-nav scaffold corpus-extraction `
  --corpus CORPUS-0001 --paper PAPER-0001 --output extraction.yaml
rf --project embodied-nav preflight corpus-extraction extraction.yaml
rf --project embodied-nav evidence corpus add-extraction extraction.yaml --dry-run
```

`create` 只接受已登记、source/fingerprint 可解析的 PAPER。`add-extraction` 拒绝 paper fingerprint 不匹配、未知 relation、路径越界和未解析引用。v1 不在命令内部调用 LLM；Agent 按 scaffold 生成文件即可。

### 9.2 Gap

```powershell
rf --project embodied-nav evidence gap detect `
  --corpus CORPUS-0001 --motifs motif-rules-v1.yaml --dry-run
rf --project embodied-nav evidence gap list --state candidate
rf --project embodied-nav evidence gap show GAP-0001
rf --project embodied-nav evidence gap review GAP-0001 `
  --decision approve --reviewer "human:principal-investigator" --rationale-file review.md
rf --project embodied-nav hypothesis new `
  --title "视觉失效恢复策略" --statement "显式恢复决策能提高失败条件下的任务完成率" `
  --gap GAP-0001 --falsification "固定协议下不优于无恢复基线"
```

`detect` 只对已通过 extraction schema 的元组执行确定性 motif。支持 motif：`missing_edge`、`assumption_failure`、`evaluation_blind_spot`、`contradictory_results`、`dataset_method_mismatch`。review 绑定 Gap fingerprint；Gap 修改后旧 review 变 stale。只有用户明确执行 `hypothesis new --gap` 才创建 HYP。

### 9.3 Claim 与图

```powershell
rf --project embodied-nav scaffold claim --output claim.yaml
rf --project embodied-nav preflight claim claim.yaml
rf --project embodied-nav evidence claim add claim.yaml --dry-run
rf --project embodied-nav evidence claim show CLAIM-0001
rf --project embodied-nav evidence claim supersede CLAIM-0001 --with claim-v2.yaml

rf --project embodied-nav evidence graph rebuild --dry-run
rf --project embodied-nav evidence graph check --strict
rf --project embodied-nav evidence graph show --claim CLAIM-0001
rf --project embodied-nav evidence graph audit `
  --claim CLAIM-0001 --mode full-chain --dry-run
```

`rebuild` 只重建 `index.json`，不改变节点与边。`check --strict` 对 stale/unavailable/pending 返回非零。`show --claim` 输出最短支持链、反证边、最早弱节点、对象指纹与 audit 状态。`audit` 默认只运行 L1；L2/L3 结果通过显式审查文件导入，避免 core 绑定 provider。

### 9.4 诊断与现有命令集成

- `rf status` 增加 Corpus 数量、candidate/approved Gap、Claim 状态和 graph readiness 摘要。
- `rf doctor` 增加 schema、悬空引用、路径越界、index drift 和 stale audit 检查。
- `rf Knowledge synthesize/check` 投影已 approved Gap 与 evidence-ready Claim；candidate Gap 进入“待审查”，不进入“Verified Facts”。
- `rf evidence check` 聚合 PAPER/REPO/matrix/Corpus/graph 诊断，但保持每个合同的独立状态。

## 10. 迁移设计

### 10.1 兼容原则

- 0.5.0 workspace 无需迁移即可继续读取和写入旧记录。
- 安装新 schema 不等于修改真实项目。
- 不从 `XIDEA` 自动创造 GAP，不从论文摘要自动创造 Claim，不用占位节点伪造完整链。
- 只对已有精确 ID 引用建立可证明的边；不根据标题、文件名或相似字符串猜关系。

### 10.2 命令

```powershell
rf --project embodied-nav migrate corpus-gap-evidence-graph --dry-run
rf --project embodied-nav migrate corpus-gap-evidence-graph
```

dry-run 必须输出：

- 将创建的目录、schema version 和记录数量；
- 可精确映射的 HYP→EXP、EXP→OBS、Artifact→OBS/CLAIM 边；
- 无法映射的记录及原因；
- 不会创建的 PROB/GAP/CLAIM；
- 预计 snapshot 路径与 rollback 命令；
- 输入 fingerprint 和 migration plan fingerprint。

### 10.3 实迁移顺序

1. 获取项目文件锁并再次计算 plan fingerprint；与 dry-run 不一致则停止。
2. 调用现有 snapshot 机制创建并验证迁移前快照。
3. 创建新目录和空的 v1 edge ledger。
4. 扫描现有正式记录，仅写入 exact-reference edges；无法证明的关系写 migration report，不写边。
5. 原子写入 ledger、audit 和 migration marker。
6. 重建 index，运行 `evidence graph check`、`status` 与 `Knowledge check`。
7. 任一步失败则保留错误证据并给出从快照恢复到新目录的命令；不得原位自动恢复或删除失败现场。

### 10.4 幂等与回滚

- migration marker 保存输入集合、文件 hash、工具版本和 plan fingerprint。
- 相同输入重放不得分配新 ID、重复边或改写时间戳。
- 输入变化后必须生成新的 migration plan，不能沿用旧 approval。
- 回滚沿用 ResearchFlow snapshot restore，目标必须是新目录；原项目不原位覆盖。

## 11. 安全、并发与可恢复性

- 所有写入使用 `atomic_text`/`append_jsonl` 与项目锁；禁止半写 YAML/JSONL。
- schema 中的路径必须先 resolve，再验证仍位于允许的 workspace/repo 根内；拒绝 `..`、绝对外部路径和 symlink escape。
- graph rebuild 使用稳定排序和 canonical JSON；同一权威输入必须得到同一 SHA-256。
- 审查记录 append-only；撤销通过新记录表达，不改写旧审计。
- Agent 的 provider 名称、模型、提示版本和输入 fingerprint 写入 provenance，但模型输出不获得特殊权威性。
- 默认无网络；检索、PDF 获取和外部语义审查由已授权的外部步骤完成，再通过 preflight/import 接入。
- Windows 文本 I/O 明确 `encoding="utf-8"` 或 `utf-8-sig` 合同；终端乱码不得触发源文件重写。

## 12. 验收测试

### 12.1 Schema 与存储单元测试

- 新 ID 并发分配唯一、宽度正确、失败不跳用已有 ID。
- CORPUS canonical fingerprint 与 paper 顺序无关；变更 scope/paper fingerprint 必须改变结果。
- Corpus 拒绝未知 PAPER、缺 source fingerprint、未核验来源和 extra fields。
- extraction 拒绝未知 node/relation、错误 paper fingerprint、悬空 claim locator 和路径逃逸。
- Gap 相同输入与 motif 产生相同 candidate fingerprint；重放不重复写 GAP。
- Gap review 必须绑定当前 fingerprint；修改 Gap 后旧 review 显示 stale。
- Claim 拒绝无 scope、无 Finding、未知 metric ID、错误 unit、错误 JSON Pointer 或 Artifact hash。
- UTF-8 中文记录在 Windows 默认代码页与显式 UTF-8 子进程路径下均可往返。

### 12.2 Graph 验证单元测试

- 每种合法关系的端点通过；反向、跨类型、自环、重复 active 边失败。
- 悬空节点、重复 ID、依赖环和 unresolved provenance 失败。
- `H->E->OBS->CLAIM` 缺任一节点时 Claim 不为 evidence-ready。
- 实验协议不能区分 falsifiable prediction 时 L2 不通过。
- Claim scope 宽于 Finding 时 L2 不通过；收窄后通过且旧 audit 保留。
- 负 Finding 被保留，并能产生 `weakens/contradicts`；不得被 completion cleanup 删除。
- reviewer unavailable、timeout、异常和解析失败均为 `unavailable/fail`，绝不默认为 pass。
- exact metric alias map 通过；模糊字符串近似但无显式 alias 时失败。
- PAPER 变化只传播到文献侧；Artifact 变化只传播到实验/Claim 侧，边界与第 8.5 节一致。
- 删除 `index.json` 后 rebuild 得到相同 hash，且不修改任何权威记录。

### 12.3 CLI 测试

- 所有新 root/group/leaf `--help` 返回 0，错误 project 返回稳定非零码。
- `--project` 在当前目录之外仍能定位正确 workspace，且不会混入另一项目记录。
- 每个写命令的 `--dry-run` 文件树与 Git 状态零变化。
- `graph check --strict` 对 pending/stale/unavailable 返回非零并列出具体 ID。
- scaffold→preflight→import 的有效路径通过；缺字段、额外字段、编码错误和路径逃逸失败。

### 12.4 迁移测试

- 0.5.0 fixture 不迁移仍可执行旧 CLI。
- dry-run 不写文件、不分配 ID、不创建 snapshot。
- 实迁移先创建并验证 snapshot；人为破坏 snapshot 时迁移停止。
- 只为 exact refs 建边；标题相似、文件名相似和模糊 metric key 不得建边。
- 不自动创建 PROB/GAP/CLAIM，不修改原 HYP/EXP/RUN/OBS。
- 相同输入迁移两次结果、ID、edge hash 完全相同。
- 中途故障不留下半写权威文件，并给出恢复到新目录的可执行命令。

### 12.5 端到端 TEST/MOCK 场景

1. 创建含 3 篇 TEST PAPER 的 CORPUS，导入 reviewed extraction。
2. motif 生成 1 个 candidate Gap，加入 1 篇 counterevidence 后 remaining scope 被收窄。
3. 未经人工 review 时 `hypothesis new --gap` 拒绝；approve 后可显式创建 HYP。
4. 建立 EXP、TEST RUN、OBS 和限定范围 CLAIM；只有完整链和 L1/L2 通过后显示 evidence-ready。
5. 篡改 metrics Artifact 后 hash mismatch，Claim 立即 stale，原 Artifact lineage 与旧 audit 保留。
6. 快照、verify、restore 到新目录后，graph rebuild hash 与源项目一致。

该场景只能证明软件合同与恢复能力，输出必须带 TEST/MOCK 标签，不能作为论文、GPU、机器人或方法效果证据。

### 12.6 完成定义

- focused tests、全量 pytest、`compileall`、CLI parser traversal、`git diff --check` 全部通过。
- 不新增图数据库依赖；新 schema 随包安装并可在 editable/wheel 两种方式加载。
- 两个真实项目只做 read-only compatibility audit；不在验收中执行实迁移。
- 文档明确区分 source verified、human reviewed、reproduced 与 scientifically established。

## 13. 实施分期

### Phase A：最小 EvidenceGraph 核心

- 新 ID、schema、record resolver、edge ledger、deterministic validator、index rebuild。
- Claim/Problem 记录与 scaffold/preflight/import。
- status/doctor/Knowledge 的只读投影。

退出条件：不用 CorpusGap，也能对现有 HYP/EXP/RUN/OBS/Artifact 做可解释的链检查。

### Phase B：CorpusGap

- CORPUS freeze/verify、逐 PAPER extraction、deterministic motifs、GAP review。
- counterevidence 和启发式排序只作为待审查信息。

退出条件：同一 corpus/extraction 能确定性重建候选，且不能绕过人工 approval 创建基于 Gap 的 HYP。

### Phase C：迁移与恢复

- dry-run、snapshot、exact-ref mapping、幂等 marker、恢复演练 fixture。
- 对真实项目仅给出 migration plan；另行授权后才执行。

### Phase D：可选增强

- provider-neutral L2 reviewer adapter、fidelity audit adapters、图可视化导出。
- 自动 repair/rollback 和跨项目长期记忆需另立 RFC，并先取得真实失败 trace 证据。

## 14. 审核结论与具体决策点

本 RFC 推荐接受，但实现前需要人明确确认三项产品取舍：

1. **人工门禁**：默认只有 `human:*` reviewer 可以把 GAP 从 `candidate` 改为 `approved`；Agent 可以写 review 建议，不能批准。推荐保持此默认。
2. **Claim 门槛**：`evidence_ready` 要求 L2 语义审查 pass；如果没有可用 reviewer，就保持 pending，而不是只靠结构检查通过。推荐保持此默认。
3. **迁移范围**：首版迁移只建立 exact-reference 边，不自动补 PROB/GAP/CLAIM。推荐保持此默认，避免把旧摘要反向包装成新事实。

这三项默认值已由用户接受，并已进入 0.6.0 实现。任何真实项目的 migration apply、Corpus 建立、extraction review 或 Gap approval 仍需该项目范围内的新授权。

## 15. 实施与验收结果

0.6.0 已完成 Phase A-D 在本地系统范围内的合同：Corpus freeze/verify、逐 PAPER extraction scaffold/preflight/import、human-only acceptance、确定性 motif、TEST/MOCK 隔离、human-only Gap approval、Gap-provenance Hypothesis、Problem/Claim、精确 metric/Artifact/alias/tolerance、typed EvidenceGraph、claim-local L1 audit、fingerprint-bound L2/L3 review import、counterevidence、DOT/JSON export、snapshot-first exact-reference migration、幂等 marker 与失败回滚。

验收使用的 Corpus、Paper、Run、Artifact、Gap 和 Claim 全部是 TEST/MOCK fixture。迁移测试覆盖 dry-run 零写入、snapshot verify 失败时零权威写入、图重建故障回滚、重复 apply 幂等，以及快照恢复后 graph fingerprint 等价。两个真实项目只执行只读兼容检查，没有创建、迁移或审查任何真实研究记录。

该结果证明软件合同、失败关闭和恢复路径，不证明任何论文主张、研究缺口、方法效果、GPU 行为或真机性能。
