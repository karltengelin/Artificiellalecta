"""Paket B steg 9: journalens ingående läge ersätts med ett nytt (B-057, P1-PENSION-001 §12.1, Karls val Q4).

Under byggfasen får det ingående läget per 2026-10-31 ersättas, men bara innan någon månad har stängts:
journalen får inte ha någon annan verifikation än det ingående läget. Det nya läget byggs som förut ur S-04
(`capital_ledger.plan_opening`), nu med det tillagda beståndet (`simulation.pension_population`).

Granskningen (`plan_reopening`) skriver ingenting. Den visar det gamla läget, det nya och en jämförelse per
försäkring. Varje försäkring i det gamla läget ska ha exakt samma kapital C och garanti G i det nya. Det nya
får bara tillföra försäkringar. Bokningen (`apply_reopening`) gör allt i en transaktion med granskningens
kontrollsumma:

1. tar bort det gamla lägets kontroller, kapitalposter, garantidelar och verifikation;
2. bokar det nya läget med `capital_ledger.apply_opening`.

Det sparade S-04-utdraget för det gamla läget ligger kvar i `valuation_extracts`. Det gamla lägets
sammanställning lämnas i bokningens svar, så att körskriptet kan spara den i sin logg (Q4).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from models import (
    LedgerBatch,
    LedgerCapitalEntry,
    LedgerControl,
    LedgerGuaranteePart,
    ValuationExtractRecord,
)
from services import capital_ledger as cl
from services import valuation_bases as vb
from services.valuation_extract import ValuationExtract

DECISION = "B-057"
ZERO = Decimal("0.00")


@dataclass
class ReopeningPlan:
    old: LedgerBatch
    new: cl.OpeningPlan
    changed: list[str]
    removed: list[str]
    added: list[str]
    other_batches: list[str]
    booked: dict[str, tuple[Decimal, Decimal]]
    planned: dict[str, tuple[Decimal, Decimal]]

    @property
    def problems(self) -> list[str]:
        out = list(self.new.problems)
        if self.other_batches:
            out.append(f"Journalen har {len(self.other_batches)} verifikationer utöver det ingående läget "
                       f"({', '.join(sorted(set(self.other_batches)))}); läget kan inte ersättas")
        if self.changed:
            first = self.changed[0]
            out.append(f"{len(self.changed)} befintliga försäkringar får annat C eller G, t.ex. {first}: "
                       f"bokat {self.booked[first]}, nytt {self.planned[first]}")
        if self.removed:
            out.append(f"{len(self.removed)} försäkringar faller bort ur läget, t.ex. {self.removed[0]}")
        if self.old.checksum == self.new.checksum:
            out.append("Det nya läget är detsamma som det bokade; ingenting att ersätta")
        return out

    @property
    def passed(self) -> bool:
        return self.new.passed and not self.problems

    @property
    def checksum(self) -> str:
        return vb.checksum({"decision": DECISION, "old": self.old.checksum, "new": self.new.checksum})

    def summary(self) -> dict:
        old_totals = self.old.content["totals"]
        new_totals = self.new.content["totals"]
        return {
            "decision": DECISION,
            "old": {"batch_id": str(self.old.id), "checksum": self.old.checksum,
                    "extract_checksum": self.old.extract_checksum, "totals": old_totals},
            "new": {"checksum": self.new.checksum, "extract_checksum": self.new.extract.checksum,
                    "totals": new_totals, "controls": self.new.content["controls"],
                    "not_transferred": self.new.content["not_transferred"]},
            "unchanged_policies": len(self.booked) - len(self.changed) - len(self.removed),
            "changed": self.changed, "removed": self.removed, "added": self.added,
            "other_batches": self.other_batches,
            "review_checksum": self.checksum, "passed": self.passed, "problems": self.problems,
        }


def _by_policy(extract) -> dict[str, tuple[Decimal, Decimal]]:
    """C och G per försäkring i ett S-04-utdrag."""
    return {p.policy_id: (p.capital, sum((g.guarantee for g in p.guarantee_parts), Decimal(0)))
            for p in extract.policies}


def booked_by_policy(session: Session, batch: LedgerBatch) -> dict[str, tuple[Decimal, Decimal]]:
    """C och G per försäkring i det bokade läget, ur det sparade utdrag som verifikationen bokades efter.

    Läget bokades exakt efter utdraget (kontrollerna *kapital per försäkring* och *garanti per försäkring*),
    och `verify_opening` prövar raderna mot verifikationen. Utdraget läses i stället för raderna, eftersom
    SQLite lagrar G med tio decimaler som flyttal.
    """
    record = session.get(ValuationExtractRecord, batch.extract_id)
    if record is None or record.checksum != batch.extract_checksum:
        raise cl.LedgerError("Det sparade S-04-utdraget för det ingående läget saknas")
    return _by_policy(ValuationExtract.model_validate(record.content))


def plan_reopening(session: Session, expected_extract_checksum: str | None = None) -> ReopeningPlan:
    """Granskar ersättningen: gammalt läge, nytt läge ur S-04 och jämförelse per försäkring. Skriver inget."""
    old = cl.opening_batch(session)
    if old is None:
        raise cl.LedgerError("Journalen har inget ingående läge att ersätta – boka det med open_capital_ledger")
    cl.verify_opening(session, old)
    others = [k for k in session.scalars(select(LedgerBatch.kind).where(LedgerBatch.id != old.id))]
    new = cl.plan_opening(session, expected_extract_checksum)
    booked = booked_by_policy(session, old)
    planned = _by_policy(new.extract)
    changed = sorted(p for p in booked if p in planned and planned[p] != booked[p])
    removed = sorted(p for p in booked if p not in planned)
    added = sorted(p for p in planned if p not in booked)
    return ReopeningPlan(old=old, new=new, changed=changed, removed=removed, added=added, other_batches=others,
                         booked=booked, planned=planned)


def apply_reopening(session: Session, actor: str, reviewed_checksum: str,
                    expected_extract_checksum: str | None = None) -> tuple[dict, bool]:
    """Ersätter det ingående läget med granskningens kontrollsumma. (sammanställning, nytt).

    Är det nya läget redan bokat (samma kontrollsumma som granskningens nya läge) blir det ingen ny effekt.
    """
    if session.bind.dialect.name == "postgresql":
        session.execute(select(func.pg_advisory_xact_lock(6047, cl.OPENING_DATE.toordinal())))
    current = cl.opening_batch(session)
    plan = plan_reopening(session, expected_extract_checksum)
    if plan.checksum != reviewed_checksum:
        if current is not None and current.checksum == plan.new.checksum:
            return {"already_reopened": True, "batch_id": str(current.id), "checksum": current.checksum}, False
        raise cl.LedgerConflict("Underlaget har ändrats sedan granskningen – granska ersättningen igen")
    if not plan.passed:
        raise cl.LedgerError("Ersättningen stoppas: " + "; ".join(plan.problems))
    summary = plan.summary()
    old_content = dict(plan.old.content)
    old_id = plan.old.id
    session.execute(delete(LedgerControl).where(LedgerControl.batch_id == old_id))
    session.execute(delete(LedgerCapitalEntry).where(LedgerCapitalEntry.batch_id == old_id))
    session.execute(delete(LedgerGuaranteePart).where(LedgerGuaranteePart.batch_id == old_id))
    session.execute(delete(LedgerBatch).where(LedgerBatch.id == old_id))
    session.flush()
    session.expire_all()
    batch, _ = cl.apply_opening(session, actor, plan.new.checksum, expected_extract_checksum)
    after = booked_by_policy(session, batch)
    wrong = [p for p, values in plan.booked.items() if after.get(p) != values]
    if wrong:
        raise cl.LedgerError(f"Efter ersättningen avviker {len(wrong)} befintliga försäkringar, t.ex. {wrong[0]}")
    return {**summary, "replaced_content": old_content, "new_batch_id": str(batch.id),
            "new_checksum": batch.checksum}, True
