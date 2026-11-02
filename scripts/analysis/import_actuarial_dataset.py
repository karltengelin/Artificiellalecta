"""Importera versionsmärkt aktuariellt utfall till Lakebase. Standard är bara validering.

Ingen modell får skriva observerat utfall. Indata är ett JSON-objekt enligt
DatasetInput: id, kind, title, source_ref, definition, synthetic och rows_json.
Varje rad valideras mot typens kontrakt, se aktuariedialogens verktygskatalog.
En rättelse är en ny version. Ingen överskrivning eller generering av utfall.
Samordna alla skarpa importer enligt AGENTS.md §4.5 före --apply.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from services import Actor, OperationContext, ServiceLayer
from services.db import database_session_factory
from services.operations.actuarial_analysis import DatasetInput, validated_dataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reason", default="")
    parser.add_argument("--operator", default="")
    args = parser.parse_args()
    if args.input.stat().st_size > 600000:
        parser.error("Underlaget överstiger 600 kB")
    data = DatasetInput.model_validate(json.loads(args.input.read_text(encoding="utf-8")))
    content = validated_dataset(data)
    print(f"Validerat: {data.id}, {data.kind}, {len(content['rows'])} celler, synthetic={data.synthetic}")
    if not args.apply:
        print("Ingen databasanslutning eller ändring. --apply kräver operatör och motivering.")
        return
    if not args.operator.strip() or not args.reason.strip():
        parser.error("Ange --operator och --reason för en skarp import")
    result = ServiceLayer(session_factory=database_session_factory()).execute("register_actuarial_dataset",
        OperationContext(actor=Actor.human(args.operator), reason=args.reason), data)
    print(result.output.payload)


if __name__ == "__main__":
    main()
