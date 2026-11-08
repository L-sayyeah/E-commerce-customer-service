"""Score ranked evidence IDs against reviewed policy evidence groups."""

import argparse
import json
import math
from pathlib import Path
from statistics import mean

from app.scripts.check_eval_dataset import read_rows


def score_case(gold, ranked_ids, k):
    ranked = list(dict.fromkeys(ranked_ids))[:k]
    labels = gold["relevance_labels"]
    groups = gold["evidence_groups"]
    relevant = {item for item, grade in labels.items() if grade > 0}
    ranks = [rank for rank, item in enumerate(ranked, 1) if item in relevant]
    covered = sum(bool(set(group).intersection(ranked)) for group in groups)
    gain = sum((2 ** labels.get(item, 0) - 1) / math.log2(rank + 1)
               for rank, item in enumerate(ranked, 1))
    ideal = sum((2 ** grade - 1) / math.log2(rank + 1)
                for rank, grade in enumerate(sorted(labels.values(), reverse=True)[:k], 1))
    return {
        "precision_at_k": len(ranks) / k,
        "recall_at_k": len(ranks) / len(relevant),
        "ndcg_at_k": gain / ideal,
        "mrr_at_k": 1 / ranks[0] if ranks else 0,
        "context_recall": covered / len(groups),
        "complete_evidence": int(covered == len(groups)),
        "unjudged_returned": sum(item not in labels for item in ranked),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("run", type=Path, help="JSONL with id and ranked_evidence_ids")
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args()
    if args.k < 1:
        parser.error("--k must be positive")

    gold = {
        row["id"]: row["gold"] for _, row in read_rows([args.dataset])
        if row["split"] != "candidate"
        and row["gold"].get("evidence_groups")
        and any(grade > 0 for grade in row["gold"].get("relevance_labels", {}).values())
    }
    runs = {}
    for location, row in read_rows([args.run]):
        case_id = row.get("id")
        ranked = row.get("ranked_evidence_ids")
        if (case_id not in gold or case_id in runs or not isinstance(ranked, list)
                or any(not isinstance(item, str) or not item for item in ranked)):
            parser.error(f"{location}: invalid, duplicate or unscorable run record")
        runs[case_id] = ranked
    if not gold or gold.keys() != runs.keys():
        parser.error(f"incomplete run: {len(gold.keys() - runs.keys())} missing predictions")

    scores = {case_id: score_case(labels, runs[case_id], args.k)
              for case_id, labels in gold.items()}
    summary = {metric: mean(score[metric] for score in scores.values())
               for metric in next(iter(scores.values()))}
    print(json.dumps({"k": args.k, "count": len(scores), "summary": summary, "cases": scores},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
