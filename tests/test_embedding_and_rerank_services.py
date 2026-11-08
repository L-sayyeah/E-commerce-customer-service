import json
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from app.services.embedding_service import EmbeddingService
from app.services.rerank_service import RerankService


REAL_ASYNC_CLIENT = httpx.AsyncClient
DIMENSIONS = 1536


def configuration(**overrides):
    values = {
        "embedding_endpoint": "https://workspace.example/compatible-mode/v1/embeddings",
        "embedding_api_key": "test-embedding-key",
        "embedding_model": "qwen3.7-text-embedding",
        "embedding_dimensions": DIMENSIONS,
        "embedding_batch_size": 20,
        "rerank_endpoint": "https://workspace.example/api/v1/services/rerank/text-rerank/text-rerank",
        "rerank_api_key": None,
        "rerank_model": "qwen3.7-text-rerank",
        "dashscope_api_key": "test-legacy-key",
        "dashscope_rerank_url": "https://dashscope.example/rerank",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@contextmanager
def mock_client(handler):
    def factory(**kwargs):
        return REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kwargs)

    with patch("httpx.AsyncClient", side_effect=factory) as client:
        yield client


class EmbeddingTests(unittest.IsolatedAsyncioTestCase):
    async def test_document_batches_preserve_input_order_and_request_dimensions(self):
        requests = []

        def handler(request):
            payload = json.loads(request.content)
            requests.append(payload)
            self.assertEqual(request.headers["Authorization"], "Bearer test-embedding-key")
            self.assertEqual(payload["dimensions"], DIMENSIONS)
            self.assertEqual(payload["encoding_format"], "float")
            return httpx.Response(200, json={"data": [
                {"index": index, "embedding": [float(text.split("-")[-1])] * DIMENSIONS}
                for index, text in reversed(list(enumerate(payload["input"])))
            ]})

        with patch("app.services.embedding_service.settings", configuration()), mock_client(handler):
            result = await EmbeddingService().embed_documents([f"document-{index}" for index in range(21)])
        self.assertEqual([len(item["input"]) for item in requests], [20, 1])
        self.assertEqual([vector[0] for vector in result], list(range(21)))

    async def test_query_uses_one_text_and_returns_one_vector(self):
        def handler(request):
            self.assertEqual(json.loads(request.content)["input"], ["退款规则"])
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5] * DIMENSIONS}]})

        with patch("app.services.embedding_service.settings", configuration()), mock_client(handler):
            result = await EmbeddingService().embed_query("退款规则")
        self.assertEqual(result, [0.5] * DIMENSIONS)

    async def test_missing_key_does_not_construct_http_client(self):
        with patch("app.services.embedding_service.settings", configuration(embedding_api_key="")):
            with patch("httpx.AsyncClient") as client:
                with self.assertRaisesRegex(ValueError, "EMBEDDING_API_KEY"):
                    await EmbeddingService().embed_query("退款")
                client.assert_not_called()

    async def test_corrupted_embeddings_are_rejected(self):
        valid = {"index": 0, "embedding": [0.1] * DIMENSIONS}
        cases = [
            ([{"index": 0, "embedding": [0.1]}], ["退款"]),
            ([valid, valid], ["退款", "换货"]),
            ([], ["退款"]),
            ([{"index": 0, "embedding": [float("nan")] * DIMENSIONS}], ["退款"]),
        ]
        for data, texts in cases:
            with self.subTest(count=len(data), input_count=len(texts)):
                with patch("app.services.embedding_service.settings", configuration()):
                    with mock_client(lambda request: httpx.Response(
                        200, content=json.dumps({"data": data}), headers={"Content-Type": "application/json"}
                    )):
                        with self.assertRaises(RuntimeError):
                            await EmbeddingService().embed_documents(texts)

    async def test_http_error_does_not_expose_upstream_response_body(self):
        with patch("app.services.embedding_service.settings", configuration()):
            with mock_client(lambda request: httpx.Response(401, text="upstream-private-details")):
                with self.assertRaisesRegex(RuntimeError, "HTTP 401") as caught:
                    await EmbeddingService().embed_query("退款")
        self.assertNotIn("upstream-private-details", str(caught.exception))

    async def test_empty_input_makes_no_request(self):
        with patch("app.services.embedding_service.settings", configuration(embedding_api_key="")):
            with patch("httpx.AsyncClient") as client:
                self.assertEqual(await EmbeddingService().embed_documents([]), [])
                client.assert_not_called()

    async def test_legacy_dashscope_adapter_remains_available(self):
        legacy = SimpleNamespace(
            aembed_documents=AsyncMock(return_value=[[0.1] * DIMENSIONS]),
            aembed_query=AsyncMock(return_value=[0.2] * DIMENSIONS),
        )
        with patch("app.services.embedding_service.settings", configuration(embedding_endpoint=None)):
            with patch("app.services.embedding_service.DashScopeEmbeddings", return_value=legacy):
                service = EmbeddingService()
                self.assertEqual(await service.embed_documents(["退款"]), [[0.1] * DIMENSIONS])
                self.assertEqual(await service.embed_query("退款"), [0.2] * DIMENSIONS)


class RerankTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.documents = [
            {"chunk_id": "A", "heading_path": "退款", "content": "退款规则", "score": 0.4},
            {"chunk_id": "B", "heading_path": "换货", "content": "换货规则", "score": 0.5},
        ]

    async def test_text_payload_shared_workspace_key_and_result_mapping(self):
        def handler(request):
            payload = json.loads(request.content)
            self.assertEqual(request.headers["Authorization"], "Bearer test-embedding-key")
            self.assertEqual(payload["input"]["query"], "如何换货")
            self.assertTrue(all(isinstance(item, str) for item in payload["input"]["documents"]))
            self.assertEqual(payload["parameters"]["top_n"], 2)
            return httpx.Response(200, json={"output": {"results": [
                {"index": 1, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.3},
            ]}})

        with patch("app.services.rerank_service.settings", configuration()), mock_client(handler):
            result = await RerankService().rerank("如何换货", self.documents, top_n=5)
        self.assertEqual([item["chunk_id"] for item in result], ["B", "A"])
        self.assertEqual(result[0]["rerank_score"], 0.9)
        self.assertEqual(result[0]["score"], 0.5)
        self.assertNotIn("rerank_score", self.documents[0])

    async def test_explicit_rerank_key_supports_another_endpoint(self):
        def handler(request):
            self.assertEqual(request.headers["Authorization"], "Bearer test-rerank-key")
            return httpx.Response(200, json={"output": {"results": [{"index": 0, "relevance_score": 0.8}]}})

        settings = configuration(rerank_endpoint="https://another.example/rerank", rerank_api_key="test-rerank-key")
        with patch("app.services.rerank_service.settings", settings), mock_client(handler):
            result = await RerankService().rerank("退款", self.documents, top_n=1)
        self.assertEqual(result[0]["chunk_id"], "A")

    async def test_embedding_key_is_not_forwarded_to_another_origin(self):
        settings = configuration(rerank_endpoint="https://another.example/rerank")
        with patch("app.services.rerank_service.settings", settings), patch("httpx.AsyncClient") as client:
            with self.assertRaisesRegex(ValueError, "RERANK_API_KEY"):
                await RerankService().rerank("退款", self.documents, top_n=1)
            client.assert_not_called()

    async def test_invalid_document_indices_are_rejected(self):
        cases = [
            [{"index": 2, "relevance_score": 0.9}],
            [{"index": 0, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.8}],
            [],
        ]
        for results in cases:
            with self.subTest(results=results):
                with patch("app.services.rerank_service.settings", configuration()):
                    with mock_client(lambda request: httpx.Response(200, json={"output": {"results": results}})):
                        with self.assertRaises(RuntimeError):
                            await RerankService().rerank("退款", self.documents, top_n=2)

    async def test_http_error_does_not_expose_upstream_response_body(self):
        with patch("app.services.rerank_service.settings", configuration()):
            with mock_client(lambda request: httpx.Response(403, text="upstream-private-details")):
                with self.assertRaisesRegex(RuntimeError, "HTTP 403") as caught:
                    await RerankService().rerank("退款", self.documents, top_n=1)
        self.assertNotIn("upstream-private-details", str(caught.exception))

    async def test_legacy_endpoint_uses_legacy_key(self):
        def handler(request):
            self.assertEqual(str(request.url), "https://dashscope.example/rerank")
            self.assertEqual(request.headers["Authorization"], "Bearer test-legacy-key")
            return httpx.Response(200, json={"output": {"results": [{"index": 0, "relevance_score": 0.8}]}})

        with patch("app.services.rerank_service.settings", configuration(rerank_endpoint=None)):
            with mock_client(handler):
                await RerankService().rerank("退款", self.documents, top_n=1)

    async def test_empty_documents_make_no_request(self):
        with patch("app.services.rerank_service.settings", configuration()), patch("httpx.AsyncClient") as client:
            self.assertEqual(await RerankService().rerank("退款", [], top_n=1), [])
            client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
