import json
import re

import logging
from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

ALLOWED_INTENTS = {
    "rag_qa",
    "order_query",
    "aftersales_check",
    "ticket_create",
    "clarify",
}

ORDER_NO_PATTERN = re.compile(r"\b[A-Z]{2,}[A-Z0-9_-]*\d+[A-Z0-9_-]*\b")


def extract_order_no(text: str) -> str | None:
    match = ORDER_NO_PATTERN.search(text.upper())
    return match.group(0) if match else None


def clean_json_text(text: str) -> str:
    value = text.strip()

    if value.startswith("```json"):
        value = value.removeprefix("```json").strip()
    elif value.startswith("```"):
        value = value.removeprefix("```").strip()

    if value.endswith("```"):
        value = value.removesuffix("```").strip()

    return value


class IntentClassifier:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.chat_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=0
        )

    async def classify(self, user_message: str, recent_messages: list[dict] | None = None) -> dict:
        context_result = self.context_classify(
            user_message=user_message,
            recent_messages=recent_messages
        )

        if context_result is not None:
            return context_result

        if not settings.agent_intent_use_llm:
            return self.rule_classify(user_message)

        try:
            return await self.llm_classify(user_message)
        except Exception:
            return self.rule_classify(user_message)

    async def llm_classify(self, user_message: str) -> dict:
        known_order_no = extract_order_no(user_message)

        prompt = [
            {
                "role": "system",
                "content": (
                    "你是跨境电商售后客服 Agent 的意图识别器。"
                    "你只能返回 JSON，不要返回 Markdown，不要解释。"
                    "intent 只能是以下之一："
                    "rag_qa, order_query, aftersales_check, ticket_create, clarify。"
                    "rag_qa 表示政策、规则、FAQ、售后知识问答。"
                    "order_query 表示查询订单、物流、发货、签收、支付状态。"
                    "aftersales_check 表示判断是否可退款、退货、换货、补发。"
                    "ticket_create 表示用户要求转人工、投诉、创建工单。"
                    "clarify 表示信息不足，需要追问。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"用户消息：{user_message}\n"
                    f"正则识别到的订单号：{known_order_no}\n\n"
                    "请返回 JSON："
                    "{\"intent\":\"...\",\"order_no\":null或订单号,\"reason\":\"...\"}"
                )
            }
        ]

        response = await self.llm.ainvoke(prompt)
        payload = json.loads(clean_json_text(str(response.content)))

        intent = payload.get("intent")

        if intent not in ALLOWED_INTENTS:
            raise ValueError(f"Invalid intent: {intent}")

        order_no = payload.get("order_no") or known_order_no

        return {
            "intent": intent,
            "order_no": order_no,
            "reason": payload.get("reason"),
            "classifier": "llm"
        }

    def rule_classify(self, user_message: str) -> dict:
        message = user_message
        normalized = message.lower()
        order_no = extract_order_no(message)

        if any(keyword in message for keyword in ["转人工", "人工客服", "投诉", "工单"]):
            intent = "ticket_create"
        elif order_no and any(
                keyword in message
                for keyword in ["退款", "退货", "换货", "补发", "售后", "丢失", "没收到"]
        ):
            intent = "aftersales_check"
        elif order_no and any(
                keyword in message
                for keyword in ["订单", "物流", "到哪", "状态", "发货", "签收"]
        ):
            intent = "order_query"
        elif any(
                keyword in message
                for keyword in ["退款", "退货", "换货", "补发", "政策", "规则", "多久", "怎么"]
        ):
            intent = "rag_qa"
        elif "order" in normalized:
            intent = "clarify"
        else:
            intent = "rag_qa"

        return {
            "intent": intent,
            "order_no": order_no,
            "reason": "rule fallback",
            "classifier": "rule",
        }

    def is_order_no_only(self, text: str) -> bool:
        order_no = extract_order_no(text)
        if not order_no:
            return False

        normalized = re.sub(r"\s+", "", text.upper())
        return normalized in {
            order_no,
            f"订单号{order_no}",
            f"ORDER_NO：{order_no}"
        }

    def context_classify(self, user_message: str, recent_messages: list[dict]) -> dict | None:
        order_no = extract_order_no(user_message)

        if not order_no or not self.is_order_no_only(user_message):

            return None

        for message in reversed(recent_messages):
            if message.get("role") != "user":
                continue

            content = message.get("content") or ""
            logger.debug(f"context: {content}")

            if self.is_order_no_only(content):
                continue

            if any(keyword in content for keyword in ["退款", "退货", "换货", "补发", "售后", "丢失", "没收到"]):
                return {
                    "intent": "aftersales_check",
                    "order_no": order_no,
                    "reason": "用户当前只补充订单号，根据上一轮售后诉求恢复为售后判断",
                    "classifier": "context"
                }

            if any(
                    keyword in content
                    for keyword in ["订单", "物流", "到哪", "状态", "发货", "签收"]
            ):
                return {
                    "intent": "order_query",
                    "order_no": order_no,
                    "reason": "用户当前只补充订单号，根据上一轮订单查询诉求恢复为订单查询",
                    "classifier": "context",
                }

            if any(keyword in content for keyword in ["转人工", "人工客服", "投诉", "工单"]):
                return {
                    "intent": "ticket_create",
                    "order_no": order_no,
                    "reason": "用户当前只补充订单号，根据上一轮人工处理诉求恢复为工单创建",
                    "classifier": "context",
                }

        return None


if __name__ == "__main__":
    classifier = IntentClassifier()
    print(classifier.is_order_no_only("ORDER1001"))
