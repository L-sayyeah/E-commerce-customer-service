import argparse
import asyncio
import json
import sys
import types
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_openai import ChatOpenAI


def patch_ragas_langchain_community_compatibility() -> None:
    """Patch old imports used by ragas 0.4.x with langchain-community 0.4.x.

    ragas 0.4.3 imports:
        langchain_community.chat_models.vertexai.ChatVertexAI

    Newer LangChain moved VertexAI integrations to langchain-google-vertexai.
    This shim keeps ragas importable without downgrading your whole LangChain stack.
    """
    module_name = "langchain_community.chat_models.vertexai"

    if module_name in sys.modules:
        return

    try:
        from langchain_google_vertexai import ChatVertexAI
    except ImportError:
        class ChatVertexAI:  # type: ignore[no-redef]
            pass

    shim = types.ModuleType(module_name)
    shim.ChatVertexAI = ChatVertexAI
    sys.modules[module_name] = shim


patch_ragas_langchain_community_compatibility()

from ragas import EvaluationDataset, evaluate
from ragas.metrics import (
    Faithfulness,
    LLMContextPrecisionWithReference,
    LLMContextRecall,
    ResponseRelevancy,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings  # noqa: E402

BASE_URL = "http://127.0.0.1:8000/api/v1"
DATASET_PATH = PROJECT_ROOT / "app/data/eval/rag_eval_dataset.json"
OUTPUT_DIR = PROJECT_ROOT / "app/data/eval"


async def call_rag_api(
    client: httpx.AsyncClient,
    question: str,
    top_k: int,
) -> dict[str, Any]:
    response = await client.post(
        f"{BASE_URL}/knowledge/rag",
        json={
            "query": question,
            "top_k": top_k,
        },
    )
    response.raise_for_status()
    body = response.json()
    return body["data"]


async def build_ragas_dataset(
    dataset_path: Path,
    top_k: int,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    raw_cases = json.loads(dataset_path.read_text(encoding="utf-8"))

    if limit:
        raw_cases = raw_cases[:limit]

    ragas_rows = []

    async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
        for index, item in enumerate(raw_cases, start=1):
            question = item["question"]
            reference = item["reference"]

            print(f"[{index}/{len(raw_cases)}] calling RAG: {question}")

            try:
                rag_result = await call_rag_api(
                    client=client,
                    question=question,
                    top_k=top_k,
                )

                answer = rag_result.get("answer") or ""
                print(f"[{index}/{len(raw_cases)}] answer: {answer}")
                sources = rag_result.get("sources") or []
                print(f"[{index}/{len(raw_cases)}] sources: {sources}")
                print("-" * 20)
                contexts = [
                    source.get("content") or ""
                    for source in sources
                    if source.get("content")
                ]

                ragas_rows.append(
                    {
                        "user_input": question,
                        "response": answer,
                        "retrieved_contexts": contexts,
                        "reference": reference,
                    }
                )

                print(f"[{index}/{len(raw_cases)}] collected contexts={len(contexts)}")
            except Exception as exc:
                print(f"[failed] {question}: {exc}")

    return ragas_rows


def build_evaluator_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,
    )


def build_evaluator_embeddings() -> DashScopeEmbeddings:
    return DashScopeEmbeddings(
        model=settings.embedding_model,
        dashscope_api_key=settings.dashscope_api_key,
    )


def run_ragas_eval(rows: list[dict[str, Any]]):
    evaluation_dataset = EvaluationDataset.from_list(rows)

    evaluator_llm = build_evaluator_llm()
    evaluator_embeddings = build_evaluator_embeddings()

    metrics = [
        Faithfulness(),
        ResponseRelevancy(),
        LLMContextPrecisionWithReference(),
        LLMContextRecall(),
    ]
    result = evaluate(
        dataset=evaluation_dataset,
        metrics=metrics,
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
        raise_exceptions=False,
        show_progress=True,
    )
    print(result)

    return result


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = await build_ragas_dataset(
        dataset_path=DATASET_PATH,
        top_k=args.top_k,
        limit=args.limit,
    )

    if not rows:
        raise RuntimeError("No valid RAG samples collected.")

    input_path = OUTPUT_DIR / "ragas_input_dataset.json"
    input_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = run_ragas_eval(rows)

    print("\nRagas result:")
    print(result)

    result_df = result.to_pandas()

    detail_path = OUTPUT_DIR / "ragas_eval_details.csv"
    result_df.to_csv(detail_path, index=False, encoding="utf-8-sig")

    summary = result_df.mean(numeric_only=True).to_frame("score")
    summary_path = OUTPUT_DIR / "ragas_eval_summary.csv"
    summary.to_csv(summary_path, encoding="utf-8-sig")

    print(f"\nSaved input dataset: {input_path}")
    print(f"Saved details: {detail_path}")
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    data = asyncio.run(build_ragas_dataset(DATASET_PATH, top_k=5, limit=20))
    eval_result = run_ragas_eval(data)
    with open("hybrid_with_rerank.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open("eval_hybrid_with_rerank.json", "w", encoding="utf-8") as f:
        f.write(eval_result)
