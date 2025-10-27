from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Optional

from .config import OracleSettings, load_config
from .datasource.http_api import HttpJsonDataSource, HttpJsonDataSourceConfig
from .lottery_client import LotteryClient
from .scheduler import OracleScheduler


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stdout,
    )


def build_datasource(settings: OracleSettings) -> HttpJsonDataSource:
    ds_settings = settings.datasource
    if not ds_settings.url:
        raise RuntimeError("DATASOURCE__URL is not configured.")
    datasource = HttpJsonDataSource(
        HttpJsonDataSourceConfig(
            url=ds_settings.url,
            issue_key=ds_settings.issue_key,
            numbers_key=ds_settings.numbers_key,
            date_key=ds_settings.date_key,
            timeout_seconds=ds_settings.timeout_seconds,
        )
    )
    return datasource


async def run(args: argparse.Namespace) -> Optional[str]:
    settings = load_config(args.env_file)
    configure_logging(args.verbose)
    logger = logging.getLogger("chainlottery.oracle")

    datasource = build_datasource(settings)
    client = LotteryClient(settings)
    scheduler = OracleScheduler(settings, datasource, client, logger=logger)

    if args.once or settings.submit_only_once:
        result = await scheduler.run_once()
        if result:
            logger.info("Oracle submitted period=%s tx=%s", result.period_id, result.tx_hash)
            return result.tx_hash
        return None

    await scheduler.run_forever()
    return None


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ChainLottery oracle service")
    parser.add_argument("--env-file", type=str, default=None, help="Path to .env file with credentials")
    parser.add_argument("--once", action="store_true", help="Run only once and exit.")
    parser.add_argument(
        "--verbose", action="store_true", help="Enable debug logging (default INFO)."
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("Oracle stopped by user.")


if __name__ == "__main__":
    main()
