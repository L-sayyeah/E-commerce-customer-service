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
from app.services.rerank_service import RerankService

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
        retrieval_top_n = max(settings.rag_retrieval_top_n, top_k)

        try:
            search_results = await self._retrieve_sources(
                query=query,
                top_k=retrieval_top_n
            )

            search_results, rerank_meta = await self._rerank_sources(
                query=query,
                sources=search_results,
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
                status="success",
                rerank_meta=rerank_meta,
                retrieval_mode=settings.rag_retrieval_mode
            )

            logger.info(
                f"RAG answer generated | trace_id: {get_trace_id()} | query: {query} | source_count: {len(search_results)}")
            return {
                "query": query,
                "answer": answer,
                "sources": search_results,
                "retrieval_mode": settings.rag_retrieval_mode
            }
        except Exception as exc:
            await self._save_log(
                query=query,
                top_k=top_k,
                sources=search_results,
                answer=None,
                status="failed",
                rerank_meta = self._build_rerank_meta("disabled"),
                retrieval_mode=settings.rag_retrieval_mode,
                error_message=str(exc)
            )
            raise

    async def stream_answer(self, query: str, top_k: int = 5):
        search_results: list[dict] = []
        rag_log: RagLog | None = None
        answer_parts: list[str] = []
        retrieval_top_n = max(settings.rag_retrieval_top_n, top_k)

        try:
            search_results = await self.knowledge_service.search(
                query=query,
                top_k=retrieval_top_n
            )

            search_results, rerank_meta = await self._rerank_sources(
                query=query,
                sources=search_results,
                top_k=top_k
            )

            context = self._build_context(results=search_results)

            rag_log = await self._save_log(
                query=query,
                top_k=top_k,
                sources=search_results,
                answer=None,
                status="success",
                rerank_meta=rerank_meta,
                retrieval_mode=settings.rag_retrieval_mode
            )

            yield {
                "type": "sources",
                "sources": search_results,
                "retrieval_mode": settings.rag_retrieval_mode
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

            logger.info(
                f"RAG stream answer completed | trace_id: {get_trace_id()} | query: {query} | sources: {len(search_results)}")
        except Exception as exc:
            if rag_log is None:
                await self._save_log(
                    query=query,
                    top_k=top_k,
                    sources=search_results,
                    answer=None,
                    status="failed",
                    retrieval_mode=settings.rag_retrieval_mode,
                    rerank_meta=self._build_rerank_meta("disabled"),
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

    async def _retrieve_sources(self, query: str, top_k: int) -> list[dict]:
        retrieval_mode = settings.rag_retrieval_mode.lower()

        if retrieval_mode == "hybrid":
            return await self.knowledge_service.hybrid_search(
                query=query,
                top_k=top_k,
                vector_weight=settings.hybrid_vector_weight
            )

        return await self.knowledge_service.search(
            query=query,
            top_k=top_k
        )

    async def _rerank_sources(
            self,
            query: str,
            sources: list[dict],
            top_k: int
    ) -> tuple[list[dict], dict]:
        if not settings.rag_rerank_enabled:
            return sources[:top_k], self._build_rerank_meta("disabled")

        try:
            rerank_service = RerankService()
            reranked_sources = await rerank_service.rerank(
                query=query,
                documents=sources,
                top_n=top_k
            )
            return reranked_sources, self._build_rerank_meta("success")
        except Exception as exc:
            logger.warning(f"Rerank failed, fallback to original sources | query={query} | error={exc}")
            return sources[:top_k], self._build_rerank_meta("failed_fallback", error=str(exc))

    async def _save_log(
            self,
            query: str,
            top_k: int,
            sources: list[dict],
            answer: str | None,
            status: str = "success",
            rerank_meta: dict | None = None,
            retrieval_mode: str | None = None,
            error_message: str | None = None
    ):
        rerank_meta = rerank_meta or self._build_rerank_meta("disabled")
        rag_log = RagLog(
            trace_id=get_trace_id(),
            query=query,
            answer=answer,
            sources_json=json.dumps(sources, ensure_ascii=False),
            top_k=top_k,
            model_name=settings.chat_model,
            retrival_mode=retrieval_mode or settings.rag_retrieval_mode,
            status=status,
            error_message=error_message,
            rerank_enabled=rerank_meta["rerank_enabled"],
            rerank_model=rerank_meta["rerank_model"],
            rerank_status=rerank_meta["rerank_status"],
            rerank_error=rerank_meta["rerank_error"],
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

    def _build_rerank_meta(
            self,
            status: str,
            error: str | None = None
    ) -> dict:
        return {
            "rerank_enabled": settings.rag_rerank_enabled,
            "rerank_model": settings.rerank_model if settings.rag_rerank_enabled else None,
            "rerank_status": status,
            "rerank_error": error,
        }
