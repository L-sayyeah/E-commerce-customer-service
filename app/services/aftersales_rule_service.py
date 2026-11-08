# backend/app/services/aftersales_rule_service.py
from datetime import datetime, timezone

from app.models.order import Order


class AftersalesRuleService:
    # Ordinary return windows from the regional policy documents. A quality
    # exception or an exchange requires facts absent from the Order model.
    refund_windows = {
        "US": 30, "EU": 14, "UK": 30, "GB": 30, "AU": 30, "CA": 30, "JP": 14, "KR": 7,
    }

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

                window = self.refund_windows.get(order.country.strip().upper())
                requires_human_review = True

                if days_since_delivered < 0:
                    reasons.append("签收时间异常，需要人工确认")
                elif window is None:
                    reasons.append("尚无法确认该订单地区适用的普通退货窗口，需要人工审核")
                elif days_since_delivered <= window:
                    refundable = True
                    reasons.append(f"订单在该地区签收后{window}天的普通退货窗口内，商品适用条件仍需核实")
                else:
                    reasons.append(f"订单已超过该地区签收后{window}天的普通退货窗口，质量等例外需人工审核")

                reasons.append("换货需结合商品类别、问题和证据确认")

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