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

## 新对话的恢复协议

先运行：

```powershell
& 'F:\codespace\ResearchOS\.venv\Scripts\rf.exe' project show embodied-nav
```

把下面内容粘贴到新对话；如果专题不是 `embodied-nav`，只替换项目 ID：

```text
请继续 ResearchFlow 项目 embodied-nav，不要依赖旧对话记忆。
先运行：
F:\codespace\ResearchOS\.venv\Scripts\rf.exe project show embodied-nav
然后按该命令输出的路径依次读取 AGENTS.md、KNOWLEDGE.md、memory/current-state.md，
再运行：
F:\codespace\ResearchOS\.venv\Scripts\rf.exe --project embodied-nav status

把 Zotero 视为书目、PDF、集合、标签、批注和引用格式的唯一主库；
ResearchFlow 只保存专题相关的精读分析、页码证据、跨论文比较、Idea 和研究决策。
先报告已验证的当前状态和下一项建议，不要自动进行远端操作、全文批量下载、GPU 运行、清理或 Zotero 写入。
```

三个启动文件各有不同职责：

- `AGENTS.md`：本专题的安全边界和启动顺序。
- `KNOWLEDGE.md`：证据、论文、矩阵和记录的索引。
- `memory/current-state.md`：当前问题、阶段、阻塞项和下一步。

聊天记录不是恢复依据；以上文件和 `rf status` 才是。

## 为另一个专题建立独立文献项目

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
