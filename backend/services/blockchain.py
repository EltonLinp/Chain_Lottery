from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from typing import Iterable, Optional, Sequence, TYPE_CHECKING, Any, Dict, Tuple

try:  # pragma: no cover - runtime compatibility shim for older eth_typing
    import eth_typing  # type: ignore
except ImportError:  # pragma: no cover
    eth_typing = None  # type: ignore
else:  # pragma: no cover
    from typing import NewType

    if not hasattr(eth_typing, "ChainId"):
        eth_typing.ChainId = NewType("ChainId", int)  # type: ignore[attr-defined]
        all_attr = getattr(eth_typing, "__all__", None)
        if isinstance(all_attr, (list, tuple)):
            if "ChainId" not in all_attr:
                eth_typing.__all__ = tuple(list(all_attr) + ["ChainId"])  # type: ignore[attr-defined]
        elif all_attr is None:
            eth_typing.__all__ = ("ChainId",)  # type: ignore[attr-defined]

if TYPE_CHECKING:  # pragma: no cover
    from web3 import Web3
    from web3.contract import Contract
    from eth_account import Account  # type: ignore

PERIOD_STATUS = {
    0: "Selling",
    1: "Closed",
    2: "ResultIn",
    3: "Settled",
}


def _ensure_event_loop() -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)


class LotteryBlockchainClient:
    """Wrapper around web3 interactions with the LotteryCore contract."""

    def __init__(self, web3: "Web3", contract: "Contract", signer_key: Optional[str] = None) -> None:
        self._web3 = web3
        self._contract = contract
        self._address = contract.address
        self._account = web3.eth.account.from_key(signer_key) if signer_key else None  # type: ignore[attr-defined]

    @classmethod
    def from_artifact(
        cls,
        rpc_url: str,
        contract_address: str,
        artifact_path: str,
        signer_key: Optional[str] = None,
    ) -> "LotteryBlockchainClient":
        _ensure_event_loop()
        from web3 import Web3
        from web3.middleware import geth_poa_middleware

        artifact = cls._load_artifact(artifact_path)
        abi = artifact.get("abi")
        if abi is None:
            raise ValueError(f"ABI not found in artifact: {artifact_path}")

        web3 = Web3(Web3.HTTPProvider(rpc_url))
        if not web3.is_connected():
            raise ConnectionError(f"Cannot connect to RPC endpoint: {rpc_url}")

        # Inject PoA middleware to support networks such as Hardhat or Polygon.
        web3.middleware_onion.inject(geth_poa_middleware, layer=0)

        contract = web3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)
        return cls(web3, contract, signer_key=signer_key)

    @staticmethod
    def _load_artifact(path: str) -> Dict[str, Any]:
        artifact_path = Path(path)
        if not artifact_path.exists():
            raise FileNotFoundError(f"Contract artifact not found: {artifact_path}")
        with artifact_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    @property
    def address(self) -> str:
        return self._address

    @property
    def chain_id(self) -> Optional[int]:
        try:
            return int(self._web3.eth.chain_id)
        except Exception:  # pragma: no cover - defensive
            return None

    async def get_period(self, period_id: int) -> Dict[str, Any]:
        def call():
            return self._contract.functions.getPeriod(int(period_id)).call()

        data = await asyncio.to_thread(call)
        status_code, result_set, winning_numbers, mask, ticket_count, total_sales, paid_out = data
        status = PERIOD_STATUS.get(int(status_code), f"Unknown({status_code})")
        return {
            "status_code": int(status_code),
            "status": status,
            "result_set": bool(result_set),
            "winning_numbers": [int(x) for x in list(winning_numbers)],
            "winning_mask": int(mask),
            "ticket_count": int(ticket_count),
            "total_sales": int(total_sales),
            "paid_out": int(paid_out),
        }

    async def get_current_period(self) -> int:
        return await asyncio.to_thread(self._contract.functions.currentPeriodId().call)

    async def get_ticket_price(self) -> int:
        return await asyncio.to_thread(self._contract.functions.ticketPrice().call)

    async def close_current_period(self) -> str:
        return await asyncio.to_thread(self._close_current_period_sync)

    async def submit_result(self, period_id: int, numbers: Iterable[int]) -> str:
        return await asyncio.to_thread(self._submit_result_sync, int(period_id), tuple(numbers))

    async def settle_period(self, period_id: int) -> str:
        return await asyncio.to_thread(self._settle_period_sync, int(period_id))

    async def open_next_period(self) -> str:
        return await asyncio.to_thread(self._open_next_period_sync)

    async def buy_ticket(self, numbers: Iterable[int], token_uri: str = "") -> Dict[str, Any]:
        normalised = self._normalise_numbers(numbers)
        return await asyncio.to_thread(self._buy_ticket_sync, normalised, token_uri or "")

    async def claim_prize(self, token_id: int) -> str:
        return await asyncio.to_thread(self._claim_prize_sync, int(token_id))

    async def estimate_matches(self, period_id: int, numbers: Iterable[int]) -> int:
        normalised = self._normalise_numbers(numbers)

        def call() -> int:
            period = self._contract.functions.getPeriod(int(period_id)).call()
            result_set = bool(period[1])
            if not result_set:
                return 0
            winning_numbers = [int(x) for x in period[2]]
            return len(set(normalised).intersection(winning_numbers))

        return await asyncio.to_thread(call)

    async def get_ticket(self, token_id: int) -> Dict[str, Any]:
        def call():
            return self._contract.functions.getTicket(int(token_id)).call()

        data = await asyncio.to_thread(call)
        period_id, buyer, numbers, number_mask, stake, claimed = data
        return {
            "token_id": int(token_id),
            "period_id": int(period_id),
            "buyer": buyer,
            "numbers": [int(x) for x in list(numbers)],
            "stake": int(stake),
            "claimed": bool(claimed),
            "number_mask": int(number_mask),
        }

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _ensure_account(self):
        if self._account is None:
            raise RuntimeError("Blockchain signer not configured; set ORACLE_SIGNER in .env")
        return self._account

    @staticmethod
    def _normalise_numbers(numbers: Iterable[int]) -> Tuple[int, ...]:
        sorted_numbers = tuple(sorted(int(n) for n in numbers))
        if len(sorted_numbers) != 6:
            raise ValueError("Exactly six numbers are required.")
        previous = 0
        for number in sorted_numbers:
            if number < 1 or number > 35:
                raise ValueError("Numbers must be between 1 and 35.")
            if number <= previous:
                raise ValueError("Numbers must be strictly ascending.")
            previous = number
        return sorted_numbers

    def _buy_ticket_sync(self, numbers: Sequence[int], token_uri: str) -> Dict[str, Any]:
        account = self._ensure_account()
        ticket_price = int(self._contract.functions.ticketPrice().call())
        fn = self._contract.functions.buyTicket(list(numbers), token_uri)
        tx_meta = self._send_transaction(fn, {"from": account.address, "value": ticket_price})

        token_id = self._extract_token_id(tx_meta["receipt"])
        if token_id is None:
            raise RuntimeError("Unable to determine ticket ID from transaction logs.")

        return {
            "tx_hash": tx_meta["tx_hash"],
            "token_id": int(token_id),
        }

    def _claim_prize_sync(self, token_id: int) -> str:
        account = self._ensure_account()
        fn = self._contract.functions.claimPrize(int(token_id))
        tx_meta = self._send_transaction(fn, {"from": account.address})
        return tx_meta["tx_hash"]

    def _send_transaction(self, fn, tx_params: Dict[str, Any]) -> Dict[str, Any]:
        account = self._ensure_account()
        tx_params = dict(tx_params)
        tx_params.setdefault("from", account.address)

        try:
            gas_estimate = fn.estimate_gas(tx_params)
        except Exception:  # pragma: no cover - rely on conservative gas limit if estimation fails
            gas_estimate = 350000

        gas_limit = max(int(math.ceil(gas_estimate * 1.2)), 250000)
        nonce = self._web3.eth.get_transaction_count(account.address)

        tx = fn.build_transaction(
            {
                **tx_params,
                "nonce": nonce,
                "gas": gas_limit,
                "gasPrice": self._web3.eth.gas_price,
            }
        )

        chain_id = self.chain_id
        if chain_id is not None:
            tx["chainId"] = chain_id

        signed = account.sign_transaction(tx)
        tx_hash = self._web3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = self._web3.eth.wait_for_transaction_receipt(tx_hash, timeout=180, poll_latency=2)
        if getattr(receipt, "status", 0) != 1:
            raise RuntimeError(f"Transaction reverted: {tx_hash.hex()}")

        return {"tx_hash": tx_hash.hex(), "receipt": receipt}

    def _transact(self, fn) -> str:
        account = self._ensure_account()
        meta = self._send_transaction(fn, {"from": account.address})
        return meta["tx_hash"]

    def _close_current_period_sync(self) -> str:
        fn = self._contract.functions.closeCurrentPeriod()
        return self._transact(fn)

    def _submit_result_sync(self, period_id: int, numbers: Sequence[int]) -> str:
        normalised = self._normalise_numbers(numbers)
        fn = self._contract.functions.submitResult(int(period_id), list(normalised))
        return self._transact(fn)

    def _settle_period_sync(self, period_id: int) -> str:
        fn = self._contract.functions.settlePeriod(int(period_id))
        return self._transact(fn)

    def _open_next_period_sync(self) -> str:
        fn = self._contract.functions.openNextPeriod()
        return self._transact(fn)

    def _extract_token_id(self, receipt) -> Optional[int]:
        try:
            events = self._contract.events.TicketPurchased().process_receipt(receipt)
            if events:
                return int(events[0]["args"]["tokenId"])
        except Exception:  # pragma: no cover
            return None
        return None
