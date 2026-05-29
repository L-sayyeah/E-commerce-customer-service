import logging

from pymilvus import connections, Collection, FieldSchema, DataType, CollectionSchema
from pymilvus.orm import utility

from app.core.config import settings

logger = logging.getLogger(__name__)


class MilvusService:
    def __init__(self):
        self.alias = "default"
        self.collection_name = settings.milvus_collection

    def connect(self) -> None:
        connections.connect(
            alias=self.alias,
            host=settings.milvus_host,
            port=settings.milvus_port
        )

    def health_check(self) -> dict:
        self.connect()
        return {
            "connected": True,
            "host": settings.milvus_host,
            "port": settings.milvus_port,
            "collection": self.collection_name
        }

    # 确保向量字段有索引
    def ensure_index(self, collection: Collection) -> bool:
        index_params = {
            "metric_type": "COSINE",
            "index_type": "HNSW",
            "params": {
             "M": 16,
             "efConstruction": 200,
            }
        }
        has_embedding_index = any(
            index.field_name == "embedding"
            for index in collection.indexes
        )

        if has_embedding_index:
            return False

        collection.create_index(
            field_name="embedding",
            index_params=index_params
        )
        return True

    def init_collection(self) -> dict:
        self.connect()

        if utility.has_collection(self.collection_name):
            collection = Collection(self.collection_name)
            index_created = self.ensure_index(collection)
            collection.load()

            return {
                "collection": self.collection_name,
                "created": False,
                "index_created": index_created,
                "description": collection.description,
                "num_entities": collection.num_entities
            }

        fields = [
            FieldSchema(
                name="id",
                dtype=DataType.INT64,
                is_primary=True,
                auto_id=True,
                description="Milvus primary key"
            ),
            FieldSchema(
                name="chunk_id",
                dtype=DataType.VARCHAR,
                max_length=64,
                description="业务切片ID"
            ),
            FieldSchema(
                name="document_id",
                dtype=DataType.VARCHAR,
                max_length=64,
                description="业务文档ID"
            ),
            FieldSchema(
                name="heading_path",
                dtype=DataType.VARCHAR,
                max_length=512,
                description="标题路径"
            ),
            FieldSchema(
                name="content",
                dtype=DataType.VARCHAR,
                max_length=4096,
                description="切片内容"
            ),
            FieldSchema(
                name="embedding",
                dtype=DataType.FLOAT_VECTOR,
                dim=settings.milvus_vector_dim,
                description="嵌入向量"
            )
        ]

        schema = CollectionSchema(
            fields=fields,
            description="Knowledge base chunk vectors",
            enable_dynamic_field=True
        )

        collection = Collection(
            name=self.collection_name,
            schema=schema
        )

        index_params = {
            "metric_type": "COSINE",
            "index_type": "HNSW",
            "params": {
                "M": 16,
                "efConstruction": 200
            }
        }

        collection.create_index(
            field_name="embedding",
            index_params=index_params
        )

        collection.load()

        logger.info(f"Created Milvus collection | collection={self.collection_name} | dim={settings.milvus_vector_dim}")

        return {
            "collection": self.collection_name,
            "created": True,
            "vector_dim": settings.milvus_vector_dim,
            "index_type": "HNSW",
            "metric_type": "COSINE"
        }

    def insert_chunks(self, chunks: list[dict]) -> list[str]:
        self.connect()

        collection = Collection(self.collection_name)

        data = [
            [chunk["chunk_id"] for chunk in chunks],
            [chunk["document_id"] for chunk in chunks],
            [chunk["heading_path"] or "" for chunk in chunks],
            [chunk["content"][:4096] for chunk in chunks],
            [chunk["embedding"] for chunk in chunks]
        ]

        result = collection.insert(data)
        collection.flush()

        return [str(primary_key) for primary_key in result.primary_keys]

    def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        self.connect()

        collection = Collection(self.collection_name)
        collection.load()

        search_params = {
            "metric_type": "COSINE",
            "params": {
                "ef": 64
            }
        }

        results = collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            output_fields=[
                "chunk_id",
                "document_id",
                "heading_path",
                "content",
            ]
        )

        hits = []
        for hit in results[0]:
            hits.append({
                "id": str(hit.id),
                "score": float(hit.score),
                "chunk_id": hit.entity.get("chunk_id"),
                "document_id": hit.entity.get("document_id"),
                "heading_path": hit.entity.get("heading_path") or None,
                "content": hit.entity.get("content")
            })
        return hits
