"""Fas 2c: modellkontrakt i SQLite med FK; Postgres-DDL utan anslutning.

Provar lagringsgränser, inte autentisering, handelslogik eller samtidighet.
Inga utils.db-motorer, marknadsdata eller externa databaser används.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, delete, event, func, insert, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateTable

from models import Base, Portfolio, PortfolioHolding, Trade
from utils.backup import backup_database, restore_database

T0 = datetime(2026, 10, 24, 10, tzinfo=UTC)
HASH = "a" * 64


def portfolio_data(**changes):
    return {
        "id": uuid.uuid4(),
        "scenario_code": uuid.uuid4().hex,
        "name": "Portföljtest",
        "scenario_description": "Fristående portföljtest, inte åtagandetäckning",
        "starts_at": T0,
        "opening_cash_sek": Decimal("1000.00"),
        "funding_basis": {
            "amount_sek": "1000.00",
            "approved_by": "karl",
            "source": "synthetic",
        },
        "guideline_reference": "SD-KAP-001",
        "guideline_version": "0.1",
        "guideline_hash": HASH,
        "scenario_basis": {"purpose": "test", "settlement": "instant_simulated"},
    } | changes


def holding_data(portfolio_id, **changes):
    return {
        "id": uuid.uuid4(),
        "portfolio_id": portfolio_id,
        "instrument_key": "SYNTHETIC-CLASS-A",
        "name": "Syntetiskt testinstrument",
        "allocation_bucket": "global_equity",
        "price_currency": "SEK",
        "instrument_basis_reference": "synthetic-instrument-list-v1",
        "instrument_basis_hash": HASH,
        "instrument_basis": {
            "synthetic": True,
            "version": "1",
            "lookthrough_at": "2026-10-23",
        },
    } | changes


def trade_data(holding_id, **changes):
    return {
        "id": uuid.uuid4(),
        "portfolio_holding_id": holding_id,
        "side": "buy",
        "status": "proposed",
        "quantity": Decimal("2.0000000000"),
        "limit_price": Decimal("50.0000000000"),
        "max_cost_sek": Decimal("2.00"),
        "max_cash_sek": Decimal("102.00"),
        "proposed_at": T0,
        "valid_until": T0 + timedelta(hours=2),
        "proposed_by": "portfolio_manager",
        "proposer_type": "agent",
        "reason": "Syntetiskt saldokontrollfall",
        "proposal_hash": HASH,
        "proposal_price_basis": {
            "price": "49.50",
            "currency": "SEK",
            "source": "synthetic",
            "observed_at": "2026-10-23T16:00:00Z",
            "fx_rate": "1",
        },
        "proposal_basis": {
            "guideline_hash": HASH,
            "instrument_hash": HASH,
            "checks": "synthetic",
        },
    } | changes


def approval():
    return {
        "approved_at": T0 + timedelta(minutes=1),
        "approved_by": "karl",
        "approval_role": "operator",
        "approved_proposal_hash": HASH,
        "approval_basis": {"proposal_hash": HASH, "decision": "approve"},
    }


def execution():
    return {
        "executed_at": T0 + timedelta(minutes=2),
        "execution_price": Decimal("50.0000000000"),
        "execution_fx_rate": Decimal("1.0000000000"),
        "gross_sek": Decimal("100.00"),
        "cost_sek": Decimal("1.00"),
        "execution_price_basis": {
            "price": "50.00",
            "currency": "SEK",
            "source": "synthetic",
            "observed_at": "2026-10-24T10:02:00Z",
            "fx_rate": "1",
        },
        "execution_basis": {
            "settlement": "instant_simulated",
            "cost_assumption": "1 SEK",
        },
    }


def rejection():
    return {
        "rejected_at": T0 + timedelta(minutes=3),
        "rejected_by": "karl",
        "rejection_reason": "Förutsättningarna har ändrats",
    }


@pytest.fixture
def capital_db():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys = ON")

    Base.metadata.create_all(engine)
    p = portfolio_data()
    h = holding_data(p["id"])
    with engine.begin() as conn:
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        conn.execute(insert(Portfolio), p)
        conn.execute(insert(PortfolioHolding), h)
    yield SimpleNamespace(engine=engine, portfolio=p["id"], holding=h["id"])
    engine.dispose()


def save_trade(db, **changes):
    row = trade_data(db.holding, **changes)
    with db.engine.begin() as conn:
        conn.execute(insert(Trade), row)
    return row["id"]


def test_lifecycle_preserves_proposal_and_each_receipt(capital_db):
    trade_id = save_trade(capital_db)
    with capital_db.engine.begin() as conn:
        conn.execute(
            update(Trade)
            .where(Trade.id == trade_id)
            .values(status="approved", **approval())
        )
    with capital_db.engine.begin() as conn:
        conn.execute(
            update(Trade)
            .where(Trade.id == trade_id)
            .values(status="executed", **execution())
        )

    with Session(capital_db.engine) as session:
        trade = session.get(Trade, trade_id)
        assert trade.holding.portfolio.id == capital_db.portfolio
        assert trade.status == "executed"
        assert trade.proposed_by == "portfolio_manager"
        assert trade.approved_by == "karl"
        assert trade.approved_proposal_hash == trade.proposal_hash == HASH
        assert trade.quantity == Decimal("2.0000000000")
        assert trade.gross_sek == Decimal("100.00")
        assert trade.cost_sek == Decimal("1.00")
        assert trade.proposal_price_basis["price"] == "49.50"
        assert trade.execution_price_basis["price"] == "50.00"
        assert trade.approval_basis["decision"] == "approve"
        assert trade.created_at is not None and trade.updated_at is not None
        assert trade.holding.portfolio.opening_cash_sek == Decimal("1000.00")


@pytest.mark.parametrize("approved", [False, True])
def test_rejection_can_preserve_an_earlier_approval_after_expiry(capital_db, approved):
    trade_id = save_trade(
        capital_db,
        status="rejected",
        **(approval() if approved else {}),
        **(rejection() | {"rejected_at": T0 + timedelta(days=1)}),
    )
    with Session(capital_db.engine) as session:
        trade = session.get(Trade, trade_id)
        assert (trade.approved_by == "karl") == approved
        assert trade.execution_basis is None
        assert trade.rejection_reason


def test_only_executed_trades_change_the_reconstructible_position(capital_db):
    # Dubbletter av samma värden är här fyra OLIKA syntetiska förslag, inte återförsök.
    save_trade(capital_db)
    save_trade(capital_db, status="approved", **approval())
    save_trade(capital_db, status="rejected", **rejection())
    buy = save_trade(capital_db, status="executed", **approval(), **execution())
    save_trade(
        capital_db,
        side="sell",
        status="executed",
        quantity=Decimal("0.5"),
        max_cash_sek=None,
        min_proceeds_sek=Decimal("24.00"),
        corrects_trade_id=buy,
        **approval(),
        **(execution() | {"gross_sek": Decimal("25.00")}),
    )
    with capital_db.engine.connect() as conn:
        rows = conn.execute(
            select(Trade.side, Trade.quantity, Trade.gross_sek, Trade.cost_sek).where(
                Trade.status == "executed"
            )
        ).all()
    quantity = sum(q if side == "buy" else -q for side, q, _, _ in rows)
    cash = Decimal(1000) + sum(
        (-gross if side == "buy" else gross) - cost for side, _, gross, cost in rows
    )
    assert (quantity, cash) == (Decimal("1.5"), Decimal("923.00"))


@pytest.mark.parametrize("field", list(approval()))
def test_half_approval_is_rejected_including_null_json(capital_db, field):
    receipt = approval() | {field: None}
    with pytest.raises(IntegrityError):
        save_trade(capital_db, status="approved", **receipt)


@pytest.mark.parametrize("field", list(execution()))
def test_half_execution_is_rejected_including_null_json(capital_db, field):
    with pytest.raises(IntegrityError):
        save_trade(
            capital_db, status="executed", **approval(), **(execution() | {field: None})
        )


@pytest.mark.parametrize("field", list(rejection()))
def test_half_rejection_is_rejected(capital_db, field):
    with pytest.raises(IntegrityError):
        save_trade(capital_db, status="rejected", **(rejection() | {field: None}))


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "approved"},
        {"status": "executed", **execution()},  # inget godkännande
        {"status": "rejected"},
        {"status": "proposed", **approval()},
        {"status": "proposed", "approval_basis": {"forged": True}},
        {"status": "approved", **approval(), **execution()},
        {"status": "executed", **approval(), **execution(), **rejection()},
        {"status": "rejected", **approval(), **execution(), **rejection()},
        {"status": "pending"},
    ],
)
def test_status_must_match_its_receipts(capital_db, changes):
    with pytest.raises(IntegrityError):
        save_trade(capital_db, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"side": "deposit"},
        {"proposer_type": "system"},
        {"quantity": 0},
        {"quantity": -1},
        {"limit_price": 0},
        {"max_cost_sek": -1},
        {"max_cash_sek": None},
        {"max_cash_sek": 0},
        {"min_proceeds_sek": 1},
        {"side": "sell", "min_proceeds_sek": 0},
        {"side": "sell", "max_cash_sek": None, "min_proceeds_sek": -1},
        {"valid_until": T0},
        {"reason": "   "},
        {"proposed_by": ""},
        {"proposal_hash": "short"},
        {"proposal_price_basis": None},
        {"proposal_basis": None},
    ],
)
def test_invalid_proposal_terms_are_rejected(capital_db, changes):
    with pytest.raises(IntegrityError):
        save_trade(capital_db, **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"approved_proposal_hash": "b" * 64},
        {"approved_by": " "},
        {"approval_role": ""},
        {"approved_at": T0 - timedelta(seconds=1)},
        {"approved_at": T0 + timedelta(hours=3)},
    ],
)
def test_approval_is_bound_to_proposal_and_validity(capital_db, changes):
    with pytest.raises(IntegrityError):
        save_trade(capital_db, status="approved", **(approval() | changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"executed_at": T0},
        {"executed_at": T0 + timedelta(hours=3)},
        {"execution_price": 0},
        {"execution_fx_rate": 0},
        {"execution_fx_rate": -1},
        {"gross_sek": 0},
        {"cost_sek": -1},
        {"cost_sek": Decimal("2.01")},
        {"execution_price": Decimal("50.01")},
        {"gross_sek": Decimal("102.00")},
    ],
)
def test_execution_must_hold_the_approved_limits(capital_db, changes):
    with pytest.raises(IntegrityError):
        save_trade(
            capital_db, status="executed", **approval(), **(execution() | changes)
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"execution_price": Decimal("49.99")},
        {"min_proceeds_sek": Decimal("99.01")},
    ],
)
def test_sell_checks_both_minimum_price_and_net_proceeds(capital_db, changes):
    row = (
        trade_data(
            capital_db.holding,
            side="sell",
            status="executed",
            max_cash_sek=None,
            min_proceeds_sek=Decimal("99.00"),
            **approval(),
            **execution(),
        )
        | changes
    )
    with pytest.raises(IntegrityError), capital_db.engine.begin() as conn:
        conn.execute(insert(Trade), row)


@pytest.mark.parametrize(
    "changes",
    [
        {"rejected_at": T0 - timedelta(seconds=1)},
        {"rejected_at": T0},
        {"rejected_by": " "},
        {"rejection_reason": ""},
    ],
)
def test_rejection_keeps_chronology_and_reason(capital_db, changes):
    with pytest.raises(IntegrityError):
        save_trade(
            capital_db, status="rejected", **approval(), **(rejection() | changes)
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"mode": "live"},
        {"scenario_type": "insurance_linked"},
        {"base_currency": "USD"},
        {"settlement_model": "T+2"},
        {"opening_cash_sek": -1},
        {"opening_cash_sek": None},
        {"name": " "},
        {"scenario_code": ""},
        {"scenario_description": ""},
        {"guideline_reference": " "},
        {"guideline_version": ""},
        {"guideline_hash": "short"},
        {"funding_basis": None},
        {"scenario_basis": None},
    ],
)
def test_scenario_cannot_enable_live_or_unfunded_trading(capital_db, changes):
    with pytest.raises(IntegrityError), capital_db.engine.begin() as conn:
        conn.execute(insert(Portfolio), portfolio_data(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"allocation_bucket": "cash"},
        {"allocation_bucket": "crypto"},
        {"instrument_key": " "},
        {"name": ""},
        {"price_currency": ""},
        {"instrument_basis_reference": ""},
        {"instrument_basis_hash": "short"},
        {"instrument_basis": None},
    ],
)
def test_instrument_requires_identity_and_permitted_allocation(capital_db, changes):
    with pytest.raises(IntegrityError), capital_db.engine.begin() as conn:
        conn.execute(
            insert(PortfolioHolding),
            holding_data(
                capital_db.portfolio,
                **({"instrument_key": uuid.uuid4().hex} | changes),
            ),
        )


def test_unique_instrument_is_scoped_to_portfolio(capital_db):
    with pytest.raises(IntegrityError), capital_db.engine.begin() as conn:
        conn.execute(insert(PortfolioHolding), holding_data(capital_db.portfolio))
    second = portfolio_data()
    with capital_db.engine.begin() as conn:
        conn.execute(insert(Portfolio), second)
        conn.execute(insert(PortfolioHolding), holding_data(second["id"]))


def test_scenario_code_cannot_be_reused(capital_db):
    with capital_db.engine.connect() as conn:
        code = conn.scalar(
            select(Portfolio.scenario_code).where(Portfolio.id == capital_db.portfolio)
        )
    with pytest.raises(IntegrityError), capital_db.engine.begin() as conn:
        conn.execute(insert(Portfolio), portfolio_data(scenario_code=code))


@pytest.mark.parametrize(
    "link", ["portfolio_holding_id", "supersedes_trade_id", "corrects_trade_id"]
)
def test_unknown_foreign_keys_are_rejected(capital_db, link):
    with pytest.raises(IntegrityError):
        save_trade(capital_db, **{link: uuid.uuid4()})


def test_holding_requires_a_known_portfolio(capital_db):
    with pytest.raises(IntegrityError), capital_db.engine.begin() as conn:
        conn.execute(insert(PortfolioHolding), holding_data(uuid.uuid4()))


@pytest.mark.parametrize("link", ["supersedes_trade_id", "corrects_trade_id"])
def test_linked_history_cannot_be_deleted_or_reference_itself(capital_db, link):
    original = save_trade(capital_db)
    save_trade(capital_db, **{link: original})
    with pytest.raises(IntegrityError), capital_db.engine.begin() as conn:
        conn.execute(delete(Trade).where(Trade.id == original))
    # Nytt id så att en PK-krock inte maskerar kontrollen av självpekning.
    new_id = uuid.uuid4()
    with pytest.raises(IntegrityError):
        save_trade(capital_db, id=new_id, **{link: new_id})


def test_parent_delete_does_not_cascade_away_history(capital_db):
    save_trade(capital_db)
    for model, key in [
        (Portfolio, capital_db.portfolio),
        (PortfolioHolding, capital_db.holding),
    ]:
        with pytest.raises(IntegrityError), Session(capital_db.engine) as session:
            parent = session.get(model, key)
            # Även med inlästa barn ska ORM lämna RESTRICT till databasen.
            children = parent.holdings if model is Portfolio else parent.trades
            assert children
            session.delete(parent)
            session.commit()
    with capital_db.engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(Trade)) == 1


def test_defaults_have_no_hidden_funding_or_position(capital_db):
    trade_id = save_trade(capital_db)
    with Session(capital_db.engine) as session:
        portfolio = session.get(Portfolio, capital_db.portfolio)
        assert (
            portfolio.mode,
            portfolio.scenario_type,
            portfolio.base_currency,
            portfolio.settlement_model,
        ) == ("paper", "standalone", "SEK", "instant_simulated")
        assert session.get(Trade, trade_id).status == "proposed"
    assert "quantity" not in PortfolioHolding.__table__.columns
    assert "cash_balance_sek" not in Portfolio.__table__.columns
    assert "total_value_sek" not in Portfolio.__table__.columns


def test_backup_restores_receipts_and_both_history_links(capital_db, tmp_path):
    rejected = save_trade(capital_db, status="rejected", **approval(), **rejection())
    executed = save_trade(
        capital_db,
        supersedes_trade_id=rejected,
        status="executed",
        **approval(),
        **execution(),
    )
    correction = save_trade(capital_db, corrects_trade_id=executed)
    folder = backup_database(capital_db.engine, tmp_path)
    path = folder / "trades.jsonl"
    records = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    # Tvinga barnen före föräldrarna; återställningen måste använda båda själv-FK:erna.
    by_id = {record["id"]: record for record in records}
    path.write_text(
        "\n".join(
            json.dumps(by_id[str(key)]) for key in [correction, executed, rejected]
        )
        + "\n",
        encoding="utf-8",
    )
    target = create_engine("sqlite://")

    @event.listens_for(target, "connect")
    def enforce_foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys = ON")

    try:
        counts = restore_database(target, folder)
        assert (
            counts["portfolios"],
            counts["portfolio_holdings"],
            counts["trades"],
        ) == (1, 1, 3)
        with Session(target) as session:
            restored = session.get(Trade, executed)
            assert restored.supersedes_trade_id == rejected
            assert restored.execution_price_basis["price"] == "50.00"
            assert restored.proposal_price_basis["price"] == "49.50"
            assert restored.approved_proposal_hash == HASH
            assert restored.gross_sek == Decimal("100.00")
            assert restored.rejection_reason is None
            assert session.get(Trade, correction).corrects_trade_id == executed
            assert session.get(Trade, correction).approval_basis is None
            assert session.get(Trade, rejected).rejection_reason
    finally:
        target.dispose()


def test_postgres_ddl_and_indexes_compile_without_a_connection():
    dialect = postgresql.dialect()
    for model in [Portfolio, PortfolioHolding, Trade]:
        ddl = str(CreateTable(model.__table__).compile(dialect=dialect))
        assert "UUID" in ddl and "JSONB" in ddl and "TIMESTAMP WITH TIME ZONE" in ddl
        assert "CHECK" in ddl
        for index in model.__table__.indexes:
            assert "CREATE INDEX" in str(CreateIndex(index).compile(dialect=dialect))
    trade_ddl = str(CreateTable(Trade.__table__).compile(dialect=dialect))
    assert "NUMERIC(24, 10)" in trade_ddl
    assert "ON DELETE RESTRICT" in trade_ddl
    assert {"portfolios", "portfolio_holdings", "trades"} <= Base.metadata.tables.keys()
