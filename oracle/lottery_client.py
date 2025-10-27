from __future__ import annotations

import asyncio
import json
import pathlib
from typing import Any, Iterable, Sequence

from web3 import Web3
from web3.contract import Contract
from web3.middleware import geth_poa_middleware

from .config import OracleSettings
from .types import PeriodSnapshot, PeriodStatus


class LotteryClient:
    """Wrapper around `LotteryCore` contract interactions."""

    def __init__(self, settings: OracleSettings) -> None:
        self._settings = settings
        self._web3 = Web3(Web3.HTTPProvider(settings.rpc_url))
        if self._web3.is_connected() is False:
            raise RuntimeError("Failed to connect to RPC endpoint")

        # For PoA testnets (e.g. Hardhat, Goerli) insert the middleware.
        self._web3.middleware_onion.inject(geth_poa_middleware, layer=0)

        abi = self._load_abi(settings.contract.abi_path)
        self._contract: Contract = self._web3.eth.contract(
            address=Web3.to_checksum_address(settings.contract.address),
            abi=abi,
        )

        self._account = self._web3.eth.account.from_key(settings.private_key)

    @staticmethod
    def _load_abi(path: str) -> Sequence[dict[str, Any]]:
        artifact_path = pathlib.Path(path)
        if not artifact_path.exists():
            raise FileNotFoundError(f"Contract artifact not found: {artifact_path}")
        with artifact_path.open("r", encoding="utf-8") as fh:
            artifact = json.load(fh)
        abi = artifact.get("abi")
        if not isinstance(abi, list):
            raise ValueError("Invalid artifact file: missing ABI")
        return abi

    async def get_current_period(self) -> PeriodSnapshot:
        return await asyncio.to_thread(self._sync_get_current_period)

    def _sync_get_current_period(self) -> PeriodSnapshot:
        period_id = self._contract.functions.currentPeriodId().call()
        period_tuple = self._contract.functions.getPeriod(period_id).call()
        # getPeriod returns (status, resultSet, winningNumbers, mask, ticketCount, totalSales, paidOut)
        status_value = int(period_tuple[0])
        status = PeriodStatus(status_value)
        winning_numbers = [int(x) for x in period_tuple[2]]
        ticket_count = int(period_tuple[4])
        result_set = bool(period_tuple[1])
        return PeriodSnapshot(
            period_id=int(period_id),
            status=status,
            result_set=result_set,
            winning_numbers=winning_numbers,
            ticket_count=ticket_count,
        )

    async def submit_result(self, period_id: int, numbers: Iterable[int]) -> str:
        sorted_numbers = tuple(sorted(int(n) for n in numbers))
        if len(sorted_numbers) != 6:
            raise ValueError("submit_result expects exactly 6 numbers")

        return await asyncio.to_thread(self._sync_submit_result, period_id, sorted_numbers)

    def _sync_submit_result(self, period_id: int, numbers: Sequence[int]) -> str:
        web3 = self._web3
        settings = self._settings
        contract_fn = self._contract.functions.submitResult(period_id, list(numbers))

        nonce = web3.eth.get_transaction_count(self._account.address)
        gas_price = web3.eth.gas_price

        tx: dict[str, Any] = contract_fn.build_transaction(
            {
                "from": self._account.address,
                "nonce": nonce,
                "gas": settings.contract.gas_limit,
                "gasPrice": gas_price,
            }
        )
        if settings.chain_id is not None:
            tx["chainId"] = settings.chain_id

        signed_tx = self._account.sign_transaction(tx)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
        receipt = web3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=180, poll_latency=2, confirmations=settings.contract.confirmations
        )
        if receipt.status != 1:
            raise RuntimeError(f"submitResult reverted: tx={tx_hash.hex()}")
        return tx_hash.hex()
