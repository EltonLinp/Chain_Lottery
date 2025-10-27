from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Sequence


class PeriodStatus(IntEnum):
    SELLING = 0
    CLOSED = 1
    RESULT_IN = 2
    SETTLED = 3


@dataclass(frozen=True)
class PeriodSnapshot:
    period_id: int
    status: PeriodStatus
    result_set: bool
    winning_numbers: Sequence[int]
    ticket_count: int
