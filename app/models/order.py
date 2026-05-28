# backend/app/models/order.py
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="订单号",
    )
    user_id: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        comment="用户ID",
    )
    platform: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="销售平台：shopify/amazon/tiktok/independent_site",
    )
    country: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="国家或地区",
    )
    currency: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="币种",
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        comment="订单金额",
    )
    payment_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="支付状态：paid/unpaid/refunded/partially_refunded",
    )
    fulfillment_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="履约状态：unfulfilled/fulfilled/partially_fulfilled/cancelled",
    )
    logistics_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="物流状态：pending/shipped/in_transit/delivered/lost/returned",
    )
    shipped_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="发货时间",
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="签收时间",
    )