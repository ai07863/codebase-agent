# CodeBase Agent

用自然语言分析任意 GitHub 仓库。提问代码结构、查找函数、理解架构。

## 快速开始

```bash
# 克隆并进入
git clone <this-repo> && cd codebase-agent

# 配置
cp .env.example .env
# 编辑 .env，填入你的 LLM_API_KEY

# 启动 Redis 并运行
docker compose up -d
codebase-agent analyze https://github.com/gin-gonic/gin
```

## 工作原理

1. **克隆** — 使用 `--depth 1` 拉取仓库
2. **AST 解析** — 用 tree-sitter 提取每个函数、类和方法
3. **索引** — embedding 存入 ChromaDB；内存中构建 AST 索引
4. **问答** — 自然语言问题路由到对应的搜索策略

## 架构

```
codebase-agent/
├── cli/           # Click 命令行
├── agent/         # ReAct 循环 + 工具
├── code_parser/   # tree-sitter AST
├── retrieval/     # ChromaDB + BM25 + AST 索引
├── embedding/     # BGE-small-zh
├── cache/         # Redis
├── evaluation/    # 评测 + Q&A 数据集
└── config/        # 配置
```

## 评测

```bash
python -m evaluation.benchmark gin
python -m evaluation.benchmark fastapi
```