# 在任意文件夹和新对话中使用 ResearchFlow

## 结论

ResearchFlow 不是绑定在 `F:\codespace\ResearchOS` 当前目录中的脚本。项目注册信息位于全局配置，研究状态位于各自的 ResearchFlow 项目工作区；因此，只要使用同一个配置和 CLI，就能在别的文件夹、别的终端和新对话中继续同一专题。

本机当前入口：

```powershell
$ResearchFlowCli = 'F:\codespace\ResearchOS\.venv\Scripts\rf.exe'
& $ResearchFlowCli project list
& $ResearchFlowCli project show embodied-nav
& $ResearchFlowCli --project embodied-nav status
```

这里的 PowerShell 变量只在当前终端有效，不修改系统 PATH。最稳妥的规则是：凡是读写项目状态的命令都显式写 `--project <专题ID>`。这样即使以后默认项目改变，也不会把记录写入错误专题。

## 两种新对话入口

| 场景 | 动作 | 是否恢复上下文 | 结果 |
|---|---|---|---|
| 接续已经存在的项目 | Import/continue | 是 | 读取该项目已有记录，核验当前状态后继续原工作流。 |
| 开启全新专题 | Initialize/start | 否 | 创建新的项目 ID、独立 repo 映射和空白研究状态。 |

两者都建议用入口提示词，因为 agent 需要知道本次是在“恢复”还是“初始化”。但提示词只是 agent 的启动协议；真正操作 ResearchFlow 的入口仍是 CLI，真正的持久状态仍是普通文件。

“不要依赖旧对话记忆”不是要求遗忘项目历史，也不是禁止使用已有成果。它表示：旧聊天内容和模型记忆不能直接当作当前事实。agent 应先从以下持久来源重建和核验状态：

- ResearchFlow 项目工作区中的 `AGENTS.md`、`KNOWLEDGE.md`、`memory/current-state.md` 及相关记录；
- `rf status` 和其他只读查询的当前输出；
- 独立研究代码仓库的当前 Git HEAD、分支和 clean/dirty 状态；
- 当任务涉及论文主张时，Zotero 条目、已验证深读记录和必要的原始 PDF。

因此，此前“只依靠项目文件恢复上下文”的说法过强。准确表述是：**不依赖聊天历史，通过 ResearchFlow 持久状态加当前外部事实重建上下文。**

## 接续已经存在的项目

先运行：

```powershell
& 'F:\codespace\ResearchOS\.venv\Scripts\rf.exe' project show embodied-nav
```

复制规范入口：[接续已经存在的项目](prompts/continue-existing-project.md)。把其中的 `<PROJECT_ID>` 替换为 `embodied-nav`，需要时填写具体 workstream 或本轮任务。

三个启动文件各有不同职责：

- `AGENTS.md`：本专题的安全边界和启动顺序。
- `KNOWLEDGE.md`：证据、论文、矩阵和记录的索引。
- `memory/current-state.md`：当前问题、阶段、阻塞项和下一步。

聊天记录可以帮助定位，但不是当前状态的权威证据。项目文件、实时 CLI/Git 状态和任务相关原始证据共同构成恢复依据。

## 为另一个专题建立独立文献项目

复制规范入口：[开启全新专题](prompts/start-new-topic.md)。这份提示词会先检查项目 ID 和 repo 路径是否冲突，再初始化新状态，不会复用或覆盖 `embodied-nav`。

不要把不同专题都塞进 `embodied-nav`。先准备一个独立的本地目录；如果未来会进入实验阶段，建议从一开始就把它建成独立 Git 仓库。然后注册一个稳定且唯一的项目 ID：

```powershell
$ResearchFlowCli = 'F:\codespace\ResearchOS\.venv\Scripts\rf.exe'
& $ResearchFlowCli project add my-topic --repo F:\research\my-topic
& $ResearchFlowCli project show my-topic
& $ResearchFlowCli --project my-topic status
```

专题文献的责任边界：

1. 在 Zotero 中用 Collection/Tag 管理候选论文、PDF、批注和引用。
2. 用 `rf evidence zotero search/show` 查找条目。
3. 只把确认进入该专题分析的条目 `link` 为 `PAPER-*`。
4. 深读后用 `paper verify` 固化文档指纹、页码主张和方法标签。
5. 用 `matrix add/synthesize/validate` 追加结构化比较、跨论文结论和 Idea。
6. 把后续实验主张继续连接为 Observation、Hypothesis、Experiment、Run 和 Decision。

同一篇 Zotero 论文可以被不同 ResearchFlow 专题引用；Zotero 仍只有一份主条目和 PDF，各专题保存自己的分析关系。ResearchFlow 不复制 Zotero PDF，也不替代 Zotero 去重、批注或引用排版。

## 日常命令

```powershell
$ResearchFlowCli = 'F:\codespace\ResearchOS\.venv\Scripts\rf.exe'
$Project = 'embodied-nav'

& $ResearchFlowCli --project $Project status
& $ResearchFlowCli --project $Project evidence search 'navigation'
& $ResearchFlowCli --project $Project evidence paper list
& $ResearchFlowCli --project $Project evidence matrix show
& $ResearchFlowCli --project $Project evidence matrix validate
& $ResearchFlowCli --project $Project doctor
```

最后一条只做本地完整性检查。只有在当前明确允许访问机器并具备 VPN/网络条件时，才运行 `doctor --probe-machines` 或 `compute probe`。

## Ubuntu 主机迁移

迁移时复制普通文件构成的 ResearchFlow home，并重新登记各项目在 Ubuntu 下的代码仓库路径；Zotero 数据库和附件由 Zotero 自己的迁移/同步机制负责。CLI 改为 Linux 虚拟环境入口，例如：

```bash
/opt/ResearchOS/.venv/bin/rf --project embodied-nav status
```

不要把 Windows 的绝对 repo 路径直接当作 Ubuntu 路径使用。迁移后先运行 `project show` 和不带 live probe 的 `doctor`，再逐项确认 Zotero loopback、Git 仓库及经批准的 SSH 机器配置。
