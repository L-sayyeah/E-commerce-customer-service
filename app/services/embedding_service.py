from langchain_community.embeddings import DashScopeEmbeddings

from app.core.config import settings


class EmbeddingService:
    def __init__(self):
        self.embeddings = DashScopeEmbeddings(
            model=settings.embedding_model,
            dashscope_api_key=settings.dashscope_api_key,
        )

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self.embeddings.aembed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        return await self.embeddings.aembed_query(text)