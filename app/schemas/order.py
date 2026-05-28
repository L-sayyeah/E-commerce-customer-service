# backend/app/schemas/order.py
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class OrderResponse(BaseModel):
    id: int
    order_no: str
    user_id: str
    platform: str
    country: str
    currency: str
    total_amount: Decimal
    payment_status: str
    fulfillment_status: str
    logistics_status: str
    shipped_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime
