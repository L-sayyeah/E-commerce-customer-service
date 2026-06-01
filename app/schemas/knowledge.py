from datetime import datetime

from pydantic import BaseModel, Field


# 创建知识文档请求模型
class CreateKnowledgeDocumentRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    source_type: str = "manual"
    source_uri: str | None = None


# 知识文档分块响应模型
class KnowledgeChunkResponse(BaseModel):
    chunk_id: str
    chunk_index: int
    heading_path: str | None
    content: str
    token_count: int | None
    milvus_vector_id: str | None


# 知识文档响应模型
class KnowledgeDocumentResponse(BaseModel):
    document_id: str
    title: str
    source_type: str
    source_uri: str | None
    status: str
    version: int
    chunk_count: int
    created_at: datetime
    chunks: list[KnowledgeChunkResponse]


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


# 知识文档搜索结果模型
class KnowledgeSearchResult(BaseModel):
    chunk_id: str
    document_id: str
    heading_path: str | None
    content: str
    score: float


# 知识文档搜索响应模型
class KnowledgeSearchResponse(BaseModel):
    query: str
    results: list[KnowledgeSearchResult]


class RagQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)


class RagSource(BaseModel):
    chunk_id: str
    document_id: str
    heading_path: str | None
    content: str
    score: float


class RagAnswerResponse(BaseModel):
    query: str
    answer: str
    sources: list[RagSource]


class KnowledgeBm25SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class KnowledgeBm25SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    heading_path: str | None
    content: str
    score: float


class KnowledgeBm25SearchResponse(BaseModel):
    query: str
    results: list[KnowledgeBm25SearchResult]


class KnowledgeHybridSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    vector_weight: float = Field(default=0.7, ge=0, le=1)


class KnowledgeHybridSearchResult(BaseModel):
    chunk_id: str
    document_id: str
    heading_path: str | None
    content: str
    score: float
    vector_score: float
    bm25_score: float
    match_type: str


class KnowledgeHybridSearchResponse(BaseModel):
    query: str
    results: list[KnowledgeHybridSearchResult]
