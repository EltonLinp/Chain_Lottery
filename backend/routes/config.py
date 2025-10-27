from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict

from flask import Blueprint, current_app, jsonify

from ..config import load_settings
from ..services.blockchain import LotteryBlockchainClient

bp = Blueprint("config", __name__)


def _load_abi(artifact_path: str):
    try:
        path = Path(artifact_path)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            artifact = json.load(fh)
        abi = artifact.get("abi")
        return abi if isinstance(abi, list) else None
    except Exception:  # pragma: no cover - best effort
        return None


def _get_blockchain_metadata() -> Dict[str, Any]:
    settings = load_settings()
    payload: Dict[str, Any] = {
        "rpc_url": settings.web3.rpc_url,
        "contract_address": settings.web3.contract_address,
        "chain_id": None,
        "ticket_price_wei": None,
    }

    try:
        client = LotteryBlockchainClient.from_artifact(
            settings.web3.rpc_url,
            settings.web3.contract_address,
            settings.web3.abi_path,
            signer_key=settings.web3.oracle_signer,
        )
        payload["chain_id"] = client.chain_id
        ticket_price = asyncio.run(client.get_ticket_price())
        payload["ticket_price_wei"] = str(ticket_price)
    except Exception as exc:  # pragma: no cover - swallow connectivity issues
        current_app.logger.warning("Unable to query blockchain metadata: %s", exc)

    abi = _load_abi(settings.web3.abi_path)
    if abi:
        payload["abi"] = abi
    return payload


@bp.get("/config")
def get_config():
    data = _get_blockchain_metadata()
    return jsonify(data)
