from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv


def _bool_from_env(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_from_env(value: Optional[str], default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _require_env(key: str) -> str:
    value = os.getenv(key)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


@dataclass(frozen=True)
class DataSourceSettings:
    url: str
    issue_key: str = "issue_id"
    numbers_key: str = "numbers"
    date_key: str = "draw_date"
    timeout_seconds: int = 10


@dataclass(frozen=True)
class ContractSettings:
    address: str
    abi_path: str = "artifacts/contracts/LotteryCore.sol/LotteryCore.json"
    gas_limit: int = 250000
    confirmations: int = 1


@dataclass(frozen=True)
class OracleSettings:
    rpc_url: str
    private_key: str
    poll_interval_seconds: int = 30
    submit_only_once: bool = False
    state_file: str = "oracle_state.json"
    chain_id: Optional[int] = None
    datasource: DataSourceSettings = DataSourceSettings(url="")
    contract: ContractSettings = ContractSettings(address="0x" + "0" * 40)

    def copy(self, **updates) -> "OracleSettings":
        return replace(self, **updates)


def load_from_environment() -> OracleSettings:
    rpc_url = _require_env("RPC_URL")
    private_key = _require_env("ORACLE_PRIVATE_KEY")

    poll_interval = _int_from_env(os.getenv("POLL_INTERVAL_SECONDS"), 30)
    submit_only_once = _bool_from_env(os.getenv("SUBMIT_ONCE"), False)
    state_file = os.getenv("STATE_FILE", "oracle_state.json")
    chain_id = os.getenv("CHAIN_ID")
    chain_id_int = int(chain_id) if chain_id else None

    datasource = DataSourceSettings(
        url=os.getenv("DATASOURCE__URL", ""),
        issue_key=os.getenv("DATASOURCE__ISSUE_KEY", "issue_id"),
        numbers_key=os.getenv("DATASOURCE__NUMBERS_KEY", "numbers"),
        date_key=os.getenv("DATASOURCE__DATE_KEY", "draw_date"),
        timeout_seconds=_int_from_env(os.getenv("DATASOURCE__TIMEOUT_SECONDS"), 10),
    )

    contract = ContractSettings(
        address=os.getenv("CONTRACT__ADDRESS", "0x" + "0" * 40),
        abi_path=os.getenv(
            "CONTRACT__ABI_PATH", "artifacts/contracts/LotteryCore.sol/LotteryCore.json"
        ),
        gas_limit=_int_from_env(os.getenv("CONTRACT__GAS_LIMIT"), 250000),
        confirmations=_int_from_env(os.getenv("CONTRACT__CONFIRMATIONS"), 1),
    )

    return OracleSettings(
        rpc_url=rpc_url,
        private_key=private_key,
        poll_interval_seconds=poll_interval,
        submit_only_once=submit_only_once,
        state_file=state_file,
        chain_id=chain_id_int,
        datasource=datasource,
        contract=contract,
    )


@lru_cache(maxsize=1)
def load_config(dotenv_path: Optional[str] = None) -> OracleSettings:
    if dotenv_path:
        load_dotenv(dotenv_path)
    else:
        default_path = pathlib.Path(".env")
        if default_path.exists():
            load_dotenv(default_path)
    return load_from_environment()
