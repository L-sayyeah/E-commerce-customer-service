"""Replay labelled conversations and optionally compare retrieval-only rewrite arms."""

import argparse
import asyncio
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from app.agents.dialogue_state import (
    DialogueState, POLICY_SCOPE_CONFIRMATION, REGIONS, needs_verified_policy_order,
    pending_policy_question, resolve_policy_scope,
)
from app.agents.nodes import AgentNodes
from app.agents.state import new_turn_state
from app.core.config import Principal, settings
from app.scripts.check_eval_dataset import read_rows


def query_matches(query: str, gold: dict) -> bool:
    normalized = query.replace("澳大利亚", "澳洲")
    regions = set(gold.get("regions", []))
    if gold.get("region"):
        regions.add(gold["region"])
    forbidden = set(gold.get("forbidden_regions", []))
    if regions:
        forbidden.update(set(REGIONS) - regions)
    return (
        all(region in normalized for region in regions)
        and not any(region in normalized for region in forbidden)
        and all(any(term in normalized for term in group) for group in gold.get("required_terms", []))
    )


async def evaluate_dialogue(row: dict, nodes: AgentNodes) -> list[dict]:
    messages = row["inputs"]["messages"]
    labels = {label["message_index"]: label for label in row["gold"]["turns"]}
    user_indices = {index for index, message in enumerate(messages) if message["role"] == "user"}
    if user_indices != labels.keys() or len(labels) != len(row["gold"]["turns"]):
        raise ValueError(f"{row['id']}: every user turn must have exactly one annotation")

    tracker = DialogueState()
    turns = []
    runtime_messages = []
    previous_index = -1
    verified_regions = row["inputs"].get("verified_order_regions", {})
    for index in sorted(user_indices):
        runtime_messages.extend(messages[previous_index + 1:index])
        previous_index = index
        pending_question = pending_policy_question(runtime_messages[-6:])
        message = messages[index]["content"]
        gold = labels[index]
        expected = gold["rewrite"]
        previous_policy_regions = tracker.policy_regions
        dialogue = tracker.for_turn(message)
        verified_region = (
            verified_regions.get(tracker.active_order)
            if needs_verified_policy_order(message, pending_question)
            else None
        )
        dialogue = resolve_policy_scope(
            dialogue, message, previous_policy_regions, verified_region, pending_question,
        )
        runtime_messages.append(messages[index])
        if dialogue.get("clarification_prompt"):
            runtime_messages.append({
                "role": "assistant", "message_type": POLICY_SCOPE_CONFIRMATION,
                "content": dialogue["clarification_prompt"],
            })
        state = new_turn_state(row["id"], "evaluation", message, messages[max(0, index - 6):index], dialogue)
        state.update(await nodes.build_context_node(state))
        await nodes._classify_intent(state)
        effective_query = state.get("retrieval_query") or message
        if state["intent"] == "clarify":
            decision = "clarify"
        elif state["intent"] != "rag_qa":
            decision = "skip"
        elif state.get("retrieval_query"):
            decision = "rewrite"
        else:
            decision = "raw"

        predicted = {**dialogue, "active_order": tracker.active_order}
        slot_results = {slot: predicted.get(slot) == value for slot, value in gold["slots"].items()}
        turn = {
            "case_id": row["id"], "family": row["family"], "turn": index,
            "message": message, "expected_slots": gold["slots"],
            "predicted_slots": {slot: predicted.get(slot) for slot in gold["slots"]},
            "slot_results": slot_results, "jga": all(slot_results.values()),
            "expected_intent": gold["intent"], "intent": state["intent"],
            "expected_decision": expected["decision"], "decision": decision,
            "decision_correct": expected["decision"] == decision,
            "clarification_prompt": dialogue.get("clarification_prompt"),
            "resumed_question": dialogue.get("clarified_question"),
            "query_correct": expected["decision"] == decision and (
                query_matches(effective_query, expected) if decision in {"raw", "rewrite"} else True
            ),
        }
        if expected["decision"] in {"raw", "rewrite"}:
            turn["query"] = effective_query

        if expected["decision"] == "rewrite":
            # Only inject verified gold slots into the same production
            # context-builder. The template may still omit the user's topic.
            gold_dialogue = {**dialogue, **gold["slots"], "region": expected.get("region"), "follow_up": True}
            oracle_state = new_turn_state(
                row["id"], "evaluation", message, messages[max(0, index - 6):index], gold_dialogue,
            )
            context = await nodes.build_context_node(oracle_state)
            oracle_query = context.get("retrieval_query") or message
            turn["oracle_query"] = oracle_query
            turn["oracle_query_correct"] = oracle_query != message and query_matches(oracle_query, expected)

            if expected.get("evidence"):
                turn["retrieval_queries"] = {
                    "raw": message, "predicted_dst": effective_query,
                    "gold_dst": oracle_query, "human_rewrite": expected["human_query"],
                }
                turn["evidence_gold"] = {key: expected[key]
                                         for key in ("evidence", "evidence_groups", "relevance_labels")}
        turns.append(turn)
    return turns


async def compare_retrieval(turns: list[dict]) -> dict:
    from app.scripts.eval_live_rag import score_evidence
    from app.services.knoewledge_service import KnowledgeService
    from app.services.rag_service import RagService

    settings.rag_retrieval_mode = "hybrid"
    settings.rag_hybrid_fusion = "weighted"
    rag = RagService(KnowledgeService(None), None)
    limit = asyncio.Semaphore(4)

    async def retrieve(query):
        async with limit:
            try:
                candidates = await rag._retrieve_sources(query, 20)
                ranked, meta = await rag._rerank_sources(query, candidates, 5)
                return ranked, meta["rerank_status"]
            except Exception as exc:
                return [], type(exc).__name__

    queries = {query for turn in turns for query in turn.get("retrieval_queries", {}).values()}
    outputs = await asyncio.gather(*(retrieve(query) for query in sorted(queries)))
    ranked_by_query = dict(zip(sorted(queries), outputs))
    by_arm = defaultdict(list)
    for turn in turns:
        if not turn.get("retrieval_queries"):
            continue
        metrics = {}
        for name, query in turn["retrieval_queries"].items():
            sources, status = ranked_by_query[query]
            if status not in {"success", "disabled", "failed_fallback"}:
                metrics[name] = {"error": status}
                continue
            scores = score_evidence(turn["evidence_gold"], sources)
            metrics[name] = {field: scores[field] for field in ("recall_at_5", "ndcg_at_5", "complete_evidence")}
            metrics[name]["rerank_status"] = status
            by_arm[name].append(metrics[name])
        turn["retrieval"] = metrics
    return {
        name: {"n": len(rows), **{field: mean(row[field] for row in rows)
                                 for field in ("recall_at_5", "ndcg_at_5", "complete_evidence")}}
        for name, rows in sorted(by_arm.items())
    }


async def main(args):
    rows = [row for _, row in read_rows([args.dataset])]
    if not rows:
        raise SystemExit("No labelled conversations")
    settings.agent_intent_use_llm = False
    nodes = AgentNodes(None, Principal(user_id="evaluation"))
    turns = [turn for row in rows for turn in await evaluate_dialogue(row, nodes)]
    slot_correct = Counter()
    slot_counts = Counter()
    decisions = defaultdict(Counter)
    for turn in turns:
        for slot, correct in turn["slot_results"].items():
            slot_counts[slot] += 1
            slot_correct[slot] += correct
        decisions[turn["expected_decision"]][turn["decision"]] += 1
    rewrites = [turn for turn in turns if turn["expected_decision"] == "rewrite"]
    result = {
        "conversations": len(rows), "turns": len(turns), "intent_mode": "rules",
        "jga_correct": sum(turn["jga"] for turn in turns),
        "intent_correct": sum(turn["intent"] == turn["expected_intent"] for turn in turns),
        "decision_correct": sum(turn["decision_correct"] for turn in turns),
        "decision_confusion": decisions,
        "slot_scores": {slot: {"correct": slot_correct[slot], "n": count} for slot, count in slot_counts.items()},
        "rewrite": {
            "n": len(rewrites),
            "predicted_correct": sum(turn["query_correct"] for turn in rewrites),
            "gold_dst_correct": sum(turn["oracle_query_correct"] for turn in rewrites),
        },
        "retrieval": await compare_retrieval(turns) if args.retrieve else None,
        "cases": turns,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "cases"}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--retrieve", action="store_true", help="Call configured live search and rerank without writing data")
    asyncio.run(main(parser.parse_args()))
