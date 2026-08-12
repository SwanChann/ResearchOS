# 入口提示词：接续已经存在的 ResearchFlow 项目

适用场景：在新对话、其他文件夹或更换 agent 后，继续一个已经用 `rf project add` 注册的项目。

使用前替换：

- `<PROJECT_ID>`：例如 `embodied-nav`。
- `<WORKSTREAM_OR_TASK>`：本轮要继续的具体工作；不确定时写“先恢复状态，不立即执行新工作”。

复制下面整个文本块到新对话：

```text
请使用 $context-handoff 的 Import/重建思路，接续已经存在的 ResearchFlow 项目。

ResearchFlow CLI：F:\codespace\ResearchOS\.venv\Scripts\rf.exe
项目 ID：<PROJECT_ID>
本轮 workstream 或任务：<WORKSTREAM_OR_TASK>

“不依赖旧对话记忆”不是遗忘项目历史，而是不要把旧聊天或模型记忆直接当作当前事实。
请从持久状态和当前环境重新核验：

1. 运行：
   & 'F:\codespace\ResearchOS\.venv\Scripts\rf.exe' project show '<PROJECT_ID>'
2. 按输出路径依次完整读取该项目的 AGENTS.md、KNOWLEDGE.md、memory/current-state.md。
3. 运行：
   & 'F:\codespace\ResearchOS\.venv\Scripts\rf.exe' --project '<PROJECT_ID>' status --verbose
   & 'F:\codespace\ResearchOS\.venv\Scripts\rf.exe' --project '<PROJECT_ID>' knowledge check
4. 如果任务涉及研究代码，先在 project show 给出的 repo 中运行 git rev-parse --show-toplevel、git rev-parse HEAD 和 git status --short；保留所有已有未提交改动。
5. 只检索本轮任务相关的 ResearchFlow 记录。涉及论文主张时，再核对 Zotero、已验证 PAPER 记录和必要的原始 PDF；不要仅凭聊天摘要下结论。
6. 如果存在多个 handoff/workstream，只选择与项目 ID 和本轮任务匹配的一条，不要混合其他工作流。
7. 只读报告 snapshot 数量、Git checkpoint 和外部资产未备份边界。不要因为存在本地 Git 或 snapshot 就声称 repo、Zotero、数据集/权重已有完整备份。
8. 若发现旧 schema、matrix axes 或未登记历史产物，只运行对应 migration `--dry-run` 并给出文件清单、风险和回退方式；未经本轮明确授权不得迁移真实项目。

第一份回复先给“恢复简报”，包含：
- 已选择的项目 ID、ResearchFlow workspace 和独立 repo；
- 已核验的当前问题、阶段、active hypothesis/experiment、latest run/decision、阻塞项和 next action；
- Git HEAD、分支、clean/dirty 状态（仅在代码任务相关时）；
- 持久记录与当前事实之间的任何不一致；
- KNOWLEDGE 生成区是否 current、review/provenance 是否 stale，以及 snapshot/外部备份边界；
- 一项优先下一步，以及它是否需要我的新授权。

恢复简报完成后，再继续本轮已明确要求且已授权的任务。
未经本轮明确授权，不进行 SSH/GPU/机器人操作、破坏性清理、Zotero 写入、Git merge/push，且不要把 TEST/MOCK 或旧记录冒充为当前科学结果。
```

这份入口不会创建新项目，也不会重置已有状态；如果 `<PROJECT_ID>` 不存在，应停止并报告，而不是自动新建同名项目。
