from pydantic import BaseModel


class AftersalesEligibilityResponse(BaseModel):
    order_no: str
    refundable: bool
    exchangeable: bool
    resendable: bool
    requires_human_review: bool
    reasons: list[str]
    ticket_no: str | None = None
