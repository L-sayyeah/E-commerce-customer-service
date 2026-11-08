# 本地最小运行环境

本地只运行应用容器。MySQL、Milvus 和 Elasticsearch 使用远端 Docker 服务，通过本机已有的 Tailscale 网络连接；DeepSeek、Embedding 和 Rerank 已完成实际 API 调用验证。

## 已复用的本地资源

| 资源 | 当前情况 |
|---|---|
| Docker Desktop | 已有安装，本次启动引擎 |
| `langchain-langgraph-rag:light` | 已有 ARM64 镜像，ID 前缀 `c29c74613faa`，作为默认基础镜像 |
| `python:3.11-slim` | 已有 ARM64 镜像，用于多阶段构建的精简运行阶段，也可作为替代构建基础镜像 |
| Python | 基础镜像中为 Python 3.11；不修改宿主机 Python |
| Tailscale | 宿主机已有连接，不在应用容器中重复部署 Tailscale |

本次增加的应用镜像名为 `custom-service-agent:local`，Compose 项目名为 `custom-service-agent`。Compose 只有 `app` 一个服务，不创建本地数据库、向量库、搜索引擎或本地模型。

## 文件用途

| 文件 | 用途 |
|---|---|
| [Dockerfile](Dockerfile) | 构建阶段复用已有依赖，运行阶段复用 Python slim 镜像，以非 root 用户运行 |
| [compose.yaml](compose.yaml) | 只启动应用并绑定 `127.0.0.1:8000` |
| [requirements.in](requirements.in) | 直接运行依赖及版本约束 |
| [requirements.txt](requirements.txt) | 解析后的依赖锁，包含版本与 wheel SHA-256，面向 CPython 3.11 / Linux ARM64 |
| [.env.runtime.example](.env.runtime.example) | 无真实凭据的配置模板 |
| `.env.runtime` | 本地私有运行配置，已加入忽略规则，不进入镜像 |
| [.dockerignore](.dockerignore) | 只允许运行所需文件进入构建上下文，排除现有 `.env` 和日志等 |

依赖锁包含当前源码所需的 Web、数据库客户端、LangGraph、模型与检索 SDK。不主动安装 Ragas 评测环境；PyMilvus 自身需要的 pandas 等传递依赖仍会安装。

原有 `.env` 保留，容器不读取该文件；Compose 通过 `.env.runtime` 将变量注入应用。

原有 `.env` 已在 Git 跟踪中，新增忽略规则不会自动解除既有跟踪。后续真实凭据填写在本地 `.env.runtime`，不要填入配置模板。

## 本次实际验证结果

验证日期：2026-11-03。

- 最终运行镜像：`custom-service-agent:local`，Linux ARM64，约 833 MB；以 UID 10001 运行。
- `python -m pip check` 通过，应用导入、LangGraph 图编译和 OpenAPI 生成通过。
- Milvus 可选 token 的空值与传递行为通过隔离检查，没有发送测试 token 到远端。
- 容器健康状态为 healthy；本机 `/health`、`/docs`、`/openapi.json` 均返回 HTTP 200，注册 31 个接口路径。
- 三项远端服务已通过认证：MySQL 8.0.46、Elasticsearch 8.13.0、Milvus 2.6.25。
- MySQL `custom_service_agent` 中 11 张预期业务表均存在，共读取到 16 张表；数据库迁移版本 `a2801d519efc` 与本地 Alembic head 一致。
- Elasticsearch 的 `knowledge_chunks` 索引、Milvus default 库的 `knowledge_chunks` 集合均存在。
- 更新凭据后，本机 `/health/db` 和 `/api/v1/knowledge/vector-store/health` 均返回 HTTP 200。
- DeepSeek `deepseek-flash` 已通过实际意图识别调用：输入“退款政策是什么？”，返回可解析 JSON，意图为 `rag_qa`；直接调用 LLM 分类函数，未使用规则回退掩盖错误。
- `qwen3.7-text-embedding` 已将两条测试文本转换为两个 1536 维向量；仅检查响应，没有写入向量库。
- `qwen3.7-text-rerank` 已完成两篇测试文档的重排，退款说明排在物流说明之前；`RAG_RERANK_ENABLED` 已开启。
- 修正了私有配置中两个 Key 字段填写为字面字符串 `DASHSCOPE_API_KEY` 的问题，改为实际密钥；修正前两个接口均返回 401，修正后均成功。
- MinerU 只读鉴权检查通过：使用不存在的测试任务 ID，携带配置的凭据返回 HTTP 200、业务码 `-60012`（任务不存在或已过期）；不携带凭据的同一请求返回 HTTP 401。未创建或验证实际解析任务。
- 没有执行远端数据库迁移、建表、索引初始化、知识入库或业务写入；完整对话和文档解析流程仍待功能联调。

## 启动与常用操作

首次使用前若没有私有配置，复制模板并填写：

```bash
cp .env.runtime.example .env.runtime
chmod 600 .env.runtime
```

已有 `.env.runtime` 时保留现有文件，不重复覆盖。

构建并启动：

```bash
docker compose up -d --build app
```

查看状态和日志：

```bash
docker compose ps
docker compose logs --tail=100 app
```

本机访问：

- 健康检查：`http://127.0.0.1:8000/health`
- 接口文档：`http://127.0.0.1:8000/docs`
- OpenAPI：`http://127.0.0.1:8000/openapi.json`

停止应用：

```bash
docker compose down
```

本地 8000 端口被占用时，可以仅对本次命令指定其他端口：

```bash
CUSTOM_SERVICE_PORT=18000 docker compose up -d app
```

如果不使用已有 LangGraph 基础镜像，也可以使用本地已有的 Python 基础镜像构建同一组锁定依赖：

```bash
CUSTOM_SERVICE_BASE_IMAGE=python:3.11-slim docker compose build app
```

## 业务接口鉴权与工单提交

业务接口需要 `Authorization: Bearer <token>`。开发部署由运维通过私有配置注册高熵随机凭证，配置值仅保存 SHA-256 摘要和对应身份。示例结构如下，其中摘要和用户 ID 要替换为实际值。

```text
AUTH_TOKEN_DIGESTS={"<64位小写十六进制摘要>":{"user_id":"<业务用户ID>","role":"customer"}}
```

使用密码学随机生成器为各用户分别生成至少 32 字节随机值。摘要登记后，将原 token 通过安全渠道交给对应用户。撤销或轮换需要更新私有配置并重启应用。此方式用于首期部署，后续可替换为已选定的身份提供方。`admin` 仅分配给受信任运维或工单处理方，可操作知识库、查阅管理日志和处理工单。空配置拒绝所有业务请求。

部署本次代码前，在目标环境应用新增 Alembic 迁移 `5c0f9a2d8e31`。迁移后用户需要创建新会话，旧会话的用户 ID 曾由客户端提交，需另行核实归属。旧工单保留，客户能通过本人订单查验有独立归属依据的关联工单，管理员可查旧工单。

创建工单使用 `POST /api/v1/tickets`，同时提供 `Idempotency-Key`。客户端为每次确认的申请生成唯一键，网络失败后用原键和相同业务参数重试。重复提交返回同一工单号，原键用于不同业务参数返回 HTTP 409。请求体中的用户 ID、优先级和来源由服务端确定。资格查询和聊天中的转人工意图只给出结果或下一步提示，由调用方在用户确认后显式提交工单。

## 多轮对话与检索路线

同步聊天和 Agent 流式聊天共用父图及政策、订单、工单子图。DST 从经授权会话的用户消息重建，跟踪订单指代、改口和歧义，以及明确的地区和工单引用。订单事实仍从授权后的数据库查询读取。

订单地区与临时政策地区分别处理。若客户先查日本订单，再问欧盟政策，之后只说“那退货规则呢”，聊天会先问是欧盟的一般规则还是刚才那笔日本订单的规则。澄清轮次暂缓政策检索；下一轮明确选择后用原问题检索。会话消息保存澄清标记，关闭 Checkpoint 时也可恢复。未核实归属的订单地区不出现在澄清选项里。Agent 流式知识答复保留现有事件名，先发意图，审查后的答案作为一个文本事件发送。普通知识流仍逐段输出。

`AGENTIC_RAG_ENABLED` 控制是否允许拆解及补检。`RAG_ADAPTIVE_RERANK_ENABLED` 控制分差截断，`RERANK_MIN_SCORE_GAP` 是待校准的分差门槛。`RAG_HYBRID_FUSION` 可选 `weighted` 或 `rrf`，默认沿用加权融合。要复现固定 Top-K 对照，将 Agentic RAG 和自适应重排两个开关都关闭。

复杂路线先保存固定 Top-5 的证据，再核对最多三个子问题的覆盖情况。聊天入口为缺口预留最多两个补充片段，已找到的基础证据保留。证据检查和补检共享 15 秒预算，基础与补检合计按 60 个候选评分对控制。显式请求 Top-5 的知识 API 在证据位置用满时返回基础结果。普通路线一次检索与重排，分差截断适用于单诉求且无明显例外信号的请求。

## 当前连接与功能开关

远端服务与模型 API 凭据已写入私有 `.env.runtime`，三项存储服务及核心模型接口已通过验证。目前配置：

```env
LANGGRAPH_CHECKPOINT_ENABLED=false
RAG_RERANK_ENABLED=true
```

`/health`、`/docs` 不触发数据库或模型请求；`/health/db` 验证业务数据库连接。模型验证独立使用项目实际客户端完成，不把健康接口正常视为模型验证成功。意图识别、Embedding、Rerank 的单次调用已通过；完整对话、检索质量、文档解析和跨轮恢复未在本次验证中覆盖。

已从应用容器使用项目实际的数据库、Elasticsearch 和 Milvus 客户端完成只读认证与版本检查，并检查了业务表、索引、集合是否存在。原有 `.env` 保留不变；模型验证仅发送少量测试文本，没有将结果入库。

已确认的远端信息：

| 服务 | 地址 | 服务端版本 |
|---|---|---|
| MySQL | `<REMOTE_HOST>:3306` | 已认证读取 8.0.46 |
| Milvus | `<REMOTE_HOST>:19530` | 已认证读取 2.6.25，使用 default 库 |
| Elasticsearch | `http://<REMOTE_HOST>:9200` | 已认证读取 8.13.0 |

统一主机名为 `<TAILSCALE_HOST>`。当前配置使用已验证 TCP 可达的 IP；若改用主机名，应另外验证容器内 DNS。

## 接通远端服务时补充的配置

在 `.env.runtime` 中按实际信息填写：

| 配置 | 应填写内容 |
|---|---|
| `DATABASE_URL` | `mysql+asyncmy://用户名:密码@Tailscale地址:端口/数据库`，账号中的特殊字符按 URL 规则编码 |
| `MILVUS_HOST`、`MILVUS_PORT` | 远端服务实际发布到宿主机的 Tailscale 地址及端口 |
| `MILVUS_TOKEN` | 远端启用认证时填写其 token，常见形式为 `用户名:密码`；代码仅在非空时传入 |
| `ELASTICSEARCH_URL` | 实际 HTTP/HTTPS 地址，不一定是默认 9200 |
| `ELASTICSEARCH_USERNAME`、`ELASTICSEARCH_PASSWORD` | 远端开启认证时填写 |
| `LLM_API_KEY`、`LLM_BASE_URL`、`CHAT_MODEL` | 已配置 DeepSeek base URL、deepseek-flash 和真实 Key，实际分类调用通过 |
| `EMBEDDING_ENDPOINT`、`EMBEDDING_MODEL`、`EMBEDDING_API_KEY` | 完整的 OpenAI 兼容 Embedding 地址、模型与 Key；新工作空间配置优先走该路径 |
| `EMBEDDING_DIMENSIONS`、`EMBEDDING_BATCH_SIZE` | 当前设为 1536 维、每批最多 20 条；与现有集合维度对齐 |
| `DASHSCOPE_API_KEY` | 未配置 EMBEDDING_ENDPOINT 时使用原有 DashScope SDK 路径；也可用于原有重排地址 |
| `RERANK_ENDPOINT`、`RERANK_MODEL`、`RERANK_API_KEY` | 原生 DashScope 重排地址、独立模型与可选 Key；与 Embedding 同源时允许复用其 Key |
| `RAG_RERANK_ENABLED` | 已在重排接口实测通过后开启，目前为 true |
| `MINERU_API_KEY` | 已填写，通过只读鉴权检查；实际文档解析未测试 |

连接地址使用远端宿主机实际发布的端口。容器内的 localhost 指应用容器自身，不是远端电脑。宿主机 Tailscale 已连接，也仍需验证 Docker 容器到该地址的路由和端口可达性。

修改配置后重新创建应用容器：

```bash
docker compose up -d --force-recreate app
```

### 客户端版本与联调范围

- Elasticsearch 客户端已锁定为 8.13.0，与用户提供的服务端版本对齐。[官方兼容说明](https://www.elastic.co/docs/reference/elasticsearch/clients/python)
- PyMilvus 锁定为 2.6.17，已成功连接远端 2.6.25；集合维度与新模型实际输出均为 1536。旧向量的模型来源和检索质量仍需单独验证。[PyMilvus 官方兼容说明](https://github.com/milvus-io/pymilvus)
- 改 Python、架构或客户端版本时，应重新解析 `requirements.in` 并更新锁；当前锁中的单一 wheel hash 不面向宿主机 macOS 或其他平台。

### Checkpoint 后续启用

私有运行配置已准备 `LANGGRAPH_CHECKPOINT_DB_URI`，但开关继续保持关闭。后续确定启用 checkpoint 时再打开并单独验证恢复流程。扩展示例使用 `mysql://...` 形式，需按已装扩展支持的格式填写，不能直接假定所有 SQLAlchemy URI 形式都支持。

启动会调用 checkpointer 的 `setup()`，可能创建相应表；它不会自动使用 `DATABASE_URL` 作为缺省连接。扩展声明需要 MySQL 8.0.19 或更新版本，并对 MySQL 9.6 起的 generated-column 行为提示兼容问题，具体远端版本需核实。[扩展官方说明](https://pypi.org/project/langgraph-checkpoint-mysql/)

## 业务数据初始化单独进行

当前业务表和本地对应的迁移 head 已存在，不需要为了连接验证重复初始化。以后确实有模型或迁移变化时，可以在应用容器中执行迁移：

```bash
docker compose exec app python -m alembic upgrade head
```

本次没有执行该命令，也没有导入订单、工单或知识数据。Milvus collection 和 ES index 已存在，后续按需检查数据与模型兼容性，不要为连通性验证重建。当前 `/knowledge/search-engine/health` 实际会尝试初始化索引，不能当成纯只读连接检查。

## 工作空间 Embedding 与 Rerank 接入

已按提供的业务空间配置私有 `.env.runtime`，用户填写的真实 Key 已用于少量在线调用，两个接口均成功。

| 项目 | 当前配置与状态 |
|---|---|
| Embedding 模型 | `qwen3.7-text-embedding` |
| Embedding 地址 | 提供的工作空间地址，完整路径为 `/compatible-mode/v1/embeddings` |
| Embedding 输出 | 显式传 `dimensions=1536`、`encoding_format=float`，文档每批最多 20 条 |
| Rerank 模型 | `qwen3.7-text-rerank`，已通过实际重排调用 |
| Rerank 地址 | 同工作空间的 `/api/v1/services/rerank/text-rerank/text-rerank`，不是 Embedding 地址 |
| Rerank 请求 | `input.query` 为字符串，`input.documents` 为字符串列表，响应读取 `output.results` |
| API Key | 两个字段已使用实际 DashScope Key，均通过认证；未在公开文件或输出中展示 |
| 开关 | `RAG_RERANK_ENABLED=true`，已在在线验证后开启 |

`EMBEDDING_WORKSPACE_ID` 保留业务空间记录；完整 endpoint 已包含工作空间信息，不会重复作为请求体字段发送。

协议与模型参数依据：[官方 OpenAI 兼容 Embedding 接口](https://help.aliyun.com/zh/model-studio/embedding-interfaces-compatible-with-openai)、[官方 Rerank 接口](https://help.aliyun.com/zh/model-studio/text-rerank-api)。文档支持不代表当前 Key 已获得模型权限。

### Key 填写与单次验证

后续更换密钥时，在私有 `.env.runtime` 填写 `EMBEDDING_API_KEY`。如果重排使用不同凭据，再填写 `RERANK_API_KEY`。不要把字段值写为字面字符串 `DASHSCOPE_API_KEY`，应用会将其当作密钥发送，而不会查找同名变量。模型 API Key 与数据库、Milvus token 是不同凭据，不能互相替代。

使新配置生效：

```bash
docker compose up -d --force-recreate app
```

以下命令可用于更换 Key 后复查，会各调用一次真实接口，但不会写入数据库或向量集合。

Embedding 单次验证：

```bash
docker compose exec -T app python - <<'PY'
import asyncio
from app.services.embedding_service import EmbeddingService

vector = asyncio.run(EmbeddingService().embed_query("售后政策查询"))
print("embedding_dimensions=", len(vector))
PY
```

Rerank 单次验证：

```bash
docker compose exec -T app python - <<'PY'
import asyncio
from app.services.rerank_service import RerankService

documents = [
    {"chunk_id": "demo-refund", "content": "退款申请说明"},
    {"chunk_id": "demo-logistics", "content": "物流查询说明"},
]
result = asyncio.run(RerankService().rerank("如何申请退款", documents, top_n=2))
print([(item["chunk_id"], item["rerank_score"]) for item in result])
PY
```

当前独立验证已通过，`RAG_RERANK_ENABLED` 已设为 true 并重新创建容器。独立重排测试不依赖该开关，开关只控制 RAG 主流程是否调用重排。

### 现有向量的兼容范围

只读检查确认现有 `knowledge_chunks.embedding` 为 1536 维，统计记录数为 100。本次没有重建或写入这些向量。

相同维度不能证明已有向量由同一个模型生成。原数据的 Embedding 模型尚未确认，不能直接将其与新模型视为兼容。后续需确认向量来源，或单独规划重新索引，不能仅凭单次 API 成功就认定检索效果正确。

可选的 `app/data/ragas_test.py` 评审脚本仍自行构造 DashScope Embedding 客户端，未同步切换到本节适配器；使用该脚本前需另行对齐评审模型和端点配置。

### 离线协议测试

已使用标准库 unittest 和 HTTPX MockTransport 编写 14 项测试，覆盖批量拆分、返回顺序、1536 维约束、缺失 Key、错误响应、重排映射、Key 来源及旧接口兼容。测试过程中容器关闭网络，不发送真实 API 请求。

```bash
docker run --rm --pull=never --network none --env-file .env.runtime \
  --mount "type=bind,src=$PWD/tests,dst=/tests,readonly" \
  --entrypoint python custom-service-agent:local \
  -m unittest discover -s /tests -v
```

这些测试验证协议适配，不代表模型权限、在线质量或现有向量兼容性已经验证。

## DeepSeek LLM 配置

私有 `.env.runtime` 已配置真实 Key；以下仅展示配置字段，Key 留空以避免公开凭据：

```env
LLM_BASE_URL=https://api.deepseek.com
CHAT_MODEL=deepseek-flash
LLM_API_KEY=
```

现有代码通过 `ChatOpenAI` 调用兼容接口，不需要增加 SDK 或修改业务流程。意图识别、RAG 回答和回复审查共用这组配置；分类和审查代码传入 temperature=0，RAG 使用 `LLM_TEMPERATURE`。

base URL 与模型名符合 [DeepSeek 官方调用说明](https://api-docs.deepseek.com/)。不修改应用的全局默认提供商，也不修改原 `.env`。实际调用 `IntentClassifier.llm_classify("退款政策是什么？")` 已返回有效 JSON，意图为 `rag_qa`；RAG 生成与回复审查的完整业务流程尚未测试。

后续更换私有 `.env.runtime` 中的 DeepSeek `LLM_API_KEY` 后，重建容器使环境变量生效：

```bash
docker compose up -d --force-recreate app
```

DeepSeek Key 与阿里云 Embedding/Rerank Key 分别配置，不能互相替代。健康检查通过仅代表应用框架可用，不代表这些模型服务已通过认证。
