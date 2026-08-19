# Oyster Harness 开发进度

这份文档记录项目真实发生的开发工作、验证结果和设计取舍。参考技术路线只提供候选方向；
当实际实现与路线冲突时，以这里记录的决定和代码现状为准。

## 当前状态

- 阶段：Phase 1 — CLI + OpenCode Go Hy3
- 更新时间：2026-08-20
- 状态：已完成
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

当前限制：

- 尚未实现 Tool Schema、Tool Registry 或 Agent Loop
- 尚不能读取、搜索、修改项目文件或运行 Shell
- 会话历史仅存在于当前进程，退出后不会持久化

## 下一阶段候选目标

Phase 2 将从“模型客户端”进入最小 Agent Runtime：

- 定义结构化 Tool Call / Tool Result
- 建立 Tool Registry 与顺序执行器
- 首批只实现 `list_dir`、`read_file` 和 `grep`
- 让 Hy3 能根据用户问题调用工具、观察结果并继续回答
- 为循环次数、无效调用和工具失败定义停止语义

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
