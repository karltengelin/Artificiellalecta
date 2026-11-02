"""Varaktig aktuariedialog på samma harness som företagets övriga team."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from agents.actuarial_workbench import Workbench
from agents.ecosystem import Ecosystem, Limits
from agents.gateways import Gateways
from agents.loop import run_agent
from agents.profile import compile_profile
from agents.run import RunRequest, RunStatus
from agents.skills import SkillRegistry
from models import ActuarialAnalysis, ActuarialConversation, ActuarialTurn
from services import default_registry
from services.errors import (
    AccessDeniedError,
    ConflictError,
    InvalidInputError,
    NotFoundError,
)

log = logging.getLogger(__name__)
STATUSES = {"queued": "Köat", "running": "Aktuarien arbetar", "completed": "Svar finns",
            "needs_human": "Behöver uppföljning", "failed": "Körningen misslyckades", "interrupted": "Avbrutet"}


class ActuarialDialogue:
    def __init__(self, trusted, agent_service, ai, *, journal_dir=None, environment_id=None, dataset_ref=None):
        self.trusted, self.agent_service, self.ai = trusted, agent_service, ai
        self.session_factory, self.journal_dir = trusted._session_factory, journal_dir
        self.environment_id, self.dataset_ref = environment_id, dataset_ref

    @staticmethod
    def _human(actor):
        if actor.type != "human":
            raise AccessDeniedError("Dialogen kräver verifierad operatör")

    def _conversation(self, session, ident, actor):
        self._human(actor)
        row = session.get(ActuarialConversation, ident)
        if row is None or row.created_by != actor.id:
            raise NotFoundError("Dialogen saknas")
        return row

    def listing(self, actor):
        self._human(actor)
        with self.session_factory() as session:
            return [{"id": r.id, "title": r.title, "created_at": r.created_at} for r in session.scalars(
                select(ActuarialConversation).where(ActuarialConversation.created_by == actor.id)
                .order_by(ActuarialConversation.created_at.desc()).limit(100))]

    def view(self, ident, actor):
        with self.session_factory() as session:
            row = self._conversation(session, ident, actor)
            turns = session.scalars(select(ActuarialTurn).where(ActuarialTurn.conversation_id == ident)
                                     .order_by(ActuarialTurn.created_at, ActuarialTurn.id)).all()
            deliveries = session.scalars(select(ActuarialAnalysis).where(ActuarialAnalysis.conversation_id == ident)
                                          .order_by(ActuarialAnalysis.created_at)).all()
            return {"id": row.id, "title": row.title,
                    "turns": [{k: getattr(t, k) for k in ("id", "instruction", "status", "result", "run_id", "created_at")}
                              for t in turns],
                    "deliveries": [{k: getattr(d, k) for k in ("id", "kind", "title", "checksum", "run_id")}
                                   for d in deliveries], "statuses": STATUSES,
                    "active": any(t.status in {"queued", "running"} for t in turns)}

    def submit(self, ident, message, *, actor, key):
        from agents.gateways.drafts import _check_content

        self._human(actor)
        message = message.strip()
        if not 1 <= len(message) <= 6000 or len(key) != 32 or len(ident) != 32:
            raise InvalidInputError("Meddelandet ska vara 1–6 000 tecken och ha ett giltigt beställnings-id")
        try:
            int(key, 16)
            int(ident, 16)
        except ValueError as exc:
            raise InvalidInputError("Ogiltig dialogreferens") from exc
        _check_content(message)
        try:
            with self.session_factory() as session:
                conv = session.scalar(select(ActuarialConversation).where(ActuarialConversation.id == ident)
                                       .with_for_update())
                if conv is None:
                    conv = ActuarialConversation(id=ident, title=message[:100], created_by=actor.id)
                    session.add(conv)
                    session.flush()
                if conv.created_by != actor.id:
                    raise AccessDeniedError("Dialogen tillhör en annan operatör")
                existing = session.scalar(select(ActuarialTurn).where(
                    ActuarialTurn.conversation_id == ident, ActuarialTurn.submission_key == key))
                if existing:
                    if existing.instruction != message or existing.submitted_by != actor.id:
                        raise ConflictError("Beställnings-id används för ett annat meddelande")
                    return existing.id
                active = session.scalar(select(ActuarialTurn.id).where(
                    ActuarialTurn.conversation_id == ident, ActuarialTurn.status.in_(("queued", "running"))))
                if active:
                    raise ConflictError("Aktuarien arbetar fortfarande med föregående meddelande")
                turn = ActuarialTurn(id=uuid4().hex, conversation_id=ident, submission_key=key,
                    instruction=message, submitted_by=actor.id, status="queued", run_id="run-"+uuid4().hex[:20],
                    created_at=datetime.now(UTC),
                    result={"limits": Ecosystem.load().agent_limits("actuary_agent").model_dump()})
                session.add(turn)
                return turn.id
        except IntegrityError as exc:
            raise ConflictError("En samtidig beställning registrerades; läs dialogen igen") from exc

    def process(self, turn_id):
        with self.session_factory() as session:
            claimed = session.execute(update(ActuarialTurn).where(ActuarialTurn.id == turn_id,
                ActuarialTurn.status == "queued").values(status="running", revision=ActuarialTurn.revision+1))
            if claimed.rowcount != 1:
                return False
            turn = session.get(ActuarialTurn, turn_id)
            ident, message, run_id = turn.conversation_id, turn.instruction, turn.run_id
            limits = Limits(**turn.result["limits"])
            previous = session.scalars(select(ActuarialTurn).where(ActuarialTurn.conversation_id == ident,
                ActuarialTurn.id != turn_id).order_by(ActuarialTurn.created_at.desc()).limit(8)).all()
            background = "\n\n".join("Operatör: "+t.instruction+"\nTidigare svar (kontrollera källan igen): "+
                str(t.result.get("summary", "")) for t in reversed(previous))[-18000:]
        try:
            eco = Ecosystem.load()
            request = RunRequest(task_id=turn_id, target_team="aktuarie", goal=message, background=background, limits=limits,
                result_schema="ActuarialAnswer", only_skills=("actuarial_workbench", "list_regulatory_documents",
                "read_regulatory_document", "write_draft"),
                constraints=("Du arbetar i en öppen aktuariedialog. Välj analys utifrån uppdraget.",
                             "Läs catalog vid behov och recall/delivery för underlag från tidigare dialog.",
                             "Tidigare svar är underlag; kontrollera datareferenser innan de används.",
                             "Observerat utfall får inte skapas av dig. Redovisa konkret saknad data.",
                             "Grunder och värderingar fastställs av människa."),
                expected_output="Slutsats, underlag, osäkerhet och nästa steg. Ställ frågor när uppdraget behöver preciseras.")
            profile = compile_profile(eco, SkillRegistry.build(eco, default_registry), self.agent_service, request=request)
            gateways = Gateways(actuarial=Workbench(self.trusted, self.agent_service, ident))
            outcome = run_agent(self.ai, profile, self.agent_service, request, gateways=gateways,
                                run_id=run_id, journal_dir=self.journal_dir)
            result = outcome.result.model_dump(mode="json")
            state = "completed" if outcome.result.status == RunStatus.COMPLETED else "needs_human"
        except Exception:
            log.exception("actuarial_dialogue_run_failed", extra={"run_id": run_id})
            state, result = "failed", {"summary": "Körningen kunde inte slutföras. Kontrollera leveranser och körspår innan nytt uppdrag.",
                                        "run_id": run_id}
        with self.session_factory() as session:
            session.execute(update(ActuarialTurn).where(ActuarialTurn.id == turn_id,
                ActuarialTurn.status == "running").values(status=state, result=result))
        return True

    def interrupt(self, ident, turn_id, actor):
        with self.session_factory() as session:
            self._conversation(session, ident, actor)
            session.execute(update(ActuarialTurn).where(ActuarialTurn.id == turn_id,
                ActuarialTurn.conversation_id == ident, ActuarialTurn.status.in_(("queued", "running")))
                .values(status="interrupted"))

    def delivery(self, ident, delivery_id, actor):
        with self.session_factory() as session:
            self._conversation(session, ident, actor)
        return Workbench(self.trusted, self.agent_service, ident)._load(delivery_id)
