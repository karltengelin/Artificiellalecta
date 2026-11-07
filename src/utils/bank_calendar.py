"""Svenska bankdagar och fakturans förfallodag (PR-ITP1-017, P1-PREMIE-001 §4.4).

En bankdag är en vardag som inte är allmän helgdag och inte heller midsommar-,
jul- eller nyårsafton, som bankerna håller stängt. Kalendern räknas fram för varje
år ur påskdagen, så den behöver inga tabeller och fungerar för alla år.

    invoice_due_date(date(2026, 11, 25))  # 2026-12-28: 25–27 december är inga bankdagar

Detta är den första delen av simuleringens verksamhetskalender (S-01). Verklig
loggtid och körbudgetar påverkas inte.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

#: Betalningsvillkor enligt PR-ITP1-017: 30 kalenderdagar från fakturadatum
PAYMENT_TERMS_DAYS = 30


def easter_sunday(year: int) -> date:
    """Påskdagen enligt den gregorianska kalendern (anonym algoritm, Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741 – algoritmens egen beteckning
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _first_weekday_from(start: date, weekday: int) -> date:
    return start + timedelta(days=(weekday - start.weekday()) % 7)


@lru_cache(maxsize=64)
def non_bank_days(year: int) -> dict[date, str]:
    """Årets helgdagar och aftnar utan bankdag, med namn. Lördagar och söndagar ingår inte."""
    easter = easter_sunday(year)
    midsummer_day = _first_weekday_from(date(year, 6, 20), 5)  # lördag 20–26 juni
    all_saints = _first_weekday_from(date(year, 10, 31), 5)  # lördag 31 okt–6 nov
    days = {
        date(year, 1, 1): "nyårsdagen",
        date(year, 1, 6): "trettondedag jul",
        easter - timedelta(days=2): "långfredagen",
        easter: "påskdagen",
        easter + timedelta(days=1): "annandag påsk",
        date(year, 5, 1): "första maj",
        easter + timedelta(days=39): "Kristi himmelsfärdsdag",
        easter + timedelta(days=49): "pingstdagen",
        date(year, 6, 6): "Sveriges nationaldag",
        midsummer_day - timedelta(days=1): "midsommarafton",
        midsummer_day: "midsommardagen",
        all_saints: "alla helgons dag",
        date(year, 12, 24): "julafton",
        date(year, 12, 25): "juldagen",
        date(year, 12, 26): "annandag jul",
        date(year, 12, 31): "nyårsafton",
    }
    return days


def is_bank_day(day: date) -> bool:
    """Svensk bankdag: måndag–fredag som inte är helgdag eller midsommar-, jul- eller nyårsafton."""
    return day.weekday() < 5 and day not in non_bank_days(day.year)


def next_bank_day(day: date) -> date:
    """Dagen själv om den är bankdag, annars närmast följande bankdag."""
    while not is_bank_day(day):
        day += timedelta(days=1)
    return day


def invoice_due_date(invoice_date: date, days: int = PAYMENT_TERMS_DAYS) -> date:
    """Förfallodag: fakturadatum plus betalningsvillkoret, flyttad till nästa bankdag (PR-ITP1-017)."""
    return next_bank_day(invoice_date + timedelta(days=days))
