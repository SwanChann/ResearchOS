# ResearchFlow V0.5.0 Definition of Done 审计

审计日期：2026-08-12

审计对象：本地优先 ResearchFlow 控制平面

结论：A-O 合同在本地 TEST/MOCK/临时 fixture 验收边界内通过；两个真实专题未迁移、未重建导航，`embodied-nav` 另完成了一次不修改源记录的新目录恢复演练；没有把系统测试冒充为科研结果。

## 验收矩阵

| 条目 | 结论 | 可核验依据 |
|---|---|---|
| A. 架构与接口先冻结 | PASS | `docs/architecture.md`、`docs/interface-design.md`、ADR-0001..0006；控制平面与研究代码仓库分离。 |
| B. 核心对象可持久化 | PASS | Project、Repository/Paper Evidence、Observation、Hypothesis、Experiment、Run、Decision 均有文件合同和校验；toy E2E 实际串联全部对象。 |
| C. 人可读 CLI | PASS | `status/show/list/search/logs/artifacts/doctor` 输出可直接检查；CLI 回归覆盖错误上下文和显式项目选择。 |
| D. 新 agent 可恢复 | PASS | 每个项目生成 `AGENTS.md`、`KNOWLEDGE.md`、`memory/current-state.md`；E2E 关闭并重新打开项目后核对最新 Experiment、Run、Decision 和引用。 |
| E. Run 可追溯 | PASS | 每个 Run 固化 experiment、commit、command、环境、时间、状态、metrics、日志和 artifacts；正式运行受 clean commit 和状态门约束。 |
| F. toy 可确定性复跑 | PASS | `tests/test_e2e_toy.py` 在独立 Git 仓库/worktree 中执行 smoke、pilot、full，验证一致 TEST/MOCK metrics。 |
| G. Git 安全 | PASS | worktree、允许/冻结路径、dirty tree、baseline commit 和 full approval 均有实现与测试；无自动 merge/push。 |
| H. 单 GPU 协调 | PASS（合同级） | 本地锁与远端原子锁目录有测试；只保证 ResearchFlow 客户端之间协作，不声称能阻止外部进程，也未验证真实 GPU heavy run。 |
| I. 不伪造科研成果 | PASS | fixture 和测试指标均标记 `TEST / MOCK`/`test_only`；文档明确 plumbing、pilot、系统验收与科学证据的边界。 |
| J. 可恢复性 | PASS（项目 workspace） | snapshot create/list/show/verify/restore、原子创建、项目隔离、manifest/路径逃逸防护、禁止 workspace 内嵌套恢复、恢复时二次哈希、确认式原位恢复与回退副本均有测试；外部 repo/Zotero/大资产明确只引用。 |
| K. Git 状态准确 | PASS | project/status/doctor 分开报告路径、repo、HEAD/unborn、branch/detached、commit/checkpoint、tracked dirty 和 untracked；普通 WARN 兼容退出 0，strict 可失败。 |
| L. 跨领域矩阵 | PASS（fixture） | generic、embodied-navigation、自定义 confirmed axes、锁定、dry-run/快照迁移、superseded cell/evidence 和幂等重放均有测试。 |
| M. Artifact/Knowledge | PASS（fixture） | 项目内路径、手工 registry 逃逸防护、SHA-256、无环双向 lineage、迁移和生成导航的人工区保留/幂等/stale/歧义 marker 检测均覆盖。 |
| N. 审核与 Idea provenance | PASS（合同级） | source/fingerprint、人审、复现、科学结论分层；review/Idea/matrix 指纹 stale；XIDEA→Hypothesis 递归 PAPER/claim 来源和 novelty 警告。 |
| O. Zotero 诊断 | PASS（mock） | 分类配置/连接/library/item/Server ID/attachment 路径；mock 断言全部请求为 GET，无写入或下载。 |

## V0.4.2 已关闭并继续保留的缺陷

### 1. 普通 doctor 隐式接触 SSH

旧行为会在本地完整性审计时探测所有配置机器，导致审计结果依赖 VPN/服务器状态，并可能产生未获当前授权的外部连接。现改为：

- `rf doctor` 只检查本地配置、项目、schema、引用、ID、技能和启动文件；
- `rf doctor --probe-machines` 才进行显式 live probe；
- 具体机器仍可用 `rf compute probe NAME [--dry-run]` 检查。

### 2. E2E 的入口和跨会话出口不完整

旧 E2E 从 Observation 开始，没有实际 Evidence 记录，也没有在流程结束后重新打开项目。现已增加：

- 带固定 commit 的 TEST/MOCK Repository Evidence；
- Evidence → Observation → Hypothesis → Experiment → Run → Observation → Decision 完整链；
- 重新打开项目后的状态恢复、启动文件和 broken-reference 检查；
- 从无关工作目录运行显式 `--project` 的 CLI 回归。

## 验证命令

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_cli.py tests/test_e2e_toy.py tests/test_project.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q researchflow tests
git diff --check
& .\.venv\Scripts\rf.exe --project embodied-nav doctor
```

V0.5.0 实际结果：

- 新增能力聚焦测试：47 passed；
- 全套测试：81 passed（fresh collection 共 81）；
- `compileall`：通过；
- `git diff --check`：通过；
- CLI root/snapshot/matrix/artifact/knowledge/Zotero doctor help smoke：6/6 exit 0；
- `embodied-nav` 与 `mllm_overthinking` 的 `project show`、`status`、不带 live probe 的 `doctor`、`matrix validate`：8/8 exit 0；两者旧 schema matrix 均保持可读且 `valid: true`；
- 两个真实项目的默认 snapshot 目录和 KNOWLEDGE 新生成区最初均为空；未执行 rebuild/migration。随后 `embodied-nav` 在自定义 E 盘目录完成 create/verify/dry-run/new-target restore，源 workspace 指纹保持不变；
- `doctor` 对 `server4090` 输出 `skipped`，未执行 SSH live probe。

本审计随获授权的 V0.5.0 本地 checkpoint 一并提交；未执行 push 或 merge。实现前基线 HEAD 为 `fe6f9589b92c2a1f9493c24f372c5fbeb034ce5f`、branch `main`。

## 不在本次 DoD 内的事项

- 实时 SSH、真实 GPU/heavy 作业、机器人和科学实验；
- GUI、云同步、向量数据库、多 agent runtime、自动无限研究；
- Zotero 写入、PDF 复制、自动做出科学判断；
- 继续扩大 embodied-nav 论文数量；
- 自动 remote cancel、远端资产清理或 Git push。

这些是将来可单独立项和授权的能力，不是当前系统合同失败。真实项目的 Artifact/Knowledge/verification/matrix schema 迁移仍需单独授权；本轮通过的是兼容读取与临时 fixture 迁移，不是实际迁移。
