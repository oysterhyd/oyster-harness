# Oyster Harness

Oyster Harness 是一个从底层机制出发构建的、带有个人取舍的轻量级 Coding Agent。
它默认通过 OpenCode Go 调用 Hy3，现在已经具备可工作的模型—工具—观察闭环。

## 为什么叫 Oyster

“Harness”是约束、调度与观测模型能力的运行时；“Oyster”则强调项目会围绕个人工作方式逐层生长，
而不是复刻现有 Coding Agent 的界面和功能清单。

## 当前能力

- 可安装的 Python 3.12 `src` layout 包
- `oyster` 品牌化交互界面和 `oyster run` 单次 Agent 任务
- 原生 tool calling Agent Loop，默认最多 12 次模型迭代
- `list_dir`、`read_file`、`grep`、`edit_file`、`write_file` 工具
- 异步 `bash` / PowerShell 7 命令工具，含超时、退出码和输出裁剪
- workspace 路径隔离，以及 `read-only` / `ask` / `auto` 三档权限
- 按模型上下文窗口管理预算，优先使用服务端输入用量，并以 `o200k_base` 作为估算回退
- 旧轮次压缩、工具输出裁剪和结构化工作记忆
- OpenCode Go Chat Completions 模型及推理强度切换
- 输入 `/` 即时弹出的命令面板，以及模型/推理/权限的二级配置选择
- `OYSTER HARNESS` 启动标志、瞬态输入框、对话面板和 Markdown 渲染
- 原地更新的工具活动，以及只保留当前模型/推理/权限/上下文剩余百分比的动态状态栏
- pytest、Ruff、Pyright 与构建检查
- GitHub Actions CI

当前边界：不同 OpenCode Go 模型没有统一公开 tokenizer，因此服务端未返回 usage 时，内部预算
使用 `o200k_base` 作一致近似；状态栏优先用服务端真实输入用量计算各模型上下文窗口的剩余
百分比，不暴露 token 数。编辑尚未支持 Unified Diff；会话退出后不会持久化；模型支持暂限
OpenCode Go 的 OpenAI-compatible Chat Completions 协议。

## 使用 Hy3

API 密钥不会写入项目配置或日志。可以通过环境变量传入：

```powershell
$env:OPENCODE_API_KEY = (Get-Content ..\api.txt -Raw).Trim()
uv run oyster --workspace .
```

也可以直接指定密钥文件：

```powershell
uv run oyster --api-key-file ..\api.txt --workspace .
uv run oyster run "分析这个项目的入口文件" --api-key-file ..\api.txt --workspace .
```

交互模式支持：

```text
/models
/model kimi-k3
/reasoning high
/permissions read-only
/clear
/status
/exit
```

输入框下方始终只有一条状态栏；提交后输入框会被永久的 `You` 对话框替换，不会重复显示
输入内容。直接输入 `/` 会在输入框内打开命令候选列表。使用 `↑` / `↓` 选择并按 Enter；选择 `/model`、
`/reasoning` 或 `/permissions` 后会进入对应配置列表，再按 Enter 即时应用。
也可以继续直接输入完整命令，例如 `/reasoning high`。

`ask` 是默认权限：读取和安全的检查命令直接执行，编辑或有副作用的命令需要逐次确认；
`read-only` 禁止修改，`auto` 允许非危险修改。危险命令始终拒绝。`api.txt` 和 `.env`
已加入 `.gitignore`，不得提交真实密钥。

## 本地开发

需要安装 [uv](https://docs.astral.sh/uv/) 和 [ripgrep](https://github.com/BurntSushi/ripgrep)。

```powershell
uv sync
uv run oyster --help
uv run oyster run --help
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv build
```

## 项目方向

近期将继续加固这条真实闭环：流式 Shell 观察、Unified Diff、语义摘要、会话恢复
和更多 Provider 协议。详细的实际进展与设计取舍见
[`docs/development-progress.md`](docs/development-progress.md)。
