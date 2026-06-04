import httpx
from langchain_community.document_compressors import DashScopeRerank

from app.core.config import settings


class RerankService:
    def __init__(self):
        self.reranker = DashScopeRerank(
            model=settings.rerank_model,
            top_n=settings.rerank_top_n,
            dashscope_api_key=settings.dashscope_api_key,
        )

    async def rerank(self, query: str, documents: list[dict], top_n: int) -> list[dict]:
        if not documents:
            return []

        candidates = documents[:100]
        top_n = min(top_n, len(candidates))

        payload = {
            "model": settings.rerank_model,
            "input": {
                "query": {
                    "text": query
                },
                "documents": [
                    {
                        "text": self._build_document_text(item)
                    }
                    for item in candidates
                ]
            },
            "parameters":{
                "top_n": top_n,
                "return_document": False,
                "instruct": "Given a customer service query, retrieve relevant passages that answer the query."
            }
        }

        headers = {
            "Authorization": f"Bearer {settings.dashscope_api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=50) as client:
            response = await client.post(
                settings.dashscope_rerank_url,
                headers=headers,
                json=payload
            )

        data = response.json()

        if response.status_code >= 400:
            raise RuntimeError(
                "DashScope rerank failed: "
                f"status_code={response.status_code}, "
                f"body={response.text}"
            )

        results = data.get("output", {}).get("results", [])

        reranked = []
        for result in results:
            index = result["index"]
            score = float(result.get("relevance_score") or 0)

            item = dict(candidates[index])
            item["rerank_score"] = score
            reranked.append(item)

        return reranked

    def _build_document_text(self, item: dict) -> str:
        heading_path = item.get("heading_path") or "未分类"
        content = item.get("content") or ""

        return f"标题路径：{heading_path}\n内容：{content}"
