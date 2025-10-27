from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, validator


class TicketPurchaseRequest(BaseModel):
    numbers: List[int] = Field(..., description="6 numbers in ascending order.")
    token_uri: Optional[str] = Field(None, description="Optional metadata URI for the ticket NFT.")

    @validator("numbers")
    def validate_numbers(cls, value: List[int]) -> List[int]:
        if len(value) != 6:
            raise ValueError("Lottery tickets require exactly 6 numbers.")
        if sorted(value) != value:
            raise ValueError("Numbers must be sorted ascending.")
        if len(set(value)) != 6:
            raise ValueError("Numbers must be unique.")
        for n in value:
            if not 1 <= n <= 35:
                raise ValueError("Numbers must be between 1 and 35.")
        return value


class TicketPurchaseResponse(BaseModel):
    ticket_id: str
    period_id: int
    status: str


class TicketStatusResponse(BaseModel):
    ticket_id: str
    period_id: int
    numbers: List[int]
    status: str
    matches: Optional[int] = None
    payout: Optional[str] = None
    claimed: bool = False


class ClaimTicketResponse(BaseModel):
    ticket_id: str
    period_id: int
    tx_hash: str
    payout: str


class DrawSubmissionRequest(BaseModel):
    period_id: Optional[int] = None
    winning_numbers: List[int]

    _validate_numbers = validator("winning_numbers", allow_reuse=True)(TicketPurchaseRequest.validate_numbers)


class AdminPeriodResponse(BaseModel):
    period_id: int
    ticket_count: int
    settled_count: int
    claimed_count: int
    winning_numbers: Optional[List[int]] = None
