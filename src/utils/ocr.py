"""OCR-referens för fakturor: modulus 10 med längdsiffra (P1-PREMIE-001 §4.4).

Referensen är basnumret, en längdsiffra och en kontrollsiffra. Längdsiffran är
referensens totala längd modulo 10. Kontrollsiffran räknas med modulus 10
(Luhn) över basnumret och längdsiffran. Banken kan därmed avvisa en felskriven
referens innan den når matchningen.

    ocr_reference("7000001")  # '700000193'
"""

from __future__ import annotations


def luhn_check_digit(digits: str) -> str:
    """Kontrollsiffran som gör `digits + siffran` giltig enligt modulus 10."""
    if not digits.isdigit():
        raise ValueError("OCR-underlaget ska bara ha siffror")
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char) * (2 if index % 2 == 0 else 1)
        total += value - 9 if value > 9 else value
    return str((10 - total % 10) % 10)


def ocr_reference(base: str) -> str:
    """Basnummer + längdsiffra + kontrollsiffra. Totalt 2–25 siffror."""
    if not base.isdigit() or not 1 <= len(base) <= 23:
        raise ValueError("Basnumret ska vara 1–23 siffror")
    with_length = base + str((len(base) + 2) % 10)
    return with_length + luhn_check_digit(with_length)


def valid_ocr(reference: str) -> bool:
    """Rätt längdsiffra och kontrollsiffra."""
    if not reference.isdigit() or not 2 <= len(reference) <= 25:
        return False
    body, length_digit, check = reference[:-2], reference[-2], reference[-1]
    return int(length_digit) == len(reference) % 10 and luhn_check_digit(body + length_digit) == check
