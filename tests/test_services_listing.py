"""Förteckningen över operationer (Fas 1f, T4) – genererad, deterministisk och aktuell."""

from pydantic import BaseModel

from services import (
    AccessRegister,
    MemoryEventLog,
    OperationContext,
    OperationKind,
    OperationRegistry,
    ProductRuleCatalog,
    ServiceLayer,
    operation,
)
from services.listing import DEFAULT_PATH, render_operations


class Empty(BaseModel):
    pass


def test_forteckningen_i_repot_stammer_med_koden_registret_och_regelstatusen():
    expected = render_operations(ServiceLayer(events=MemoryEventLog()))
    assert DEFAULT_PATH.exists(), "kör python scripts/list_operations.py"
    assert DEFAULT_PATH.read_text(encoding="utf-8") == expected, (
        "02_system/tjänstelager_operationer.md är inte aktuell – kör python scripts/list_operations.py"
    )


def test_forteckningen_ar_deterministisk_och_markt_som_genererad():
    service = ServiceLayer(events=MemoryEventLog())
    first, second = render_operations(service), render_operations(service)
    assert first == second
    assert "Genererad – ändra inte för hand" in first.splitlines()[2]


def test_rader_visar_registrets_och_effektiv_niva_med_skal(tmp_path):
    (tmp_path / "PR-T-001-x.md").write_text("> **Granskningsstatus:** Utkast\n", encoding="utf-8")
    registry = OperationRegistry()

    @operation(name="b_write", description="Skriver | något", kind=OperationKind.WRITE,
               rules=["PR-T-001"], pii=True, registry=registry)
    def b_write(ctx: OperationContext, data: Empty) -> Empty:
        return Empty()

    @operation(name="a_read", description="Läser", kind=OperationKind.READ, registry=registry)
    def a_read(ctx: OperationContext, data: Empty) -> Empty:
        return Empty()

    service = ServiceLayer(registry=registry, register=AccessRegister.from_dict({"b_write": "APPROVAL"}),
                           rules=ProductRuleCatalog(tmp_path), events=MemoryEventLog())
    rows = [line for line in render_operations(service).splitlines() if line.startswith("| `")]
    assert rows == [
        "| `a_read` | Läser | `read` | – | Nej | saknas | `HUMAN_ONLY` | saknas i åtkomstregistret |",
        (
            r"| `b_write` | Skriver \| något | `write` | PR-T-001 (utkast) | Ja | `APPROVAL` | `HUMAN_ONLY` "
            "| produktregel inte godkänd: PR-T-001 (utkast) |"
        ),
    ]
