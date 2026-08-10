# ResearchFlow V0.4.2 Definition of Done 审计

审计日期：2026-08-11

审计对象：本地优先 ResearchFlow 控制平面

结论：A-I 合同在本地 TEST/MOCK 验收边界内通过；未把远端 CPU fixture、GPU 可用性或具身导航研究结论冒充为系统验收结果。

## 验收矩阵

| 条目 | 结论 | 可核验依据 |
|---|---|---|
| A. 架构与接口先冻结 | PASS | `docs/architecture.md`、`docs/interface-design.md`、ADR-0001..0005；控制平面与研究代码仓库分离。 |
| B. 核心对象可持久化 | PASS | Project、Repository/Paper Evidence、Observation、Hypothesis、Experiment、Run、Decision 均有文件合同和校验；toy E2E 实际串联全部对象。 |
| C. 人可读 CLI | PASS | `status/show/list/search/logs/artifacts/doctor` 输出可直接检查；CLI 回归覆盖错误上下文和显式项目选择。 |
| D. 新 agent 可恢复 | PASS | 每个项目生成 `AGENTS.md`、`KNOWLEDGE.md`、`memory/current-state.md`；E2E 关闭并重新打开项目后核对最新 Experiment、Run、Decision 和引用。 |
| E. Run 可追溯 | PASS | 每个 Run 固化 experiment、commit、command、环境、时间、状态、metrics、日志和 artifacts；正式运行受 clean commit 和状态门约束。 |
| F. toy 可确定性复跑 | PASS | `tests/test_e2e_toy.py` 在独立 Git 仓库/worktree 中执行 smoke、pilot、full，验证一致 TEST/MOCK metrics。 |
| G. Git 安全 | PASS | worktree、允许/冻结路径、dirty tree、baseline commit 和 full approval 均有实现与测试；无自动 merge/push。 |
| H. 单 GPU 协调 | PASS（合同级） | 本地锁与远端原子锁目录有测试；只保证 ResearchFlow 客户端之间协作，不声称能阻止外部进程，也未验证真实 GPU heavy run。 |
| I. 不伪造科研成果 | PASS | fixture 和测试指标均标记 `TEST / MOCK`/`test_only`；文档明确 plumbing、pilot、系统验收与科学证据的边界。 |

## 本轮发现并关闭的缺陷

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

实际结果：

- 聚焦项目/CLI/E2E 测试：16 passed；
- 全套测试：43 passed；
- `compileall`：通过；
- `git diff --check`：通过；
- 从 `C:\Users\Modes` 运行绝对路径 CLI：`project show`、`status`、`matrix validate`、`doctor` 均通过；
- embodied-nav 文献矩阵：18 papers × 12 axes，216 个 supported cells，10 条 syntheses，6 条 ideas，`valid: true`；
- `doctor` 对 `server4090` 输出 `skipped`，未执行 SSH live probe。

最终 commit 以本轮提交后的 `git log -1` 为准；提交只包含 ResearchFlow 系统、测试和文档，不包含远端操作或具身导航科研变更。

## 不在本次 DoD 内的事项

- 实时 SSH、真实 GPU/heavy 作业、机器人和科学实验；
- GUI、云同步、向量数据库、多 agent runtime、自动无限研究；
- Zotero 写入、PDF 复制、自动做出科学判断；
- 继续扩大 embodied-nav 论文数量；
- 自动 remote cancel、远端资产清理或 Git push。

这些是将来可单独立项和授权的能力，不是当前系统合同失败。专题的 18 篇现有文献是文献层真实验收语料；继续加论文属于使用系统做研究，而不是完成 ResearchFlow 本身的必要条件。
