# 跨境电商售后客服 Agent 评测数据

本目录包含用于 MySQL、Milvus、Elasticsearch、RAG 和 Agent 工作流评测的模拟业务数据。数据贴近跨境电商售后客服场景，但不包含真实用户隐私。

## 数据规模

- `knowledge/`：20 篇跨境电商售后知识库 Markdown 文档
- `seed/orders_seed.json`：200 条订单种子数据
- `seed/orders_seed.sql`：200 条订单 SQL 种子数据
- `seed/tickets_seed.json`：80 条工单种子数据
- `eval/rag_eval_dataset.json`：60 条 RAG 评测问题
- `eval/agent_eval_dataset.json`：20 条 Agent 工作流评测用例

## 建议导入顺序

1. 导入 `seed/orders_seed.json` 或按实际模型调整 `seed/orders_seed.sql` 后导入 MySQL。
2. 将 `knowledge/*.md` 逐个通过知识库创建接口入库。
3. 确认每个文档同步写入 Milvus 和 Elasticsearch。
4. 使用 `eval/rag_eval_dataset.json` 做 Ragas 或 Hit@K 评测。
5. 使用 `eval/agent_eval_dataset.json` 做 Agent 意图识别、工具调用和上下文补全评测。

## 说明

这批数据刻意包含相近规则和干扰项，例如美国30天、欧盟14天、日本14天、韩国7天、电子产品45天、物流10/15/5天等，用于测试 Hybrid Search 和 Rerank 是否能正确区分相似政策。