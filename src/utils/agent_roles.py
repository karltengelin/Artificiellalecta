"""Databasrättigheter för agentteamens begränsade roller (harness.md §5.1).

Agentens tjänstelager läser försäkringsdata och lägger till förslag och loggrader –
inget mer. Ingen UPDATE eller DELETE någonstans: agenten kan inte ändra affärsdata,
inte avgöra ett förslag och inte ändra loggen. Provkörning av förslag och
handläggarens godkännanden går via den betrodda anslutningen (DATABASE_URL).

Tabellerna listas uttryckligen. En ny tabell – t.ex. kapitalförvaltningens – ger
ingen rättighet förrän den läggs till här efter granskning.

Används av scripts/setup/grant_agent_role.py och tests/test_agents_postgres_role.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Connection

#: SQLAlchemy hämtar servergenererade tidsstämplar med INSERT … RETURNING, vilket kräver
#: SELECT på just de kolumnerna. Kolumnrättigheten ger inte åtkomst till radernas innehåll.
RETURNING_COLUMNS = ("created_at", "updated_at")


@dataclass(frozen=True)
class RoleGrants:
    role: str
    select: tuple[str, ...]
    insert: tuple[str, ...]  # får även SELECT på RETURNING_COLUMNS
    # SELECT på enbart dessa kolumner: ((tabell, (kolumn, …)), …). Övriga kolumner förblir stängda.
    columns: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def tables(self) -> list[str]:
        return sorted(set(self.select) | set(self.insert) | {t for t, _ in self.columns})

    def statements(self, schema: str = "public") -> list[str]:
        """SQL som ger rollen exakt dessa rättigheter i schemat (idempotent)."""
        _check_identifier(self.role)
        _check_identifier(schema)
        for table in self.tables:
            _check_identifier(table)
        for table, cols in self.columns:
            if table in self.select or not cols:
                raise ValueError(f"Kolumnrättighet för {table}: tabellen har redan full SELECT eller saknar kolumner")
            for column in cols:
                _check_identifier(column)
        q = f'"{schema}"'
        # REVOKE på tabellnivå tar även bort kolumnrättigheter i Postgres
        out = [
            f'REVOKE ALL ON ALL TABLES IN SCHEMA {q} FROM "{self.role}"',
            f'GRANT USAGE ON SCHEMA {q} TO "{self.role}"',
        ]
        out += [f'GRANT SELECT ON {q}."{t}" TO "{self.role}"' for t in self.select]
        out += [f'GRANT INSERT ON {q}."{t}" TO "{self.role}"' for t in self.insert]
        columns = ", ".join(f'"{c}"' for c in RETURNING_COLUMNS)
        out += [f'GRANT SELECT ({columns}) ON {q}."{t}" TO "{self.role}"' for t in self.insert]
        for table, cols in self.columns:
            listed = ", ".join(f'"{c}"' for c in cols)
            out.append(f'GRANT SELECT ({listed}) ON {q}."{table}" TO "{self.role}"')
        return out


FORSAKRING = RoleGrants(
    role="agent_forsakring",
    select=(
        "base_amounts",
        "cases",  # ärenden (B-033); kundscope verkställs i harness, inte i databasen
        "employers",
        "insured_persons",
        "policies",
        "policy_benefits",
        "policy_states",
        "premium_transactions",
        "product_parameters",  # premieberäkningens parametrar (B-035); kräver migrate_product_parameters.py först
        "salary_reports",
    ),
    insert=("approval_requests", "operation_events"),
)

#: Aktuarieteamet (B-035 val I): beståndsinsikten läser individrader i betrodd kod och lämnar
#: bara aggregat. Bara tabellerna estimate_parameter_change_impact och get_product_parameters
#: läser – inga löner, ärenden eller arbetsgivare. Inga förslag: ingen INSERT på kön.
#: Ledningsaggregatet get_company_metrics (OC-3a val D) får bara de kolumner det summerar:
#: förmånens koppling och premieradens typ, status, betaldatum och belopp – inte pensionsgrundande
#: lön eller beräkningsunderlag.
AKTUARIE = RoleGrants(
    role="agent_aktuarie",
    select=(
        "base_amounts",
        "insured_persons",
        "policies",
        "policy_states",
        "product_parameters",
    ),
    insert=("operation_events",),
    columns=(
        ("policy_benefits", ("id", "policy_id")),
        ("premium_transactions", ("benefit_id", "transaction_type", "status", "paid_date", "amount_sek")),
    ),
)

#: Compliance-teamet: produktparametrarna (get_product_parameters) och basbeloppen för
#: förhandsberäkningen (calculate_premium_preview). Ingen individdata och inga förslag –
#: aktiveringsförslaget i parameterflödet läggs av motorn med den betrodda anslutningen.
COMPLIANCE = RoleGrants(
    role="agent_compliance",
    select=("base_amounts", "product_parameters"),
    insert=("operation_events",),
)

ROLE_GRANTS = {"forsakring": FORSAKRING, "aktuarie": AKTUARIE, "compliance": COMPLIANCE}


def inspect_role(conn: Connection, grants: RoleGrants, schema: str = "public") -> list[str]:
    """Förkontroller före GRANT. Returnerar problem – tom lista betyder klart att köra."""
    problems: list[str] = []
    role = conn.execute(
        text("SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls FROM pg_roles WHERE rolname = :r"),
        {"r": grants.role},
    ).one_or_none()
    if role is None:
        return [f"Rollen '{grants.role}' finns inte – operatören skapar den i Databricks"]
    if any(role):
        problems.append(f"Rollen '{grants.role}' har superuser, CREATEROLE, CREATEDB eller BYPASSRLS")
    memberships = conn.execute(
        text(
            "SELECT m.rolname FROM pg_auth_members a JOIN pg_roles m ON m.oid = a.roleid "
            "JOIN pg_roles r ON r.oid = a.member WHERE r.rolname = :r"
        ),
        {"r": grants.role},
    ).scalars().all()
    if memberships:
        problems.append(f"Rollen '{grants.role}' är medlem i {', '.join(memberships)} – den ärver rättigheter")
    owners = dict(conn.execute(
        text("SELECT tablename, tableowner FROM pg_tables WHERE schemaname = :s"), {"s": schema}
    ).all())
    me = conn.execute(text("SELECT current_user")).scalar_one()
    for table in grants.tables:
        if table not in owners:
            problems.append(f"Tabellen {schema}.{table} finns inte")
        elif owners[table] != me:
            problems.append(f"Tabellen {schema}.{table} ägs av {owners[table]}, inte {me}")
    return problems


def current_privileges(conn: Connection, role: str, schema: str = "public") -> dict[str, list[str]]:
    rows = conn.execute(
        text(
            "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
            "WHERE grantee = :r AND table_schema = :s ORDER BY table_name, privilege_type"
        ),
        {"r": role, "s": schema},
    ).all()
    out: dict[str, list[str]] = {}
    for table, privilege in rows:
        out.setdefault(table, []).append(privilege)
    return out


def current_column_privileges(conn: Connection, role: str, schema: str = "public") -> dict[str, list[str]]:
    """Kolumnrättigheter utöver tabellrättigheterna – {"tabell.kolumn": [rättigheter]}."""
    rows = conn.execute(
        text(
            "SELECT c.table_name, c.column_name, c.privilege_type FROM information_schema.column_privileges c "
            "WHERE c.grantee = :r AND c.table_schema = :s AND NOT EXISTS ("
            "  SELECT 1 FROM information_schema.role_table_grants t WHERE t.grantee = c.grantee"
            "  AND t.table_schema = c.table_schema AND t.table_name = c.table_name"
            "  AND t.privilege_type = c.privilege_type) "
            "ORDER BY 1, 2, 3"
        ),
        {"r": role, "s": schema},
    ).all()
    out: dict[str, list[str]] = {}
    for table, column, privilege in rows:
        out.setdefault(f"{table}.{column}", []).append(privilege)
    return out


def _check_identifier(name: str) -> None:
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", name):
        raise ValueError(f"Ogiltigt identifierare för SQL: {name!r}")
