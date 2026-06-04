from datetime import datetime

from pydantic import BaseModel, Field


class CreateDocumentParseTaskRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    file_url: str = Field(min_length=1)
    model_version: str | None = None
    language: str | None = None
    data_id: str | None = None
    page_ranges: str | None = None


class DocumentParseTaskResponse(BaseModel):
    task_id: str
    file_name: str
    file_url: str
    parse_engine: str
    model_version: str
    language: str | None
    status: str
    full_zip_url: str | None
    document_id: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
