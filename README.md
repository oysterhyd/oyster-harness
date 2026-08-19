# Oyster Harness

Oyster Harness 是一个从底层机制出发构建的、带有个人取舍的轻量级 Coding Agent。
项目当前已完成基础工程和模型交互层，默认通过 OpenCode Go 调用 Hy3。

## 为什么叫 Oyster

“Harness”是约束、调度与观测模型能力的运行时；“Oyster”则强调项目会围绕个人工作方式逐层生长，
而不是复刻现有 Coding Agent 的界面和功能清单。

## 当前能力

- 可安装的 Python 3.12 `src` layout 包
- `oyster run` 单次流式调用
- `oyster chat` 有状态多轮交互
- OpenCode Go `hy3` Provider
- pytest、Ruff、Pyright 与构建检查
- GitHub Actions CI

当前边界：CLI 可以正常对话，但还没有文件读取、搜索、Shell、代码修改等工具，
因此此时是可用的模型客户端，还不是完整的 Coding Agent。

## 使用 Hy3

API 密钥不会写入项目配置或日志。可以通过环境变量传入：

```powershell
$env:OPENCODE_API_KEY = (Get-Content ..\api.txt -Raw).Trim()
uv run oyster run "用一句话介绍你自己"
uv run oyster chat
```

也可以直接指定密钥文件：

```powershell
uv run oyster run "用一句话介绍你自己" --api-key-file ..\api.txt
uv run oyster chat --api-key-file ..\api.txt
```

在交互模式输入 `/exit` 或 `/quit` 退出。`api.txt` 和 `.env` 已加入 `.gitignore`，不得提交真实密钥。

## 本地开发

需要安装 [uv](https://docs.astral.sh/uv/)。

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

近期将围绕一条真实的 Agent 闭环逐步推进：模型交互、工具调用、受控执行、结果观察和停止判断。
详细的实际进展与设计取舍见 [`docs/development-progress.md`](docs/development-progress.md)。
