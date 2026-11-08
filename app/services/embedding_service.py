import math

import httpx
from langchain_community.embeddings import DashScopeEmbeddings

from app.core.config import settings


class EmbeddingService:
    def __init__(self):
        self.embeddings = None
        if not settings.embedding_endpoint:
            self.embeddings = DashScopeEmbeddings(
                model=settings.embedding_model,
                dashscope_api_key=settings.dashscope_api_key,
            )

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if settings.embedding_endpoint:
            return await self._embed_compatible(texts)
        return await self.embeddings.aembed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        if settings.embedding_endpoint:
            return (await self._embed_compatible([text]))[0]
        return await self.embeddings.aembed_query(text)

    async def _embed_compatible(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Embedding inputs must be non-empty strings")
        if not settings.embedding_api_key:
            raise ValueError("EMBEDDING_API_KEY is required for EMBEDDING_ENDPOINT")

        vectors: list[list[float]] = []
        headers = {"Authorization": f"Bearer {settings.embedding_api_key}"}
        async with httpx.AsyncClient(timeout=60) as client:
            for start in range(0, len(texts), settings.embedding_batch_size):
                batch = texts[start:start + settings.embedding_batch_size]
                response = await client.post(
                    settings.embedding_endpoint,
                    headers=headers,
                    json={
                        "model": settings.embedding_model,
                        "input": batch,
                        "dimensions": settings.embedding_dimensions,
                        "encoding_format": "float",
                    },
                )
                if response.is_error:
                    raise RuntimeError(f"Embedding API returned HTTP {response.status_code}")
                try:
                    data = response.json()["data"]
                except (ValueError, KeyError, TypeError) as exc:
                    raise RuntimeError("Embedding API returned an invalid response") from exc
                vectors.extend(self._decode_batch(data, len(batch)))
        return vectors

    def _decode_batch(self, data: list, count: int) -> list[list[float]]:
        if not isinstance(data, list) or len(data) != count:
            raise RuntimeError("Embedding response count does not match input count")
        ordered: dict[int, list[float]] = {}
        for item in data:
            if not isinstance(item, dict):
                raise RuntimeError("Embedding response contains an invalid item")
            index = item.get("index")
            if type(index) is not int or not 0 <= index < count or index in ordered:
                raise RuntimeError("Embedding response contains invalid or duplicate indices")
            vector = item.get("embedding")
            if not isinstance(vector, list) or len(vector) != settings.embedding_dimensions:
                raise RuntimeError("Embedding vector dimensions do not match EMBEDDING_DIMENSIONS")
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in vector
            ):
                raise RuntimeError("Embedding response contains non-finite or non-numeric values")
            ordered[index] = [float(value) for value in vector]
        return [ordered[index] for index in range(count)]
