"""A1-v1/manad-v1: källbunden FTA-brygga, samma A6-motor och strikt nollrest."""

from dataclasses import replace
from decimal import ROUND_HALF_UP, Decimal

from services import valuation_bases as vb
from services.valuation import policy_inputs
from services.valuation_extract import ValuationExtract
from skills.calculation import fta_valuation as fv

VERSION = "A1-v1/manad-v1"
ORE = Decimal("0.01")


def ore(amount: Decimal) -> Decimal:
    return amount.quantize(ORE, rounding=ROUND_HALF_UP)


def balance_display(total: fv.Totals) -> dict:
    surplus = total.capital - ore(total.fta) + ore(total.deficit)
    return {"capital_sek": str(total.capital), "fta_sek": str(ore(total.fta)),
            "surplus_sek": str(surplus), "deficit_sek": str(ore(total.deficit)),
            "surplus_display_adjustment_sek": str(surplus - ore(total.surplus)),
            "exact_surplus_sek": str(total.surplus), "exact_deficit_sek": str(total.deficit)}


def change_analysis(opening: ValuationExtract, closing: ValuationExtract,
                    old_model: fv.ValuationModel, new_model: fv.ValuationModel, *,
                    premium_sek: Decimal, expected_opening: Decimal, expected_closing: Decimal,
                    sources: dict) -> dict:
    old, full = policy_inputs(opening), policy_inputs(closing)
    if {p.policy_id for p in old} != {p.policy_id for p in full}:
        raise ValueError("Förändrad population saknar kontrakt i första månadsförsöket")
    for a, b in zip(sorted(old, key=lambda p: p.policy_id), sorted(full, key=lambda p: p.policy_id), strict=True):
        if a.plan_start != b.plan_start or a.state != b.state:
            raise ValueError("Plan-/lägesändring stöds inte av försöket")
    def value(model, on, policies):
        return fv.totals(fv.value_policies(model, on, policies))

    ib = value(old_model, opening.valuation_date, old)
    aged = value(old_model, closing.valuation_date, old)
    added = value(old_model, closing.valuation_date, full)
    curve_only = value(replace(old_model, curve=new_model.curve), closing.valuation_date, full)
    ub = value(new_model, closing.valuation_date, full)
    if ib.fta != expected_opening or ub.fta != expected_closing:
        raise ValueError("Oberoende IB/UB avviker från analysens omvärdering")
    # Nya delar uppstår vid t1. Steg 4 förräntar aldrig en månadsstängningspremie från t0.
    states = [ib.fta, ib.fta + premium_sek, ib.fta + added.fta - aged.fta]
    states += [states[-1], added.fta, added.fta, added.fta, curve_only.fta, ub.fta, ub.fta]
    labels = ["Premier på garantigrund", "Garanti- till FTA-grund", "Utbetalningar (verifierat inga)",
              "Tid och förräntning", "Dödsfall (verifierat inga)", "Planändring (verifierat ingen)",
              "Ändrad räntekurva", "Övriga antaganden", "Modell/data (oförändrade)"]
    mapping = ["F2", "E8", "F3", "F4/F5", "E1/E2", "E11", "E17/F6", "E11/F6", ""]
    rows = [{"label": "Ingående FTA", "fta_sek": float(ore(ib.fta)), "exact_sek": str(ib.fta),
             "source_checksum": vb.checksum(sources)}]
    steps = []
    for index, label in enumerate(labels, 1):
        delta = states[index] - states[index-1]
        rounded = ore(states[index]) - ore(states[index-1])
        evidence = {"period_start": opening.valuation_date.isoformat(), "period_end": closing.valuation_date.isoformat(),
            "step": index, "version": VERSION, "sources": sources, "before_sek": str(states[index-1]),
            "after_sek": str(states[index]), "exact_change_sek": str(delta), "reported_change_sek": str(rounded),
            "rounding_metadata_sek": str(rounded - ore(delta)), "fi_reference": mapping[index-1]}
        steps.append({**evidence, "checksum": vb.checksum(evidence)})
        rows.append({"label": label, "fta_sek": float(rounded), "exact_sek": str(delta),
                     "source_checksum": steps[-1]["checksum"]})
    residual = expected_closing - states[-1]
    if residual != 0 or ib.fta + sum((states[i]-states[i-1] for i in range(1, len(states))), Decimal(0)) != ub.fta:
        raise ValueError("Oförklarad FTA-differens stoppar månaden")
    if ore(ib.fta) + sum((Decimal(s["reported_change_sek"]) for s in steps), Decimal(0)) != ore(ub.fta):
        raise ValueError("FTA-bryggan stämmer inte på öret")
    rows += [{"label": "Oanalyserat", "fta_sek": 0.0, "exact_sek": str(residual),
              "source_checksum": vb.checksum({"ub": str(expected_closing), "state9": str(states[-1]), "sources": sources})},
             {"label": "Utgående FTA", "fta_sek": float(ore(ub.fta)), "exact_sek": str(ub.fta),
              "source_checksum": vb.checksum(sources)}]
    return {"rows": rows, "steps": steps, "step_version": VERSION, "unexplained_sek": str(residual),
            "status": "reconciled", "opening": balance_display(ib), "closing": balance_display(ub),
            "synthetic": True, "scenario_only": True}
