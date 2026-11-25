"""Läsningarna för handläggarsidan *Pensioner och utbetalningar* (paket B steg 8, B-056, Karls val Z4, Z6, Z9).

Samma kedja som steg 6:s prov (`test_payout_orders.claimed`): B har en beslutad livsvarig plan från november,
novembers stängning har bokat anspråket och i dag är 2026-12-04.

- `get_pension_status` svarar läget utan personuppgifter och fallerar aldrig när steg 4–7 saknas – den säger
  vilka tabeller som saknas och med vilket skript de införs.
- `list_payout_parts` visar delarna med försäkringsnummer, namn, 66-årsmånad, läge och plan men aldrig
  personnumret.
- `get_payout_person` visar skattestatus och konton i alla versioner med maskerade kontonummer.
- Alla tre nekas agenter, i registret och i operationen.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
import yaml

from services import pension_desk as desk
from services import pension_claims as pc
from services import payout_orders as po
from services import death_reports as dr
from services import payout_plans as plans
from services.errors import AccessDeniedError, NotFoundError
from tests import test_payout_orders as orders
from tests import test_premium_month_export as export_tests
from tests.test_services_postgres import TEST_URL, isolated_schema
from tests.test_pension_claims import AGENT, DECEMBER, POLICY
from tests.test_premium_month_export import PERSONS, run

pytestmark = pytest.mark.filterwarnings("ignore:Dialect sqlite:sqlalchemy.exc.SAWarning")

chain = export_tests.chain
clock = export_tests.clock
claimed = orders.claimed

READS = ("get_pension_status", "list_payout_parts", "get_payout_person")


@pytest.fixture
def chain_on_postgres(monkeypatch):
    """Paket A:s testbestånd (export_tests.chain) i ett isolerat Postgres-schema i stället för SQLite."""
    if not TEST_URL:
        pytest.skip("SERVICES_TEST_POSTGRES_URL saknas – ingen isolerad Postgres")
    with isolated_schema() as schema:
        monkeypatch.setattr(export_tests, "create_engine", lambda *args, **kwargs: schema.engine)
        yield schema


def drop(db, *groups):
    """Tar bort steg 4–7:s tabeller som i Lakebase före migrationerna (senare steg först)."""
    with db.engine.begin() as conn:
        for tables in groups:
            for table in tables[::-1]:
                conn.exec_driver_sql(f"DROP TABLE {table}")


def status(db):
    return run(db, "get_pension_status").payload


def by_step(payload) -> dict[int, dict]:
    return {s["step"]: s for s in payload["steps"]}


# --- get_pension_status ---------------------------------------------------------------------------


def test_laget_med_alla_steg_inforda(claimed):
    payload = status(claimed)
    assert all(s["introduced"] for s in payload["steps"])
    assert payload["months"]["last_closed"] == "2026-11-30" and payload["months"]["next_open"] == "2026-12-01"
    assert payload["parts"]["by_state"]["in_payout"] == 1 and payload["parts"]["total"] == 4
    assert payload["company_capital_registered"] is True
    with claimed.factory() as s:
        assert payload["balances"]["payment_liability_sek"] == str(pc.account_balance(s, pc.LIABILITY, DECEMBER))
        assert payload["balances"]["company_sek"] == str(pc.account_balance(s, pc.COMPANY, DECEMBER))
    assert payload["balances"]["tax_liability_sek"] == "0.00"
    assert payload["balances"]["inheritance_pool_sek"] == "0.00"
    assert set(payload["cases"]) == set(desk.PENSION_CASE_TYPES)


def test_laget_saknar_personuppgifter(claimed):
    orders.tax(claimed)
    orders.account(claimed)
    text = json.dumps(status(claimed))
    assert not any(pnr[-4:] in text and pnr in text for pnr in PERSONS.values())
    assert orders.B_PNR not in text and "12345678" not in text
    assert "AL-0001" not in text  # inga försäkringsnummer heller


def test_laget_utan_steg_4_till_7_fallerar_inte(claimed):
    drop(claimed, plans.PLAN_TABLES, pc.CLAIM_TABLES, po.ORDER_TABLES, dr.DEATH_TABLES)
    payload = status(claimed)
    steps = by_step(payload)
    assert [steps[n]["introduced"] for n in range(1, 8)] == [True, True, True, False, False, False, False]
    assert steps[6]["missing_tables"] == list(po.ORDER_TABLES) and steps[6]["script"] == "migrate_payout_orders.py"
    assert not any(steps[n]["partial"] for n in range(1, 8))
    assert payload["balances"] == {} and payload["company_capital_registered"] is None
    assert payload["months"]["last_closed"] == "2026-11-30"


def test_delvis_infort_steg_raknas_som_ej_infort(claimed):
    drop(claimed, dr.DEATH_TABLES[-1:])
    steps = by_step(status(claimed))
    assert steps[7]["introduced"] is False and steps[7]["partial"] is True
    assert steps[7]["missing_tables"] == [dr.DEATH_TABLES[-1]]
    assert "inheritance_pool_sek" not in status(claimed)["balances"]


def test_bara_steg_4_infort(claimed):
    drop(claimed, pc.CLAIM_TABLES, po.ORDER_TABLES, dr.DEATH_TABLES)
    steps = by_step(status(claimed))
    assert [steps[n]["introduced"] for n in range(4, 8)] == [True, False, False, False]
    parts = run(claimed, "list_payout_parts").payload
    assert parts["plans_introduced"] is True and parts["total"] == 4


# --- list_payout_parts ----------------------------------------------------------------------------


def test_delarna_med_plan_och_utan_personnummer(claimed):
    payload = run(claimed, "list_payout_parts").payload
    assert payload["total"] == 4 and [p["policy_number"] for p in payload["parts"]] == sorted(POLICY.values())
    b = next(p for p in payload["parts"] if p["policy_number"] == POLICY["B"])
    assert b["state"] == "in_payout" and b["sixty_six_month"] == "2026-11-01"
    assert b["plan"]["form"] == "lifelong" and b["plan"]["m_sek"] == "10000.00"
    assert b["owner_name"]
    text = json.dumps(payload)
    assert orders.B_PNR not in text and not any(pnr in text for pnr in PERSONS.values())


def test_delarna_urval_och_sidor(claimed):
    assert run(claimed, "list_payout_parts", {"state": "in_payout"}).payload["total"] == 1
    assert run(claimed, "list_payout_parts", {"policy_number": POLICY["B"]}).payload["total"] == 1
    page = run(claimed, "list_payout_parts", {"limit": 2, "offset": 2}).payload
    assert page["total"] == 4 and page["count"] == 2 and page["parts"][0]["policy_number"] == POLICY["C"]
    # Saknad skattestatus vid bankfilen ger ärendet tax_status hos B
    orders.account(claimed)
    orders.create(claimed)
    found = run(claimed, "list_payout_parts", {"case_type": "tax_status"}).payload
    assert [p["policy_number"] for p in found["parts"]] == [POLICY["B"]]
    assert "tax_status" in {c["case_type"] for c in found["parts"][0]["open_cases"]}


def test_delarna_soks_inte_pa_personnummer(claimed):
    assert run(claimed, "list_payout_parts", {"query": orders.B_PNR[:8]}).payload["total"] == 0


# --- get_payout_person ----------------------------------------------------------------------------


def test_personen_med_alla_versioner_och_maskerat_konto(claimed):
    orders.tax(claimed)
    orders.tax(claimed, rate="0.4000", received="2026-11-22")
    orders.account(claimed, "12345678")
    orders.account(claimed, "87654321")
    payload = run(claimed, "get_payout_person", {"policy_number": POLICY["B"]}).payload
    assert payload["personal_id_number"] == orders.B_PNR and payload["policies"] == [POLICY["B"]]
    assert [t["version"] for t in payload["tax_statuses"]] == [1, 2]
    assert [t["rate"] for t in payload["tax_statuses"]] == ["0.3000", "0.4000"]
    assert [a["account_number"] for a in payload["accounts"]] == ["****5678", "****4321"]
    assert payload["current_account"]["account_number"] == "****4321"
    text = json.dumps(payload)
    assert "12345678" not in text and "87654321" not in text
    same = run(claimed, "get_payout_person", {"personal_id_number": orders.B_PNR}).payload
    assert same == payload


def test_personen_utan_steg_6(claimed):
    drop(claimed, po.ORDER_TABLES, dr.DEATH_TABLES)
    payload = run(claimed, "get_payout_person", {"policy_number": POLICY["B"]}).payload
    assert payload["orders_introduced"] is False and payload["tax_statuses"] == [] and payload["accounts"] == []
    assert payload["parts"][0]["state"] == "in_payout"


def test_okand_person_och_fel_indata(claimed):
    with pytest.raises(NotFoundError):
        run(claimed, "get_payout_person", {"policy_number": "AL-999999"})
    with pytest.raises(Exception, match="antingen"):
        run(claimed, "get_payout_person", {"policy_number": POLICY["B"], "personal_id_number": orders.B_PNR})


# --- åtkomst --------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", READS)
def test_agenter_nekas(claimed, name):
    data = {"policy_number": POLICY["B"]} if name == "get_payout_person" else {}
    with pytest.raises(AccessDeniedError):
        run(claimed, name, data, ctx=AGENT)


def test_registret_har_dem_som_human_only():
    with open("src/services/access_register.yaml", encoding="utf-8") as f:
        register = yaml.safe_load(f)["operations"]
    assert all(register[name] == "HUMAN_ONLY" for name in READS)


def test_stegens_tabeller_ar_migreringarnas():
    # Sidan läser steg 1:s och 2:s tabellnamn ur modellerna för att slippa en cirkelimport
    from utils import migration_capital_ledger, migration_payout_parts
    tables = {number: names for number, _, names, _ in desk.STEPS}
    assert tables[1] == migration_payout_parts.TABLES
    assert tables[2] == migration_capital_ledger.TABLES


# --- Postgres -------------------------------------------------------------------------------------


def test_lasningarna_mot_postgres(chain_on_postgres, claimed):
    db = claimed
    assert db.engine is chain_on_postgres.engine
    orders.tax(db)
    orders.account(db)
    payload = status(db)
    assert all(s["introduced"] for s in payload["steps"])
    assert payload["parts"]["by_state"]["in_payout"] == 1
    assert Decimal(payload["balances"]["payment_liability_sek"]) > 0
    parts = run(db, "list_payout_parts", {"query": POLICY["B"][-3:]}).payload
    assert [p["policy_number"] for p in parts["parts"]] == [POLICY["B"]]
    person = run(db, "get_payout_person", {"policy_number": POLICY["B"]}).payload
    assert person["current_account"]["account_number"] == "****5678"
