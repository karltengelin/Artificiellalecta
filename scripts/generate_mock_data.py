"""Genererar syntetisk mockdata för försäkringstagare och försäkrade.

Datat skrivs till `data/employers.csv` och `data/insured_persons.csv`.
Skripten `seed_supabase.py` läser därifrån och laddar in i databasen.

⚠️  All data är **syntetisk** – inga riktiga personer eller bolag.
    Personnummer och organisationsnummer är tekniskt giltiga (passerar Luhn)
    men slumpgenererade. Eventuella krockar med riktiga är en slumpartad
    sammanträffning, inte avsikt.

Default-omfattning: 20 arbetsgivare och ~500 anställda totalt.

Användning:
    python scripts/generate_mock_data.py
    python scripts/generate_mock_data.py --employers 5 --employees 50
"""

from __future__ import annotations

import argparse
import csv
import random
import uuid
from datetime import date, timedelta
from pathlib import Path

# --- Konstanter och namnlistor ---

FIRST_NAMES_MALE = [
    "Erik", "Lars", "Anders", "Mikael", "Johan", "Per", "Karl", "Stefan", "Thomas",
    "Daniel", "Magnus", "Henrik", "Jonas", "Mattias", "Fredrik", "Niklas", "Marcus",
    "David", "Joakim", "Robert", "Andreas", "Jan", "Patrik", "Christian", "Martin",
    "Alexander", "Filip", "Oskar", "Viktor", "Gustav", "Emil", "Anton", "Simon",
]
FIRST_NAMES_FEMALE = [
    "Anna", "Maria", "Margareta", "Elisabeth", "Eva", "Birgitta", "Kristina", "Karin",
    "Sara", "Lena", "Helena", "Susanne", "Marie", "Sofia", "Linda", "Camilla",
    "Jenny", "Therese", "Emma", "Hanna", "Julia", "Linnea", "Astrid", "Alice",
    "Olivia", "Ella", "Wilma", "Maja", "Ebba", "Klara", "Saga", "Agnes",
]
LAST_NAMES = [
    "Andersson", "Johansson", "Karlsson", "Nilsson", "Eriksson", "Larsson", "Olsson",
    "Persson", "Svensson", "Gustafsson", "Pettersson", "Jonsson", "Jansson", "Hansson",
    "Bengtsson", "Jönsson", "Lindberg", "Jakobsson", "Magnusson", "Lindström",
    "Olofsson", "Lindqvist", "Lindgren", "Berg", "Axelsson", "Bergström", "Lundberg",
    "Lundgren", "Lundqvist", "Mattsson", "Berglund", "Fredriksson", "Sandberg",
    "Henriksson", "Forsberg", "Sjöberg", "Wallin", "Engström", "Eklund", "Danielsson",
]

CITIES = [
    ("Stockholm", "11122"), ("Göteborg", "41103"), ("Malmö", "21115"),
    ("Uppsala", "75320"), ("Västerås", "72215"), ("Örebro", "70212"),
    ("Linköping", "58222"), ("Helsingborg", "25220"), ("Jönköping", "55322"),
    ("Norrköping", "60221"), ("Lund", "22350"), ("Umeå", "90325"),
    ("Gävle", "80323"), ("Borås", "50330"), ("Eskilstuna", "63220"),
    ("Halmstad", "30242"), ("Växjö", "35231"), ("Karlstad", "65225"),
    ("Sundsvall", "85230"), ("Östersund", "83134"),
]

COMPANY_PREFIXES = [
    "Nordic", "Svensk", "Tech", "Industri", "Konsult", "Bygg", "Handels", "Forsk",
    "Data", "Kraft", "Energi", "Logistik", "Teknik", "Service", "Plåt", "Stål",
    "Maskin", "Skogs", "Bil", "Marin", "Mat", "Hälso", "Pharma", "Med",
]
COMPANY_THEMES = [
    "Gruppen", "Partner", "Lösningar", "Systems", "Group", "Industries", "Solutions",
    "Konsult", "Bolaget", "Företaget", "& Co", "Norden",
]

STREETS = [
    "Storgatan", "Kungsgatan", "Drottninggatan", "Vasagatan", "Sveavägen",
    "Industrivägen", "Verkstadsgatan", "Hantverkargatan", "Skeppsbron", "Norra Vägen",
]


# --- Luhn-helpers ---

def luhn_check_digit(number_without_check: str) -> int:
    """Beräknar Luhn-kontrollsiffra för svenska PNR (10 siffror utan check) och
    organisationsnummer (9 siffror utan check)."""
    total = 0
    for i, ch in enumerate(number_without_check):
        d = int(ch)
        product = d * (2 if i % 2 == 0 else 1)
        total += product // 10 + product % 10
    return (10 - total % 10) % 10


def generate_personal_id_number(rng: random.Random) -> tuple[str, date]:
    """Returnerar (PNR YYYYMMDDXXXX, födelsedatum). Födelseår 1979–2000."""
    year = rng.randint(1979, 2000)
    month = rng.randint(1, 12)
    # Använd 1–28 så vi slipper månadslängd
    day = rng.randint(1, 28)
    birth = date(year, month, day)
    # 3 slumpsiffror (de tre sista innan checken)
    serial = f"{rng.randint(0, 999):03d}"
    # Luhn-grunden är de sista 10 siffrorna (YYMMDDXXX), checksumman blir 11:e
    yy_mmdd = f"{year % 100:02d}{month:02d}{day:02d}"
    base = yy_mmdd + serial  # 9 siffror
    check = luhn_check_digit(base)
    pnr = f"{year:04d}{month:02d}{day:02d}{serial}{check}"
    return pnr, birth


def generate_org_number(rng: random.Random) -> str:
    """Returnerar 10-siffrigt orgnummer för AB (börjar på 55, 56 eller 55x)."""
    # AB-orgnummer börjar typiskt med 5
    first = "55"
    body = "".join(str(rng.randint(0, 9)) for _ in range(7))
    base = first + body  # 9 siffror
    check = luhn_check_digit(base)
    return base + str(check)


# --- Genereringsfunktioner ---

def generate_employer(rng: random.Random, index: int) -> dict:
    name = f"{rng.choice(COMPANY_PREFIXES)}{rng.choice(COMPANY_THEMES)} AB"
    # Lägg till numerisk suffix så namnen blir unika i mockdatan
    name = f"{name} #{index + 1:02d}"
    city, postal = rng.choice(CITIES)
    contact_first = rng.choice(FIRST_NAMES_MALE + FIRST_NAMES_FEMALE)
    contact_last = rng.choice(LAST_NAMES)
    affiliation = date(rng.randint(2005, 2024), rng.randint(1, 12), rng.randint(1, 28))
    return {
        "id": str(uuid.uuid4()),
        "org_number": generate_org_number(rng),
        "name": name,
        "industry_code": f"{rng.randint(10000, 99999)}",
        "address_street": f"{rng.choice(STREETS)} {rng.randint(1, 99)}",
        "address_postal_code": postal,
        "address_city": city,
        "contact_name": f"{contact_first} {contact_last}",
        "contact_email": f"{contact_first.lower()}.{contact_last.lower()}@"
        f"{name.split()[0].lower()}.se",
        "contact_phone": f"+46 {rng.randint(10, 99)} {rng.randint(100, 999)} "
        f"{rng.randint(10, 99)} {rng.randint(10, 99)}",
        "collective_agreement": "ITP",
        "affiliation_date": affiliation.isoformat(),
        "status": "active",
    }


def generate_insured_person(
    rng: random.Random, employer: dict, employer_affiliation: date
) -> dict:
    pnr, birth = generate_personal_id_number(rng)
    first = rng.choice(FIRST_NAMES_MALE + FIRST_NAMES_FEMALE)
    last = rng.choice(LAST_NAMES)
    # Anställningsstart: tidigast 22 års ålder, senast 2025-01-01, och aldrig före
    # arbetsgivarens anslutningsdatum.
    earliest_employment = max(
        date(birth.year + 22, 1, 1),
        employer_affiliation,
    )
    latest_employment = date(2025, 12, 31)
    if earliest_employment > latest_employment:
        # I praktiken sällsynt – fall tillbaka på arbetsgivarens anslutning
        emp_start = employer_affiliation
    else:
        span_days = (latest_employment - earliest_employment).days
        emp_start = earliest_employment + timedelta(days=rng.randint(0, span_days))

    # ITP1 startar månaden efter 25-årsdagen eller anställningsstart, beroende på
    # vilket som inträffar senast.
    age_25 = date(birth.year + 25, birth.month, birth.day)
    itp1_start = max(age_25, emp_start)

    # 95 % är aktiva, 5 % har slutat
    if rng.random() < 0.95:
        status = "active"
        emp_end: date | None = None
    else:
        status = "terminated"
        # Sluta någon gång mellan start och idag
        span_days = max(1, (date(2026, 5, 1) - emp_start).days)
        emp_end = emp_start + timedelta(days=rng.randint(30, span_days))

    monthly_salary = round(rng.gauss(45000, 12000), 2)
    monthly_salary = max(25000.0, min(monthly_salary, 150000.0))

    # Tjänstgöringsgrad: mest 100 %, men en del deltid
    rate = rng.choices([100, 80, 75, 50], weights=[80, 8, 7, 5])[0]

    return {
        "id": str(uuid.uuid4()),
        "personal_id_number": pnr,
        "first_name": first,
        "last_name": last,
        "email": f"{first.lower()}.{last.lower()}@example.se",
        "phone": f"+46 70 {rng.randint(100, 999)} {rng.randint(10, 99)} "
        f"{rng.randint(10, 99)}",
        "employer_id": employer["id"],
        "employment_start_date": emp_start.isoformat(),
        "employment_end_date": emp_end.isoformat() if emp_end else "",
        "monthly_salary_sek": f"{monthly_salary:.2f}",
        "employment_rate": f"{rate}.00",
        "itp1_start_date": itp1_start.isoformat(),
        "status": status,
    }


# --- Main ---

EMPLOYER_FIELDS = [
    "id", "org_number", "name", "industry_code",
    "address_street", "address_postal_code", "address_city",
    "contact_name", "contact_email", "contact_phone",
    "collective_agreement", "affiliation_date", "status",
]

INSURED_FIELDS = [
    "id", "personal_id_number", "first_name", "last_name", "email", "phone",
    "employer_id", "employment_start_date", "employment_end_date",
    "monthly_salary_sek", "employment_rate", "itp1_start_date", "status",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--employers", type=int, default=20,
                        help="Antal arbetsgivare (default 20)")
    parser.add_argument("--employees", type=int, default=500,
                        help="Ungefärligt totalantal anställda (default 500)")
    parser.add_argument("--seed", type=int, default=20260516,
                        help="Slumpfrö för reproducerbarhet")
    parser.add_argument("--out-dir", default="data",
                        help="Utskriftsmapp (default data/)")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Generera arbetsgivare
    employers = [generate_employer(rng, i) for i in range(args.employers)]

    # Fördela anställda. Mest jämnt med viss variation.
    per_employer_avg = max(1, args.employees // args.employers)
    insured: list[dict] = []
    for emp in employers:
        affiliation = date.fromisoformat(emp["affiliation_date"])
        # ±40 % spridning runt snittet
        count = max(1, int(rng.uniform(per_employer_avg * 0.6,
                                       per_employer_avg * 1.4)))
        for _ in range(count):
            insured.append(generate_insured_person(rng, emp, affiliation))

    # Skriv ut
    employers_path = out_dir / "employers.csv"
    insured_path = out_dir / "insured_persons.csv"

    with employers_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=EMPLOYER_FIELDS)
        writer.writeheader()
        writer.writerows(employers)

    with insured_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=INSURED_FIELDS)
        writer.writeheader()
        writer.writerows(insured)

    print(f"Skrev {len(employers)} arbetsgivare → {employers_path}")
    print(f"Skrev {len(insured)} försäkrade → {insured_path}")


if __name__ == "__main__":
    main()
