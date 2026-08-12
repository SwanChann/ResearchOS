# 入口提示词：开启全新的 ResearchFlow 专题

适用场景：在新对话中创建一个此前尚未注册的新专题，而不是接续现有项目。

使用前替换：

- `<TOPIC_NAME>`：专题的人类可读名称。
- `<PROJECT_ID>`：只使用小写字母、数字、`-` 或 `_`。
- `<REPO_PATH>`：独立于 ResearchFlow workspace 的本地目录。
- `<INITIAL_RESEARCH_QUESTION>`：初始研究问题；允许后续修订。
- `<FIRST_TASK>`：例如“只完成初始化并给出首批检索方案”。

复制下面整个文本块到新对话：

```text
请在本地 ResearchFlow 中开启一个全新的专题。这是 Initialize/start，不是恢复或覆盖已有项目。

ResearchFlow CLI：F:\codespace\ResearchOS\.venv\Scripts\rf.exe
专题名称：<TOPIC_NAME>
建议项目 ID：<PROJECT_ID>
独立 repo 路径：<REPO_PATH>
初始研究问题：<INITIAL_RESEARCH_QUESTION>
初始化后的第一项任务：<FIRST_TASK>

先读取 F:\codespace\ResearchOS\AGENTS.md、README.md、docs\interface-design.md、
docs\cross-folder-session-usage.md 和 docs\decisions\ADR-0004-zotero-literature-authority.md。
然后执行以下初始化审计：

1. 运行：
   & 'F:\codespace\ResearchOS\.venv\Scripts\rf.exe' project list
   确认项目 ID 尚未注册。
2. 检查 repo 路径的解析后绝对路径，确认不会覆盖现有项目、用户资产或 ResearchFlow workspace。
3. 如果必要输入仍保留尖括号占位符，先向我询问缺失值，不要猜测。
4. 若 ID 或路径发生冲突，停止并具体报告冲突；不要覆盖，也不要把它当成接续项目。

在没有冲突且所有占位符已填写的前提下，本提示词授权你：
- 创建指定的本地 repo 目录（仅当它尚不存在）；
- 在该目录初始化本地 Git 仓库；
- 运行 rf project add 注册新项目；
- 在 ResearchFlow 文件合同内填写初始研究问题、当前阶段和 next action；
- 运行 project show、status 和不带 --probe-machines 的 doctor 验证初始化。

初始化时必须遵守：
- Zotero 是书目、PDF、集合、标签、批注和引用格式的主库；ResearchFlow 只保存该专题的分析与证据关系。
- 默认不创建或修改 Zotero Collection/Tag，不下载论文，不进行批量外部检索；这些操作另列方案，等待本轮明确授权。
- 不创建科学结论、baseline、hypothesis 或 experiment 来填充空白；尚无证据时明确写“未建立/待检索”。
- 选择矩阵前先查看 `matrix templates list`；默认使用跨领域 generic，领域模板或自定义 axes 必须由用户问题支持并显式确认，不能让 Agent 静默决定维度。
- 初始化后明确提示 workspace 尚无 snapshot、repo 可能是 unborn HEAD、外部 Zotero/数据资产未备份；不自动 commit 或创建远端。
- 不配置或探测 SSH，不运行 GPU/机器人，不清理资产，不执行 Git push。

完成后给“初始化简报”，包含：
- 最终项目 ID、workspace、独立 repo 和 Git HEAD/分支/clean 状态；若尚无首个 commit，明确报告 unborn HEAD，不要伪造 commit；
- 三个新会话启动文件的准确路径；
- 已写入的初始问题、范围、当前阶段和 next action；
- 尚未执行的 Zotero/检索动作；
- snapshot、Git checkpoint、KNOWLEDGE 生成导航和外部资产备份状态；
- 针对 <FIRST_TASK> 的一项优先建议和需要我批准的下一控制点。
```

如果目标其实是继续一个已存在的项目，应改用 [接续已经存在的项目](continue-existing-project.md)，不要运行本提示词的初始化步骤。
