# CodeBase Agent — 设计文档

## 概述

基于 RAG + AST 的代码库智能问答 Agent。输入 GitHub 仓库链接，自动分析代码结构，支持自然语言问答、架构理解、代码定位。

## 目标

- 解决开发者理解陌生代码库的痛点
- 展示企业级 Agent 工程能力（RAG、AST、多策略检索、Docker 部署）
- 可量化评估，有评测基准，非玩具项目

## Phase 1 范围（CLI 优先，Web 后续）

### 核心功能

1. **AST 代码切片** — 基于 tree-sitter 按函数/类/方法切片，保留签名、文档、调用关系
2. **多策略检索** — AST 精确索引 + Embedding 语义检索 + BM25 关键词检索，三路召回
3. **Agent ReAct 推理** — 单 Agent 多步推理，自动选择检索策略，验证引用后生成答案
4. **评测框架** — 2 个开源项目、30 条 Q&A 对的基准集，对比纯文本基线

### 技术栈

| 组件 | 选型 | 说明 |
|---|---|---|
| AST 解析 | tree-sitter (py-tree-sitter) | 跨 40+ 语言统一接口 |
| 向量库 | ChromaDB | 嵌入式，零运维 |
| 缓存 | Redis (Docker) | LLM 回答 + embedding 缓存 |
| Embedding | BGE-small-zh (本地) | 免费，中英文通用 |
| LLM | OpenAI / 兼容 API | 环境变量配置 `LLM_MODEL`、`LLM_API_KEY`、`LLM_BASE_URL`，默认 gpt-4o-mini |
| CLI | Click + Rich | 命令行交互，终端高亮输出 |
| Web (Phase 2) | FastAPI | 自动文档、异步支持 |
| 容器 | Docker + docker-compose | app + redis 一键部署 |

### 架构

```
User: codebase-agent analyze <url>
          │
          ▼
┌──────────────────────────────┐
│    Agent (ReAct Loop)        │
│  ┌────────────────────────┐  │
│  │ 思考→工具调用→观察→回答│  │
│  └──────┬─────────────────┘  │
│    ┌────┼────┬───────┐      │
│    ▼    ▼    ▼       ▼       │
│ AST  语义  BM25   文件阅读   │
└──────────────────────────────┘
    │         │          │
    ▼         ▼          ▼
┌──────┐ ┌────────┐ ┌───────┐
│AST   │ │ChromaDB│ │Redis  │
│索引  │ │向量检索 │ │缓存   │
└──────┘ └────────┘ └───────┘
```

### 数据流

1. `git clone --depth 1` → 本地临时目录
2. tree-sitter AST 解析 → 提取函数/类/方法节点
3. 每个节点 → embedding → ChromaDB + 构建内存 AST 索引
4. 用户提问 → Agent 分类问题类型 → 路由到对应检索策略
5. 多步推理（ReAct）→ 验证引用 → 生成答案
6. Redis 缓存：相同问题 hash 直接命中

### 目录结构

```
codebase-agent/
├── cli/
│   └── main.py
├── agent/
│   ├── router.py
│   ├── react_loop.py
│   └── tools/
│       ├── ast_search.py
│       ├── semantic_search.py
│       └── file_reader.py
├── code_parser/
│   ├── ast_parser.py
│   ├── chunker.py
│   └── relationship.py
├── retrieval/
│   ├── vector_store.py
│   ├── ast_index.py
│   └── hybrid_search.py
├── cache/
│   └── redis_cache.py
├── embedding/
│   └── embedder.py
├── evaluation/
│   ├── benchmark.py
│   └── data/
├── config/
│   └── settings.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

### 部署

```yaml
# docker-compose.yml
services:
  app:
    build: .
    volumes:
      - ./data:/app/data
    depends_on:
      - redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

### 评测方案

**基准数据集：**
- gin-gonic/gin (Go, ~15K 行) — 15 条 Q&A
- FastAPI (Python, ~30K 行) — 15 条 Q&A

**指标：**
- Top-3 命中率：检索是否命中正确答案所在代码块
- 答案准确率（1-5 人工评分）
- 引用准确率：引用的代码行是否支持结论

**基线对比：** 纯文本 500 字分块 vs AST 结构切片

### 成本控制

- 本地 embedding 模型（免费）
- 简单问题不走 LLM（纯检索）
- 复杂问答用便宜模型
- Redis 缓存 LLM 结果，相同/相似问题不重复调用
- 用户自配 API key

### Phase 2 规划（当前不实现）

- FastAPI Web 服务
- 多 Agent 编排 (LangGraph)
- 架构可视化（Mermaid 依赖图）
- 变更分析（PR diff 理解）
- 在线 Demo

## 设计原则

- 每个模块独立可测试
- 先 CLI 后 Web，快速验证效果
- 评测先行，量化证明深度
- 工程完备性：Docker、Redis、日志、配置管理