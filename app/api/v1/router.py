from fastapi import APIRouter, Depends

from app.api.v1 import chat, order, tickets, knowledge, admin
from app.core.auth import require_admin, require_principal

api_router = APIRouter(dependencies=[Depends(require_principal)])
api_router.include_router(chat.router)
api_router.include_router(order.router)
api_router.include_router(tickets.router)
api_router.include_router(knowledge.router)
api_router.include_router(admin.router, dependencies=[Depends(require_admin)])
