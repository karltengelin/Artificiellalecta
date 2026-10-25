"""Anslutning, stamdata och arbetsgivare i tjänstelagret (Fas 4 S5).

enroll_insured_person (PR-ITP1-012/013), update_current_salary (stamdata, skild
från löneunderlaget i PR-ITP1-014), update_contact_details (PR-ITP1-031),
register_employer och list_employers. Stoppade anrop lämnar data och
händelselogg orörda.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from models import (
    Employer,
    InsuredPerson,
    OperationEventRecord,
    Policy,
    PolicyBenefit,
    PolicyState,
    ProductParameter,
)
from services import (
    AccessDeniedError,
    Actor,
    AgentAccess,
    BlockedError,
    ConflictError,
    InvalidInputError,
    MemoryEventLog,
    NotFoundError,
    OperationContext,
    ProductRuleCatalog,
    ServiceLayer,
)
from services.operations import common

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

TODAY = date(2026, 10, 11)
HUMAN = OperationContext(actor=Actor.human("karl"), reason="Anmälan från arbetsgivaren")
AGENT = OperationContext(actor=Actor.agent("case_handler", team="forsakring"), reason="Anmälningsfil", run_id="r1")
EMPLOYER = "5560000001"  # Testbolaget AB i conftest, ITP sedan 2010
NEW = "199204171236"  # 34 år
YOUNG = "200305104564"  # 23 år – 25-årsmånaden 2028-05
OLD = "195802027895"  # 68 år


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(common, "today", lambda: TODAY)


def service(db, today: date = TODAY) -> ServiceLayer:
    return ServiceLayer(session_factory=db.session_factory, rules=ProductRuleCatalog(today=today))


def enrollment(**overrides) -> dict:
    data = {
        "personal_id_number": NEW, "first_name": "Nora", "last_name": "Nyström",
        "employer_org_number": EMPLOYER, "employment_start_date": "2026-09-01", "itp1_start_date": "2026-09-01",
        "employment_category": "ordinary", "affiliation_reference": "ANM-2026-09-17",
        "monthly_salary_sek": "41000", "employment_rate": "100",
    }
    return {**data, **overrides}


def counts(db) -> tuple:
    with db.session_factory() as s:
        return tuple(
            s.scalar(select(func.count()).select_from(model))
            for model in (InsuredPerson, Policy, PolicyBenefit, PolicyState, Employer, OperationEventRecord)
        )


def person(db, pnr: str) -> InsuredPerson:
    with db.session_factory() as s:
        return s.scalars(select(InsuredPerson).where(InsuredPerson.personal_id_number == pnr)).one()


# --- anslutning ---------------------------------------------------------------------------------


def test_anslutning_skapar_person_forsakring_forman_och_premiebetalande(insurance_db):
    result = service(insurance_db).execute("enroll_insured_person", HUMAN, enrollment()).output
    assert (result.policy_number, result.state, result.premium_from_month) == ("AL-000002", "premium_paying",
                                                                             date(2026, 9, 1))
    assert result.information_letter_sent is False
    with insurance_db.session_factory() as s:
        policy = s.scalars(select(Policy).where(Policy.policy_number == "AL-000002")).one()
        assert (policy.signed_date, policy.start_date, policy.product_code) == (date(2026, 9, 1), date(2026, 9, 1), "ITP1")
        [benefit] = policy.benefits
        assert (benefit.benefit_type, benefit.start_date) == ("retirement_dc", date(2026, 9, 1))
        [state] = policy.states
        assert (state.state, state.valid_from, state.valid_to) == ("premium_paying", date(2026, 9, 1), None)
        assert "ANM-2026-09-17" in state.note
        nora = policy.insured_person
        assert (nora.status, nora.itp1_start_date, nora.monthly_salary_sek) == ("active", date(2026, 9, 1), Decimal("41000"))
        event = s.scalars(select(OperationEventRecord).where(OperationEventRecord.operation == "enroll_insured_person")).one()
    assert (event.outcome, event.actor_id) == ("executed", "karl")
    assert "PR-ITP1-012 v1.0 kommande" in event.detail


def test_under_25_ansluts_med_premie_fran_25_arsmanaden(insurance_db):
    result = service(insurance_db).execute("enroll_insured_person", HUMAN, enrollment(personal_id_number=YOUNG)).output
    assert result.premium_from_month == date(2028, 5, 1)
    assert "25-årsmånaden 2028-05" in result.note


def change_age(db, key: str, value: int, valid_from: date) -> None:
    """Ny version i en isolerad testdatabas; inga produktregler eller startvärden ändras."""
    with db.session_factory() as s:
        old = s.scalars(select(ProductParameter).where(ProductParameter.key == key)).one()
        old.valid_to = valid_from - timedelta(days=1)
        s.add(ProductParameter(
            key=key, value=Decimal(value), unit="years", valid_from=valid_from,
            rule_id="PR-ITP1-013", rule_version="test-2", source_ref="testkälla",
            decision_ref="testbeslut", created_by="test",
        ))


@pytest.mark.parametrize(("age", "year"), [(24, 2027), (26, 2029)])
def test_premiestart_foljer_versionerad_startalder(insurance_db, age, year):
    change_age(insurance_db, "premium_age_start", age, date(2026, 9, 1))
    result = service(insurance_db).execute("enroll_insured_person", HUMAN, enrollment(personal_id_number=YOUNG)).output
    assert result.premium_from_month == date(year, 5, 1)
    assert f"{age}-årsmånaden {year}-05" in result.note


def test_anslutning_och_premieberakning_foljer_samma_slutalder_och_giltighet(insurance_db):
    change_age(insurance_db, "premium_age_end", 69, date(2026, 9, 1))
    svc = service(insurance_db)
    # En framtida version får inte ändra prövningen av en äldre startmånad.
    with pytest.raises(BlockedError, match="66 år"):
        svc.execute("enroll_insured_person", HUMAN, enrollment(
            personal_id_number=OLD, employment_start_date="2026-08-01", itp1_start_date="2026-08-31",
        ))
    result = svc.execute("enroll_insured_person", HUMAN, enrollment(
        personal_id_number=OLD, itp1_start_date="2026-09-15",
    )).output
    assert result.premium_from_month == date(2026, 9, 1)
    preview = svc.execute("calculate_premium_preview", HUMAN, {
        "monthly_salary_sek": "41000", "birth_date": "1958-02-02", "period_month": "2026-09-01",
    }).output
    assert preview.in_age_window is True
    assert preview.calculation_basis["age_window"] == [25, 69]


def test_anslutning_stoppar_vid_den_andrade_slutaldersmanaden(insurance_db):
    change_age(insurance_db, "premium_age_end", 34, date(2026, 4, 1))
    svc = service(insurance_db)
    before = counts(insurance_db)
    with pytest.raises(BlockedError, match="34 år 2026-04"):
        svc.execute("enroll_insured_person", HUMAN, enrollment(
            employment_start_date="2026-04-01", itp1_start_date="2026-04-01",
        ))
    assert counts(insurance_db) == before
    result = svc.execute("enroll_insured_person", HUMAN, enrollment(
        employment_start_date="2026-03-01", itp1_start_date="2026-03-31",
    )).output
    assert result.start_date == date(2026, 3, 31)


def test_saknad_aldersparameter_stoppar_anslutning_utan_skrivning(insurance_db):
    with insurance_db.session_factory() as s:
        s.scalars(select(ProductParameter).where(ProductParameter.key == "premium_age_end")).one().status = "withdrawn"
    before = counts(insurance_db)
    with pytest.raises(NotFoundError, match="premium_age_end"):
        service(insurance_db).execute("enroll_insured_person", HUMAN, enrollment())
    assert counts(insurance_db) == before


def test_retroaktiv_anslutning_skapar_inga_premier(insurance_db):
    result = service(insurance_db).execute(
        "enroll_insured_person", HUMAN, enrollment(employment_start_date="2025-03-01", itp1_start_date="2025-03-01")
    ).output
    overview = service(insurance_db).execute("get_premium_history", HUMAN, {"policy_number": result.policy_number})
    assert overview.output.count == 0


@pytest.mark.parametrize(
    ("overrides", "error", "text"),
    [
        ({"employment_category": "ceo"}, BlockedError, "verkställande direktör"),
        ({"employment_category": "opted_out"}, BlockedError, "PR-ITP1-012"),
        ({"employment_start_date": "2026-10-01", "itp1_start_date": "2026-10-12"}, BlockedError, "i framtiden"),
        ({"personal_id_number": OLD}, BlockedError, "PR-ITP1-016"),
        ({"employment_start_date": "2009-01-01", "itp1_start_date": "2009-06-01"}, BlockedError,
         "före arbetsgivarens ITP-anslutning"),
        ({"employer_org_number": "5566778899"}, NotFoundError, "Ingen arbetsgivare"),
        ({"personal_id_number": "199204171234"}, InvalidInputError, "kontrollsiffra"),
        ({"itp1_start_date": "2026-08-01"}, InvalidInputError, "före anställningen"),
        ({"employment_category": "ordinary", "email": "inte-en-adress"}, InvalidInputError, "email"),
    ],
)
def test_anslutning_som_inte_stods_stoppas_och_ingenting_andras(insurance_db, overrides, error, text):
    before = counts(insurance_db)
    with pytest.raises(error, match=text):
        service(insurance_db).execute("enroll_insured_person", HUMAN, enrollment(**overrides))
    assert counts(insurance_db) == before


def test_arbetsgivare_som_inte_ar_aktiv_stoppar_anslutningen(insurance_db):
    with insurance_db.session_factory() as s:
        s.scalars(select(Employer)).one().status = "paused"
    with pytest.raises(BlockedError, match="status paused"):
        service(insurance_db).execute("enroll_insured_person", HUMAN, enrollment())


def test_befintligt_personnummer_ar_konflikt_eller_aterantallning(insurance_db):
    svc = service(insurance_db)
    svc.execute("enroll_insured_person", HUMAN, enrollment())
    with pytest.raises(ConflictError, match="finns redan som aktiv"):
        svc.execute("enroll_insured_person", HUMAN, enrollment())
    with insurance_db.session_factory() as s:
        nora = s.scalars(select(InsuredPerson).where(InsuredPerson.personal_id_number == NEW)).one()
        nora.status, nora.employment_end_date = "terminated", date(2026, 9, 30)
    with pytest.raises(BlockedError, match="anställningshistorik"):
        svc.execute("enroll_insured_person", HUMAN, enrollment())


def test_agent_far_foresla_anslutning_forst_nar_reglerna_galler(insurance_db):
    with pytest.raises(AccessDeniedError):
        service(insurance_db).execute("enroll_insured_person", AGENT, enrollment())
    after = service(insurance_db, date(2026, 11, 2))
    assert after.decision("enroll_insured_person").effective == AgentAccess.APPROVAL
    result = after.execute("enroll_insured_person", AGENT, enrollment())
    assert result.pending
    assert counts(insurance_db)[0] == 1  # bara ett förslag – ingen person skapad


# --- aktuell lön ---------------------------------------------------------------------------------


def test_aktuell_lon_andras_som_stamdata_utan_loneunderlag(insurance_db):
    svc = service(insurance_db)
    svc.execute("enroll_insured_person", HUMAN, enrollment())
    out = svc.execute("update_current_salary", HUMAN, {"personal_id_number": NEW, "monthly_salary_sek": "43500"}).output
    assert (out.previous_salary_sek, out.monthly_salary_sek, out.employment_rate) == (
        Decimal("41000.00"), Decimal("43500"), Decimal("100.00"))
    assert "PR-ITP1-014" in out.note
    assert person(insurance_db, NEW).monthly_salary_sek == Decimal("43500")
    assert svc.execute("get_salary_reports", HUMAN, {"personal_id_number": NEW}).output.reports == []
    with pytest.raises(ConflictError):
        svc.execute("update_current_salary", HUMAN, {"personal_id_number": NEW, "monthly_salary_sek": "43500.00"})
    out = svc.execute("update_current_salary", HUMAN,
                      {"personal_id_number": NEW, "monthly_salary_sek": "43500", "employment_rate": "80"}).output
    assert (out.previous_employment_rate, out.employment_rate) == (Decimal("100.00"), Decimal("80"))


def test_aktuell_lon_stoppas_efter_anstallningens_slut(insurance_db):
    with pytest.raises(BlockedError, match="pågående anställning"):
        service(insurance_db).execute("update_current_salary", HUMAN,
                                      {"personal_id_number": "199001011234", "monthly_salary_sek": "50000"})


def test_aktuell_lon_ar_endast_handlaggare_aven_nar_reglerna_galler(insurance_db):
    after = service(insurance_db, date(2026, 11, 2))
    decision = after.decision("update_current_salary")
    assert decision.effective == AgentAccess.HUMAN_ONLY
    with pytest.raises(AccessDeniedError):
        after.execute("update_current_salary", AGENT, {"personal_id_number": NEW, "monthly_salary_sek": "1"})


# --- kontaktuppgifter ----------------------------------------------------------------------------


def test_kontaktuppgifter_andras_och_tas_bort(insurance_db):
    svc = service(insurance_db)
    svc.execute("enroll_insured_person", HUMAN, enrollment(email="nora@example.se"))
    out = svc.execute("update_contact_details", HUMAN, {
        "personal_id_number": NEW, "email": "", "phone": "+46 70-123 45 67", "source": "insured",
    }).output
    assert [(c.field, c.previous, c.new) for c in out.changed] == [
        ("email", "nora@example.se", None), ("phone", None, "+46 70-123 45 67")]
    nora = person(insurance_db, NEW)
    assert (nora.email, nora.phone) == (None, "+46 70-123 45 67")
    assert svc.execute("get_insured_overview", HUMAN, {"personal_id_number": NEW}).output.phone == "+46 70-123 45 67"
    with pytest.raises(ConflictError):
        svc.execute("update_contact_details", HUMAN,
                    {"personal_id_number": NEW, "email": None, "phone": "+46 70-123 45 67", "source": "insured"})
    with pytest.raises(InvalidInputError):
        svc.execute("update_contact_details", HUMAN,
                    {"personal_id_number": NEW, "email": "fel@", "phone": None, "source": "insured"})


def test_kontaktuppgifter_for_avliden_stoppas(insurance_db):
    with insurance_db.session_factory() as s:
        s.scalars(select(InsuredPerson)).one().status = "deceased"
    with pytest.raises(BlockedError, match="avliden"):
        service(insurance_db).execute("update_contact_details", HUMAN, {
            "personal_id_number": "199001011234", "email": "x@example.se", "phone": None, "source": "other"})


# --- arbetsgivare --------------------------------------------------------------------------------


def test_ny_arbetsgivare_registreras_och_listas(insurance_db):
    svc = service(insurance_db)
    out = svc.execute("register_employer", HUMAN, {
        "org_number": "5566778899", "name": "Nyföretaget AB", "affiliation_date": "2026-01-01",
        "address_postal_code": "411 05", "address_city": "Göteborg", "contact_name": "Lena Lön",
        "contact_email": "lon@nyforetaget.se", "industry_code": "",
    }).output
    assert (out.collective_agreement, out.status) == ("ITP", "active")
    with insurance_db.session_factory() as s:
        employer = s.scalars(select(Employer).where(Employer.org_number == "5566778899")).one()
        assert (employer.address_postal_code, employer.industry_code) == ("41105", None)
    svc.execute("enroll_insured_person", HUMAN, enrollment(employer_org_number="5566778899"))
    before = len(svc.events.list()) if hasattr(svc.events, "list") else None
    listing = svc.execute("list_employers", HUMAN, {}).output
    assert [(e.org_number, e.active_insured) for e in listing.employers] == [("5566778899", 1), ("5560000001", 0)]
    assert len(svc.events.list()) == before  # listan har inga personuppgifter och loggas inte


@pytest.mark.parametrize(
    ("overrides", "error", "text"),
    [
        ({"org_number": "5560000001"}, ConflictError, "finns redan"),
        ({"org_number": "5566778890"}, InvalidInputError, "kontrollsiffra"),
        ({"affiliation_date": "2026-12-01"}, BlockedError, "framtiden"),
        ({"contact_email": "lön"}, InvalidInputError, "contact_email"),
    ],
)
def test_arbetsgivare_som_inte_kan_registreras(insurance_db, overrides, error, text):
    before = counts(insurance_db)
    with pytest.raises(error, match=text):
        service(insurance_db).execute("register_employer", HUMAN, {
            "org_number": "5566778899", "name": "Nyföretaget AB", "affiliation_date": "2026-01-01", **overrides})
    assert counts(insurance_db) == before


def test_registret_for_de_nya_operationerna():
    svc = ServiceLayer(events=MemoryEventLog(), rules=ProductRuleCatalog(today=date(2026, 11, 2)))
    levels = {name: svc.decision(name).effective for name in (
        "enroll_insured_person", "update_current_salary", "update_contact_details", "register_employer",
        "list_employers")}
    assert levels == {
        "enroll_insured_person": AgentAccess.APPROVAL,
        "update_current_salary": AgentAccess.HUMAN_ONLY,
        "update_contact_details": AgentAccess.HUMAN_ONLY,
        "register_employer": AgentAccess.HUMAN_ONLY,
        "list_employers": AgentAccess.AGENT,
    }
