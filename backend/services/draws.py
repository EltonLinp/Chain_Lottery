from __future__ import annotations

import datetime as dt
from typing import List, Optional

from ..db import session_scope
from ..models import Draw, Ticket


class DrawRepository:
    def remove_draws_before(self, period_id: int) -> None:
        with session_scope() as session:
            session.query(Draw).filter(Draw.period_id < period_id).delete()

    def set_draw(self, period_id: int, numbers: List[int]) -> Draw:
        with session_scope() as session:
            draw = session.get(Draw, period_id)
            if draw is not None:
                draw.set_numbers(numbers)
                draw.submitted_at = dt.datetime.utcnow()
                session.flush()
                session.refresh(draw)
                session.expunge(draw)
                return draw
            draw = Draw(period_id=period_id)
            draw.set_numbers(numbers)
            session.add(draw)
            session.flush()
            session.refresh(draw)
            session.expunge(draw)
            return draw

    def get_draw(self, period_id: int) -> Optional[Draw]:
        with session_scope() as session:
            draw = session.get(Draw, period_id)
            if draw:
                session.expunge(draw)
            return draw

    def list_draws(self) -> List[Draw]:
        with session_scope() as session:
            draws = session.query(Draw).order_by(Draw.period_id.desc()).all()
            for draw in draws:
                session.expunge(draw)
            return draws
