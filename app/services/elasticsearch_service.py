from elasticsearch import AsyncElasticsearch
from elasticsearch.helpers import async_bulk

from app.core.config import settings


class ElasticsearchService:
    def __init__(self):
        self.client = AsyncElasticsearch(hosts=[settings.elasticsearch_url])
        self.index_name = settings.elasticsearch_index
        self.analyzer = settings.elasticsearch_analyzer

    async def close(self) -> None:
        await self.client.close()

    async def health_check(self) -> dict:
        info = await self.client.info()
        return {
            "connected": True,
            "cluster_name": info["cluster_name"],
            "version": info.get("version", {}).get("number"),
            "index": self.index_name
        }

    async def init_index(self) -> dict:
        exists = await self.client.indices.exists(index=self.index_name)

        if exists:
            return {
                "index": self.index_name,
                "exists": False
            }

        mappings = {
            "properties": {
                "chunk_id": {
                    "type": "keyword",
                },
                "document_id": {
                    "type": "keyword",
                },
                "heading_path": {
                    "type": "text",
                    "analyzer": self.analyzer,
                },
                "content": {
                    "type": "text",
                    "analyzer": self.analyzer,
                },
                "status": {
                    "type": "keyword",
                },
                "created_at": {
                    "type": "date",
                },
            }
        }

        settings_body = {
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }

        await self.client.indices.create(
            index=self.index_name,
            settings=settings_body,
            mappings=mappings
        )

        return {
            "index": self.index_name,
            "created": True,
            "analyzer": self.analyzer
        }

    async def index_chunks(self, chunks: list[dict]) -> dict:
        actions = []

        for chunk in chunks:
            actions.append(
                {
                    "_op_type": "index",
                    "_index": self.index_name,
                    "_id": chunk["chunk_id"],
                    "_source": {
                        "chunk_id": chunk["chunk_id"],
                        "document_id": chunk["document_id"],
                        "heading_path": chunk.get("heading_path"),
                        "content": chunk["content"],
                        "status": chunk.get("status", "active"),
                    },
                }
            )

        success_count, errors = await async_bulk(
            client=self.client,
            actions=actions,
            raise_on_error=False,
        )
        return {
            "success_count": success_count,
            "errors": errors
        }

    async def search_chunks(self, query: str, top_k: int = 5) -> list[dict]:
        response = await self.client.search(
            index=self.index_name,
            query={
                "bool": {
                    "filter": [
                        {
                            "term": {
                                "status": "active",
                            }
                        }
                    ],
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "heading_path^2",
                                    "content",
                                ],
                                "type": "best_fields",
                            }
                        }
                    ],
                }
            },
            size=top_k
        )

        hits = response.get("hits", {}).get("hits", [])
        return [
            {
                "chunk_id": hit["_source"]["chunk_id"],
                "document_id": hit["_source"]["document_id"],
                "heading_path": hit["_source"].get("heading_path"),
                "content": hit["_source"]["content"],
                "score": float(hit["_score"] or 0),
            }
            for hit in hits
        ]

