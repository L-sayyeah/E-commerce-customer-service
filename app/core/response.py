from typing import TypeVar, Generic

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "success"
    data: T | None = None


def success_response(data: T | None = None) -> ApiResponse[T]:
    return ApiResponse(data=data)
