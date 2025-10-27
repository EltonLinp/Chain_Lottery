from __future__ import annotations

import asyncio
from typing import Dict

from flask import Blueprint, current_app, jsonify, request

try:  # pragma: no cover - ensure eth_typing compatibility before importing web3
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

from web3.exceptions import ContractLogicError

from ..config import load_settings
from ..schemas import AdminPeriodResponse, DrawSubmissionRequest
from ..services.draws import DrawRepository
from ..services.tickets import TicketRepository
from .tickets import get_blockchain_client

bp = Blueprint("admin", __name__)
draw_repo = DrawRepository()
ticket_repo = TicketRepository()


def _require_admin() -> bool:
    settings = load_settings()
    api_key = settings.admin_api_key
    if api_key:
        provided = request.headers.get("X-Admin-Token")
        if provided != api_key:
            return False
    return True


@bp.before_request
def verify_admin():
    if not _require_admin():
        return jsonify({"error": "unauthorized"}), 401
    return None


@bp.get("/periods")
def list_periods():
    periods = ticket_repo.list_periods()
    response = [AdminPeriodResponse(**period).dict() for period in periods]
    return jsonify(response)


@bp.post("/draws")
def submit_draw():
    payload = request.get_json(force=True, silent=True) or {}
    data = DrawSubmissionRequest(**payload)

    try:
        blockchain_client = get_blockchain_client()
    except Exception as exc:  # pragma: no cover
        current_app.logger.exception("Unable to initialise blockchain client: %s", exc)
        return jsonify({"error": "blockchain client unavailable"}), 500

    if getattr(blockchain_client, "_account", None) is None:
        return jsonify({"error": "server signer missing; set ORACLE_SIGNER in environment"}), 400

    try:
        current_period_on_chain = asyncio.run(blockchain_client.get_current_period())
    except Exception as exc:  # pragma: no cover
        current_app.logger.exception("Failed to read current period from chain: %s", exc)
        return jsonify({"error": "failed to read current period from chain"}), 500

    target_period = data.period_id or current_period_on_chain
    if target_period != current_period_on_chain:
        return jsonify({
            "error": f"on-chain settlement is limited to the active period {current_period_on_chain}."
        }), 400

    try:
        period_info = asyncio.run(blockchain_client.get_period(target_period))
    except Exception as exc:  # pragma: no cover
        current_app.logger.exception("Failed to read period %s from chain: %s", target_period, exc)
        return jsonify({"error": "failed to read period from chain"}), 500

    if period_info.get("result_set"):
        existing_draw = draw_repo.get_draw(target_period)
        return jsonify({
            "period_id": target_period,
            "current_period": current_period_on_chain,
            "winning_numbers": existing_draw.get_numbers() if existing_draw else period_info.get("winning_numbers"),
            "transactions": {},
            "warnings": ["result already submitted on-chain"],
            "already_set": True,
        })

    status = period_info.get("status")
    tx_hashes: Dict[str, str] = {}
    warnings = []

    def record_tx(label: str, coroutine):
        try:
            tx_hash = asyncio.run(coroutine)
        except ContractLogicError as exc:
            current_app.logger.exception("%s failed: %s", label, exc)
            raise
        except RuntimeError as exc:
            current_app.logger.exception("%s failed: %s", label, exc)
            raise
        except Exception as exc:  # pragma: no cover
            current_app.logger.exception("%s failed unexpectedly: %s", label, exc)
            raise
        if tx_hash:
            tx_hashes[label] = tx_hash
        return tx_hash

    try:
        if status == "Selling":
            record_tx("close_period", blockchain_client.close_current_period())
        elif status == "Closed":
            warnings.append("Period already closed on-chain; skipping close step.")
        else:
            return jsonify({"error": f"period {target_period} status {status} cannot be settled on-chain"}), 400

        record_tx("submit_result", blockchain_client.submit_result(target_period, data.winning_numbers))
        record_tx("settle_period", blockchain_client.settle_period(target_period))
        record_tx("open_next_period", blockchain_client.open_next_period())
        new_current_period = asyncio.run(blockchain_client.get_current_period())
    except ContractLogicError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400

    draw_repo.remove_draws_before(target_period)
    draw = draw_repo.set_draw(target_period, data.winning_numbers)
    stats = ticket_repo.apply_draw(target_period, data.winning_numbers)
    ticket_repo.set_current_period(new_current_period)

    return jsonify({
        "period_id": target_period,
        "current_period": new_current_period,
        "previous_status": status,
        "winning_numbers": draw.get_numbers(),
        "updated_tickets": stats["updated"],
        "winners": stats["winners"],
        "transactions": tx_hashes,
        "warnings": warnings,
    })

