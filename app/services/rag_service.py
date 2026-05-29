import logging
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.services.knoewledge_service import KnowledgeService

logger = logging.getLogger(__name__)


class RagService:
    def __init__(self, knowledge_service: KnowledgeService):
        self.knowledge_service = knowledge_service
        self.llm = ChatOpenAI(
            model=settings.chat_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature
        )

    async def answer(self, query: str, top_k: int = 5) -> dict:
        search_results = await self.knowledge_service.search(
            query=query,
            top_k=top_k
        )

        context = self._build_context(results=search_results)
        prompt = self._build_prompt(query=query, context=context)

        response = await self.llm.ainvoke(prompt)
        answer = response.content

        logger.info(f"RAG answer generated | query: {query} | source_count: {len(search_results)}")

        return {
            "query": query,
            "answer": answer,
            "sources": search_results
        }

    def _build_context(self, results: list[dict]) -> str:
        if not results:
            return "暂无可用知识库内容"

        blocks = []
        for index, item in enumerate(results, start=1):
            heading = item.get("heading_path") or "未分类"
            content = item.get("content") or ""
            blocks.append(
                f"来源{index}\n"
                f"标题路径：{heading}\n"
                f"内容：{content}\n"
            )
        return "\n\n".join(blocks)

    def _build_prompt(self, query: str, context: str) -> list[dict]:
        return [
            {
                "role": "system",
                "content": (
                    "你是跨境电商售后客服 Agent。"
                    "请只基于提供的知识库上下文回答用户问题。"
                    "如果上下文不足以回答，请明确说明需要进一步确认，不要编造政策。"
                    "回答要简洁、礼貌、可执行。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"用户问题：{query}\n\n"
                    f"知识库上下文：\n{context}\n\n"
                    "请给出客服回复。"
                ),
            },
        ]
