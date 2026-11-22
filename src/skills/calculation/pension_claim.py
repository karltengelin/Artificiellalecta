"""Månadsrättens finansiering och debitering av kundkapitalet (paket B steg 5, B-047 punkt 6 och 8, Karls val W5–W8).

Domänregler: PR-ITP1-020 steg 5, PR-ITP1-026, PR-ITP1-027 och PR-ITP1-028. Ren beräkning utan
sidoeffekter; månadsstängningen (`services.month_close`) läser journal och planer.

**Bruttoanspråket.** Ett anspråk per uttagsdel och rättighetsmånad. Bruttot är beslutat M, utom på den
tidsbegränsade delens sista rätt, där M_sista = max(M, C efter månadens kostnader) (PR-ITP1-027).

**Finansieringen (PR-ITP1-028, W5).** Från kundkapitalet tas min(brutto, C). Bristen K = brutto − den
delen förs från bolagskontot så långt det räcker, direkt till betalningsskulden (Karls val W5: stödet
passerar inte C, eftersom det förbrukas samma månad). Det som bolagskontot inte täcker står kvar som ej
finansierat på anspråket (W8). Fall 14: C 100 953,83 kr och M 500 kr ger skuld 500 kr och C 100 453,83 kr.
Fall 35: C 80, rätt 100 och bolagskonto 0 ger 80 ur C och 20 ej finansierat.

**Debiteringen per kapitalspår (PR-ITP1-020).** Pensionsdebiten fördelas på delens spår efter deras
tillgängliga kapital, i ören med största bråkrest. Ingen andel överstiger sitt spår.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from skills.calculation.capital_rollforward import allocate_cents

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class ClaimError(ValueError):
    """Anspråket kan inte räknas, t.ex. negativt kapital eller belopp som inte är i ören."""


@dataclass(frozen=True)
class ClaimFunding:
    """Ett anspråks brutto och finansiering: kundkapital, bolagsstöd och ej finansierat."""

    gross: Decimal
    from_capital: Decimal
    company_support: Decimal
    unfunded: Decimal
    final_settlement: bool

    def plain(self) -> dict:
        return {"gross_sek": str(self.gross), "from_capital_sek": str(self.from_capital),
                "company_support_sek": str(self.company_support), "unfunded_sek": str(self.unfunded),
                "final_settlement": self.final_settlement}


def _cents(value: Decimal, what: str) -> Decimal:
    if value < 0 or value != value.quantize(CENT):
        raise ClaimError(f"{what} ska vara icke-negativt och i hela ören")
    return value


def claim_funding(amount: Decimal, capital: Decimal, company: Decimal, *, final: bool = False) -> ClaimFunding:
    """Brutto och finansiering för en rätt: M (eller max(M, C) på sista rätten), ur C, bolagsstöd och ej finansierat.

    `capital` är delens C efter månadens avkastning, avgift och skattebelastning; `company` är bolagskontots
    saldo som finns kvar för anspråket.
    """
    amount, capital, company = (_cents(amount, "Beloppet M"), _cents(capital, "Kapitalet"),
                                _cents(company, "Bolagskontot"))
    if amount <= 0:
        raise ClaimError("En månadsrätt har ett positivt belopp (PR-ITP1-009)")
    gross = max(amount, capital) if final else amount
    from_capital = min(gross, capital)
    support = min(gross - from_capital, company)
    return ClaimFunding(gross, from_capital, support, gross - from_capital - support, final)


def debit_tracks(amount: Decimal, balances: list[Decimal]) -> list[Decimal]:
    """Debitens fördelning på kapitalspåren efter deras kapital, i ören med största bråkrest (PR-ITP1-020)."""
    amount = _cents(amount, "Debiten")
    total = sum(balances, ZERO)
    if amount > total:
        raise ClaimError(f"Debiten {amount} kr överskrider delens kapital {total} kr")
    shares = allocate_cents(amount, balances)
    if any(s > b for s, b in zip(shares, balances, strict=True)):
        raise ClaimError("En debitering överskrider ett kapitalspår")
    return shares


__all__ = ["ClaimError", "ClaimFunding", "claim_funding", "debit_tracks"]
