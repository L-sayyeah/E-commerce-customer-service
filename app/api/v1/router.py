from fastapi import APIRouter

from app.api.v1 import chat, order, tickets, knowledge

api_router = APIRouter()
api_router.include_router(chat.router)
api_router.include_router(order.router)
api_router.include_router(tickets.router)
api_router.include_router(knowledge.router)
