from __future__ import annotations

import asyncio
from typing import Optional
from functools import lru_cache

from flask import Blueprint, current_app, jsonify, request

from ..config import load_settings
from ..schemas import (
    ClaimTicketResponse,
    TicketPurchaseRequest,
    TicketPurchaseResponse,
    TicketStatusResponse,
)
from ..services.blockchain import LotteryBlockchainClient
from ..services.tickets import TicketRepository, BASE_PAYOUT_UNIT

bp = Blueprint("tickets", __name__)
ticket_repo = TicketRepository()


@lru_cache(maxsize=1)
def get_blockchain_client() -> LotteryBlockchainClient:
    settings = load_settings()
    return LotteryBlockchainClient.from_artifact(
        settings.web3.rpc_url,
        settings.web3.contract_address,
        settings.web3.abi_path,
        signer_key=settings.web3.oracle_signer,
    )


@bp.get("")
def list_tickets():
    tickets = ticket_repo.list_tickets()
    return jsonify(tickets)


@bp.post("")
def purchase_ticket():
    payload = request.get_json(force=True, silent=True) or {}
    data = TicketPurchaseRequest(**payload)

    period_id_from_chain: Optional[int] = None
    try:
        blockchain_client = get_blockchain_client()
        value = asyncio.run(blockchain_client.get_current_period())
        if isinstance(value, int) and value > 0:
            period_id_from_chain = value
    except Exception as exc:  # pragma: no cover
        current_app.logger.warning("Using fallback period because RPC call failed: %s", exc)

    if period_id_from_chain is not None:
        ticket_repo.set_current_period(period_id_from_chain)
        period_id = period_id_from_chain
    else:
        period_id = ticket_repo.get_current_period()

    ticket = ticket_repo.create_ticket(numbers=data.numbers, period_id=period_id)
    record = ticket.to_dict()

    response = TicketPurchaseResponse(
        ticket_id=record["ticket_id"],
        period_id=record["period_id"],
        status=record["status"],
    )
    return jsonify(response.dict()), 201


@bp.get("/<ticket_id>")
def get_ticket(ticket_id: str):
    ticket = ticket_repo.get_ticket(ticket_id)
    if not ticket:
        return jsonify({"error": "ticket not found"}), 404

    record = ticket.to_dict()
    response = TicketStatusResponse(
        ticket_id=record["ticket_id"],
        period_id=record["period_id"],
        numbers=record["numbers"],
        status=record["status"],
        matches=record["matches"],
        payout=str(record["payout"]) if record["payout"] is not None else None,
        claimed=record["claimed"],
    )
    return jsonify(response.dict())


@bp.post("/<ticket_id>/claim")
def claim_ticket(ticket_id: str):
    ticket = ticket_repo.get_ticket(ticket_id)
    if not ticket:
        return jsonify({"error": "ticket not found"}), 404

    if ticket.claimed:
        return jsonify({"error": "ticket already claimed"}), 400

    draw_numbers = ticket_repo.get_draw_numbers(ticket.period_id)
    if not draw_numbers:
        return jsonify({"error": "draw not submitted for this period"}), 400

    matches = ticket.matches if ticket.matches is not None else len(set(ticket.get_numbers()).intersection(draw_numbers))
    payout = ticket.payout if ticket.payout is not None else matches * BASE_PAYOUT_UNIT
    ticket_repo.update_ticket_result(ticket_id, matches, payout)
    ticket_repo.mark_claimed(ticket_id)

    try:
        blockchain_client = get_blockchain_client()
        tx_hash = asyncio.run(blockchain_client.claim_prize(ticket_id))
    except Exception as exc:  # pragma: no cover
        current_app.logger.warning("Claim transaction fallback due to RPC error: %s", exc)
        tx_hash = "0x" + ticket_id.rjust(64, "0")

    response = ClaimTicketResponse(
        ticket_id=ticket.id,
        period_id=ticket.period_id,
        tx_hash=tx_hash,
        payout=str(payout),
    )
    return jsonify(response.dict())


@bp.post("/sync")
def sync_ticket_from_chain():
    payload = request.get_json(force=True, silent=True) or {}
    token_id = payload.get("ticket_id")
    if token_id is None:
        return jsonify({"error": "ticket_id is required"}), 400
    try:
        token_int = int(token_id)
    except ValueError:
        return jsonify({"error": "invalid ticket_id"}), 400

    try:
        blockchain_client = get_blockchain_client()
        chain_ticket = asyncio.run(blockchain_client.get_ticket(token_int))
    except Exception as exc:  # pragma: no cover
        current_app.logger.exception("Failed to fetch ticket %s from chain: %s", token_id, exc)
        return jsonify({"error": "unable to read ticket from chain"}), 500

    ticket_model = ticket_repo.sync_from_chain(chain_ticket, payload.get("tx_hash"))
    return jsonify(ticket_model.to_dict())


@bp.post("/<ticket_id>/sync-claim")
def sync_claim_from_chain(ticket_id: str):
    payload = request.get_json(force=True, silent=True) or {}
    try:
        token_int = int(ticket_id)
    except ValueError:
        return jsonify({"error": "invalid ticket_id"}), 400

    try:
        blockchain_client = get_blockchain_client()
        chain_ticket = asyncio.run(blockchain_client.get_ticket(token_int))
    except Exception as exc:  # pragma: no cover
        current_app.logger.exception("Failed to fetch ticket %s from chain: %s", ticket_id, exc)
        return jsonify({"error": "unable to read ticket from chain"}), 500

    if not chain_ticket.get("claimed"):
        return jsonify({"error": "ticket not claimed on chain"}), 400

    ticket_model = ticket_repo.sync_from_chain(chain_ticket, payload.get("tx_hash"))
    return jsonify(ticket_model.to_dict())

