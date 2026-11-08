from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Principal
from app.models.order import Order


class OrderService:
    def __init__(self, db: AsyncSession, principal: Principal):
        self.db = db
        self.principal = principal

    async def get_by_order_no(self, order_no: str) -> Order | None:
        stmt = select(Order).where(
            Order.order_no == order_no,
            Order.user_id == self.principal.user_id,
        )
        order = (await self.db.execute(stmt)).scalar_one_or_none()
        # The database collation can match differently cased account identifiers.
        if order is None or order.user_id != self.principal.user_id:
            return None
        return order
