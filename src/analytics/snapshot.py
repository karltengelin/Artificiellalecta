"""Operatörens offline-adapter för befintlig JSONL-backup. Ingen Lakebaseåtkomst.

Nuvarande schema saknar historisk arbetsgivare på premien. Anroparen
måste uttryckligen acceptera aktuell snapshot-koppling som scenarioantagande.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from analytics.premium_impact import PremiumObservation


def load_snapshot(source: Path, *, assume_current_employer: bool = False):
    if not assume_current_employer:
        raise ValueError("Historisk arbetsgivare saknas: bekräfta snapshot-koppling som scenarioantagande")
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))

    def rows(name):
        if name not in manifest["tables"]:
            raise ValueError(f"Backup saknar tabell: {name}")
        records = [json.loads(line) for line in (source / f"{name}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(records) != manifest["row_counts"].get(name):
            raise ValueError(f"Radantal stämmer inte för {name}")
        return records

    def index(name):
        records = rows(name)
        result = {str(row["id"]): row for row in records}
        if len(result) != len(records):
            raise ValueError(f"Dubbla ID i {name}")
        return result

    people, policies, benefits = (index(name) for name in ("insured_persons", "policies", "policy_benefits"))
    base_amounts = rows("base_amounts")
    ibb = {int(row["year"]): Decimal(str(row["income_base_amount_sek"])) for row in base_amounts}
    if len(ibb) != len(base_amounts):
        raise ValueError("Dubbla basbeloppsår")
    observations = []
    for row in rows("premium_transactions"):
        if row["transaction_type"] != "premium":
            continue
        benefit = benefits[str(row["benefit_id"])]
        if benefit["benefit_type"] != "retirement_dc":
            continue
        policy = policies[str(benefit["policy_id"])]
        person = people[str(policy["insured_person_id"])]
        pnr = str(person.get("personal_id_number", ""))
        try:
            birth = date(int(pnr[:4]), int(pnr[4:6]), int(pnr[6:8])) if len(pnr) == 12 and pnr.isdigit() else None
        except ValueError:
            birth = None
        month = date.fromisoformat(row["period_month"])
        if month.day != 1:
            raise ValueError("Premieperiod är inte månadens första dag")
        observations.append(PremiumObservation(
            str(row["id"]), str(person["id"]), str(person.get("employer_id") or ""),
            str(policy["id"]), str(benefit["id"]), month,
            Decimal(str(row["pensionable_salary_sek"])) if row["pensionable_salary_sek"] is not None else None,
            Decimal(str(row["amount_sek"])), birth, row["status"],
        ))
    return observations, ibb, manifest["created_at"]
