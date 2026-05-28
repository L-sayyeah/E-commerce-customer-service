import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order

logger = logging.getLogger(__name__)


class OrderService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_order_no(self, order_no: str) -> Order | None:
        stmt = select(Order).where(Order.order_no == order_no)
        result = await self.db.execute(stmt)
        order = result.scalar_one_or_none()

        if order is None:
            logger.info(f"订单不存在 | 订单号: {order_no}")
        else:
            logger.info(f"找到订单 | 订单号: {order_no} | 用户ID: {order.user_id}")
        return order
