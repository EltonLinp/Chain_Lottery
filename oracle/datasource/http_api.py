from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import requests

from .base import DrawData, ResultDataSource


@dataclass(frozen=True)
class HttpJsonDataSourceConfig:
    """Configuration describing how to parse the upstream JSON payload."""

    url: str
    issue_key: str = "issue_id"
    numbers_key: str = "numbers"
    date_key: str = "draw_date"
    timeout_seconds: int = 10


class HttpJsonDataSource(ResultDataSource):
    """Fetch draw data from a JSON HTTP endpoint."""

    def __init__(self, config: HttpJsonDataSourceConfig) -> None:
        self._config = config

    async def fetch_latest(self) -> DrawData:
        response_json = await asyncio.to_thread(
            self._get_json, self._config.url, self._config.timeout_seconds
        )
        return self._parse_payload(response_json)

    @staticmethod
    def _get_json(url: str, timeout_seconds: int) -> Mapping[str, Any]:
        resp = requests.get(url, timeout=timeout_seconds)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, Mapping):
            raise ValueError("HTTP API returned non-object payload")
        return data

    def _parse_payload(self, payload: Mapping[str, Any]) -> DrawData:
        cfg = self._config
        try:
            issue_id = str(payload[cfg.issue_key])
        except KeyError as exc:
            raise ValueError(f"Missing issue id field: {cfg.issue_key}") from exc

        try:
            raw_numbers = payload[cfg.numbers_key]
        except KeyError as exc:
            raise ValueError(f"Missing numbers field: {cfg.numbers_key}") from exc

        numbers = self._parse_numbers(raw_numbers)
        draw_date = self._parse_date(payload.get(cfg.date_key))

        return DrawData(issue_id=issue_id, draw_date=draw_date, numbers=numbers)

    @staticmethod
    def _parse_numbers(raw: Any) -> Sequence[int]:
        if not isinstance(raw, Iterable):
            raise ValueError("numbers field must be iterable")
        numbers = []
        for value in raw:
            if not isinstance(value, int):
                raise ValueError("numbers must be integers")
            numbers.append(value)
        if len(numbers) == 0:
            raise ValueError("numbers field empty")
        return tuple(numbers)

    @staticmethod
    def _parse_date(raw: Any) -> dt.datetime:
        if raw is None:
            return dt.datetime.utcnow()
        if isinstance(raw, (int, float)):
            return dt.datetime.utcfromtimestamp(raw)
        if isinstance(raw, str):
            try:
                # ISO-8601 parsing
                return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Invalid date string format") from exc
        raise ValueError("Unrecognized draw date format")
