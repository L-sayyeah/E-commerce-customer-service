"""Resolve dialogue references from user turns without treating them as business facts."""

import re
from dataclasses import dataclass, field

from app.agents.intent_classifier import ORDER_NO_PATTERN

TICKET_PATTERN = re.compile(r"(?<![A-Z0-9])TK[A-Z0-9]{8,32}(?![A-Z0-9])", re.IGNORECASE)
REGIONS = ("美国", "欧盟", "英国", "加拿大", "澳洲", "日本", "韩国")
ORDER_COUNTRIES = {
    "US": "美国", "EU": "欧盟", "UK": "英国", "GB": "英国", "AU": "澳洲",
    "CA": "加拿大", "JP": "日本", "KR": "韩国",
}
POLICY_SCOPE_CONFIRMATION = "policy_scope_confirmation"
ORDER_SCOPE = re.compile(r"这单|那单|这笔|那笔|该订单|原订单|这(?:个|笔)订单|刚才.*订单")
POLICY_REQUEST = re.compile(r"政策|规则|条例|条款|窗口|期限|时效|到账|退货|签收后.{0,8}多少天")
BROAD_RETURN = re.compile(
    r"退货规则|退货政策|无理由退货|退货期限|退货窗口|退货条件|退货怎么(?:办|处理)|"
    r"还能退|能退吗|多久能退|签收后.{0,8}多少天"
)
FOLLOW_UP = re.compile(r"^那|这单|这个订单|该订单|它|上一笔|前一笔|最后一笔|还能|那.*[呢吗]|之前.*订单")
RESET_ORDER = re.compile(r"另一笔|换一单|另一个订单|不是这单|不是这个订单|别查这单")
ORDINAL = re.compile(r"第([一二三四五六七八九1-9])(?:笔|单|个订单)")
NUMBERS = "一二三四五六七八九"


@dataclass
class DialogueState:
    orders: list[str] = field(default_factory=list)
    active_order: str | None = None
    ambiguous_order: bool = False
    order_source: int | None = None
    policy_regions: tuple[str, ...] = ()
    policy_region_source: int | None = None
    ticket_no: str | None = None
    turn: int = 0

    def apply(self, text: str) -> None:
        self.turn += 1
        mentioned = list(dict.fromkeys(ORDER_NO_PATTERN.findall(text.upper())))
        for order in mentioned:
            if order not in self.orders:
                self.orders.append(order)

        selected = None
        changes_order = bool(mentioned or RESET_ORDER.search(text) or ORDINAL.search(text))
        if len(mentioned) == 1:
            selected = mentioned[0]
        elif len(mentioned) > 1:
            correction = re.split(r"改成|换成|说错了[，,\s]*是|应该是", text)
            if len(correction) > 1:
                corrected = set(ORDER_NO_PATTERN.findall(correction[-1].upper()))
                if len(corrected) == 1:
                    selected = corrected.pop()
        elif match := ORDINAL.search(text):
            number = match[1]
            index = int(number) - 1 if number.isdigit() else NUMBERS.index(number)
            if index < len(self.orders):
                selected = self.orders[index]
        elif "最后一笔" in text and self.orders:
            changes_order = True
            selected = self.orders[-1]

        if changes_order:
            self.active_order = selected
            self.ambiguous_order = selected is None
            self.order_source = self.turn if selected is not None else None

        regions = regions_in(text)
        if regions and not mentioned and not ORDER_SCOPE.search(text):
            self.policy_regions = regions
            self.policy_region_source = self.turn
        tickets = set(TICKET_PATTERN.findall(text.upper()))
        if tickets:
            self.ticket_no = tickets.pop() if len(tickets) == 1 else None

    def for_turn(self, text: str) -> dict:
        self.apply(text)
        follow_up = bool(FOLLOW_UP.search(text) or ORDINAL.search(text) or RESET_ORDER.search(text))
        explicit_order = bool(ORDER_NO_PATTERN.search(text.upper()))
        resolves_order = explicit_order or follow_up
        ticket_is_relevant = "工单" in text or TICKET_PATTERN.search(text)
        return {
            "version": 1,
            "turn": self.turn,
            "active_order": self.active_order,
            "order_no": self.active_order if resolves_order else None,
            "ambiguous_order": resolves_order and self.ambiguous_order,
            "order_source": self.order_source if resolves_order else None,
            "order_inherited": bool(follow_up and self.active_order and not explicit_order),
            "region": self.policy_regions[0] if (
                follow_up and len(self.policy_regions) == 1 and self.policy_region_source != self.turn
            ) else None,
            "region_source": self.policy_region_source,
            "ticket_no": self.ticket_no if ticket_is_relevant else None,
            "follow_up": follow_up,
        }



def regions_in(text: str) -> tuple[str, ...]:
    normalized = text.replace("澳大利亚", "澳洲")
    return tuple(region for region in REGIONS if region in normalized)


def has_order_scope(text: str) -> bool:
    return bool(ORDER_SCOPE.search(text) or ORDINAL.search(text) or ORDER_NO_PATTERN.search(text.upper()))


def needs_verified_policy_order(text: str, pending_question: str | None) -> bool:
    return bool(pending_question or (POLICY_REQUEST.search(text) and (
        has_order_scope(text) or (FOLLOW_UP.search(text) and not regions_in(text))
    )))



def pending_policy_question(messages: list[dict]) -> str | None:
    index = len(messages) - 1
    while index >= 1 and (
        messages[index]["role"] == "assistant"
        and messages[index].get("message_type") == POLICY_SCOPE_CONFIRMATION
        and messages[index - 1]["role"] == "user"
    ):
        text = messages[index - 1]["content"]
        if POLICY_REQUEST.search(text):
            return text
        index -= 2
    return None

def resolve_policy_scope(
    dialogue: dict,
    text: str,
    previous_policy_regions: tuple[str, ...],
    verified_order_region: str | None,
    pending_question: str | None = None,
) -> dict:
    explicit_regions = regions_in(text)
    order_scope = has_order_scope(text)
    choices = tuple(dict.fromkeys(
        (*previous_policy_regions, *((verified_order_region,) if verified_order_region else ()))
    ))

    if pending_question:
        choice = re.sub(r"[，。？、！,.?!\s]+", "", text.replace("澳大利亚", "澳洲"))
        region_choice = next((
            region for region in choices
            if re.fullmatch(r"(?:我问的是|我想问|问|是)?"
                            + re.escape(region) + r"(?:的|政策|订单|的政策|的订单)?", choice)
        ), None)
        order_choice = bool(re.fullmatch(r"(?:是|我问的是)?(?:这单|那单|原订单|刚才那单|刚才的订单)", choice))
        if region_choice or order_choice:
            chosen = verified_order_region if order_choice else region_choice
            if chosen is None:
                return {**dialogue, "clarification_prompt": "请提供要核对的订单号，或告诉我想查哪个地区的政策。"}
            return {
                **dialogue, "region": chosen, "policy_intent": True,
                "clarified_question": pending_question,
                "order_no": dialogue.get("order_no") if order_choice else None,
                "ambiguous_order": False,
            }
        if re.fullmatch(r"对|是|是的|不清楚|不知道|这个|那个", choice):
            prompt = (
                "请确认您要查哪个地区的退货规则（" + "、".join(choices) + "）。"
                if len(choices) > 1 else "请告诉我想查哪个地区的政策，或明确是刚才那笔订单。"
            )
            return {**dialogue, "order_no": None, "clarification_prompt": prompt}

    if not POLICY_REQUEST.search(text):
        return dialogue

    if explicit_regions and not order_scope:
        return {**dialogue, "region": None, "order_no": None, "ambiguous_order": False, "policy_intent": True}

    if order_scope and re.search(r"政策|规则|条例|条款|窗口|期限", text):
        if dialogue.get("ambiguous_order"):
            return dialogue
        if verified_order_region:
            return {**dialogue, "region": verified_order_region, "policy_intent": True}
        return {**dialogue, "clarification_prompt": "请提供要核对的订单号，或告诉我想查哪个地区的政策。"}

    if not order_scope and not explicit_regions and dialogue.get("follow_up"):
        if BROAD_RETURN.search(text) and len(choices) > 1:
            if len(previous_policy_regions) == 1 and verified_order_region:
                prompt = (f"您是想问{previous_policy_regions[0]}的一般退货规则，"
                          f"还是刚才那笔{verified_order_region}订单的退货规则？")
            else:
                prompt = "请确认您要查哪个地区的退货规则（" + "、".join(choices) + "）。"
            return {**dialogue, "order_no": None, "clarification_prompt": prompt}
        if BROAD_RETURN.search(text) and previous_policy_regions and dialogue.get("active_order") and not verified_order_region:
            prompt = (f"您是想问{previous_policy_regions[0]}的一般退货规则，"
                      "还是刚才那笔订单的退货规则？")
            return {**dialogue, "order_no": None, "clarification_prompt": prompt}
        if len(previous_policy_regions) == 1 and not dialogue.get("ambiguous_order"):
            return {**dialogue, "region": previous_policy_regions[0], "order_no": None, "policy_intent": True}

    return dialogue


def policy_query(question: str, dialogue: dict) -> tuple[str, str | None]:
    question = dialogue.get("clarified_question") or question
    region = dialogue.get("region")
    return question, f"{region}售后政策：{question}" if region else None
