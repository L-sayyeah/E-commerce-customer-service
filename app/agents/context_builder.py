import re
from typing import Any


ORDER_NO_PATTERN = re.compile(r"\bORDER\d+\b", re.IGNORECASE)
TICKET_ID_PATTERN = re.compile(r"\b(?:ticket|工单)[\s#:：-]*(\d+)\b", re.IGNORECASE)


FOLLOW_UP_KEYWORDS = [
    "这个",
    "这单",
    "该订单",
    "它",
    "这个订单",
    "还能",
    "那",
    "刚才",
    "上面",
    "这个包裹",
    "这个工单",
]


INTENT_KEYWORDS = {
    "aftersales_check": ["退款", "退货", "换货", "补发", "售后", "赔偿"],
    "order_query": ["订单", "物流", "包裹", "签收", "发货", "到哪"],
    "ticket_create": ["工单", "人工", "客服介入", "投诉"],
    "rag_qa": ["规则", "政策", "说明", "怎么处理", "多久"],
}


class ContextBuilder:
    def build(
        self,
        user_message: str,
        recent_messages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        recent_messages = recent_messages or []

        recent_order_no = self._extract_recent_order_no(user_message, recent_messages)
        recent_ticket_id = self._extract_recent_ticket_id(user_message, recent_messages)
        last_intent = self._infer_last_intent(recent_messages)
        current_has_order_no = bool(ORDER_NO_PATTERN.search(user_message))
        is_follow_up = self._is_follow_up(user_message)

        memory_used = False
        memory_reason = None

        if is_follow_up and recent_order_no and not current_has_order_no:
            memory_used = True
            memory_reason = f"当前问题是追问，复用了最近一次订单号 {recent_order_no}"

        return {
            "recent_order_no": recent_order_no,
            "recent_ticket_id": recent_ticket_id,
            "last_intent": last_intent,
            "is_follow_up": is_follow_up,
            "memory_used": memory_used,
            "memory_reason": memory_reason,
            "context_summary": self._build_summary(
                recent_order_no=recent_order_no,
                recent_ticket_id=recent_ticket_id,
                last_intent=last_intent,
                is_follow_up=is_follow_up,
                memory_used=memory_used,
            ),
        }

    # 获取最近一次的订单号
    def _extract_recent_order_no(self, user_message: str, recent_messages: list[dict[str, Any]],) -> str | None:
        current_match = ORDER_NO_PATTERN.search(user_message)
        if current_match:
            return current_match.group(0).upper()

        for message in reversed(recent_messages):
            content = str(message.get("content") or "")
            match = ORDER_NO_PATTERN.search(content)
            if match:
                return match.group(0).upper()

        return None

    def _extract_recent_ticket_id(self, user_message: str, recent_messages: list[dict[str, Any]]) -> int | None:
        current_match = TICKET_ID_PATTERN.search(user_message)
        if current_match:
            return int(current_match.group(1))

        for message in reversed(recent_messages):
            content = str(message.get("content") or "")
            match = TICKET_ID_PATTERN.search(content)
            if match:
                return int(match.group(1))

        return None

    def _infer_last_intent(self, recent_messages: list[dict[str, Any]]) -> str | None:
        for message in reversed(recent_messages):
            content = str(message.get("content") or "")
            for intent, keywords in INTENT_KEYWORDS.items():
                if any(keyword in content for keyword in keywords):
                    return intent

        return None

    def _is_follow_up(self, user_message: str) -> bool:
        normalized = user_message.strip()
        return any(keyword in normalized for keyword in FOLLOW_UP_KEYWORDS)

    def _build_summary(
        self,
        recent_order_no: str | None,
        recent_ticket_id: int | None,
        last_intent: str | None,
        is_follow_up: bool,
        memory_used: bool,
    ) -> str:
        parts = []

        if recent_order_no:
            parts.append(f"最近订单号：{recent_order_no}")

        if recent_ticket_id:
            parts.append(f"最近工单ID：{recent_ticket_id}")

        if last_intent:
            parts.append(f"上一轮可能意图：{last_intent}")

        parts.append(f"是否追问：{is_follow_up}")
        parts.append(f"是否使用业务记忆：{memory_used}")

        return "；".join(parts)