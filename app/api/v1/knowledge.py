import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.response import ApiResponse, success_response
from app.models.document_parse_task import DocumentParseTask
from app.schemas.document_parse_task import DocumentParseTaskResponse, CreateDocumentParseTaskRequest
from app.schemas.knowledge import KnowledgeDocumentResponse, CreateKnowledgeDocumentRequest, KnowledgeChunkResponse, \
    KnowledgeSearchResponse, KnowledgeSearchRequest, KnowledgeSearchResult, RagAnswerResponse, RagQueryRequest, \
    RagSource, KnowledgeBm25SearchResponse, KnowledgeBm25SearchRequest, KnowledgeBm25SearchResult, \
    KnowledgeHybridSearchResponse, KnowledgeHybridSearchRequest, KnowledgeHybridSearchResult, KnowledgeDocumentListItem, \
    KnowledgeDocumentDetailResponse
from app.services.elasticsearch_service import ElasticsearchService
from app.services.knoewledge_service import KnowledgeService
from app.services.milvus_service import MilvusService
from app.services.mineru_service import MinerUService
from app.services.rag_service import RagService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def build_parse_task_response(task: DocumentParseTask) -> DocumentParseTaskResponse:
    return DocumentParseTaskResponse(
        task_id=task.task_id,
        file_name=task.file_name,
        file_url=task.file_url,
        parse_engine=task.parse_engine,
        model_version=task.model_version,
        language=task.language,
        status=task.status,
        full_zip_url=task.full_zip_url,
        document_id=task.document_id,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


# 创建知识文档
@router.post("/documents", response_model=ApiResponse[KnowledgeDocumentResponse])
async def create_knowledge_document(request: CreateKnowledgeDocumentRequest, db: AsyncSession = Depends(get_db)):
    service = KnowledgeService(db)
    document, chunks = await service.create_document(request)

    data = KnowledgeDocumentResponse(
        document_id=document.document_id,
        title=document.title,
        source_type=document.source_type,
        source_uri=document.source_uri,
        status=document.status,
        index_status=document.index_status,
        index_error=document.index_error,
        version=document.version,
        chunk_count=len(chunks),
        created_at=document.created_at,
        chunks=[
            KnowledgeChunkResponse(
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                heading_path=chunk.heading_path,
                content=chunk.content,
                token_count=chunk.token_count,
                milvus_vector_id=chunk.milvus_vector_id
            )
            for chunk in chunks
        ],
    )

    return success_response(data)


# 检查向量库健康状态
@router.get("/vector-store/health", response_model=ApiResponse[dict])
async def vector_store_health():
    service = MilvusService()
    result = service.health_check()
    return success_response(result)


# 初始化向量库
@router.post("/vector-store/init", response_model=ApiResponse[dict])
async def init_vector_store():
    service = MilvusService()
    result = service.init_collection()
    return success_response(result)


# 搜索知识文档
@router.post("/search", response_model=ApiResponse[KnowledgeSearchResponse])
async def search_knowledge(request: KnowledgeSearchRequest, db: AsyncSession = Depends(get_db)):
    service = KnowledgeService(db)
    results = await service.search(query=request.query, top_k=request.top_k)

    data = KnowledgeSearchResponse(
        query=request.query,
        results=[
            KnowledgeSearchResult(
                chunk_id=item["chunk_id"],
                document_id=item["document_id"],
                heading_path=item["heading_path"],
                content=item["content"],
                score=item["score"]
            )
            for item in results
        ]
    )

    return success_response(data)


@router.post("/rag", response_model=ApiResponse[RagAnswerResponse])
async def rag_answer(request: RagQueryRequest, db: AsyncSession = Depends(get_db)):
    knowledge_service = KnowledgeService(db)
    rag_service = RagService(knowledge_service, db)

    result = await rag_service.answer(
        query=request.query,
        top_k=request.top_k,
    )

    data = RagAnswerResponse(
        query=result["query"],
        answer=result["answer"],
        sources=[
            RagSource(
                chunk_id=item["chunk_id"],
                document_id=item["document_id"],
                heading_path=item["heading_path"],
                content=item["content"],
                score=item["score"],
                rerank_score=item.get("rerank_score"),
                vector_score=item["vector_score"],
                bm25_score=item["bm25_score"],
                match_type=item["match_type"]
            )
            for item in result["sources"]
        ],
        retrieval_mode=result["retrieval_mode"]
    )

    return success_response(data)


@router.post("/rag/stream")
async def rag_answer_stream(request: RagQueryRequest, db: AsyncSession = Depends(get_db)):
    knowledge_service = KnowledgeService(db)
    rag_service = RagService(knowledge_service, db)

    async def event_generator():
        async for event in rag_service.stream_answer(query=request.query, top_k=request.top_k):
            event_type = event["type"]

            if event_type == "sources":
                yield {
                    "event": event_type,
                    "data": json.dumps(
                        {
                            "sources": event["sources"],
                            "retrieval_mode": event.get("retrieval_mode")
                        },
                        ensure_ascii=False
                    )
                }
            elif event_type == "token":
                yield {
                    "event": event_type,
                    "data": json.dumps(
                        {
                            "content": event["content"]
                        },
                        ensure_ascii=False
                    )
                }
            elif event_type == "done":
                yield {
                    "event": event_type,
                    "data": json.dumps(
                        {
                            "message": "done"
                        },
                        ensure_ascii=False
                    )
                }

    return EventSourceResponse(event_generator())


@router.get("/search-engine/health", response_model=ApiResponse[dict])
async def search_engine_health():
    service = ElasticsearchService()

    try:
        result = await service.init_index()
    finally:
        await service.close()

    return success_response(result)


@router.post("/bm25-search", response_model=ApiResponse[KnowledgeBm25SearchResponse])
async def bm25_search_knowledge(request: KnowledgeBm25SearchRequest, db: AsyncSession = Depends(get_db)):
    service = KnowledgeService(db)
    results = await service.bm25_search(query=request.query, top_k=request.top_k)

    data = KnowledgeBm25SearchResponse(
        query=request.query,
        results=[
            KnowledgeBm25SearchResult(
                chunk_id=item["chunk_id"],
                document_id=item["document_id"],
                heading_path=item["heading_path"],
                content=item["content"],
                score=item["score"],
            )
            for item in results
        ]
    )

    return success_response(data)


@router.post("/hybrid-search", response_model=ApiResponse[KnowledgeHybridSearchResponse])
async def hybrid_search_knowledge(request: KnowledgeHybridSearchRequest, db: AsyncSession = Depends(get_db)):
    service = KnowledgeService(db)
    results = await service.hybrid_search(query=request.query, top_k=request.top_k, vector_weight=request.vector_weight)

    data = KnowledgeHybridSearchResponse(
        query=request.query,
        results=[
            KnowledgeHybridSearchResult(
                chunk_id=item["chunk_id"],
                document_id=item["document_id"],
                heading_path=item["heading_path"],
                content=item["content"],
                score=item["score"],
                vector_score=item["vector_score"],
                bm25_score=item["bm25_score"],
                match_type=item["match_type"],
            )
            for item in results
        ]
    )

    return success_response(data)


# 创建文档解析任务
@router.post("/parse-tasks", response_model=ApiResponse[DocumentParseTaskResponse])
async def create_document_parse_task(request: CreateDocumentParseTaskRequest, db: AsyncSession = Depends(get_db)):
    model_version = request.model_version or settings.mineru_model_version
    language = request.language or settings.mineru_language

    mineru_service = MinerUService()
    mineru_result = await mineru_service.create_parse_task(
        file_url=request.file_url,
        data_id=request.data_id,
        page_ranges=request.page_ranges
    )

    data = mineru_result.get("data", {})
    task_id = data.get("task_id")

    if not task_id:
        raise AppException(
            message=f"MinerU response missing task_id: {mineru_result}",
            code=502,
            status_code=502
        )

    task = DocumentParseTask(
        task_id=task_id,
        file_name=request.file_name,
        file_url=request.file_url,
        parse_engine="mineru",
        model_version=model_version,
        language=language,
        status="submitted",
        full_zip_url=None,
        result_json=json.dumps(mineru_result, ensure_ascii=False),
        error_message=None,
    )

    db.add(task)
    await db.commit()
    await db.refresh(task)

    return success_response(build_parse_task_response(task))


# 文档查询任务
@router.get("/parse-tasks/{task_id}", response_model=ApiResponse[DocumentParseTaskResponse])
async def get_document_parse_task(task_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(DocumentParseTask).where(DocumentParseTask.task_id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()

    if task is None:
        raise AppException(
            message=f"Task ID: {task_id} not found",
            code=404,
            status_code=404
        )

    mineru_service = MinerUService()
    mineru_result = await mineru_service.get_parse_task(task_id)

    data = mineru_result.get("data", {})

    task.status = data.get("state") or task.status
    task.full_zip_url = data.get("full_zip_url") or task.full_zip_url
    task.result_json = json.dumps(mineru_result, ensure_ascii=False)

    if task.status == "failed":
        task.error_message = data.get("err_msg") or "MinerU parse failed"
    else:
        task.error_message = None

    await db.commit()
    await db.refresh(task)

    await db.commit()
    await db.refresh(task)

    return success_response(build_parse_task_response(task))


@router.post("/parse-tasks/{task_id}/index", response_model=ApiResponse[KnowledgeDocumentResponse])
async def index_document_parse_task(task_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(DocumentParseTask).where(DocumentParseTask.task_id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if task is None:
        raise AppException(
            message="Document parse task not found",
            code=404,
            status_code=404,
        )

    if task.status != "done":
        raise AppException(
            message=f"Document parse task is not done: {task.status}",
            code=400,
            status_code=400,
        )

    if not task.full_zip_url:
        raise AppException(
            message="Document parse task full_zip_url is empty",
            code=400,
            status_code=400,
        )

    if task.document_id:
        raise AppException(
            message=f"Document parse task already indexed: {task.document_id}",
            code=400,
            status_code=400,
        )

    mineru_service = MinerUService()
    markdown_content = await mineru_service.download_and_extract_markdown(task.full_zip_url)

    knowledge_service = KnowledgeService(db)
    document, chunks = await knowledge_service.create_document(
        CreateKnowledgeDocumentRequest(
            title=task.file_name,
            content=markdown_content,
            source_type="mineru",
            source_uri=task.file_url
        )
    )

    task.document_id = document.document_id
    task.status = "indexed"

    await db.commit()
    await db.refresh(task)

    data = KnowledgeDocumentResponse(
        document_id=document.document_id,
        title=document.title,
        source_type=document.source_type,
        source_uri=document.source_uri,
        status=document.status,
        index_status=document.index_status,
        index_error=document.index_error,
        version=document.version,
        chunk_count=len(chunks),
        created_at=document.created_at,
        chunks=[
            KnowledgeChunkResponse(
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                heading_path=chunk.heading_path,
                content=chunk.content,
                token_count=chunk.token_count,
                milvus_vector_id=chunk.milvus_vector_id,
            )
            for chunk in chunks
        ]
    )

    return success_response(data)


@router.get("/documents", response_model=ApiResponse[list[KnowledgeDocumentListItem]])
async def list_knowledge_documents(
        status: str | None = None,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        db: AsyncSession = Depends(get_db)
):
    service = KnowledgeService(db)
    items = await service.list_documents(
        status=status,
        limit=limit,
        offset=offset
    )

    data = [
        KnowledgeDocumentListItem(
            document_id=item["document"].document_id,
            title=item["document"].title,
            source_type=item["document"].source_type,
            source_uri=item["document"].source_uri,
            status=item["document"].status,
            index_status=item["document"].index_status,
            index_error=item["document"].index_error,
            version=item["document"].version,
            chunk_count=item["chunk_count"],
            created_at=item["document"].created_at,
            updated_at=item["document"].updated_at,
        )
        for item in items
    ]

    return success_response(data)


@router.get("/documents/{document_id}", response_model=ApiResponse[KnowledgeDocumentDetailResponse])
async def get_knowledge_document_detail(document_id: str, db: AsyncSession = Depends(get_db)):
    service = KnowledgeService(db)
    result = await service.get_document_detail(document_id)

    if result is None:
        raise AppException(
            message="Knowledge document not found",
            code=404,
            status_code=404
        )

    document, chunks = result

    data = KnowledgeDocumentDetailResponse(
        document_id=document.document_id,
        title=document.title,
        source_type=document.source_type,
        source_uri=document.source_uri,
        status=document.status,
        index_status=document.index_status,
        index_error=document.index_error,
        version=document.version,
        content_hash=document.content_hash,
        chunk_count=len(chunks),
        created_at=document.created_at,
        updated_at=document.updated_at,
        chunks=[
            KnowledgeChunkResponse(
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                heading_path=chunk.heading_path,
                content=chunk.content,
                token_count=chunk.token_count,
                milvus_vector_id=chunk.milvus_vector_id,
            )
            for chunk in chunks
        ],
    )

    return success_response(data)


@router.post("/documents/{document_id}/retry-index",response_model=ApiResponse[KnowledgeDocumentDetailResponse])
async def retry_knowledge_document_index(
    document_id: str,
    db: AsyncSession = Depends(get_db),
):
    service = KnowledgeService(db)

    try:
        result = await service.retry_index_document(document_id)
    except ValueError as exc:
        raise AppException(
            message=str(exc),
            code=400,
            status_code=400,
        ) from exc

    if result is None:
        raise AppException(
            message="Knowledge document not found",
            code=404,
            status_code=404,
        )

    document, chunks = result

    data = KnowledgeDocumentDetailResponse(
        document_id=document.document_id,
        title=document.title,
        source_type=document.source_type,
        source_uri=document.source_uri,
        status=document.status,
        index_status=document.index_status,
        index_error=document.index_error,
        version=document.version,
        content_hash=document.content_hash,
        chunk_count=len(chunks),
        created_at=document.created_at,
        updated_at=document.updated_at,
        chunks=[
            KnowledgeChunkResponse(
                chunk_id=chunk.chunk_id,
                chunk_index=chunk.chunk_index,
                heading_path=chunk.heading_path,
                content=chunk.content,
                token_count=chunk.token_count,
                milvus_vector_id=chunk.milvus_vector_id,
            )
            for chunk in chunks
        ],
    )

    return success_response(data)