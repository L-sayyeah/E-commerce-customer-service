# app/services/mineru_service.py
import tempfile
import zipfile
from pathlib import Path

import httpx

from app.core.config import settings


class MinerUService:
    def __init__(self):
        self.base_url = settings.mineru_base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {settings.mineru_api_key}",
            "Content-Type": "application/json",
            "Accept": "*/*",
        }

    async def create_parse_task(
        self,
        file_url: str,
        data_id: str | None = None,
        page_ranges: str | None = None,
    ) -> dict:
        payload = {
            "url": file_url,
            "model_version": settings.mineru_model_version,
            "language": settings.mineru_language,
            "enable_formula": settings.mineru_enable_formula,
            "enable_table": settings.mineru_enable_table,
            "is_ocr": settings.mineru_is_ocr,
        }

        if data_id:
            payload["data_id"] = data_id

        if page_ranges:
            payload["page_ranges"] = page_ranges

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/extract/task",
                headers=self.headers,
                json=payload,
            )

        result = response.json()

        if response.status_code >= 400 or result.get("code") != 0:
            raise RuntimeError(f"MinerU create parse task failed: {result}")

        return result

    async def get_parse_task(
        self,
        task_id: str,
    ) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(
                f"{self.base_url}/extract/task/{task_id}",
                headers=self.headers,
            )

        result = response.json()

        if response.status_code >= 400 or result.get("code") != 0:
            raise RuntimeError(f"MinerU get parse task failed: {result}")

        return result

    def _find_markdown_file(self, extract_dir: Path) -> Path | None:
        full_md = list(extract_dir.rglob("full.md"))
        if full_md:
            return full_md[0]

        markdown_files = list(extract_dir.rglob("*.md"))
        if markdown_files:
            return markdown_files[0]

        return None

    async def download_and_extract_markdown(self, full_zip_url: str) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(full_zip_url)

            if response.status_code >= 400:
                raise RuntimeError(f"Download MinerU result failed: status_code={response.status_code}")

            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                zip_path = temp_path / "mineru_result.zip"

                zip_path.write_bytes(response.content)

                extract_dir = temp_path / "extract"
                extract_dir.mkdir(parents=True, exist_ok=True)

                with zipfile.ZipFile(zip_path, "r") as zip_file:
                    zip_file.extractall(extract_dir)

                markdown_file = self._find_markdown_file(extract_dir)

                if markdown_file is None:
                    raise RuntimeError("MinerU result markdown file not found")

                markdown_content = markdown_file.read_text(encoding="utf-8")

                if not markdown_content.strip():
                    raise RuntimeError("MinerU result markdown content is empty")

                return markdown_content