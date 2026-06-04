from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    app_name: str = "Custom Service Agent"
    debug: bool = True
    api_prefix: str = "/api/v1"

    database_url: str = Field(min_length=1)

    # 日志配置
    log_level: str = "INFO"
    log_file: str = "logs/app.log"

    # Milvus 配置
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "knowledge_chunks"
    milvus_vector_dim: int = 1536

    # Elasticsearch 配置
    elasticsearch_url: str = "http://127.0.0.1:9200"
    elasticsearch_username: str | None = None
    elasticsearch_password: str | None = None
    elasticsearch_index: str = "knowledge_chunks"
    elasticsearch_analyzer: str = "standard"

    # Dashscope 配置
    dashscope_api_key: str | None = None

    # ARK 配置
    llm_api_key: str | None = None
    llm_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    chat_model: str = "doubao-seed-2-0-lite-260428"
    llm_temperature: float = 0.7

    # embedding模型
    embedding_model: str = "tongyi-embedding-vision-plus-2026-03-06"
    embedding_dimensions: int = 1536

    agent_intent_use_llm: bool = True

    # RAG 配置
    rag_retrieval_mode: str = "hybrid"
    hybrid_vector_weight: float = 0.7

    # Rerank 配置
    rag_rerank_enabled: bool = True
    rag_retrieval_top_n: int = 20
    rerank_model: str = "qwen3-vl-rerank"
    rerank_top_n: int = 5
    dashscope_rerank_url: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    )

    # MinerU 配置
    mineru_api_key: str | None = None
    mineru_base_url: str = "https://mineru.net/api/v4"
    mineru_model_version: str = "vlm"
    mineru_language: str = "ch"
    mineru_enable_formula: bool = True
    mineru_enable_table: bool = True
    mineru_is_ocr: bool = False

    # 知识库重试配置
    knowledge_index_max_retries: int = 3
    knowledge_index_retry_base_seconds: float = 1.0

    # checkpoint 配置
    langgraph_checkpoint_enabled: bool = True
    langgraph_checkpoint_backend: str = "mysql"
    langgraph_checkpoint_db_uri: str | None = None

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
    )


settings = Settings()
