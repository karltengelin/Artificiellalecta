"""Läs sparade uppdrag, beslut och leveranskvitton i deras ursprungliga format."""

from sqlalchemy import inspect, select

from agents.deliveries import DeliveryStore
from agents.gateways import DraftGateway
from agents.journal import DEFAULT_JOURNAL_DIR
from agents.trace import read_run_trace
from models.flow import Flow, FlowGateDecision, FlowStep
from services.errors import NotFoundError

TITLES = {
    "company_question": "Bolagsfråga",
    "product_report": "Produktrapport",
    "rule_change_parameter": "Regeländring till produktparameter",
    "rule_change_code": "Regeländring som kräver kod",
    "premium_month_review": "Månadsgranskning",
}


class MissionArchive:
    def __init__(self, factory, *, deliveries=None, drafts=None, journal_dir=DEFAULT_JOURNAL_DIR):
        self.factory = factory
        self.deliveries = deliveries or DeliveryStore()
        self.drafts = drafts or DraftGateway()
        self.journal_dir = journal_dir

    def list(self):
        with self.factory() as session:
            if not inspect(session.connection()).has_table(Flow.__tablename__):
                return []
            return list(session.scalars(select(Flow).order_by(Flow.created_at.desc(), Flow.flow_id.desc())))

    def get(self, ident):
        with self.factory() as session:
            if not inspect(session.connection()).has_table(Flow.__tablename__):
                raise NotFoundError("Uppdraget finns inte i arkivet")
            record = session.get(Flow, ident)
            if record is None:
                raise NotFoundError("Uppdraget finns inte i arkivet")
            steps = list(session.scalars(select(FlowStep).where(FlowStep.flow_id == ident).order_by(FlowStep.position)))
            decisions = list(session.scalars(select(FlowGateDecision).where(FlowGateDecision.flow_id == ident)
                                             .order_by(FlowGateDecision.created_at, FlowGateDecision.id)))
            return record, steps, decisions

    @staticmethod
    def delivery_receipt(steps):
        return next((step.result.get("delivery") for step in steps
                     if step.step_key == "render" and step.status == "completed" and step.result), None)

    def delivery(self, ident, version, name):
        _, steps, _ = self.get(ident)
        receipt = self.delivery_receipt(steps)
        if not receipt or receipt["version"] != version or name not in receipt["files"]:
            raise NotFoundError("Rapportfilen finns inte i arkivet")
        return self.deliveries.read(ident, version, name, receipt["files"][name])

    def step(self, ident, key):
        _, steps, _ = self.get(ident)
        step = next((s for s in steps if s.step_key == key), None)
        if step is None:
            raise NotFoundError("Underlaget finns inte i arkivet")
        return step

    def draft(self, ident, key, name):
        step = self.step(ident, key)
        if not step.run_id or f"utkast:{step.team}/{step.run_id}/{name}" not in (step.artifact_refs or []):
            raise NotFoundError("Utkastet finns inte i arkivet")
        return self.drafts.read_draft(step.team, step.run_id, name)

    def trace(self, ident, key):
        step = self.step(ident, key)
        return read_run_trace(self.journal_dir, step.run_id)
