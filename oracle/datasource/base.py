from __future__ import annotations

import abc
import datetime as dt
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class DrawData:
    """Normalized draw payload returned by data sources."""

    issue_id: str
    draw_date: dt.datetime
    numbers: Sequence[int]

    def sorted_numbers(self) -> Sequence[int]:
        return tuple(sorted(self.numbers))


class ResultDataSource(abc.ABC):
    """Abstract result provider."""

    @abc.abstractmethod
    async def fetch_latest(self) -> DrawData:
        """Return the newest draw that has not been submitted yet.

        Implementations should raise `RuntimeError` or `ValueError` if
        remote data is unavailable or validation fails.
        """

    async def close(self) -> None:
        """Optional hook for connectors that require cleanup."""
        return None
