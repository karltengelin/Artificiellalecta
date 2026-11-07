"""OCR-referens med längd- och kontrollsiffra (utils/ocr.py, P1-PREMIE-001 §4.4)."""

import pytest

from utils.ocr import luhn_check_digit, ocr_reference, valid_ocr


def test_kontrollsiffra_enligt_modulus_10():
    assert luhn_check_digit("7992739871") == "3"  # standardexemplet för Luhn


def test_referens_har_langdsiffra_och_kontrollsiffra():
    reference = ocr_reference("7000001")
    assert reference == "700000193"
    assert reference[-2] == str(len(reference) % 10)
    assert valid_ocr(reference)


@pytest.mark.parametrize("broken", ["700000194", "700000183", "70000019", "abc", ""])
def test_felskriven_referens_avvisas(broken):
    assert not valid_ocr(broken)


def test_alla_lopnummer_ger_giltiga_unika_referenser():
    references = {ocr_reference(f"7{n:06d}") for n in range(1, 2001)}
    assert len(references) == 2000 and all(valid_ocr(r) for r in references)
