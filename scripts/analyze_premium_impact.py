"""IBB-scenario från offline-backup eller tydligt märkt syntetiskt exempel.

python scripts/analyze_premium_impact.py --scenario-ibb 85000
python scripts/analyze_premium_impact.py --snapshot backups/<tid> --month 2026-06 \
    --scenario-ibb 85000 --assume-current-employer
"""

import argparse
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from analytics.premium_impact import PremiumObservation, compare_ibb, render_markdown  # noqa: E402
from analytics.snapshot import load_snapshot  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--month", default="2026-06")
    parser.add_argument("--scenario-ibb", required=True)
    parser.add_argument("--assume-current-employer", action="store_true")
    parser.add_argument("--output", type=Path, help="Utan argument skrivs Markdown till stdout")
    args = parser.parse_args()
    try:
        month = date.fromisoformat(args.month + "-01")
        alternative = Decimal(args.scenario_ibb)
        if args.snapshot:
            records, parameters, stamp = load_snapshot(args.snapshot, assume_current_employer=args.assume_current_employer)
            if month.year not in parameters:
                raise ValueError("Basbelopp saknas för analysåret")
            baseline = parameters[month.year]
            source = f"Offline-backup {stamp}; samma år och löner, hypotetiskt annat IBB"
            attribution = "Nuvarande koppling i backupen, uttryckligt scenarioantagande; historisk arbetsgivare ej verifierad"
        else:
            if month.year != 2026:
                raise ValueError("Demot stöder endast 2026; andra år kräver snapshot med årsparameter")
            baseline = Decimal("83400")
            records = [PremiumObservation(str(i), f"person-{i}", "demo-employer", f"policy-{i}", f"benefit-{i}", month,
                                          Decimal(salary), Decimal(amount), date(1990, 1, 1))
                       for i, (salary, amount) in enumerate((("35000", "1575.00"), ("80000", "10708.13"), ("250000", "49258.13")), 1)]
            source = "Tre helt syntetiska exempel; inga uppgifter hämtade från beståndet"
            attribution = "Konstruerad arbetsgivare i demot"
        report = compare_ibb(records, month=month, baseline_ibb=baseline, scenario_ibb=alternative)
        markdown = render_markdown(report, source=source, attribution=attribution)
    except (ValueError, InvalidOperation, KeyError, OSError) as exc:
        parser.error(str(exc))
    if args.output:
        args.output.write_text(markdown, encoding="utf-8")
    else:
        print(markdown, end="")


if __name__ == "__main__":
    main()
