import hashlib
import json
import re
from uuid import uuid4

import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeDocument, KnowledgeChunk
from app.schemas.knowledge import CreateKnowledgeDocumentRequest
from app.services.elasticsearch_service import ElasticsearchService
from app.services.embedding_service import EmbeddingService
from app.services.milvus_service import MilvusService

logger = logging.getLogger(__name__)


class KnowledgeService:
    max_chunk_chars = 800
    chunk_overlap_chars = 100

    split_separators = ["\n\n", "\n", "。", "！", "？", "；", "，", " "]

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_document(self, request: CreateKnowledgeDocumentRequest) -> tuple[KnowledgeDocument, list[KnowledgeChunk]]:
        # 生成document_id
        document_id = f"DOC{uuid4().hex[:16].upper()}"
        # 计算content_hash值
        content_hash = hashlib.sha256(request.content.encode("utf-8")).hexdigest()

        document = KnowledgeDocument(
            document_id=document_id,
            title=request.title,
            source_type=request.source_type,
            source_uri=request.source_uri,
            status="active",
            version=1,
            content_hash=content_hash
        )
        # 保存knowledge_documents
        self.db.add(document)
        await self.db.flush()

        # 把原文切成多个 chunk
        chunk_payloads = self._split_markdown_with_fallback(request.content)

        chunks: list[KnowledgeChunk] = []
        for index, payload in enumerate(chunk_payloads):
            chunk = KnowledgeChunk(
                chunk_id=f"CHK{uuid4().hex[:16].upper()}",
                document_id=document.document_id,
                chunk_index=index,
                content=payload["content"],
                heading_path=payload.get("heading_path"),
                token_count=self._estimate_token_count(payload["content"]),
                metadata_json=json.dumps(
                    {
                        "title": request.title,
                        "source_type": request.source_type,
                        "heading_path": payload.get("heading_path"),
                    },
                    ensure_ascii=False,
                ),
                status="active",
            )
            self.db.add(chunk)
            chunks.append(chunk)

        if chunks:
            embedding_service = EmbeddingService()
            milvus_service = MilvusService()

            texts = [chunk.content for chunk in chunks]
            embeddings = await embedding_service.embed_documents(texts)

            milvus_payloads = []
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                milvus_payloads.append({
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "heading_path": chunk.heading_path,
                    "content": chunk.content,
                    "embedding": embedding
                })
            milvus_vector_ids = milvus_service.insert_chunks(milvus_payloads)
            for chunk, vector_id in zip(chunks, milvus_vector_ids, strict=True):
                chunk.milvus_vector_id = vector_id

            elasticsearch_service = ElasticsearchService()
            try:
                await elasticsearch_service.index_chunks(
                    [
                        {
                            "chunk_id": chunk.chunk_id,
                            "document_id": chunk.document_id,
                            "heading_path": chunk.heading_path,
                            "content": chunk.content,
                            "status": chunk.status,
                        }
                        for chunk in chunks
                    ]
                )
            finally:
                await elasticsearch_service.close()

        await self.db.commit()
        await self.db.refresh(document)

        for chunk in chunks:
            await self.db.refresh(chunk)

        logger.info(f"Created knowledge document | document_id={document.document_id} | chunk_count = {len(chunks)}")

        return document, chunks

    # 把原文档切成多个chunk
    def _split_markdown_with_fallback(self, content: str) -> list[dict]:
        sections = self._split_by_markdown_headings(content)

        chunks: list[dict] = []
        for section in sections:
            section_content = section["content"].strip()
            if not section_content:
                continue

            heading_path = section.get("heading_path")
            split_contents = self._recursive_split(section_content)

            for split_content in split_contents:
                chunks.append(
                    {
                        "heading_path": heading_path,
                        "content": split_content.strip(),
                    }
                )

        return chunks

    # 按Markdown标题切成section
    def _split_by_markdown_headings(self, content: str) -> list[dict]:
        # 1.将内容按行分割
        lines = content.splitlines()
        sections: list[dict] = []

        # 2.维护标题栈（记录当前层级的标题路径）
        heading_stack: list[tuple[int, str]] = []
        current_lines: list[str] = []
        current_heading_path: str | None = None

        # 3. 匹配 Markdown 标题的正则表达式（# 开头，最多6级）
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$")

        # 4. 内部函数：将当前累积的内容刷新为一个 section
        def flush_current() -> None:
            nonlocal current_lines, current_heading_path
            text = "\n".join(current_lines).strip()
            if text:
                sections.append(
                    {
                        "heading_path": current_heading_path,
                        "content": text
                    }
                )
            current_lines = []

        # 5. 遍历每一行
        for line in lines:
            match = heading_pattern.match(line.strip())

            if match:
                # 遇到标题行：先刷新之前的内容
                flush_current()

                # 解析标题行：提取标题层级和标题内容
                level = len(match.group(1))  # 标题层级
                title = match.group(2).strip()  # 标题内容

                heading_stack[:] = [
                    (item_level, item_title)
                    for item_level, item_title in heading_stack
                    if item_level < level
                ]
                heading_stack.append((level, title))

                current_heading_path = ">".join(
                    item_title for _, item_title in heading_stack
                )
                current_lines.append(line)
            else:
                current_lines.append(line)

        flush_current()

        if not sections and content.strip():
            sections.append(
                {
                    "heading_path": None,
                    "content": content.strip()
                }
            )
        return sections

    # 如果内容不超过max_chunk_chars，则直接返回一个chunk，否则按分隔符切分
    def _recursive_split(self, text: str) -> list[str]:
        if len(text) <= self.max_chunk_chars:
            return [text]
        return self._split_by_separators(text, self.split_separators)

    # 内容太长，尝试用分隔符切分
    def _split_by_separators(self, text: str, separators: list[str]) -> list[str]:
        if len(text) <= self.max_chunk_chars:
            return [text]

        # 尝试用分隔符切分，按窗口硬切
        if not separators:
            return self._split_by_window(text)

        separator = separators[0]
        parts = text.split(separator)

        if len(parts) == 1:
            return self._split_by_separators(text, separators[1:])

        chunks: list[str] = []
        current = ""

        for part in parts:
            candidate = part if not current else current + separator + part

            if len(candidate) <= self.max_chunk_chars:
                current = candidate
            else:
                if current:
                    chunks.extend(self._split_by_separators(current, separators[1:]))
                current = part

        if current:
            chunks.extend(self._split_by_separators(current, separators[1:]))

        return self._add_overlap(chunks)

    # 文字没有换行、没有标点、没有空格，按窗口硬切
    def _split_by_window(self, text: str) -> list[str]:
        chunks: list[str] = []
        start = 0

        while start < len(text):
            end = start + self.max_chunk_chars
            chunks.append(text[start:end])
            start = end

        return chunks

    # 添加重叠上下文
    def _add_overlap(self, chunks: list[str]) -> list[str]:
        if self.chunk_overlap_chars <= 0 or len(chunks) <= 1:
            return chunks

        overlapped: list[str] = []

        for index, chunk in enumerate(chunks):
            if index == 0:
                overlapped.append(chunk)
                continue

            previous = chunks[index - 1]
            overlap = previous[-self.chunk_overlap_chars:]
            overlapped.append((overlap + chunk).strip())

        return overlapped

        # 估计 token 数量

    def _estimate_token_count(self, text: str) -> int:
        return max(1, len(text) // 4)

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        embedding_service = EmbeddingService()
        milvus_service = MilvusService()

        query_embedding = await embedding_service.embed_query(query)
        results = milvus_service.search(query_embedding, top_k)

        logger.info(f"Knowledge search completed | query={query} | top_k={top_k} | result_count={len(results)}")
        return results

    async def bm25_search(self, query: str, top_k: int = 5) -> list[dict]:
        elasticsearch_service = ElasticsearchService()
        try:
            results = await elasticsearch_service.search_chunks(query=query, top_k=top_k)
        finally:
            await elasticsearch_service.close()

        logger.info(f"BM25 search completed | query={query} | top_k={top_k} | result_count={len(results)}")

        return results

    async def hybrid_search(self, query: str, top_k: int = 5, vector_weight: float = 0.7) -> list[dict]:
        bm25_weight = 1 - vector_weight

        vector_results = await self.search(query=query, top_k=top_k)
        bm25_results = await self.bm25_search(query=query, top_k=top_k)

        max_bm25_score = max([item["score"] for item in bm25_results], default=0)

        merged: dict[str, dict] = {}

        for item in vector_results:
            chunk_id = item["chunk_id"]
            vector_score = max(0.0, min(1.0, float(item["score"] or 0)))

            merged[chunk_id] = {
                "chunk_id": chunk_id,
                "document_id": item["document_id"],
                "heading_path": item.get("heading_path"),
                "content": item["content"],
                "vector_score": vector_score,
                "bm25_score": 0.0,
                "match_type": "vector",
            }

        for item in bm25_results:
            chunk_id = item["chunk_id"]
            bm25_score = float(item["score"] or 0)

            if max_bm25_score > 0:
                bm25_score = bm25_score / max_bm25_score
            else:
                bm25_score = 0.0

            if chunk_id in merged:
                merged[chunk_id]["bm25_score"] = bm25_score
                merged[chunk_id]["match_type"] = "hybrid"
            else:
                merged[chunk_id] = {
                    "chunk_id": chunk_id,
                    "document_id": item["document_id"],
                    "heading_path": item.get("heading_path"),
                    "content": item["content"],
                    "vector_score": 0.0,
                    "bm25_score": bm25_score,
                    "match_type": "bm25",
                }

        results = []
        for item in merged.values():
            final_score = item["vector_score"] * vector_weight + item["bm25_score"] * bm25_weight
            item["score"] = final_score
            results.append(item)

        results.sort(key=lambda item: item["score"], reverse=True)

        logger.info(f"Hybrid search completed | query={query} | top_k={top_k}"
                    f" | vector_result_count={len(vector_results)}"
                    f" | bm25_result_count={len(bm25_results)}"
                    f" | result_count={len(results)}")

        return results[:top_k]
