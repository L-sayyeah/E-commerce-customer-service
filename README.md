# 跨境电商售后客服 Agent 系统

## 项目简介

本项目是一个面向跨境电商售后场景的智能客服 Agent 后端系统，基于 FastAPI、LangGraph、LangChain、MySQL、Milvus、Elasticsearch、Rerank 和 Ragas 构建。

系统支持客服对话、知识库管理、RAG 检索、订单查询、售后规则判断、Agent 工作流、工单管理、日志追踪、文档解析和离线评测。核心目标是让客服 Agent 不仅能回答售后政策问题，还能结合订单状态、物流状态和售后规则完成业务判断，并通过日志和评测体系保证可观测、可迭代。

本项目适合作为后端智能体、RAG、LangGraph 工作流和企业级客服系统方向的简历项目。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| Web 框架 | FastAPI |
| Agent 编排 | LangGraph |
| LLM 编排 | LangChain |
| 大模型 | Doubao Seed / OpenAI 兼容接口 |
| Embedding | DashScope Embeddings |
| Rerank | DashScope qwen3-vl-rerank |
| 关系数据库 | MySQL |
| 向量数据库 | Milvus |
| 关键词检索 | Elasticsearch BM25 |
| 文档解析 | MinerU 精准解析 API |
| RAG 评测 | Ragas |
| 日志追踪 | trace_id、RAG logs、Agent node logs |
| 部署 | Docker / Docker Compose |

## 核心功能

### 客服对话

- 创建客服会话
- 发送用户消息
- 普通响应与 SSE 流式响应
- 支持多轮对话上下文
- 支持基于 Agent 的客服入口

### LangGraph Agent 工作流

系统将一次客服请求拆分为多个可观测节点：

```text
用户消息
-> build_context
-> classify_intent
-> route
-> rag / order_query / aftersales_check / ticket_create / clarify
-> response_guard
-> final
```

已实现能力：

- LLM 意图识别
- 规则兜底分类
- 上下文工程节点 `ContextBuilder`
- 最近订单号和追问识别
- 订单查询工具
- 售后判断工具
- 工单创建或复用工具
- RAG 问答工具
- Response Guard 安全检查
- Agent action 执行轨迹
- Agent node 级别日志
- LangGraph checkpoint 状态持久化

### 知识库管理

- 创建知识库文档
- Markdown 标题层级切分
- 递归字符切分兜底
- chunk overlap
- 文档内容 Hash
- 文档索引状态管理
- 索引失败自动重试
- 手动重建索引接口
- 文档详情和 chunk 查询

### RAG 检索链路

系统支持三种检索模式：

1. Vector Search：Milvus 向量召回
2. BM25 Search：Elasticsearch 关键词召回
3. Hybrid Search：向量召回 + BM25 融合排序

RAG 链路：

```text
用户问题
-> Hybrid Search
-> Rerank
-> Prompt 构建
-> LLM 生成答案
-> 返回 sources 和 answer
-> 记录 RAG 日志
```

### Rerank

- 使用 DashScope `qwen3-vl-rerank`
- 支持 Rerank 开关
- 支持 Rerank 失败 fallback
- 记录 rerank_status、rerank_model、rerank_error

### 订单与售后规则

- 根据订单号查询订单
- 判断退款、换货、补发资格
- 根据国家、签收时间、物流状态、订单金额判断售后策略
- 对高风险场景标记人工审核
- 对需要人工处理的售后请求创建或复用工单

### 工单管理

- 创建工单
- 查询工单
- 更新工单状态
- 记录工单操作日志
- 支持同一订单未关闭工单复用
- 支持 low / medium / high / urgent 优先级

### 文档解析

- 接入 MinerU 精准解析 API
- 创建文档解析任务
- 查询解析任务状态
- 获取 `full_zip_url`
- 下载并解压 Markdown
- 将解析结果写入知识库并同步索引到 Milvus 和 Elasticsearch

### 日志与可观测性

- 请求级 `trace_id`
- RAG 检索日志
- Agent run 日志
- Agent node 日志
- 工单操作日志
- 支持按 trace_id 聚合查询一次请求的完整链路

可观测内容包括：

- 用户问题
- 意图识别结果
- 节点耗时
- 工具调用轨迹
- RAG sources
- Rerank 状态
- LLM 回答
- 异常信息

## RAG 评测结果

项目使用 Ragas 对 Vector、Hybrid、Hybrid + Rerank 三种策略进行了离线评测。评测集包含跨境电商售后政策相关问题，覆盖退款、物流、支付、工单、人工审核、国家差异等场景。

| 检索策略 | Faithfulness | Answer Relevancy | Context Precision | Context Recall |
| --- | ---: | ---: | ---: | ---: |
| Vector | 0.8863 | 0.4823 | 0.8696 | 0.9500 |
| Hybrid | 0.9037 | 0.5451 | 0.8517 | 1.0000 |
| Hybrid + Rerank | 0.7592 | 0.6196 | 1.0000 | 1.0000 |

评测结论：

- Hybrid Search 相比纯向量检索提升了上下文召回率。
- Hybrid + Rerank 在答案相关性和上下文精确率上表现最好。
- Rerank 后 Faithfulness 有下降，说明后续仍需要优化 Prompt 约束和上下文压缩策略。
- 该评测结果可用于指导 RAG 检索策略、Rerank 策略和 Prompt 策略迭代。

## 项目目录

```text
app/
├── agents/              # LangGraph Agent 状态、节点、图、上下文工程、工具封装
├── api/                 # FastAPI 路由
├── core/                # 配置、数据库、日志、中间件、异常、响应结构
├── data/                # 知识库数据、评测集、seed 数据、评测结果
├── models/              # SQLAlchemy ORM 模型
├── schemas/             # Pydantic 请求和响应模型
├── services/            # 业务服务、RAG、Embedding、Milvus、ES、MinerU、Rerank
└── main.py              # FastAPI 启动入口

migrations/              # Alembic 数据库迁移
logs/                    # 日志目录
```

## 主要接口

### 健康检查

```http
GET /health
GET /health/db
```

### 客服对话

```http
POST /api/v1/chat/sessions
POST /api/v1/chat/messages
POST /api/v1/chat/messages/stream
POST /api/v1/chat/agent/messages
POST /api/v1/chat/agent/messages/stream
```

### 知识库

```http
POST /api/v1/knowledge/documents
GET  /api/v1/knowledge/documents
GET  /api/v1/knowledge/documents/{document_id}
POST /api/v1/knowledge/documents/{document_id}/retry-index
```

### 检索与 RAG

```http
POST /api/v1/knowledge/search
POST /api/v1/knowledge/bm25-search
POST /api/v1/knowledge/hybrid-search
POST /api/v1/knowledge/rag
POST /api/v1/knowledge/rag/stream
```

### 订单与售后

```http
GET /api/v1/orders/{order_no}
GET /api/v1/orders/{order_no}/aftersales-eligibility
```

### 工单

```http
POST /api/v1/tickets
GET  /api/v1/tickets
GET  /api/v1/tickets/{ticket_no}
PATCH /api/v1/tickets/{ticket_no}/status
GET  /api/v1/tickets/{ticket_no}/logs
```

### MinerU 文档解析

```http
POST /api/v1/knowledge/parse-tasks
GET  /api/v1/knowledge/parse-tasks/{task_id}
POST /api/v1/knowledge/parse-tasks/{task_id}/index
```

### 后台日志

```http
GET /api/v1/admin/logs/rag
GET /api/v1/admin/logs/agent-runs
GET /api/v1/admin/logs/agent-nodes
GET /api/v1/admin/logs/traces/{trace_id}
```

## 环境变量示例

请在项目根目录创建 `.env`。

```env
APP_NAME=Custom Service Agent
DEBUG=true
API_PREFIX=/api/v1

DATABASE_URL=mysql+asyncmy://root:password@127.0.0.1:3306/custom_service_agent

LOG_LEVEL=INFO
LOG_FILE=logs/app.log

MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
MILVUS_COLLECTION=knowledge_chunks
MILVUS_VECTOR_DIM=1536

ELASTICSEARCH_URL=http://127.0.0.1:9200
ELASTICSEARCH_USERNAME=
ELASTICSEARCH_PASSWORD=
ELASTICSEARCH_INDEX=knowledge_chunks
ELASTICSEARCH_ANALYZER=standard

DASHSCOPE_API_KEY=your_dashscope_api_key

LLM_API_KEY=your_llm_api_key
LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
CHAT_MODEL=doubao-seed-2-0-lite-260428
LLM_TEMPERATURE=0.7

EMBEDDING_MODEL=text-embedding-v2
EMBEDDING_DIMENSIONS=1536

RAG_RETRIEVAL_MODE=hybrid
HYBRID_VECTOR_WEIGHT=0.7
RAG_RERANK_ENABLED=true
RAG_RETRIEVAL_TOP_N=20
RERANK_MODEL=qwen3-vl-rerank
RERANK_TOP_N=5

MINERU_API_KEY=your_mineru_api_key
MINERU_BASE_URL=https://mineru.net/api/v4
MINERU_MODEL_VERSION=vlm
MINERU_LANGUAGE=ch

LANGGRAPH_CHECKPOINT_ENABLED=true
LANGGRAPH_CHECKPOINT_BACKEND=mysql
LANGGRAPH_CHECKPOINT_DB_URI=mysql+asyncmy://root:password@127.0.0.1:3306/custom_service_agent
```

## 启动方式

### 1. 创建虚拟环境

```bash
python -m venv .venv
```

Windows：

```bash
.venv\Scripts\activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 初始化数据库

```bash
alembic upgrade head
```

### 4. 启动 FastAPI

```bash
uvicorn app.main:app --reload --port 8000
```

访问：

```text
http://127.0.0.1:8000/docs
```

## 数据准备

项目内置了评测和演示数据：

```text
app/data/knowledge/         # 跨境电商售后知识库 Markdown
app/data/eval/              # RAG 和 Agent 评测集
app/data/seed/              # MySQL 订单和工单 seed 数据
```

建议顺序：

1. 导入 MySQL seed 数据。
2. 初始化 Milvus collection。
3. 初始化 Elasticsearch index。
4. 将 `app/data/knowledge/*.md` 通过知识库接口入库。
5. 确认文档同步写入 MySQL、Milvus 和 Elasticsearch。
6. 运行 RAG 或 Ragas 评测脚本。

## 面试亮点

### 1. 为什么使用 LangGraph

普通 Chain 适合线性问答，但客服售后场景包含意图识别、订单查询、售后判断、工单创建、安全检查和人工审核等多个业务节点。LangGraph 可以把流程拆成显式状态机，使每个节点可观测、可恢复、可单独优化。

### 2. 为什么使用 Hybrid Search

纯向量检索适合语义召回，但对订单、国家、天数、支付方式等精确关键词不够稳定。BM25 对关键词敏感，但语义泛化较弱。Hybrid Search 融合 Milvus 向量召回和 Elasticsearch BM25，兼顾语义和关键词。

### 3. Rerank 的作用

Hybrid Search 负责扩大召回，Rerank 负责对候选上下文重新排序，提高 TopK 上下文精确率，使最终进入 Prompt 的内容更相关。

### 4. trace_id 的作用

trace_id 用于串联一次请求中的 HTTP 请求、Agent run、Agent node、RAG 检索和工单操作。线上排查时可以通过 trace_id 还原完整调用链路。

### 5. 上下文工程

项目没有简单把历史消息全部塞进 Prompt，而是通过 ContextBuilder 提取最近订单号、最近工单、上一轮意图、当前是否追问等结构化上下文，提高多轮客服对话的稳定性。

### 6. 评测闭环

项目使用 Ragas 对不同检索策略进行离线评测，并根据 Faithfulness、Answer Relevancy、Context Precision、Context Recall 分析检索和生成效果，使 RAG 优化有数据依据。

## 后续优化方向

- 接入 JWT 鉴权和 RBAC 权限控制
- 完善后台管理页面
- 增加 Human-in-the-loop 审核任务持久化
- 增加 RAG Prompt 自动优化和上下文压缩
- 增加 Agent 工作流自动化评测
- 增加 Docker Compose 一键部署
- 增加 CI 测试和接口自动化测试

## 简历描述参考

```text
基于 FastAPI + LangGraph 构建跨境电商售后客服 Agent 系统，支持客服对话、订单查询、售后规则判断、知识库 RAG 问答、工单管理和日志追踪。系统结合 Milvus 向量检索、Elasticsearch BM25、DashScope Rerank 和 Doubao 大模型，实现 Hybrid RAG 检索与流式回答，并通过 Ragas 对 Vector、Hybrid、Hybrid+Rerank 进行离线评测。实验结果显示，Hybrid+Rerank 将 Answer Relevancy 从 0.482 提升至 0.620，Context Precision 从 0.870 提升至 1.000，Context Recall 从 0.950 提升至 1.000。
```