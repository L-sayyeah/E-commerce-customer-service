import argparse
import asyncio
import csv
import json
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1"
DATASET_PATH = Path("app/data/eval/rag_eval_dataset.json")
OUTPUT_PATH = Path("app/data/eval/rag_eval_summary.csv")

MODES = {
    "vector": "/knowledge/search",
    "bm25": "/knowledge/bm25-search",
    "hybrid": "/knowledge/hybrid-search",
    "rag": "/knowledge/rag",
}


def unwrap_response(body: dict[str, Any]) -> dict[str, Any]:
    return body.get("data", body)


def get_results(mode: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    if mode == "rag":
        return data.get("sources", []) or []

    return data.get("results", []) or []


def get_content(results: list[dict[str, Any]], top_k: int) -> str:
    return "\n".join(
        str(item.get("content") or "")
        for item in results[:top_k]
    ).lower()


def matched_keywords(
        results: list[dict[str, Any]],
        expected_keywords: list[str],
        top_k: int,
) -> list[str]:
    content = get_content(results, top_k)

    return [
        keyword
        for keyword in expected_keywords
        if keyword.lower() in content
    ]


def is_hit(
        results: list[dict[str, Any]],
        expected_keywords: list[str],
        top_k: int,
        min_match: int = 2,
) -> bool:
    matched = matched_keywords(
        results=results,
        expected_keywords=expected_keywords,
        top_k=top_k,
    )

    required = min(min_match, len(expected_keywords))
    return len(matched) >= required


def first_hit_rank(
        results: list[dict[str, Any]],
        expected_keywords: list[str],
        max_k: int = 5,
) -> int | None:
    for k in range(1, max_k + 1):
        if is_hit(
                results=results,
                expected_keywords=expected_keywords,
                top_k=k,
        ):
            return k

    return None


async def search(
        client: httpx.AsyncClient,
        mode: str,
        question: str,
        top_k: int,
        vector_weight: float,
) -> list[dict[str, Any]]:
    url = BASE_URL + MODES[mode]

    payload = {
        "query": question,
        "top_k": top_k,
    }

    if mode == "hybrid":
        payload["vector_weight"] = vector_weight

    response = await client.post(url, json=payload)
    response.raise_for_status()

    body = response.json()
    data = unwrap_response(body)

    return get_results(mode, data)


async def eval_one_case(
        client: httpx.AsyncClient,
        mode: str,
        item: dict[str, Any],
        top_k: int,
        vector_weight: float,
) -> dict[str, Any]:
    question = item["question"]
    expected_keywords = item.get("expected_keywords", [])

    results = await search(
        client=client,
        mode=mode,
        question=question,
        top_k=top_k,
        vector_weight=vector_weight,
    )

    hit_1 = is_hit(results, expected_keywords, top_k=1)
    hit_3 = is_hit(results, expected_keywords, top_k=3)
    hit_5 = is_hit(results, expected_keywords, top_k=5)

    rank = first_hit_rank(
        results=results,
        expected_keywords=expected_keywords,
        max_k=5
    )

    return {
        "mode": mode,
        "question": question,
        "expected_keywords": expected_keywords,
        "hit@1": hit_1,
        "hit@3": hit_3,
        "hit@5": hit_5,
        "first_hit_rank": rank,
        "matched_keywords": matched_keywords(results, expected_keywords, top_k),
        "top_results": [
            {
                "rank": index + 1,
                "chunk_id": result.get("chunk_id"),
                "document_id": result.get("document_id"),
                "heading_path": result.get("heading_path"),
                "score": result.get("score"),
                "rerank_score": result.get("rerank_score"),
                "vector_score": result.get("vector_score"),
                "bm25_score": result.get("bm25_score"),
                "match_type": result.get("match_type"),
                "content_preview": (result.get("content") or "")[:120],
            }
            for index, result in enumerate(results[:top_k])
        ]
    }


async def eval_mode(
        client: httpx.AsyncClient,
        mode: str,
        dataset: list[dict[str, Any]],
        top_k: int,
        vector_weight: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    details = []

    for index, item in enumerate(dataset, start=1):
        try:
            detail = await eval_one_case(
                client=client,
                mode=mode,
                item=item,
                top_k=top_k,
                vector_weight=vector_weight,
            )
        except Exception as exc:
            detail = {
                "mode": mode,
                "question": item.get("question"),
                "expected_keywords": item.get("expected_keywords", []),
                "hit@1": False,
                "hit@3": False,
                "hit@5": False,
                "first_hit_rank": None,
                "matched_keywords@5": [],
                "top_results": [],
                "error": str(exc),
            }
        details.append(detail)

        print(
            f"[{mode}] "
            f"{index}/{len(dataset)} "
            f"hit@5={detail['hit@5']} "
            f"{detail['question']}"
        )
    total = len(details)

    hit_1 = sum(1 for item in details if item["hit@1"]) / total
    hit_3 = sum(1 for item in details if item["hit@3"]) / total
    hit_5 = sum(1 for item in details if item["hit@5"]) / total

    reciprocal_ranks = [
        0 if item["first_hit_rank"] is None else 1 / item["first_hit_rank"]
        for item in details
    ]

    summary = {
        "mode": mode,
        "total": total,
        "hit@1": hit_1,
        "hit@3": hit_3,
        "hit@5": hit_5,
        "mrr@5": sum(reciprocal_ranks) / total,
    }

    return summary, details


def save_summary(summary_rows: list[dict[str, Any]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "mode",
                "total",
                "hit@1",
                "hit@3",
                "hit@5",
                "mrr@5",
            ],
        )
        writer.writeheader()

        for row in summary_rows:
            writer.writerow(
                {
                    "mode": row["mode"],
                    "total": row["total"],
                    "hit@1": round(row["hit@1"], 4),
                    "hit@3": round(row["hit@3"], 4),
                    "hit@5": round(row["hit@5"], 4),
                    "mrr@5": round(row["mrr@5"], 4),
                }
            )


def save_details(details: list[dict[str, Any]]) -> None:
    detail_path = OUTPUT_PATH.parent / "rag_eval_details.json"
    detail_path.write_text(
        json.dumps(details, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def print_summary(summary_rows: list[dict[str, Any]]) -> None:
    print("\nRAG Evaluation Summary")
    print("-" * 72)
    print(
        f"{'mode':<10}"
        f"{'total':>8}"
        f"{'hit@1':>12}"
        f"{'hit@3':>12}"
        f"{'hit@5':>12}"
        f"{'mrr@5':>12}"
    )
    print("-" * 72)
    for row in summary_rows:
        print(
            f"{row['mode']:<10}"
            f"{row['total']:>8}"
            f"{row['hit@1']:>12.2%}"
            f"{row['hit@3']:>12.2%}"
            f"{row['hit@5']:>12.2%}"
            f"{row['mrr@5']:>12.4f}"
        )


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--vector-weight", type=float, default=0.7)
    parser.add_argument(
        "--modes",
        default="vector,bm25,hybrid,rag",
        help="可选：vector,bm25,hybrid,rag",
    )
    args = parser.parse_args()

    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    modes = [
        mode.strip()
        for mode in args.modes.split(",")
        if mode.strip()
    ]

    summary_rows = []
    all_details = []

    async with httpx.AsyncClient(timeout=60) as client:
        for mode in modes:
            if mode not in MODES:
                raise ValueError(f"Unsupported mode: {mode}")

            summary, details = await eval_mode(
                client=client,
                mode=mode,
                dataset=dataset,
                top_k=args.top_k,
                vector_weight=args.vector_weight,
            )

            summary_rows.append(summary)
            all_details.extend(details)

    print_summary(summary_rows)
    save_summary(summary_rows)
    save_details(all_details)

    print(f"\nSummary saved to: {OUTPUT_PATH}")
    print(f"Details saved to: {OUTPUT_PATH.parent / 'rag_eval_details.json'}")


if __name__ == "__main__":
    asyncio.run(main())
