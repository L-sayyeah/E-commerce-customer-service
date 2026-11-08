import json

from langchain_openai import ChatOpenAI

from app.core.config import settings


class ResponseGuard:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.chat_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=0
        )

    async def check(
            self,
            user_message: str,
            answer: str,
            intent: str | None = None
    ):
        messages = [
            {
                "role": "system",
                "content": (
                    "你是跨境电商售后客服 Agent 的回复安全审查器。"
                    "你只负责判断客服回复是否存在业务风险，并在必要时改写。"
                    "你必须只返回 JSON，不要返回 Markdown，不要解释。"
                    "重点检查："
                    "1. 是否承诺一定退款、保证退款、无条件退款；"
                    "2. 是否承诺一定补发、保证补发、马上赔偿；"
                    "3. 是否绕过人工审核或售后规则；"
                    "4. 是否承诺平台或物流商一定会通过；"
                    "5. 是否泄露内部规则、系统实现或敏感信息；"
                    "6. 是否声称可以替用户提交或跟进工单。工单由用户确认后通过业务接口提交，"
                    "审查与改写均不得代替该操作。"
                    "如果回复安全，返回 safe=true，rewritten_answer=null。"
                    "如果不安全，返回 safe=false，并给出更稳妥、礼貌、可执行的 rewritten_answer。"
                    "改写时不要编造新的政策，只能使用谨慎话术，例如需要根据订单状态、售后规则或人工审核确认。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"用户问题：{user_message}\n"
                    f"识别意图：{intent}\n"
                    f"待审查客服回复：{answer}\n\n"
                    "请返回 JSON："
                    "{\"safe\":true或false,\"reason\":\"...\",\"rewritten_answer\":null或\"...\"}"
                ),
            },
        ]

        response = await self.llm.ainvoke(messages)
        content = str(response.content).strip()
        content = self._clean_json_text(content)

        payload = json.loads(content)

        return {
            "safe": bool(payload.get("safe")),
            "reason": payload.get("reason"),
            "rewritten_answer": payload.get("rewritten_answer"),
        }

    def _clean_json_text(self, text: str) -> str:
        value = text.strip()

        if value.startswith("```json"):
            value = value.removeprefix("```json").strip()
        elif value.startswith("```"):
            value = value.removeprefix("```").strip()

        if value.endswith("```"):
            value = value.removesuffix("```").strip()

        return value
