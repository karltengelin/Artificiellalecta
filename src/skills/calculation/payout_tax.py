"""Preliminär skatt på ett bankuppdrag (paket B steg 6, B-054, PR-ITP1-026, Karls val X3–X5).

Ren beräkning utan sidoeffekter; tjänstelagret (`services.payout_orders`) läser skattestatus, anspråk och planer.

**Per uppdrag (X3).** Skatten räknas på summan av personens rader i uppdraget, alltså alla delar hos
bolaget tillsammans, med utbetalningsdagens år (PR-ITP1-026 p. 3 och 5). Ett procentavdrag räknas i hela
kronor och öretalet bortfaller; ingen avrundning uppåt. Netto = brutto − skatt och blir aldrig negativt.

**Gränserna (SFL 10 kap. 3–4 §§).** För A-skatt – sidoinkomst, huvudinkomst och individuellt beslut – görs
inget avdrag när uppdragets brutto understiger 100 kr eller den förväntade årssumman från bolaget till
personen understiger 1 000 kr. Exakt 100 och 1 000 kr omfattas inte. Gränserna gäller inte SINK.

**Huvudinkomst (X4).** Kräver en versionsbunden skattetabell för året, som byggs som eget steg när Karl hämtat
Skatteverkets tabeller. Till dess blockeras uppdraget (`TaxBlocked`), och skulden står kvar (fall 21).

Fall 18: brutto 1 000,00 kr som sidoinkomst ger skatt 300 kr och netto 700,00 kr.
Fall 19: brutto 333,33 kr som sidoinkomst ger 30 % = 99,999 och skatt 99 kr, netto 234,33 kr.
Fall 20: brutto 99,99 kr ger inget avdrag; brutto 100,00 kr med förväntad årssumma 1 200 kr ger 30 kr.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

CENT = Decimal("0.01")
KRONA = Decimal(1)
ZERO = Decimal("0.00")
SIDE_RATE = Decimal("0.30")
#: SFL 10 kap. 3–4 §§: inget A-skatteavdrag under dessa belopp (strikt mindre än)
PAYMENT_LIMIT = Decimal(100)
YEAR_LIMIT = Decimal(1000)
A_TAX_KINDS = ("side_income", "main_income", "individual_decision")


class TaxError(ValueError):
    """Skatten kan inte räknas, t.ex. negativt brutto eller okänt slag."""


class TaxBlocked(TaxError):
    """Uppdraget kan inte betalas med registrerad status (huvudinkomst utan skattetabell, X4)."""

    def __init__(self, reason: str, text: str):
        super().__init__(text)
        self.reason = reason


@dataclass(frozen=True)
class TaxRule:
    """Den del av skattestatusen som beräkningen behöver."""

    kind: str
    rate: Decimal | None = None
    fixed_amount: Decimal | None = None


@dataclass(frozen=True)
class TaxResult:
    gross: Decimal
    tax: Decimal
    net: Decimal
    method: str
    basis: dict

    def plain(self) -> dict:
        return {"gross_sek": str(self.gross), "tax_sek": str(self.tax), "net_sek": str(self.net),
                "tax_method": self.method, **self.basis}


def whole_kronor(value: Decimal) -> Decimal:
    """Hela kronor: öretalet bortfaller (PR-ITP1-026)."""
    return value.quantize(KRONA, rounding=ROUND_FLOOR).quantize(CENT)


def withholding(gross: Decimal, rule: TaxRule, expected_year_total: Decimal, *, thresholds: bool = True) -> TaxResult:
    """Skatteavdraget på ett uppdrag med bruttot `gross` (summan av personens rader).

    `expected_year_total` är den förväntade årssumman från bolaget till personen under utbetalningsåret.
    `thresholds` nej: gränserna för småbelopp tillämpas inte – utbetalning till dödsbo i första versionen
    (paket B steg 7, Karls val Y10; tolkningsfrågan ligger hos projekt 4).
    """
    gross = Decimal(str(gross))
    if gross <= 0 or gross != gross.quantize(CENT):
        raise TaxError("Bruttot ska vara positivt och i hela ören")
    basis = {"tax_kind": rule.kind, "rate": str(rule.rate) if rule.rate is not None else None,
             "fixed_amount_sek": str(rule.fixed_amount) if rule.fixed_amount is not None else None,
             "expected_year_total_sek": str(expected_year_total)}
    if rule.kind == "main_income":
        raise TaxBlocked("table_missing", "Huvudinkomst kräver skattetabell för året – den finns inte i första "
                                          "versionen; betalningen blockeras och skulden står kvar (X4)")
    if rule.kind not in (*A_TAX_KINDS, "sink"):
        raise TaxError(f"Okänt skatteslag {rule.kind}")
    if rule.kind in A_TAX_KINDS and thresholds:
        if gross < PAYMENT_LIMIT:
            return TaxResult(gross, ZERO, gross, "below_100", basis)
        if expected_year_total < YEAR_LIMIT:
            return TaxResult(gross, ZERO, gross, "below_1000", basis)
    if rule.kind == "individual_decision" and rule.fixed_amount is not None:
        tax, method = min(whole_kronor(Decimal(str(rule.fixed_amount))), whole_kronor(gross)), "fixed"
    else:
        rate = rule.rate if rule.rate is not None else (SIDE_RATE if rule.kind == "side_income" else None)
        if rate is None:
            raise TaxError(f"Skatteslaget {rule.kind} saknar sats")
        rate = Decimal(str(rate))
        if rule.kind == "side_income" and rate < SIDE_RATE:
            raise TaxError("Sidoinkomst har minst 30 % avdrag; lägre avdrag kräver beslut")
        tax, method = min(whole_kronor(gross * rate), whole_kronor(gross)), "percent"
    return TaxResult(gross, tax, gross - tax, method, basis)


__all__ = ["A_TAX_KINDS", "PAYMENT_LIMIT", "SIDE_RATE", "YEAR_LIMIT", "TaxBlocked", "TaxError", "TaxResult",
           "TaxRule", "whole_kronor", "withholding"]
