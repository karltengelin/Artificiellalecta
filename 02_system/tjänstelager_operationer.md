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
| `correct_premium_transaction` | Rättar en premierad efter rättat löneunderlag (PR-ITP1-019 p.1): räknar om premien med premiemånadens IBB och skapar en länkad rättelserad med differensen som ny fordran eller kredit. Ursprungsraden bevaras. Minskning av redan mottagen premie blockeras. | `write` | PR-ITP1-001 (specificerad), PR-ITP1-014 (specificerad), PR-ITP1-017 (specificerad), PR-ITP1-019 (specificerad), PR-ITP1-032 (specificerad) | Ja | `HUMAN_ONLY` | `HUMAN_ONLY` | – |
| `get_insured_overview` | Visar en försäkrad med anställning, lön, försäkringar, pågående läge per försäkring och kapital per förmån. Sök på personnummer eller försäkringsnummer. | `read` | – | Ja | `AGENT` | `AGENT` | – |
| `get_premium_history` | Visar premietransaktioner för en försäkring månad för månad – typ, lön, belopp och betalstatus – med summan av betalda belopp. Valfritt urval på månader. | `read` | – | Ja | `AGENT` | `AGENT` | – |
| `get_salary_reports` | Visar registrerat löneunderlag (pensionsmedförande lön per månad) för en försäkrad, med alla versioner och vilken som gäller. Saknad månad = ingen rapport; 0,00 = rapporterad noll. | `read` | – | Ja | `AGENT` | `AGENT` | – |
| `register_salary_report` | Registrerar pensionsmedförande lön (PR-ITP1-014) för en försäkrad hos sin arbetsgivare en utbetalningsmånad: ny rapport eller rättelse som ny version. Uttrycklig noll tillåts. Skapar ingen premie och räknar inte om gamla premier. | `write` | PR-ITP1-013 (specificerad), PR-ITP1-014 (specificerad), PR-ITP1-017 (specificerad) | Ja | `APPROVAL` | `HUMAN_ONLY` | produktregel inte godkänd: PR-ITP1-013 (specificerad), PR-ITP1-014 (specificerad), PR-ITP1-017 (specificerad) |
| `set_policy_paid_up` | Registrerar anställningens slut (avanmälan) och sätter försäkringen i fribrev från dagen efter (PR-ITP1-013). Bara premiebetalande försäkring vars pension inte har startat; ingen framtidsdatering. | `write` | PR-ITP1-013 (specificerad) | Ja | `APPROVAL` | `HUMAN_ONLY` | produktregel inte godkänd: PR-ITP1-013 (specificerad) |
