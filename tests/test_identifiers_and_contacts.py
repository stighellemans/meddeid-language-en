from __future__ import annotations

import pytest

from meddeid_language_en import (
    classify_identifier,
    is_approved_synthetic_identifier,
    is_approved_synthetic_phone,
    is_valid_identifier,
)


@pytest.mark.parametrize(
    "value,hint,category,valid",
    [
        ("943 476 5919", "NHS", "nhs_number", True),
        ("AB 12 34 56 C", None, "nino", True),
        ("GMC-TEST-1234567", None, "professional_id", True),
        ("MRN-GB-123456", None, "internal_id", True),
        ("943 476 5918", "NHS", "nhs_number", False),
    ],
)
def test_gb_identifier_families(value: str, hint: str | None, category: str, valid: bool) -> None:
    assert classify_identifier(value, profile_id="en-GB", hint=hint) == category
    assert is_valid_identifier(value, profile_id="en-GB", hint=hint) is valid


@pytest.mark.parametrize(
    "value,category,valid",
    [
        ("1234567893", "npi", True),
        ("1EG4-TE5-MK73", "mbi", True),
        ("078-05-1120", "ssn", True),
        ("000-12-3456", "ssn", False),
        ("MRN-US-123456", "internal_id", True),
    ],
)
def test_us_identifier_families(value: str, category: str, valid: bool) -> None:
    assert classify_identifier(value, profile_id="en-US") == category
    assert is_valid_identifier(value, profile_id="en-US") is valid


def test_approved_synthetic_identifiers_are_narrowly_anchored() -> None:
    assert is_approved_synthetic_identifier("MRN-GB-123456", profile_id="en-GB")
    assert is_approved_synthetic_identifier("GMC-TEST-1234567", profile_id="en-GB")
    assert is_approved_synthetic_identifier("1234567893", profile_id="en-US")
    assert not is_approved_synthetic_identifier("NPI-TEST-1234567893", profile_id="en-US")
    assert not is_approved_synthetic_identifier("MRN-US-123456 extra", profile_id="en-US")


@pytest.mark.parametrize(
    "profile_id,value",
    [
        ("en-GB", "01234567"),
        ("en-GB", "012 345 678"),
        ("en-GB", "012345/67"),
        ("en-GB", "L26A01234"),
        ("en-GB", "GMC 0123456"),
        ("en-US", "M1234567"),
        ("en-US", "26/123456"),
        ("en-US", "LAB-01234567"),
        ("en-US", "LIC01234567"),
    ],
)
def test_diverse_suite_identifier_formats_are_approved(
    profile_id: str, value: str
) -> None:
    assert is_approved_synthetic_identifier(value, profile_id=profile_id)


@pytest.mark.parametrize(
    "profile_id,value,expected",
    [
        ("en-GB", "07700 900123", True),
        ("en-GB", "+44 7700 900999", True),
        ("en-GB", "07700 901123", False),
        ("en-US", "(202) 555-0100", True),
        ("en-US", "+1 787 555 0199", True),
        ("en-US", "(202) 555-0200", False),
    ],
)
def test_official_fictional_phone_ranges(profile_id: str, value: str, expected: bool) -> None:
    assert is_approved_synthetic_phone(value, profile_id=profile_id) is expected
