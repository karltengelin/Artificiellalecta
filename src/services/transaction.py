"""Tjänstelagrets transaktionsgräns (tjänstelager.md §6–7).

Ett anrop till tjänstelagret är en databastransaktion: affärsändringen,
raden i händelseloggen och godkännandeärendets status sparas tillsammans
eller inte alls. Bara tjänstelagret gör commit och rollback – operationerna
får sessionen men inte transaktionen (`guard_operation`).

Utan databas (tester, körning utan anslutning) finns ingen rollback; kön i
minnet registrerar i stället hur dess ändringar återställs (`on_rollback`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from services.errors import ServiceError

SessionFactory = Callable[[], AbstractContextManager[Any]]  # se services.db


@dataclass
class Transaction:
    session: Any = None  # databassessionen; None utan databas
    _undo: list[Callable[[], None]] = field(default_factory=list)

    def on_rollback(self, undo: Callable[[], None]) -> None:
        """Återställning av en ändring utanför databasen om anropet fallerar."""
        self._undo.append(undo)


@contextmanager
def transaction(session_factory: SessionFactory | None) -> Iterator[Transaction]:
    """En transaktion: commit om blocket lyckas, annars rollback av allt."""
    tx = Transaction()
    scope = session_factory() if session_factory is not None else nullcontext(None)
    try:
        with scope as session:
            tx.session = session
            yield tx
    except BaseException:
        for undo in reversed(tx._undo):
            undo()
        raise


@contextmanager
def guard_operation(session: Any, name: str) -> Iterator[None]:
    """Hindrar en operation från att göra commit, och upptäcker rollback eller stängning.

    En operation som gjorde commit själv kunde spara en ändring utan sin loggrad
    eller utan godkännandets status – det fel som transaktionsgränsen ska utesluta.
    """
    if not isinstance(session, Session):
        yield
        return

    def refuse_commit(_session: Session) -> None:
        raise ServiceError(f"'{name}' får inte göra commit – transaktionen ägs av tjänstelagret")

    started = session.get_transaction() or session.begin()
    event.listen(session, "before_commit", refuse_commit)
    try:
        yield
    finally:
        event.remove(session, "before_commit", refuse_commit)
    if session.get_transaction() is not started:
        raise ServiceError(
            f"'{name}' avslutade transaktionen (rollback/close) – tjänstelagret äger transaktionen"
        )
