import asyncio
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from oracle.config import ContractSettings, DataSourceSettings, OracleSettings
from oracle.datasource.base import DrawData, ResultDataSource
from oracle.scheduler import OracleScheduler
from oracle.types import PeriodSnapshot, PeriodStatus


class FakeDataSource(ResultDataSource):
    def __init__(self, draw: DrawData) -> None:
        self._draw = draw
        self.closed = False
        self.calls = 0

    async def fetch_latest(self) -> DrawData:
        self.calls += 1
        return self._draw

    async def close(self) -> None:
        self.closed = True


class FakeClient:
    def __init__(self, snapshot: PeriodSnapshot, tx_hash: str = "0x123") -> None:
        self._snapshot = snapshot
        self.tx_hash = tx_hash
        self.submissions = []

    async def get_current_period(self) -> PeriodSnapshot:
        return self._snapshot

    async def submit_result(self, period_id: int, numbers):
        self.submissions.append((period_id, tuple(numbers)))
        return self.tx_hash


class OracleSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self._tmpdir.name) / "state.json"

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _make_settings(self) -> OracleSettings:
        return OracleSettings(
            rpc_url="http://localhost:8545",
            private_key="0x" + "1" * 64,
            poll_interval_seconds=5,
            submit_only_once=True,
            state_file=str(self.state_path),
            datasource=DataSourceSettings(url="http://example.test"),
            contract=ContractSettings(address="0x" + "0" * 40),
        )

    def test_scheduler_skips_when_period_not_closed(self) -> None:
        settings = self._make_settings()
        draw = DrawData(issue_id="2025-001", draw_date=dt.datetime.utcnow(), numbers=[1, 2, 3, 4, 5, 6])
        datasource = FakeDataSource(draw)
        snapshot = PeriodSnapshot(
            period_id=1,
            status=PeriodStatus.SELLING,
            result_set=False,
            winning_numbers=(0, 0, 0, 0, 0, 0),
            ticket_count=10,
        )
        client = FakeClient(snapshot)
        scheduler = OracleScheduler(settings, datasource, client)

        result = asyncio.run(scheduler.run_once())

        self.assertIsNone(result)
        self.assertEqual(datasource.calls, 1)
        self.assertEqual(client.submissions, [])

    def test_scheduler_submits_closed_period_and_persists_state(self) -> None:
        settings = self._make_settings()
        draw = DrawData(issue_id="2025-002", draw_date=dt.datetime.utcnow(), numbers=[8, 9, 10, 11, 12, 13])
        datasource = FakeDataSource(draw)
        snapshot = PeriodSnapshot(
            period_id=2,
            status=PeriodStatus.CLOSED,
            result_set=False,
            winning_numbers=(0, 0, 0, 0, 0, 0),
            ticket_count=40,
        )
        client = FakeClient(snapshot, tx_hash="0xabc")
        scheduler = OracleScheduler(settings, datasource, client)

        result = asyncio.run(scheduler.run_once())

        self.assertIsNotNone(result)
        self.assertEqual(result.period_id, 2)
        self.assertEqual(result.tx_hash, "0xabc")
        self.assertTrue(datasource.closed)
        self.assertEqual(client.submissions, [(2, (8, 9, 10, 11, 12, 13))])

        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["last_issue_id"], "2025-002")


if __name__ == "__main__":
    unittest.main()
