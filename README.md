# Oyster Harness

Oyster Harness 是一个从底层机制出发构建的、带有个人取舍的轻量级 Coding Agent。
项目当前处于工程初始化阶段；现阶段只建立可验证的 CLI 与质量基线，不提前填充尚未设计的 Agent 模块。

## 为什么叫 Oyster

“Harness”是约束、调度与观测模型能力的运行时；“Oyster”则强调项目会围绕个人工作方式逐层生长，
而不是复刻现有 Coding Agent 的界面和功能清单。

## 当前能力

- 可安装的 Python 3.12 `src` layout 包
- `oyster` 命令行入口
- pytest、Ruff、Pyright 与构建检查
- GitHub Actions CI

## 本地开发

需要安装 [uv](https://docs.astral.sh/uv/)。

```powershell
uv sync
uv run oyster --help
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv build
```

## 项目方向

近期将围绕一条真实的 Agent 闭环逐步推进：模型交互、工具调用、受控执行、结果观察和停止判断。
详细的实际进展与设计取舍见 [`docs/development-progress.md`](docs/development-progress.md)。
