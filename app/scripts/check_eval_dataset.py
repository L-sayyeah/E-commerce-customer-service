"""Validate evaluation JSONL and enforce the held-out sample floor."""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

CATEGORIES = {
    "single_hop", "multi_evidence", "rewrite_dst", "insufficient_evidence",
    "tools", "security", "recovery_idempotency", "judge",
}
MIN_ACCEPTANCE = 101
SPLITS = {"candidate", "development", "calibration", "acceptance"}
METRIC_FIELDS = {
    "context_precision": {"relevance_labels"},
    "context_recall": {"evidence_groups"},
    "faithfulness": {"reference_claims"},
    "answer_relevancy": {"user_goals"},
    "answer_correctness": {"required_facts", "forbidden_claims"},
}
CATEGORY_FIELDS = {
    "single_hop": {"evidence_groups", "required_facts"},
    "multi_evidence": {"evidence_groups", "required_facts"},
    "rewrite_dst": {"slots", "allowed_writes"},
    "insufficient_evidence": {"outcome", "missing", "allowed_writes"},
    "tools": {"allowed_writes", "expected_state", "tool_expectations"},
    "security": {"allowed_writes", "expected_state", "security_assertions"},
    "recovery_idempotency": {"expected_state", "execution_assertions"},
    "judge": {"human_ratings"},
}


def read_rows(paths):
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if line.strip():
                    yield f"{path}:{line_number}", json.loads(line)


def check(rows):
    errors = []
    coverage = defaultdict(Counter)
    metrics = defaultdict(Counter)
    measured = defaultdict(set)
    families = defaultdict(set)
    ids = set()
    inputs_seen = set()
    for location, row in rows:
        if not isinstance(row, dict):
            errors.append(f"{location}: expected an object")
            continue
        case_id = row.get("id")
        split = row.get("split")
        family = row.get("family")
        categories = row.get("categories")
        inputs = row.get("inputs")
        gold = row.get("gold")
        if (
            not isinstance(case_id, str) or not case_id
            or not isinstance(split, str) or split not in SPLITS
            or not isinstance(family, str) or not family
            or not isinstance(categories, list) or not categories
            or any(not isinstance(item, str) or item not in CATEGORIES for item in categories)
            or len(set(categories)) != len(categories)
            or not isinstance(inputs, dict) or not inputs
            or not isinstance(gold, dict) or not gold
        ):
            errors.append(f"{location}: invalid case envelope")
            continue
        fingerprint = json.dumps(inputs, ensure_ascii=False, sort_keys=True)
        if case_id in ids or fingerprint in inputs_seen:
            errors.append(f"{location}: duplicate case id or inputs ({case_id})")
            continue
        ids.add(case_id)
        inputs_seen.add(fingerprint)
        if split != "candidate":
            families[family].add(split)
            reviewed_by = row.get("reviewed_by")
            if split == "acceptance" and (
                row.get("review_kind") != "independent_human"
                or not isinstance(reviewed_by, str)
                or reviewed_by.casefold().startswith(("codex:", "llm:", "auto:"))
            ):
                errors.append(f"{location}: acceptance requires recorded independent human review")
                continue
            if not isinstance(reviewed_by, str) or not reviewed_by.strip():
                errors.append(f"{location}: reviewed_by required outside candidate split")
                continue
        for category in categories:
            if split != "candidate":
                required_fields = (
                    {"expected_ratings"} if category == "judge" and split == "calibration"
                    else CATEGORY_FIELDS[category]
                )
                missing = required_fields - gold.keys()
                if missing:
                    errors.append(f"{location}: {category} missing gold fields {sorted(missing)}")
                    continue
            coverage[split][category] += 1
            if split != "candidate":
                for metric, required in METRIC_FIELDS.items():
                    if all(gold.get(field) for field in required - {"forbidden_claims"}) and (
                        "forbidden_claims" not in required or isinstance(gold.get("forbidden_claims"), list)
                    ):
                        measured[split, metric].add(case_id)

    for family, splits in sorted(families.items()):
        if len(splits) > 1:
            errors.append(f"family {family!r} leaks across {sorted(splits)}")
    for (split, metric), case_ids in measured.items():
        metrics[split][metric] = len(case_ids)
    return errors, coverage, metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("datasets", nargs="+", type=Path)
    parser.add_argument("--require-acceptance", action="store_true")
    args = parser.parse_args()

    try:
        errors, coverage, metrics = check(read_rows(args.datasets))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Cannot read dataset: {exc}\n")

    gaps = {
        name: MIN_ACCEPTANCE - coverage["acceptance"][name]
        for name in sorted(CATEGORIES)
        if coverage["acceptance"][name] < MIN_ACCEPTANCE
    }
    metric_gaps = {
        name: MIN_ACCEPTANCE - metrics["acceptance"][name]
        for name in sorted(METRIC_FIELDS)
        if metrics["acceptance"][name] < MIN_ACCEPTANCE
    }
    print(json.dumps({
        "category_counts": coverage,
        "metric_label_counts": metrics,
        "acceptance_category_gaps": gaps,
        "acceptance_metric_gaps": metric_gaps,
        "errors": errors,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return int(bool(errors or (args.require_acceptance and (gaps or metric_gaps))))


if __name__ == "__main__":
    sys.exit(main())
