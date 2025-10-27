from __future__ import annotations

import secrets
from typing import Dict, List, Optional

from sqlalchemy import case, desc, func

from ..db import session_scope
from ..models import Draw, SystemState, Ticket

BASE_PAYOUT_UNIT = 100


def _compute_matches(numbers: List[int], winning_numbers: List[int]) -> int:
    return len(set(numbers).intersection(winning_numbers))


class TicketRepository:
    def _ensure_state(self, session) -> SystemState:
        state = session.get(SystemState, 1)
        if state is None:
            state = SystemState(id=1, current_period=1)
            session.add(state)
            session.flush()
        return state

    def get_current_period(self) -> int:
        with session_scope() as session:
            state = self._ensure_state(session)
            session.expunge(state)
            return state.current_period

    def set_current_period(self, period_id: int) -> None:
        with session_scope() as session:
            state = self._ensure_state(session)
            state.current_period = max(period_id, 1)
            session.flush()

    def increment_period(self, base_period: Optional[int] = None) -> int:
        with session_scope() as session:
            state = self._ensure_state(session)
            if base_period is not None and base_period >= state.current_period:
                state.current_period = base_period + 1
            else:
                state.current_period += 1
            session.flush()
            session.refresh(state)
            next_period = state.current_period
            session.expunge(state)
            return next_period

    def create_ticket(self, numbers: List[int], period_id: Optional[int] = None) -> Ticket:
        with session_scope() as session:
            state = self._ensure_state(session)
            use_period = period_id if period_id is not None else state.current_period

            ticket = Ticket(
                id=secrets.token_hex(8),
                period_id=use_period,
                status="pending",
                claimed=False,
            )
            ticket.set_numbers(numbers)
            session.add(ticket)
            session.flush()
            session.refresh(ticket)
            session.expunge(ticket)
            return ticket

    def get_ticket(self, ticket_id: str) -> Optional[Ticket]:
        with session_scope() as session:
            ticket = session.get(Ticket, ticket_id)
            if ticket:
                session.expunge(ticket)
            return ticket

    def sync_from_chain(self, chain_ticket: Dict[str, object], tx_hash: Optional[str] = None) -> Ticket:
        token_id = str(chain_ticket['token_id'])
        with session_scope() as session:
            ticket = session.get(Ticket, token_id)
            is_claimed = bool(chain_ticket.get('claimed'))
            status = 'claimed' if is_claimed else 'pending'
            if ticket is None:
                ticket = Ticket(
                    id=token_id,
                    period_id=int(chain_ticket['period_id']),
                    status=status,
                    claimed=is_claimed,
                    buyer=chain_ticket.get('buyer'),
                    tx_hash=tx_hash,
                )
                ticket.set_numbers(chain_ticket['numbers'])
                session.add(ticket)
            else:
                ticket.period_id = int(chain_ticket['period_id'])
                ticket.set_numbers(chain_ticket['numbers'])
                ticket.claimed = is_claimed
                if chain_ticket.get('buyer'):
                    ticket.buyer = chain_ticket['buyer']
                if tx_hash:
                    ticket.tx_hash = tx_hash
                ticket.status = 'claimed' if ticket.claimed else ticket.status or 'pending'
            session.flush()
            session.refresh(ticket)
            session.expunge(ticket)
            return ticket

    def update_ticket_result(
        self, ticket_id: str, matches: int, payout: int, status: str = 'result_in'
    ) -> Optional[Ticket]:
        with session_scope() as session:
            ticket = session.get(Ticket, ticket_id)
            if not ticket:
                return None
            ticket.matches = matches
            ticket.payout = payout
            if not ticket.claimed:
                ticket.status = status
            session.flush()
            session.refresh(ticket)
            session.expunge(ticket)
            return ticket

    def mark_claimed(self, ticket_id: str, tx_hash: Optional[str] = None) -> Optional[Ticket]:
        with session_scope() as session:
            ticket = session.get(Ticket, ticket_id)
            if not ticket:
                return None
            ticket.claimed = True
            ticket.status = 'claimed'
            if tx_hash:
                ticket.tx_hash = tx_hash
            session.flush()
            session.refresh(ticket)
            session.expunge(ticket)
            return ticket

    def apply_draw(self, period_id: int, winning_numbers: List[int]) -> Dict[str, int]:
        updated = 0
        winners = 0
        with session_scope() as session:
            tickets = session.query(Ticket).filter(Ticket.period_id == period_id).all()
            for ticket in tickets:
                numbers = ticket.get_numbers()
                matches = _compute_matches(numbers, winning_numbers)
                ticket.matches = matches
                ticket.payout = matches * BASE_PAYOUT_UNIT if matches > 0 else 0
                if not ticket.claimed:
                    ticket.status = 'result_in'
                updated += 1
                if matches > 0:
                    winners += 1

            session.flush()
            for ticket in tickets:
                session.expunge(ticket)
        return {'updated': updated, 'winners': winners}

    def list_tickets(self, limit: Optional[int] = None) -> List[Dict[str, object]]:
        with session_scope() as session:
            query = session.query(Ticket).order_by(desc(Ticket.created_at))
            if limit:
                query = query.limit(limit)
            records = query.all()
            result = []
            for ticket in records:
                result.append(ticket.to_dict())
                session.expunge(ticket)
            return result

    def get_draw_numbers(self, period_id: int) -> Optional[List[int]]:
        with session_scope() as session:
            draw = session.get(Draw, period_id)
            if draw:
                numbers = draw.get_numbers()
                session.expunge(draw)
                return numbers
            return None

    def list_periods(self, limit: Optional[int] = None) -> List[Dict[str, object]]:
        with session_scope() as session:
            state = self._ensure_state(session)

            stats_rows = (
                session.query(
                    Ticket.period_id.label("period_id"),
                    func.count(Ticket.id).label("ticket_count"),
                    func.sum(
                        case(
                            (Ticket.status.in_(("result_in", "claimed")), 1),
                            else_=0,
                        )
                    ).label("settled_count"),
                    func.sum(
                        case(
                            (Ticket.claimed.is_(True), 1),
                            else_=0,
                        )
                    ).label("claimed_count"),
                )
                .group_by(Ticket.period_id)
                .all()
            )
            stats_map = {int(row.period_id): row for row in stats_rows}

            draws = session.query(Draw).all()
            draw_map: Dict[int, List[int]] = {}
            for draw in draws:
                draw_map[int(draw.period_id)] = draw.get_numbers()
                session.expunge(draw)

            period_ids = set(stats_map.keys()) | set(draw_map.keys()) | {int(state.current_period)}
            ordered_ids = sorted(period_ids, reverse=True)
            if limit:
                ordered_ids = ordered_ids[:limit]

            results: List[Dict[str, object]] = []
            for period_id in ordered_ids:
                row = stats_map.get(period_id)
                ticket_count = int(row.ticket_count) if row and row.ticket_count is not None else 0
                settled_count = int(row.settled_count) if row and row.settled_count is not None else 0
                claimed_count = int(row.claimed_count) if row and row.claimed_count is not None else 0

                results.append(
                    {
                        "period_id": int(period_id),
                        "ticket_count": ticket_count,
                        "settled_count": settled_count,
                        "claimed_count": claimed_count,
                        "winning_numbers": draw_map.get(period_id),
                    }
                )

            session.expunge(state)
            return results
