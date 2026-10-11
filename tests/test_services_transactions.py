"""Tjänstelagrets transaktionsgräns: godkännande, förslag och avslag (tjänstelager.md §6–7).

Affärsändring, loggrad och godkännandets status sparas i en transaktion.
Testerna visar att ett fel var som helst lämnar allt orört och att ett
förslag aldrig verkställs två gånger – inte heller vid samtidiga godkännanden.

Samtidighet testas här mot en SQLite-fil (`insurance_file_db`), där databasen
serialiserar transaktionerna. Samma scenarier körs mot Postgres i
tests/test_services_postgres.py när en isolerad Postgres finns.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from models import ApprovalRequestRecord, InsuredPerson, OperationEventRecord
from services import (
    AccessRegister,
    Actor,
    ApprovalError,
    ConflictError,
    MemoryEventLog,
    NotFoundError,
    OperationContext,
    OperationKind,
    OperationRegistry,
    ProductRuleCatalog,
    ServiceConfigError,
    ServiceError,
    ServiceLayer,
    operation,
)
from services.approvals import DatabaseApprovalStore
from services.events import DatabaseEventLog

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

PERSON = "199001011234"
HUMAN = OperationContext(actor=Actor.human("karl"))
AGENT = OperationContext(actor=Actor.agent("case_handler", team="forsakring"), reason="Kunden bytte adress", run_id="run-3")


class EmailChange(BaseModel):
    personal_id_number: str
    email: str


class Changed(BaseModel):
    email: str


class Hooks:
    """Styr testoperationen: räknar körningar, kan vänta eller fallera."""

    def __init__(self) -> None:
        self.calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block_first = False
        self.fail_first = False
        self.commit_inside = False
        self.rollback_inside = False

    def reset(self) -> None:
        self.__init__()


HOOKS = Hooks()
registry = OperationRegistry()


@operation(name="set_email", description="Byter e-post", kind=OperationKind.WRITE,
           rules=["PR-T-001"], pii=True, registry=registry)
def set_email(ctx: OperationContext, data: EmailChange) -> Changed:
    session = ctx.require_session()
    person = session.scalar(select(InsuredPerson).where(InsuredPerson.personal_id_number == data.personal_id_number))
    if person is None:
        raise NotFoundError("Ingen försäkrad med det personnumret")
    HOOKS.calls += 1
    first = HOOKS.calls == 1
    person.email = data.email
    session.flush()
    if first and HOOKS.block_first:
        HOOKS.entered.set()
        assert HOOKS.release.wait(10), "testet släppte aldrig operationen"
    if first and HOOKS.fail_first:
        raise RuntimeError("simulerat fel i operationen")
    if HOOKS.commit_inside:
        session.commit()
    if HOOKS.rollback_inside:
        session.rollback()
    return Changed(email=data.email)


@pytest.fixture
def rules(tmp_path):
    (tmp_path / "PR-T-001-x.md").write_text("> **Granskningsstatus:** Godkänd\n", encoding="utf-8")
    return ProductRuleCatalog(tmp_path)


@pytest.fixture(autouse=True)
def _reset_hooks():
    HOOKS.reset()
    yield
    HOOKS.release.set()


def make_service(db, rules, **overrides) -> ServiceLayer:
    options = {
        "registry": registry,
        "register": AccessRegister.from_dict({"set_email": "APPROVAL"}),
        "rules": rules,
        "session_factory": db.session_factory,
    }
    return ServiceLayer(**(options | overrides))


def propose(service: ServiceLayer, email: str = "ny@example.se") -> str:
    """Lägger ett agentförslag. Provkörningen mot aktuellt läge räknas inte som körning."""
    result = service.execute("set_email", AGENT, {"personal_id_number": PERSON, "email": email})
    assert result.pending
    HOOKS.calls = 0
    return result.approval_id


def email(db) -> str | None:
    with db.session_factory() as s:
        return s.scalar(select(InsuredPerson.email).where(InsuredPerson.personal_id_number == PERSON))


def events(db, outcome: str | None = None) -> list[OperationEventRecord]:
    with db.session_factory() as s:
        rows = s.scalars(select(OperationEventRecord).order_by(OperationEventRecord.occurred_at)).all()
    return [r for r in rows if outcome is None or r.outcome == outcome]


def approval_status(db, approval_id: str) -> str:
    with db.session_factory() as s:
        return s.get(ApprovalRequestRecord, approval_id).status


def flaky_commit_factory(engine, failures: int = 1):
    """Som services.db.session_factory_for, men de första commit-försöken fallerar
    (t.ex. avbruten anslutning till Lakebase precis när allt ska sparas)."""
    maker = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    left = {"failures": failures}

    @contextmanager
    def scope():
        session = maker()
        try:
            yield session
            if left["failures"]:
                left["failures"] -= 1
                raise OperationalError("COMMIT", {}, Exception("simulerat avbrott vid commit"))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return scope


# --- godkännande ---------------------------------------------------------------


def assert_failed_status_save_rolls_back_everything(db, rules) -> None:
    """Reviewfelet: ändring och loggrad sparades, sedan föll statusen – och nästa försök körde igen."""
    approval_id = propose(make_service(db, rules))
    flaky = make_service(db, rules, session_factory=flaky_commit_factory(db.engine),
                         events=DatabaseEventLog(db.session_factory),
                         approvals=DatabaseApprovalStore(db.session_factory))

    with pytest.raises(OperationalError):
        flaky.approve(approval_id, HUMAN, note="OK")

    assert email(db) is None  # ingen affärsändring
    assert events(db, "executed") == []  # ingen executed-rad
    assert approval_status(db, approval_id) == "pending"  # kan hanteras på nytt

    make_service(db, rules).approve(approval_id, HUMAN, note="OK, andra försöket")
    assert email(db) == "ny@example.se"
    (executed,) = events(db, "executed")
    assert (executed.actor_id, executed.proposed_by, executed.approval_id) == ("karl", "case_handler", approval_id)
    assert approval_status(db, approval_id) == "approved"


class TestGodkannandeTransaktion:
    def test_fel_nar_godkannandets_status_sparas_rullar_tillbaka_andring_och_loggrad(self, insurance_db, rules):
        assert_failed_status_save_rolls_back_everything(insurance_db, rules)

    def test_fel_i_statusuppdateringen_kor_aldrig_operationen(self, insurance_db, rules):
        class BrokenStore(DatabaseApprovalStore):
            def decide(self, *args, **kwargs):
                super().decide(*args, **kwargs)
                raise OperationalError("UPDATE approval_requests", {}, Exception("simulerat"))

        service = make_service(insurance_db, rules)
        approval_id = propose(service)
        broken = make_service(insurance_db, rules, approvals=BrokenStore(insurance_db.session_factory))
        with pytest.raises(OperationalError):
            broken.approve(approval_id, HUMAN)
        assert (HOOKS.calls, email(insurance_db), events(insurance_db, "executed")) == (0, None, [])
        assert approval_status(insurance_db, approval_id) == "pending"

    def test_fel_i_operationen_lamnar_forslaget_pending_och_det_kan_avslas(self, insurance_db, rules):
        service = make_service(insurance_db, rules)
        approval_id = propose(service)
        HOOKS.fail_first = True
        with pytest.raises(RuntimeError):
            service.approve(approval_id, HUMAN)
        assert (email(insurance_db), events(insurance_db, "executed")) == (None, [])
        assert approval_status(insurance_db, approval_id) == "pending"

        service.reject(approval_id, HUMAN, note="Läget har ändrats")
        assert approval_status(insurance_db, approval_id) == "rejected"
        (rejected,) = events(insurance_db, "rejected")
        assert (rejected.proposed_by, rejected.detail, rejected.reason) == (
            "case_handler", "Läget har ändrats", "Kunden bytte adress",
        )

    def test_upprepat_godkannande_utfor_aldrig_andringen_tva_ganger(self, insurance_db, rules):
        service = make_service(insurance_db, rules)
        approval_id = propose(service)
        service.approve(approval_id, HUMAN)
        with pytest.raises(ApprovalError, match="redan approved"):
            service.approve(approval_id, HUMAN)
        with pytest.raises(ApprovalError, match="redan approved"):
            service.reject(approval_id, HUMAN)
        assert HOOKS.calls == 1
        assert len(events(insurance_db, "executed")) == 1

    def test_godkant_forslag_provas_mot_aktuellt_lage(self, insurance_db, rules):
        service = make_service(insurance_db, rules)
        approval_id = propose(service)
        with insurance_db.session_factory() as s:  # läget ändras efter att förslaget lades
            s.execute(InsuredPerson.__table__.update().values(personal_id_number="199001019999"))
        with pytest.raises(NotFoundError):
            service.approve(approval_id, HUMAN)
        assert approval_status(insurance_db, approval_id) == "pending"
        assert events(insurance_db, "executed") == []

    def test_bara_manniska_kan_godkanna_och_avsla(self, insurance_db, rules):
        service = make_service(insurance_db, rules)
        approval_id = propose(service)
        system = OperationContext(actor=Actor.system("batch"))
        for ctx in (AGENT, system):
            with pytest.raises(ApprovalError, match="människa"):
                service.approve(approval_id, ctx)
            with pytest.raises(ApprovalError, match="människa"):
                service.reject(approval_id, ctx)
        assert approval_status(insurance_db, approval_id) == "pending"


class TestSamtidigaGodkannanden:
    def test_samtidiga_godkannanden_kan_inte_bada_verkstalla(self, insurance_file_db, rules):
        assert_concurrent_approvals_execute_once(insurance_file_db, rules)

    def test_om_forsta_godkannandet_fallerar_kan_det_andra_verkstalla(self, insurance_file_db, rules):
        assert_second_approval_takes_over_after_failure(insurance_file_db, rules)


def _approve_in_thread(service, approval_id, results, key):
    def run():
        try:
            results[key] = service.approve(approval_id, HUMAN)
        except Exception as exc:  # noqa: BLE001 – utfallet kontrolleras av testet
            results[key] = exc

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def assert_concurrent_approvals_execute_once(db, rules) -> None:
    """A har tagit ärendet och står i operationen när B försöker godkänna samma ärende."""
    service = make_service(db, rules)
    approval_id = propose(service)
    HOOKS.block_first = True
    results: dict = {}

    first = _approve_in_thread(service, approval_id, results, "a")
    assert HOOKS.entered.wait(10)
    second = _approve_in_thread(make_service(db, rules), approval_id, results, "b")
    second.join(0.5)
    assert second.is_alive(), "B ska vänta på A:s transaktion, inte gå förbi"
    HOOKS.release.set()
    first.join(15)
    second.join(15)

    assert not isinstance(results["a"], Exception), results["a"]
    assert isinstance(results["b"], ApprovalError) and "redan approved" in str(results["b"])
    assert HOOKS.calls == 1
    assert len(events(db, "executed")) == 1
    assert approval_status(db, approval_id) == "approved"


def assert_second_approval_takes_over_after_failure(db, rules) -> None:
    """A tar ärendet men fallerar – ärendet rullas tillbaka till pending och B verkställer en gång."""
    service = make_service(db, rules)
    approval_id = propose(service)
    HOOKS.block_first = True
    HOOKS.fail_first = True
    results: dict = {}

    first = _approve_in_thread(service, approval_id, results, "a")
    assert HOOKS.entered.wait(10)
    second = _approve_in_thread(make_service(db, rules), approval_id, results, "b")
    second.join(0.5)
    HOOKS.release.set()
    first.join(15)
    second.join(15)

    assert isinstance(results["a"], RuntimeError)
    assert not isinstance(results["b"], Exception), results["b"]
    assert HOOKS.calls == 2  # A:s körning rullades tillbaka, B:s sparades
    (executed,) = events(db, "executed")
    assert executed.approval_id == approval_id
    assert email(db) == "ny@example.se"
    assert approval_status(db, approval_id) == "approved"


# --- förslag och avslag ------------------------------------------------------------


class FailingEventLog(DatabaseEventLog):
    def __init__(self, session_factory, fail_on: str) -> None:
        super().__init__(session_factory)
        self.fail_on = fail_on

    def record(self, event, session=None):
        super().record(event, session)
        if event.outcome == self.fail_on:
            raise OperationalError("INSERT operation_events", {}, Exception("simulerat"))


class TestForslagOchAvslag:
    def test_fel_i_loggraden_vid_forslag_lamnar_inget_arende(self, insurance_db, rules):
        service = make_service(insurance_db, rules, events=FailingEventLog(insurance_db.session_factory, "proposed"))
        with pytest.raises(OperationalError):
            propose(service)
        with insurance_db.session_factory() as s:
            assert s.scalars(select(ApprovalRequestRecord)).all() == []
        assert events(insurance_db) == []

    def test_fel_nar_arendet_sparas_lamnar_ingen_loggrad(self, insurance_db, rules):
        class BrokenStore(DatabaseApprovalStore):
            def add(self, request, tx=None):
                super().add(request, tx)
                raise OperationalError("INSERT approval_requests", {}, Exception("simulerat"))

        service = make_service(insurance_db, rules, approvals=BrokenStore(insurance_db.session_factory))
        with pytest.raises(OperationalError):
            propose(service)
        assert events(insurance_db) == []

    def test_fel_i_loggraden_vid_avslag_lamnar_arendet_pending(self, insurance_db, rules):
        approval_id = propose(make_service(insurance_db, rules))
        service = make_service(insurance_db, rules, events=FailingEventLog(insurance_db.session_factory, "rejected"))
        with pytest.raises(OperationalError):
            service.reject(approval_id, HUMAN, note="Nej")
        assert approval_status(insurance_db, approval_id) == "pending"
        assert events(insurance_db, "rejected") == []

    def test_forslag_provas_mot_aktuellt_lage_innan_det_laggs(self, insurance_db, rules):
        service = make_service(insurance_db, rules)
        with pytest.raises(NotFoundError):
            service.execute("set_email", AGENT, {"personal_id_number": "190001010000", "email": "x@example.se"})
        with insurance_db.session_factory() as s:
            assert s.scalars(select(ApprovalRequestRecord)).all() == []
        assert events(insurance_db) == []

    def test_provkorningen_sparar_ingenting(self, insurance_db, rules):
        make_service(insurance_db, rules).execute("set_email", AGENT, {"personal_id_number": PERSON, "email": "y@x.se"})
        assert HOOKS.calls == 1  # provkörd en gång …
        assert email(insurance_db) is None  # … men inget sparat
        assert [e.outcome for e in events(insurance_db)] == ["proposed"]


# --- operationerna äger inte transaktionen ---------------------------------------------


class TestTransaktionsgransen:
    def test_operation_far_inte_gora_commit(self, insurance_db, rules):
        HOOKS.commit_inside = True
        with pytest.raises(ServiceError, match="får inte göra commit"):
            make_service(insurance_db, rules).execute(
                "set_email", OperationContext(actor=Actor.human("karl"), reason="Test"),
                {"personal_id_number": PERSON, "email": "x@example.se"},
            )
        assert (email(insurance_db), events(insurance_db)) == (None, [])

    def test_operation_far_inte_gora_rollback(self, insurance_db, rules):
        HOOKS.rollback_inside = True
        with pytest.raises(ServiceError, match="avslutade transaktionen"):
            make_service(insurance_db, rules).execute(
                "set_email", OperationContext(actor=Actor.human("karl"), reason="Test"),
                {"personal_id_number": PERSON, "email": "x@example.se"},
            )
        assert (email(insurance_db), events(insurance_db)) == (None, [])

    def test_krock_med_databasens_unikhetsregler_blir_konflikt_utan_andring(self, insurance_db, rules):
        from datetime import date
        from decimal import Decimal

        from models import SalaryReport

        conflict_registry = OperationRegistry()

        @operation(name="double_report", description="t", kind=OperationKind.WRITE, rules=["PR-T-001"],
                   registry=conflict_registry)
        def double_report(ctx: OperationContext, data: Changed) -> Changed:
            for _ in range(2):  # samma version två gånger – unikt index
                ctx.session.add(SalaryReport(
                    insured_person_id=insurance_db.ids.person, employer_id=insurance_db.ids.employer,
                    period_month=date(2025, 6, 1), version=1, pensionable_salary_sek=Decimal(1),
                    source="manual", received_date=date(2025, 7, 1),
                ))
            return data

        service = ServiceLayer(registry=conflict_registry, register=AccessRegister.from_dict({}), rules=rules,
                               session_factory=insurance_db.session_factory)
        with pytest.raises(ConflictError, match="integritetsregler"):
            service.execute("double_report", OperationContext(actor=Actor.human("karl"), reason="Test"),
                            {"email": "x"})
        with insurance_db.session_factory() as s:
            assert s.scalars(select(SalaryReport)).all() == []
        assert events(insurance_db) == []

    def test_databaskon_kraver_gemensam_transaktion(self, insurance_db, rules):
        with pytest.raises(ServiceConfigError, match="session_factory"):
            ServiceLayer(registry=registry, register=AccessRegister.from_dict({}), rules=rules,
                         approvals=DatabaseApprovalStore(insurance_db.session_factory), events=MemoryEventLog())
        with pytest.raises(ServiceConfigError, match="session_factory"):
            ServiceLayer(registry=registry, register=AccessRegister.from_dict({}), rules=rules,
                         events=DatabaseEventLog(insurance_db.session_factory))


class TestUtanDatabas:
    def test_fel_vid_godkannande_aterstaller_arendet_i_minnet(self, rules):
        memory_registry = OperationRegistry()
        state = {"fail": True, "calls": 0}

        @operation(name="touch", description="t", kind=OperationKind.WRITE, rules=["PR-T-001"], registry=memory_registry)
        def touch(ctx: OperationContext, data: Changed) -> Changed:
            state["calls"] += 1
            if state["fail"]:
                raise RuntimeError("simulerat")
            return data

        service = ServiceLayer(registry=memory_registry, register=AccessRegister.from_dict({"touch": "APPROVAL"}),
                               rules=rules, events=MemoryEventLog())
        approval_id = service.execute("touch", AGENT, {"email": "a@b.se"}).approval_id
        with pytest.raises(RuntimeError):
            service.approve(approval_id, HUMAN)
        assert service.approvals.get(approval_id).status == "pending"
        state["fail"] = False
        service.approve(approval_id, HUMAN)
        assert service.approvals.get(approval_id).status == "approved"
        assert [e.outcome for e in service.events.events] == ["proposed", "executed"]
