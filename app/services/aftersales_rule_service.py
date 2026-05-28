# backend/app/services/aftersales_rule_service.py
from datetime import datetime, timezone

from app.models.order import Order


class AftersalesRuleService:
    refund_window_days = 30
    exchange_window_days = 45

    def evaluate(self, order: Order) -> dict:
        reasons: list[str] = []

        refundable = False
        exchangeable = False
        resendable = False
        requires_human_review = False

        if order.payment_status != "paid":
            reasons.append("订单未支付或已退款，不支持退款")
            return {
                "refundable": False,
                "exchangeable": False,
                "resendable": False,
                "requires_human_review": False,
                "reasons": reasons,
            }

        if order.logistics_status == "lost":
            resendable = True
            requires_human_review = True
            reasons.append("物流状态为丢失，可申请补发，但需要人工审核")

        if order.logistics_status in {"pending", "shipped", "in_transit"}:
            requires_human_review = True
            reasons.append("订单仍在运输或待发货状态，需要人工确认当前履约进度")

        if order.logistics_status == "delivered":
            if order.delivered_at is None:
                requires_human_review = True
                reasons.append("订单已签收但缺少签收时间，需要人工审核")
            else:
                now = datetime.now(timezone.utc)
                delivered_at = order.delivered_at

                if delivered_at.tzinfo is None:
                    delivered_at = delivered_at.replace(tzinfo=timezone.utc)

                days_since_delivered = (now - delivered_at).days

                if days_since_delivered <= self.refund_window_days:
                    refundable = True
                    reasons.append(f"订单在签收后{self.refund_window_days}天内，支持退款申请")
                else:
                    reasons.append(f"订单已超过签收后{self.refund_window_days}天退款期")

                if days_since_delivered <= self.exchange_window_days:
                    exchangeable = True
                    reasons.append(f"订单在签收后{self.exchange_window_days}天内，支持换货申请")
                else:
                    reasons.append(f"订单已超过签收后{self.exchange_window_days}天换货期")

        if order.fulfillment_status == "cancelled":
            refundable = order.payment_status == "paid"
            exchangeable = False
            resendable = False
            reasons.append("订单已取消，如已支付则支持退款")

        if not reasons:
            reasons.append("当前订单状态暂不满足自动售后规则，需要人工审核")
            requires_human_review = True

        return {
            "refundable": refundable,
            "exchangeable": exchangeable,
            "resendable": resendable,
            "requires_human_review": requires_human_review,
            "reasons": reasons,
        }