from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.response import ApiResponse, success_response
from app.schemas.knowledge import KnowledgeDocumentResponse, CreateKnowledgeDocumentRequest, KnowledgeChunkResponse, \
    KnowledgeSearchResponse, KnowledgeSearchRequest, KnowledgeSearchResult, RagAnswerResponse, RagQueryRequest, \
    RagSource
from app.services.knoewledge_service import KnowledgeService
from app.services.milvus_service import MilvusService
from app.services.rag_service import RagService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


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
    rag_service = RagService(knowledge_service)

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
                score=item["score"]
            )
            for item in result["sources"]
        ]
    )

    return success_response(data)
