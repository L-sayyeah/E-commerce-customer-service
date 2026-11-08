import math
from urllib.parse import urlsplit

import httpx

from app.core.config import settings


class RerankService:
    async def rerank(self, query: str, documents: list[dict], top_n: int) -> list[dict]:
        if not documents:
            return []

        candidates = documents[:100]
        top_n = min(top_n, len(candidates))
        if top_n < 1:
            raise ValueError("Rerank top_n must be positive")

        endpoint = settings.rerank_endpoint or settings.dashscope_rerank_url
        api_key = settings.rerank_api_key
        if not api_key and not settings.rerank_endpoint:
            api_key = settings.dashscope_api_key
        if not api_key and settings.rerank_endpoint and settings.embedding_endpoint:
            rerank_url = urlsplit(endpoint)
            embedding_url = urlsplit(settings.embedding_endpoint)
            if (rerank_url.scheme, rerank_url.hostname, rerank_url.port) == (
                embedding_url.scheme, embedding_url.hostname, embedding_url.port
            ):
                api_key = settings.embedding_api_key
        if not api_key:
            raise ValueError("Configure RERANK_API_KEY or a matching workspace EMBEDDING_API_KEY")

        payload = {
            "model": settings.rerank_model,
            "input": {
                "query": query,
                "documents": [
                    self._build_document_text(item)
                    for item in candidates
                ]
            },
            "parameters":{
                "top_n": top_n,
                "instruct": "Given a customer service query, retrieve relevant passages that answer the query."
            }
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=50) as client:
            response = await client.post(
                endpoint,
                headers=headers,
                json=payload
            )

        if response.is_error:
            raise RuntimeError(f"Rerank API returned HTTP {response.status_code}")
        try:
            results = response.json()["output"]["results"]
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("Rerank API returned an invalid response") from exc
        if not isinstance(results, list) or not 0 < len(results) <= top_n:
            raise RuntimeError("Rerank API returned an invalid result count")

        reranked = []
        seen = set()
        for result in results:
            if not isinstance(result, dict):
                raise RuntimeError("Rerank API returned an invalid result item")
            index = result.get("index")
            if type(index) is not int or not 0 <= index < len(candidates) or index in seen:
                raise RuntimeError("Rerank API returned invalid or duplicate document indices")
            seen.add(index)
            try:
                score = float(result["relevance_score"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError("Rerank API returned an invalid relevance score") from exc
            if not math.isfinite(score):
                raise RuntimeError("Rerank API returned a non-finite relevance score")

            item = dict(candidates[index])
            item["rerank_score"] = score
            reranked.append(item)

        return reranked

    def _build_document_text(self, item: dict) -> str:
        heading_path = item.get("heading_path") or "未分类"
        content = item.get("content") or ""

        return f"标题路径：{heading_path}\n内容：{content}"
