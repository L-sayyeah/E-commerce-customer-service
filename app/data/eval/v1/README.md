# 售后 Agent 验收数据

当前候选集包含 8 类、每类 120 条，共 960 条。全部使用仓库政策及模拟订单。正式验收每类至少 101 条独立且已复核的用例，五项回答及检索指标也分别要求至少 101 条可评分的用例。开发、校准和候选数据分开统计。

| 类别 | 当前素材 | 晋级前重点补齐 |
|---|---|---|
| single_hop | 旧题和政策小节 | 将文档标题式问句改成真实客服提问，标记最小证据及难负例 |
| multi_evidence | 两条政策小节的组合 | 用有业务依赖的案例替换机械组合，加入订单事实与冲突政策 |
| rewrite_dst | 明确切换订单、序数指代 | 缺槽、长对话、跨任务、清除旧槽及多候选 |
| insufficient_evidence | 多订单指代歧义 | 政策缺失、版本冲突、订单事实不足、检索不可用 |
| tools | 授权查订单 | 无需工具、参数错误、调用依赖、条件式建单和部分失败 |
| security | 五个来源的跨用户读取注入 | 正常对照、危险工具名、审批重放、响应和日志泄露 |
| recovery_idempotency | 建单并发、响应丢失、恢复重放 | 同键异参、过期审批、模拟退款部分额度、未知状态和乱序回调 |
| judge | 有依据的引文及虚报退款 | 人工逐项评分，补正确改述、部分正确、过期政策、证据错配及合理澄清 |

候选里的重复模板仅用于准备测试素材。换订单号、换同义措辞和重跑同一故障不能直接认定为独立验收样本。

## 记录与复核

每行一个 JSON 对象。字段包括 `id`、`categories`、`family`、`split`、`inputs`、`gold`。晋级时添加 `reviewed_by`。将晋级记录从候选池移出并保存到对应分区。共享用例用多个类别标签记录一次；同一指标只计一次。家族标识应由复核者统一整理，近似问题和共享场景模板不得跨分区。候选生成器给出的 family 是整理提示。

- `relevance_labels` 记录候选证据 ID、相关等级和适用性。`evidence_groups` 记录必需证据点和可互换的证据 ID。
- `reference_claims` 记录参考原子主张及支持证据。评估实际回答时使用模型实际看到的证据和实际产生的主张。
- `user_goals`、`required_facts` 和 `forbidden_claims` 分别记录用户目标、必答事实和禁止断言。无禁止断言时用空数组。
- `tool_expectations`、`expected_state` 和执行断言描述允许或禁止的工具与可核验副作用。`human_ratings` 保存人工逐项判定及依据。

校准集用于调整 Judge 量表，验收集用于比较 Judge 与人工标签。模型、提示词和语料版本随报告保存。权限、金额和业务状态由程序断言。当前检查器只检查记录结构、精确重复、声明的家族切分和标注字段覆盖，语义独立性、标签准确性及实际运行可评分性需要人工复核和运行报告。

## 命令

从仓库根目录执行。

```bash
python3 app/scripts/build_eval_candidates.py
python3 app/scripts/check_eval_dataset.py app/data/eval/v1/candidates.jsonl
python3 app/scripts/check_eval_dataset.py --require-acceptance app/data/eval/v1/candidates.jsonl
```

最后一条目前预期退出码为 1，并列出缺口。正式数据准备好后，将对应 JSONL 一并传入进行发布检查。候选生成命令会重建 candidates.jsonl，复核中的修改应保存在独立文件。

## 已核对的开发用例与检索评分

`development.jsonl` 有 16 条单跳题、4 条多证据题。证据 ID 使用文档名和小节标题，并保留原文供核查。标签已与仓库政策核对，属于开发集，留出验收和人工独立复核仍需另做。

检索运行产物用 JSONL 记录，每行含 `id` 和按排序输出的 `ranked_evidence_ids`。重复证据 ID 只保留第一次出现。真实检索需要把索引 chunk 映射到政策证据 ID。给定完整的运行文件后可执行：

```bash
python3 -m app.scripts.score_eval_retrieval app/data/eval/v1/development.jsonl /path/to/run.jsonl --k 5
```

报告含 Precision@k、Recall@k、nDCG@k、MRR@k、证据组覆盖率及完整覆盖率。未知片段按零相关计分，并单列数量以暴露标注缺口。开发集当前主要标注正例，做正式排序比较前应补充跨检索策略结果池中的难负例与适用性判定。回答与 Judge 分数仍需实际运行评审。

## 正式复核队列与试跑

- `policy-review-queue.jsonl` 有 24 条逐项标注的政策候选，单跳和多证据各 12 条。每条含证据原文、必答事实和禁止断言。复核人应确认问题独立性、政策版本、必答事实与证据对应，再从候选文件移到目标分区。
- `workflow-development.jsonl` 有 28 条流程开发题，涵盖 DST、证据不足、工具、权限和恢复。工具、权限及恢复的预期结果独立保存，执行报告应以真实 API、数据库和业务状态判断。
- `judge-calibration.jsonl` 有 8 条合成校准题，包含证据忠实但过时、虚报补发、正确追问和答案注入等情形。`expected_ratings` 是编写用例时设定的对照分数。正式验收需独立人工评分。
- 正式记录额外要求 `review_kind: independent_human` 和真实的 `reviewed_by` 标识。严格覆盖检查仍要求每类和每项指标 101 条。近义题和场景独立性由复核者确认。

固定 Top-5、动态重排、Agentic RAG 和 Agentic RAG + RRF 可用 [实跑评测脚本](../../../scripts/eval_live_rag.py) 做同题对照。以下命令从仓库根目录运行，需先加载项目私有运行配置：

```bash
python -m app.scripts.eval_live_rag app/data/eval/v1/development.jsonl /tmp/rag-eval.json
python -m app.scripts.eval_live_rag app/data/eval/v1/judge-calibration.jsonl /tmp/judge-calibration.json --calibrate
python -m app.scripts.eval_live_rag app/data/eval/v1/development.jsonl /tmp/rag-rejudged.json --rejudge /tmp/rag-eval.json
```

Judge 可通过 `EVAL_JUDGE_MODEL`、`EVAL_JUDGE_BASE_URL` 和 `EVAL_JUDGE_API_KEY` 指定。未配置时沿用回答模型。当前量表分开调用三个评分项，证据忠实度评审只接收回答与本次证据。复评复用保存的生成结果。评测不写业务数据库或索引。详细运行产物包含检索文本，应保存到受控路径。

Context Precision 在此报告采用「入模片段中匹配金标证据的比例」，与固定分母的 Precision@5 分开。它依赖已标注的原文，未匹配的内容可能是尚未标注的有效证据。延迟是服务层检索、重排与生成的耗时，排除 Judge 和 HTTP 请求。


复跑当前聊天检索方案时，使用 `--profiles fixed agentic --agentic-top-k 7`。固定路线仍为 Top-5，复杂聊天在保留基础证据后最多补充两条。Recall@5 和 nDCG@5 固定观察前五条，Context Recall 和完整证据覆盖观察全部实际入模片段。

## DST 与 Query Rewrite 多轮回归

`multiturn-development.jsonl` 保存 30 段开发对话和 81 个已标注用户轮次。每个用户轮次分别标注业务引用、路由和预期改写方式。有证据标注的改写题额外保存独立查询与最小相关证据。以下命令使用当前规则意图路由，不执行工具或写入业务数据。

```bash
python -m app.scripts.eval_multiturn app/data/eval/v1/multiturn-development.jsonl /tmp/multiturn-local.json
python -m app.scripts.eval_multiturn app/data/eval/v1/multiturn-development.jsonl /tmp/multiturn-live.json --retrieve
```

第二条需要配置实际搜索和重排服务，比较原问、预测 DST 后改写、金标 DST 后改写和预先编写的参考查询。正式验收按对话数统计，多个轮次不能增加独立样本数。


`multiturn-clarification-development.jsonl` 增加 7 段澄清对话和 26 个用户轮次，覆盖选择政策地区、选择原订单、模糊确认后再次询问、跳转到新问题、同地区及未验证订单等情况。用同一复跑脚本将数据文件替换为该文件即可。结果见 [逐轮回归](results/policy-clarification-2026-11-04.json)。
