from fastapi import APIRouter

from app.api.v1 import chat, order

api_router = APIRouter()
api_router.include_router(chat.router)
api_router.include_router(order.router)
