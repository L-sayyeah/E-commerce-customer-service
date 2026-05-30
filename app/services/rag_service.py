import json
import logging

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.request_context import get_trace_id
from app.models.rag_log import RagLog
from app.services.knoewledge_service import KnowledgeService

logger = logging.getLogger(__name__)


class RagService:
    def __init__(self, knowledge_service: KnowledgeService, db: AsyncSession):
        self.knowledge_service = knowledge_service
        self.db = db
        self.llm = ChatOpenAI(
            model=settings.chat_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature
        )
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "你是跨境电商售后客服 Agent。"
                           "请只基于提供的知识库上下文回答用户问题。"
                           "如果上下文不足以回答，请明确说明需要进一步确认，不要编造政策。"
                           "回答要简洁、礼貌、可执行。"),
                ("human", "用户问题：{query}\n\n"
                          "知识库上下文：\n{context}\n\n"
                          "请给出客服回复。")
            ]
        )
        self.chain = self.prompt | self.llm | StrOutputParser()

    async def answer(self, query: str, top_k: int = 5) -> dict:
        search_results: list[dict] = []

        try:
            search_results = await self.knowledge_service.search(
                query=query,
                top_k=top_k
            )

            context = self._build_context(results=search_results)

            answer = await self.chain.ainvoke(
                {
                    "query": query,
                    "context": context
                }
            )

            await self._save_log(
                query=query,
                top_k=top_k,
                sources=search_results,
                answer=answer,
                status="success"
            )

            logger.info(f"RAG answer generated | trace_id: {get_trace_id()} | query: {query} | source_count: {len(search_results)}")
            return {
                "query": query,
                "answer": answer,
                "sources": search_results
            }
        except Exception as exc:
            await self._save_log(
                query=query,
                top_k=top_k,
                sources=search_results,
                answer=None,
                status="failed",
                error_message=str(exc)
            )
            raise

    async def stream_answer(self, query: str, top_k: int = 5):
        search_results: list[dict] = []
        rag_log: RagLog | None = None
        answer_parts: list[str] = []

        try:
            search_results = await self.knowledge_service.search(
                query=query,
                top_k=top_k
            )

            context = self._build_context(results=search_results)

            rag_log = await self._save_log(
                query=query,
                top_k=top_k,
                sources=search_results,
                answer=None,
                status="success"
            )

            yield {
                "type": "sources",
                "sources": search_results
            }

            async for chunk in self.chain.astream({"query": query, "context": context}):
                if chunk:
                    answer_parts.append(chunk)
                    yield {
                        "type": "token",
                        "content": chunk
                    }
            final_answer = "".join(answer_parts)

            if rag_log is not None:
                await self._update_log_answer(
                    rag_log=rag_log,
                    answer=final_answer,
                    status="success"
                )

            yield {
                "type": "done"
            }

            logger.info(f"RAG stream answer completed | trace_id: {get_trace_id()} | query: {query} | sources: {len(search_results)}")
        except Exception as exc:
            if rag_log is None:
                await self._save_log(
                    query=query,
                    top_k=top_k,
                    sources=search_results,
                    answer=None,
                    status="failed",
                    error_message=str(exc)
                )
            else:
                await self._update_log_answer(
                    rag_log=rag_log,
                    answer="".join(answer_parts) or None,
                    status="failed",
                    error_message=str(exc)
                )
            raise


    def _build_context(self, results: list[dict]) -> str:
        if not results:
            return "暂无可用知识库内容"

        blocks = []
        for index, item in enumerate(results, start=1):
            heading = item.get("heading_path") or "未分类"
            content = item.get("content") or ""
            score = item.get("score")

            blocks.append(
                f"来源{index}\n"
                f"标题路径：{heading}\n"
                f"相关分数：{score}\n"
                f"内容：{content}\n"
            )
        return "\n\n".join(blocks)

    async def _save_log(
            self,
            query: str,
            top_k: int,
            sources: list[dict],
            answer: str | None,
            status: str = "success",
            error_message: str | None = None
    ):
        rag_log = RagLog(
            trace_id=get_trace_id(),
            query=query,
            answer=answer,
            sources_json=json.dumps(sources, ensure_ascii=False),
            top_k=top_k,
            model_name=settings.chat_model,
            status=status,
            error_message=error_message
        )

        self.db.add(rag_log)
        await self.db.commit()
        await self.db.refresh(rag_log)

        return rag_log

    async def _update_log_answer(
            self,
            rag_log: RagLog,
            answer: str | None,
            status: str = "success",
            error_message: str | None = None
    ) -> None:
        rag_log.answer = answer
        rag_log.status = status
        rag_log.error_message = error_message

        await self.db.commit()
