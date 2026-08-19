# Oyster Harness 开发进度

这份文档记录项目真实发生的开发工作、验证结果和设计取舍。参考技术路线只提供候选方向；
当实际实现与路线冲突时，以这里记录的决定和代码现状为准。

## 当前状态

- 阶段：Phase 0 — 工程初始化
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

## 下一阶段候选目标

Phase 1 不直接追求完整对话体验，而是先定义最薄的模型边界：

- 定义与厂商无关的模型请求、文本增量和最终响应模型
- 只接入一个首选 Provider，避免过早实现多 Provider 抽象
- 让 CLI 展示真实流式输出
- 为网络失败、配置缺失和中断行为建立可测试语义

进入 Phase 1 前，需要先确定首选模型服务与鉴权方式。

## 变更日志

### 2026-08-20

- 阅读并评估 AI 生成的工程化方案。
- 采用其中的 Phase 0 工程基线，但缩减了过早设计的目录结构。
- 确立 Oyster 命名与“由真实能力驱动结构”的项目原则。
- 创建首个 CLI 垂直切片、测试和 CI 配置。
- 通过 Ruff、Pyright、pytest（2 tests）、包构建以及 CLI 烟雾测试。
- 初始化 Git，将 `main` 推送至 GitHub 私有仓库 `oysterhyd/oyster-harness`。
