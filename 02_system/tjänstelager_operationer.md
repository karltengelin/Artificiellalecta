# Tjänstelagrets operationer

> **Genererad – ändra inte för hand.** Skapas med `python scripts/list_operations.py`
> ur operationsregistret, åtkomstregistret (`src/services/access_register.yaml`) och
> produktreglernas status (`01_domän/produktregler/`). Kontrolleras av
> `tests/test_services_listing.py`. Design och nivåer: [tjänstelager.md](tjänstelager.md) §4.

**Effektiv nivå** är den strängaste av registrets nivå och golven: saknas i registret →
`HUMAN_ONLY`; `external` → minst `APPROVAL`; `write`/`external` vars produktregel inte är
godkänd och giltig → `HUMAN_ONLY`. Handläggare får alltid utföra alla operationer (B-017).

**Regelpaket:** PR-ITP1 v1.0 – inte infört.

| Operation | Beskrivning | Typ | Produktregler | PII | Register | Effektiv | Skäl till skärpning |
|-----------|-------------|-----|---------------|-----|----------|----------|---------------------|
| `calculate_premium_preview` | Förhandsberäknar ITP1-premien för en månadslön en viss månad enligt premietrappan, med rätt inkomstbasbelopp för året. Sparar ingenting. | `compute` | PR-ITP1-001 (specificerad) | Nej | `AGENT` | `AGENT` | – |
| `get_insured_overview` | Visar en försäkrad med anställning, lön, försäkringar, pågående läge per försäkring och kapital per förmån. Sök på personnummer eller försäkringsnummer. | `read` | – | Ja | `AGENT` | `AGENT` | – |
| `get_premium_history` | Visar premietransaktioner för en försäkring månad för månad – typ, lön, belopp och betalstatus – med summan av betalda belopp. Valfritt urval på månader. | `read` | – | Ja | `AGENT` | `AGENT` | – |
