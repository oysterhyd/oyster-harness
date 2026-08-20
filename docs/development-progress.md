# Oyster Harness 开发进度

这份文档记录项目真实发生的开发工作、验证结果和设计取舍。参考技术路线只提供候选方向；
当实际实现与路线冲突时，以这里记录的决定和代码现状为准。

## 当前状态

- 阶段：Phase 2–4 垂直切片 — Coding Agent MVP
- 更新时间：2026-08-20
- 状态：首个垂直切片已完成
- 远端：`oysterhyd/oyster-harness`（private）

## 已确定的项目取舍

1. 产品名使用 **Oyster Harness**，Python 包名为 `oyster_harness`，CLI 命令为 `oyster`。
   不沿用参考文档中的通用名称 `codeagent`。
2. 保留 Python 3.12、uv、Typer、Rich、pytest、Ruff 和 Pyright 这组简单且成熟的工程组合。
3. 不按照最终架构图预先创建大量空模块。每个目录必须由已经进入实现的能力驱动产生。
4. 第一阶段以“可安装、可执行、可测试、可发布构建”为完成标准；LLM 和 Agent Runtime 尚未实现。
5. 暂不添加开源许可证。仓库为私有，未来公开前再明确选择许可证。
6. 首个模型服务只接入 OpenCode Go，默认模型固定为 `hy3`。当前不做多 Provider 配置系统。
7. 模型调用边界使用项目自有 Protocol 与 `httpx` 实现，不直接把 OpenAI SDK 类型渗透到会话层。
8. API 密钥只从 `OPENCODE_API_KEY` 或显式 `--api-key-file` 读取，不持久化、不记录。
9. Phase 2 不照搬参考方案的完整分层：先以少量可工作的模块跑通闭环，再由真实复杂度驱动拆分。
10. 上下文管理采用 `o200k_base` 的确定性内部预算、工具输出裁剪和工作记忆；由于 Go
    模型没有统一公开 tokenizer，不向用户展示近似 token 数。状态栏对齐 Codex / Claude Code，
    显示受管上下文窗口的整数剩余百分比。不提前引入 SQLite、embedding 或 Tree-sitter。
11. 首版 TUI 继续使用 Rich，以品牌化启动区、对话面板、工具活动和状态栏形成个人风格；
    只有交互需求超出 Rich 能力后才考虑 Textual。
12. 模型切换先覆盖 OpenCode Go 的 OpenAI-compatible Chat Completions 模型；Responses 与
    Anthropic 协议模型必须有独立适配后才标记为支持。
13. 不采用参考方案的“大而全”目录树。当前 Runtime、Context、Tools、Permissions、TUI
    各自保持一个聚焦模块；只有模块内部出现真实分化后再拆包。
14. 首个编辑原语使用 `edit_file(path, old_text, new_text)` 的单次精确替换。它比整文件重写
    更容易验证，也避免在 MVP 中过早实现不完整的 Unified Diff 解析器。
15. Rich 继续负责品牌、对话和工具活动渲染；输入层只引入 `prompt_toolkit`，用于 `/`
    实时命令面板与二级配置选择，不把整个应用迁移到全屏 TUI 框架。
16. 输入框、配置列表和回复中的状态栏都是瞬态区域：提交后用 `You` 面板替换输入渲染，
    工具状态按 call ID 原地更新，完成回复后不把旧状态栏写入滚动历史。
17. 系统提示由固定行为说明与每轮刷新的运行时身份组成。模型 ID、推理强度、权限模式和
    workspace 以运行时值为准，避免 Agent 猜测自己的身份。
18. context 百分比使用当前模型的广告窗口作为分母，流式响应提供 usage 时优先采用服务端
    `prompt_tokens`；只有调用前或 usage 缺失时才退回 `o200k_base` 估算。切换模型会同步窗口，
    但不会清空会话历史或工作记忆。

## 里程碑

### Phase 0：工程初始化

- [x] 建立 Python 3.12 `src` layout
- [x] 配置 uv 项目与依赖
- [x] 建立 `oyster` CLI 和版本命令
- [x] 配置 pytest、Ruff 与严格模式 Pyright
- [x] 添加 GitHub Actions CI
- [x] 生成锁文件并通过本地质量检查
- [x] 初始化 Git 并推送 GitHub 私有仓库

完成标准：

```powershell
uv run oyster --help
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv build
```

以上命令全部成功，且远端私有仓库可访问。

### Phase 1：CLI + OpenCode Go Hy3

- [x] 定义与厂商无关的 `ChatMessage` 和 `ChatProvider`
- [x] 实现 OpenCode Go `hy3` 的 OpenAI-compatible SSE 流式调用
- [x] 实现 `oyster run` 单次输入输出
- [x] 实现 `oyster chat` 多轮输入输出和 `/exit` 退出
- [x] 支持环境变量与显式密钥文件，不将密钥纳入 Git
- [x] 为配置、会话、Provider 和 CLI 添加单元测试
- [x] 完成真实 API 单次调用与两轮上下文测试

真实调用验收：

- 单次命令要求固定回复，Hy3 返回 `OYSTER_OK`
- 交互会话第一轮写入代号 `PEARL42`，第二轮能准确回忆该代号
- `/exit` 正常结束，退出码为 0

Phase 1 完成时的限制：

- 尚未实现 Tool Schema、Tool Registry 或 Agent Loop
- 尚不能读取、搜索、修改项目文件或运行 Shell
- 会话历史仅存在于当前进程，退出后不会持久化

### Phase 2–4 垂直切片：Coding Agent MVP

- [x] Provider 可流式组装文本和原生 OpenAI-compatible tool calls
- [x] 顺序执行的 Agent Loop，并为最大迭代次数定义停止语义
- [x] `list_dir`、`read_file`、`grep`、`edit_file`、`write_file`
- [x] 支持 bash / PowerShell 7、超时、退出码和有界输出的异步 Shell
- [x] workspace 路径隔离，阻止相对路径和符号链接逃逸
- [x] `read-only` / `ask` / `auto` 权限模式和独立于 Prompt 的危险命令拒绝
- [x] `o200k_base` token 预算、工具输出裁剪、按用户轮次压缩和结构化工作记忆
- [x] 逐模型上下文窗口、服务端输入 usage 统计与本地估算回退
- [x] 模型、推理强度和权限的 CLI 参数与交互命令切换
- [x] `OYSTER HARNESS` 品牌启动区、用户/Agent 对话框、原地工具活动和唯一动态状态栏
- [x] 输入 `/` 实时显示命令列表，回车进入模型/推理/权限二级配置列表
- [x] Windows 重定向输出的 UTF-8 兼容处理

真实闭环验收：

- Hy3 自主调用 `read_file` 读取 README 第一行并回答 `Oyster Harness`
- Hy3 自主调用 `shell`，通过 PowerShell 7 执行 `Get-Location` 并观察退出码和输出
- Hy3 在隔离临时文件上依次执行读取、`edit_file`、再次读取，确认标题从
  `Oyster Harness` 变为 `Oyster Pearl`，随后删除临时文件
- 默认 `oyster` 入口显示品牌界面；`/model`、`/reasoning`、`/permissions` 和 `/status`
  在同一会话中即时更新状态栏
- 真实 PTY 中输入 `/` 后一次 Enter 进入模型列表，并完成 model、reasoning、permissions
  三类配置的方向键选择和回车应用
- 真实 PTY 中 Agent 准确报告产品 `Oyster Harness`、Agent 名 `Oyster`、模型 `hy3`、
  推理强度 `low` 和权限 `read-only`
- 真实 PTY 中普通输入提交后只留下 `You` 面板；工具结束后只保留一条
  `✓ read_file · README.md`，没有额外的 `done`
- 在 `TERM=dumb` 的 Windows ConPTY 中，输入框下方仍显示唯一且完整的动态状态栏；
  回复完成后旧状态栏不进入滚动历史
- context 使用 Codex 风格的 `N% context left`，并与 Claude Code 的
  `remaining_percentage` 语义一致，不在状态栏显示 tokenizer 估算值
- Hy3 使用 256k 上下文窗口；服务端报告 10,200 输入 token 时显示 `96% context left`，
  切换到 Kimi K3 后窗口更新为 1,048,576 且会话历史保留

当前限制：

- `edit_file` 只支持单次精确替换，尚未实现 Unified Diff 和 Patch Validator
- Shell 在进程结束后一次性返回 stdout/stderr，尚未向模型流式回注过程输出
- OpenCode Go 的 `/models` 端点不返回上下文上限，因此逐模型窗口来自版本化元数据快照，
  可能随上游模型调整而需要更新；usage 缺失时的 `o200k_base` 回退仍是近似值
- 尚没有 LLM 语义摘要
- 完整历史仅在当前进程中保留，退出后没有 history / resume
- Go 的 Responses 与 Anthropic Messages 协议模型尚未接入
- 命令策略是保守规则集，不等同于容器或 OS 级强隔离

## 下一阶段候选目标

下一阶段优先加固 Coding Loop，而不是扩张到多 Agent、MCP 或向量数据库：

- [x] 用真实 Hy3 请求确认原生 tool calling 与 `reasoning_effort` 请求可用
- [x] 定义结构化 Tool Call / Tool Result
- [x] 建立 Tool Registry 与顺序执行器
- [x] 实现首批文件、搜索、编辑和 Shell 工具
- [x] 实现 workspace sandbox 与三档权限模式
- [x] 让 Hy3 调用工具、观察结果并继续回答
- [x] 为上下文预算、循环上限、无效调用和工具失败定义停止语义
- [x] 实现运行时切换与品牌化 TUI
- [ ] 增加 Unified Diff `apply_patch` 与 dry-run 验证
- [ ] 为长时间 Shell 增加过程事件、取消和更稳健的进程树清理
- [x] 引入 tokenizer 驱动的 token 预算
- [ ] 增加可测试的语义 compaction
- [ ] 持久化会话，并提供 history / resume
- [ ] 为 Responses 和 Anthropic Messages 增加独立 Provider 适配

## 变更日志

### 2026-08-20

- 阅读并评估 AI 生成的工程化方案。
- 采用其中的 Phase 0 工程基线，但缩减了过早设计的目录结构。
- 确立 Oyster 命名与“由真实能力驱动结构”的项目原则。
- 创建首个 CLI 垂直切片、测试和 CI 配置。
- 通过 Ruff、Pyright、pytest（2 tests）、包构建以及 CLI 烟雾测试。
- 初始化 Git，将 `main` 推送至 GitHub 私有仓库 `oysterhyd/oyster-harness`。
- 修复 `setup-uv` 浮动标签不可解析的问题；GitHub Actions 的质量任务全部通过。
- 确认 OpenCode Go 密钥有效，模型列表包含 `hy3`。
- 完成 Hy3 流式 Provider、单次 CLI 调用和有状态交互会话。
- 本地 Ruff、Pyright、构建及 10 项测试全部通过。
- 完成真实 Hy3 单次调用和两轮上下文验收，未记录或提交 API 密钥。
- 完成首个 Coding Agent 垂直切片：原生 tool calling、Agent Loop、文件/搜索/编辑/Shell、
  上下文压缩、工作记忆、权限与 workspace 隔离。
- 完成 Oyster 品牌 TUI、对话面板、工具活动、运行时状态栏和交互切换命令。
- 通过 27 项自动化测试、Ruff、formatter、严格 Pyright、包构建和三条真实 Hy3
  Agent 闭环验收。
- 增加 `/` 命令面板与模型、推理、权限二级选择；保留非交互管道输入的兼容路径。
- 修复 TUI 输入重复：prompt_toolkit 输入框提交后整块擦除，由单个 `You` 面板接替。
- 工具活动由 call ID 关联开始和结束事件，在同一行从 `◌` 更新为 `✓` / `×`，不再输出
  独立 `done` 行。
- 完善动态系统提示，加入产品、Agent、Provider、当前模型、推理强度、权限和 workspace。
- 将字符预算替换为内部的 `tiktoken` / `o200k_base` 预算；状态栏不显示 token 数，改为
  Codex 风格的 `N% context left`。
- 将启动标识明确为 `OYSTER HARNESS`；压缩输入区布局，并兼容 `TERM=dumb` 的 Windows
  ConPTY 动态渲染。
- 通过 32 项自动化测试、Ruff、formatter 和严格 Pyright；完成真实 Hy3 身份、工具原地
  更新、唯一 statusline 与 `/` 配置选择验收。
- 修复 context 首轮错误骤降：移除统一的 20k 分母，为 OpenCode Go 模型记录各自上下文窗口，
  请求流式 usage，并优先用服务端 `prompt_tokens` 计算剩余百分比；模型切换同步更新窗口。
- 通过 34 项自动化测试、Ruff、formatter、严格 Pyright 和包构建；真实 Hy3 流返回 24 个
  输入 token，按 256k 窗口显示 `100% context left`。
- 修复 `auto` 权限下 PowerShell 磁盘查询被误拒绝：危险规则不再把只读的 `Format-Table`
  当成磁盘格式化命令，同时继续拦截 `format` / `format.com` 与 `Format-Volume`。
- 通过 35 项自动化测试、Ruff、formatter、严格 Pyright 和包构建；真实 Hy3 Agent 在
  `auto` 模式下一次执行带 `Format-List` 的 D 盘查询成功，未再触发权限拒绝。
- 修复 Linux CI 的平台类型收窄错误：shell 工具测试直接按 `os.name` 设置对应的 shell 与
  命令，并在 Windows 本地增加 `pyright --pythonplatform Linux` 验证路径。
