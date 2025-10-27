from __future__ import annotations

import asyncio
import json
import logging
import pathlib
from dataclasses import dataclass
from typing import Optional, Protocol

from .config import OracleSettings
from .datasource import DrawData, ResultDataSource
from .types import PeriodStatus, PeriodSnapshot


class LotteryClientProtocol(Protocol):
    async def get_current_period(self) -> PeriodSnapshot:
        ...

    async def submit_result(self, period_id: int, numbers) -> str:
        ...


@dataclass
class SchedulerResult:
    period_id: int
    issue_id: str
    tx_hash: str


class OracleStateStore:
    """Very small persistence layer to avoid resubmitting the same draw."""

    def __init__(self, path: str) -> None:
        self._path = pathlib.Path(path)

    def load_last_issue(self) -> Optional[str]:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return data.get("last_issue_id")

    def save_last_issue(self, issue_id: str) -> None:
        payload = {"last_issue_id": issue_id}
        self._path.write_text(json.dumps(payload), encoding="utf-8")


class OracleScheduler:
    def __init__(
        self,
        settings: OracleSettings,
        datasource: ResultDataSource,
        client: LotteryClientProtocol,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._settings = settings
        self._datasource = datasource
        self._client = client
        self._state = OracleStateStore(settings.state_file)
        self._last_issue_id = self._state.load_last_issue()
        self._logger = logger or logging.getLogger("chainlottery.oracle")

    async def run_forever(self) -> None:
        interval = self._settings.poll_interval_seconds
        self._logger.info("Oracle loop started; poll interval=%s", interval)
        while True:
            try:
                should_continue = await self._attempt_submission()
                if not should_continue and self._settings.submit_only_once:
                    self._logger.info("Submit-once flag set; exiting loop.")
                    return
            except Exception as exc:
                self._logger.exception("Oracle iteration failed: %s", exc)
            await asyncio.sleep(interval)

    async def run_once(self) -> Optional[SchedulerResult]:
        try:
            return await self._attempt_submission()
        finally:
            await self._datasource.close()

    async def _attempt_submission(self) -> Optional[SchedulerResult]:
        draw = await self._datasource.fetch_latest()

        if self._last_issue_id == draw.issue_id:
            self._logger.debug("Issue %s already submitted; skipping.", draw.issue_id)
            return None

        period_snapshot = await self._client.get_current_period()
        if period_snapshot.status != PeriodStatus.CLOSED:
            self._logger.info(
                "Current period %s not closed yet (status=%s); waiting.",
                period_snapshot.period_id,
                period_snapshot.status.name,
            )
            return None
        if period_snapshot.result_set:
            self._logger.info(
                "Period %s already has results on-chain; skipping.", period_snapshot.period_id
            )
            return None

        sorted_numbers = draw.sorted_numbers()
        self._logger.info(
            "Submitting oracle result for period %s issue %s -> %s",
            period_snapshot.period_id,
            draw.issue_id,
            sorted_numbers,
        )
        tx_hash = await self._client.submit_result(period_snapshot.period_id, sorted_numbers)
        self._logger.info("submitResult broadcast: %s", tx_hash)

        self._last_issue_id = draw.issue_id
        self._state.save_last_issue(draw.issue_id)

        return SchedulerResult(
            period_id=period_snapshot.period_id,
            issue_id=draw.issue_id,
            tx_hash=tx_hash,
        )
