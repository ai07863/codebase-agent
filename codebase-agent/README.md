# CodeBase Agent

用自然语言分析 GitHub 仓库：提问代码结构、查找函数、理解架构、查看调用关系、评审 PR。

## 快速开始

### Web 界面（推荐）

```bash
# 配置
cp .env.example .env
# 编辑 .env：填入 LLM_API_KEY（+ LLM_MODEL / LLM_BASE_URL）

# 启动（Windows）
run.cmd
# 或手动：
#   python -m uvicorn web.main:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000/ui/ 。输入一个 **Python 或 Go** 仓库地址点"分析"，然后在"问答"里提问。

> 首次启动会下载 embedding 模型（约 30MB），之后 `run.cmd` 用本地缓存离线加载，启动只需几秒。
> Windows 下如遇命令行中文乱码，可先执行 `chcp 65001`。

### 命令行

```bash
pip install -e ".[dev]"        # 安装（含测试依赖）
codebase-agent analyze https://github.com/psf/requests
```

## 功能

- **代码问答**：混合检索（向量 + BM25 + AST 名字匹配，RRF 融合）+ 项目结构地图；引用文件可点击查看源码；长函数按块索引。
- **对话历史**：SQLite 持久化，左侧可折叠边栏，支持多轮追问（历史会带入模型）。
- **依赖图**：基于 vis-network，四种视图（洋葱分层逐层展开 / 交互式 / 模块聚合 / 调用树）；点边显示关系说明。
- **PR 分析**：拉取 GitHub PR（会切到 PR head 保证行号对齐），输出中文报告 + AI 总结（改了什么、影响、风险）。
- **Go 支持**：tree-sitter-python + tree-sitter-go，按语言映射节点类型。

## 配置（`.env`）

| 变量 | 说明 | 默认 |
|---|---|---|
| `LLM_API_KEY` | LLM 密钥 | 空 |
| `LLM_MODEL` | 模型名 | `gpt-4o-mini` |
| `LLM_BASE_URL` | OpenAI 兼容地址 | `https://api.openai.com/v1` |
| `LLM_TIMEOUT` | LLM 请求超时（秒） | `60` |
| `LLM_RETRIES` | 失败重试次数（401/403/404 不重试，失败会降级返回命中位置） | `2` |
| `LLM_PRICE_INPUT_PER_1K` / `LLM_PRICE_OUTPUT_PER_1K` | 每千 token 单价（估算成本用，0=不计） | `0` |
| `LLM_BUDGET_USD` | 预算（美元，超预算时 `check_alerts.py` 告警；0=不启用） | `0` |
| `EMBEDDING_MODEL` | 向量模型 | `BAAI/bge-small-zh-v1.5` |
| `REDIS_HOST` / `REDIS_PORT` | 问答缓存（可选，不可用会自动降级） | `localhost` / `6379` |
| `HISTORY_DB` | 对话历史 SQLite | `./data/history.db` |
| `REPO_CACHE_DIR` | 解析结果缓存 | `./data/cache` |
| `API_TOKEN` | 设置后所有 API 需带 `X-API-Token`（默认不鉴权，仅本机） | 空 |
| `AUTH_USER` / `AUTH_PASSWORD` | 浏览器登录（HTTP Basic）；设置密码后 `/ui` 与 API 都需登录，`/health` 除外 | `admin` / 空 |
| `RATE_LIMIT_PER_MIN` | 每客户端每分钟昂贵请求上限（`/repos/*`、`/analysis/*`；0=关闭） | `60` |
| `CORS_ORIGINS` | 允许的跨域来源（逗号分隔） | 本机 |
| `DEBUG` | `1` 时错误信息回显详情 | `0` |

## 工作原理

1. **克隆** — `--depth 1` 拉取
2. **AST 解析** — tree-sitter 提取每个函数/类/方法（结果按文件指纹落盘缓存）
3. **索引** — 按块 embedding 存入 ChromaDB（仅对新增/变更块重嵌）；BM25 + 内存 AST 索引
4. **问答** — 路由到精确/混合检索，拼装上下文交给 LLM，答案可带 Mermaid 架构图

## 架构

```
codebase-agent/
├── cli/           # Click 命令行
├── agent/         # ReAct 循环 + 检索编排
├── code_parser/   # tree-sitter AST（Python/Go）+ 解析缓存
├── retrieval/     # ChromaDB + BM25 + AST 索引 + RRF 融合
├── embedding/     # 可配置向量模型
├── cache/         # Redis（可选）
├── analysis/      # PR diff / 影响分析 / 中文报告
├── web/           # FastAPI + 静态前端（UI、对话历史、文件查看）
├── evaluation/    # 评测 + Q&A 数据集
└── config/        # 配置
```

## 测试

```bash
pip install -e ".[dev]"
pytest                 # 全部（含会下载 embedding 模型的 slow 测试）
pytest -m "not slow"   # 快速测试（CI 使用）
python evaluation/benchmark.py fastapi --min-hit-rate 0.6   # 检索回归门槛
```

## 指标与反馈

- 每次问答都会记录一条 trace（路由、召回命中、上下文字符/token、LLM 耗时与错误、是否缓存）。
- 页面顶部 **📊 指标**：最近 7 天成功率、缓存命中率、延迟 P50/P95、👍/👎 好评率。
- 接口：`GET /traces`、`GET /metrics/summary?days=7`、`GET /metrics/prometheus`（Prometheus 抓取）。
- 每条回答下可点 👍/👎，写入 `answer_feedback` 表。
- 告警检查：`python scripts/check_alerts.py --days 1`（异常返回非零码，可接计划任务）。

## 备份与恢复

```bash
python scripts/backup.py                        # 备份到 data/backups/<时间戳>/
python scripts/backup.py --keep 7               # 只保留最近 7 份
python scripts/backup.py --restore data/backups/<时间戳>   # 先停服务再恢复
```

`history.db` 用 SQLite 在线备份（运行中安全）；`chroma` 目录建议空闲时备份。

## 部署（Docker）

```bash
docker compose up -d --build     # 应用 + Redis
# 应用: http://127.0.0.1:8000/ui/
```

## 公网访问（Cloudflare）

- 隧道：`cloudflared tunnel run image-agent`（`run.cmd` 会自动拉起）。
- **鉴权（二选一）**：
  - **应用内密码（推荐，免费、无需绑卡）**：在 `.env` 设 `AUTH_USER`、`AUTH_PASSWORD`，
    浏览器访问会弹出登录框；`/health` 保持公开供健康检查。未登录 `401` 并返回 `WWW-Authenticate`。
  - **Cloudflare Access**：Zero Trust → Access → Applications 加 Self-hosted 应用，
    策略 Allow → Emails → 你的邮箱，IdP 用 One-time PIN（需在 Cloudflare 绑定支付方式）。
- 限流中间件会优先读取 `CF-Connecting-IP`，隧道后能区分真实客户端。

## 数据清理

- 删除某个仓库（含克隆与索引）：`DELETE /repos/{repo_name}`
- 对话历史可用界面里的"删除"按钮，或直接删 `data/history.db`
- 彻底重建索引：删掉 `data/chroma` 后重新分析