from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv


@dataclass(frozen=True)
class FlaskSettings:
    secret_key: str = "chainlottery-dev-secret"
    debug: bool = True


@dataclass(frozen=True)
class Web3Settings:
    rpc_url: str
    contract_address: str
    abi_path: str
    oracle_signer: Optional[str] = None


@dataclass(frozen=True)
class AppSettings:
    flask: FlaskSettings
    web3: Web3Settings
    database_url: str
    admin_api_key: Optional[str]


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


@lru_cache(maxsize=1)
def load_settings(dotenv_path: Optional[str] = None) -> AppSettings:
    if dotenv_path:
        load_dotenv(dotenv_path)
    else:
        load_dotenv()

    flask_settings = FlaskSettings(
        secret_key=os.getenv("FLASK_SECRET_KEY", "chainlottery-dev-secret"),
        debug=os.getenv("FLASK_DEBUG", "1") == "1",
    )

    abi_path = os.getenv(
        "LOTTERY_ABI_PATH", "artifacts/contracts/LotteryCore.sol/LotteryCore.json"
    )

    web3_settings = Web3Settings(
        rpc_url=_require("RPC_URL"),
        contract_address=_require("LOTTERY_CONTRACT_ADDRESS"),
        abi_path=abi_path,
        oracle_signer=os.getenv("ORACLE_SIGNER"),
    )

    database_url = os.getenv("DATABASE_URL", "sqlite:///chainlottery.db")
    admin_api_key = os.getenv("ADMIN_API_KEY")

    return AppSettings(
        flask=flask_settings,
        web3=web3_settings,
        database_url=database_url,
        admin_api_key=admin_api_key,
    )
