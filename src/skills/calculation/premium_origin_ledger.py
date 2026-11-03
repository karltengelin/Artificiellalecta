"""Kapitalspår per ursprung med oförändrad avrundning per försäkring (PR-020).

Månadsbeloppen räknas av close_month. Bara deras fördelning på ursprung tillkommer.
Historisk rekonstruktion behåller källa, premiens ID och de frysta grundversionerna.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from skills.calculation.capital_rollforward import allocate_cents, close_month
from utils.checksums import checksum

if TYPE_CHECKING:
    from services.valuation_extract import ValuationExtract

ZERO = Decimal("0.00")
VERSION = "premium-origins-1"


def origin_code_version():
    import hashlib

    digest = hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    return VERSION + "+" + digest


@dataclass(frozen=True)
class Origin:
    id: str
    policy_id: str
    capital: Decimal


def roll_origins(month: date, rate: Decimal, origins: list[Origin], additions: list[Origin], *,
                 fee_rate: Decimal, tax_rate: Decimal) -> tuple[list[Origin], list[dict], object]:
    old = {o.id: o for o in origins}
    new = {o.id: o for o in additions}
    if len(old) != len(origins) or len(new) != len(additions) or set(old) & set(new):
        raise ValueError("Ett ursprung får bara tillföras en gång")
    if any(o.capital < 0 or o.capital != o.capital.quantize(Decimal("0.01")) for o in [*origins, *additions]):
        raise ValueError("Varje ursprungs kapital ska vara icke-negativt och i hela ören")
    openings, added = defaultdict(Decimal), defaultdict(Decimal)
    old_by_policy, new_by_policy = defaultdict(list), defaultdict(list)
    for o in origins:
        openings[o.policy_id] += o.capital
        old_by_policy[o.policy_id].append(o)
    for o in additions:
        added[o.policy_id] += o.capital
        new_by_policy[o.policy_id].append(o)
    closed = close_month(month, rate, openings, added, fee_rate=fee_rate, tax_rate=tax_rate)
    result, entries = [], []
    for policy, line in sorted(closed.lines.items()):
        tracks = sorted(old_by_policy[policy], key=lambda o: o.id)
        balances = [o.capital for o in tracks]
        for kind, amount, sign in (("return", line.investment_return, 1), ("fee", line.fee, -1), ("tax", line.tax, -1)):
            weights = [v * (-1 if amount < 0 else 1) for v in balances]
            shares = allocate_cents(amount, weights)
            for index, (o, share) in enumerate(zip(tracks, shares, strict=True)):
                balances[index] += sign * share
                if balances[index] < 0:
                    raise ValueError("En debitering överskrider ursprungets kapital")
                if share:
                    entries.append({"origin_id": o.id, "policy_id": policy, "kind": kind,
                                    "amount": str(sign * share), "month": month.isoformat()})
        policy_result = [Origin(o.id, policy, balance) for o, balance in zip(tracks, balances, strict=True)]
        for o in sorted(new_by_policy[policy], key=lambda o: o.id):
            policy_result.append(o)
            entries.append({"origin_id": o.id, "policy_id": policy, "kind": "premium", "amount": str(o.capital),
                            "month": month.isoformat()})
        if sum((o.capital for o in policy_result), ZERO) != line.closing:
            raise ValueError("Ursprungsspåren stämmer inte med försäkringens kapital")
        result.extend(policy_result)
    return sorted(result, key=lambda o: o.id), entries, closed


def reconstruct_origins(extract: ValuationExtract) -> tuple[list[Origin], str]:
    """Återskapa från premiehistorik och frysta månadsgrunder, inte dagens premieandel."""
    import hashlib

    by_month = defaultdict(list)
    for policy in extract.policies:
        for part in policy.guarantee_parts:
            by_month[part.received_month].append(Origin(part.premium_id, policy.policy_id, part.premium))
    origins, digest = [], hashlib.sha256()
    for m in extract.months:
        origins, entries, closed = roll_origins(m.month, m.rate, origins, by_month.get(m.month, []),
            fee_rate=m.fee_rate, tax_rate=m.tax_rate)
        if (closed.total("closing") != m.closing or closed.total("opening") != m.opening
                or closed.total("investment_return") != m.returns or closed.total("fee") != m.fees
                or closed.total("tax") != m.taxes or closed.total("premiums") != m.premiums):
            raise ValueError("S-04:s historiska månadsavräkning kan inte återskapas")
        digest.update(checksum({"month": m.month.isoformat(), "entries": entries}).encode())
    totals = defaultdict(Decimal)
    for origin in origins:
        totals[origin.policy_id] += origin.capital
    if any(totals[p.policy_id] != p.capital for p in extract.policies):
        raise ValueError("Rekonstruerat kapital per försäkring avviker från S-04")
    return origins, digest.hexdigest()
