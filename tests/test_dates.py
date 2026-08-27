from __future__ import annotations

from datetime import date

import pytest

from meddeid_language_en import (
    date_replacement,
    date_age_variants,
    parse_date_text,
    pseudonymize_date_text,
)


def test_ambiguous_numeric_dates_are_locale_specific() -> None:
    assert parse_date_text("03/04/2025", profile_id="en-GB").value == date(2025, 4, 3)
    assert parse_date_text("03/04/2025", profile_id="en-US").value == date(2025, 3, 4)


@pytest.mark.parametrize(
    "profile_id,text,expected",
    [
        ("en-GB", "3 April 2025", date(2025, 4, 3)),
        ("en-GB", "Thursday, 3rd Apr. 2025", date(2025, 4, 3)),
        ("en-US", "April 3, 2025", date(2025, 4, 3)),
        ("en-US", "Thursday, Apr. 3rd, 2025", date(2025, 4, 3)),
        ("en-US", "2025-04-03", date(2025, 4, 3)),
    ],
)
def test_supported_date_forms(profile_id: str, text: str, expected: date) -> None:
    assert parse_date_text(text, profile_id=profile_id).value == expected


@pytest.mark.parametrize("text", ["31/02/2025", "02/31/2025", "14:30", "120/80", "5 mg", "98.6 F", "03/04"])
def test_rejects_impossible_or_weak_non_dates(text: str) -> None:
    assert parse_date_text(text, profile_id="en-GB") is None
    assert parse_date_text(text, profile_id="en-US") is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("42-year-old", "42-year-old"),
        ("aged 42 years", "aged 42 years"),
        ("42 y/o", "42 y/o"),
        ("6 weeks old", "6 weeks old"),
        ("30 gestational weeks", "6 months"),
    ],
)
def test_age_forms_use_the_shared_granularity_policy(text: str, expected: str) -> None:
    parsed = parse_date_text(text, profile_id="en-GB", label="Age_Birthdate")
    assert parsed is not None and parsed.precision == "relative"
    assert pseudonymize_date_text(text, profile_id="en-GB", label="Age_Birthdate", date_shift_days=800) == expected


@pytest.mark.parametrize(
    "text",
    [
        "3-day-old",
        "aged 3 days",
        "age 3 days",
        "day 3 of life",
        "18-month-old",
        "aged 18 months",
        "18 m/o",
        "3 wk old",
        "6 w/o",
        "2 d/o",
        "50 y/o",
    ],
)
def test_every_generated_and_common_abbreviated_age_is_pseudonymizable(text: str) -> None:
    assert parse_date_text(text, profile_id="en-US", label="Age_Birthdate") is not None
    assert (
        pseudonymize_date_text(
            text,
            profile_id="en-US",
            label="Age_Birthdate",
            date_shift_days=0,
        )
        is not None
    )


def test_numeric_only_age_uses_surrounding_context_in_pseudonymization() -> None:
    parsed = parse_date_text(
        "43",
        profile_id="en-GB",
        label="Age_Birthdate",
        context_before="The patient, aged ",
        context_after=", was reviewed.",
    )
    assert parsed is not None
    assert parsed.attributes == {"prefix": "", "age": 43, "unit": "years"}

    replacement = date_replacement(
        "43",
        profile_id="en-GB",
        label="Age_Birthdate",
        date_shift_days=0,
        context_before="The patient, aged ",
        context_after=", was reviewed.",
        document_creation_date="2028-08-07",
        age_granularity_policy=None,
    )
    assert replacement is not None
    assert replacement.body == "43"
    assert replacement.kind == "age_generalized"


@pytest.mark.parametrize(
    ("text", "expected_variant"),
    [
        ("day 3 of life", "day 3 of life"),
        ("4 m/o", "4 m/o"),
        ("43 y/o", "43 y/o"),
    ],
)
def test_generator_age_surfaces_are_available_to_age_variant_detection(
    text: str, expected_variant: str
) -> None:
    assert expected_variant in date_age_variants(
        text,
        profile_id="en-GB",
        label="Age_Birthdate",
    )


def test_high_ages_follow_the_same_suite_policy_as_other_languages() -> None:
    assert pseudonymize_date_text(
        "97-year-old", profile_id="en-GB", label="Age_Birthdate", date_shift_days=30
    ) == "97-year-old"
    assert pseudonymize_date_text(
        "aged 104 years", profile_id="en-US", label="Age_Birthdate", date_shift_days=-30
    ) == "aged 104 years"


def test_format_preserving_shifts_cover_leap_days_partial_dates_and_ranges() -> None:
    assert pseudonymize_date_text("29/02/2024", profile_id="en-GB", label="Date", date_shift_days=1) == "01/03/2024"
    assert pseudonymize_date_text("February 2024", profile_id="en-US", label="Date", date_shift_days=31) == "March 2024"
    assert pseudonymize_date_text("3–5 April 2025", profile_id="en-GB", label="Date", date_shift_days=2) == "5–7 April 2025"
    assert pseudonymize_date_text("April 29-30, 2025", profile_id="en-US", label="Date", date_shift_days=2) == "May 1-2, 2025"


def test_pseudonymization_is_deterministic_and_preserves_numeric_style() -> None:
    for profile_id, raw in (("en-GB", "03.04.25"), ("en-US", "03-04-2025")):
        first = pseudonymize_date_text(raw, profile_id=profile_id, label="Date", date_shift_days=37)
        second = pseudonymize_date_text(raw, profile_id=profile_id, label="Date", date_shift_days=37)
        assert first == second
        assert raw[2] in first
        assert len(first.split(raw[2])[-1]) == len(raw.split(raw[2])[-1])


def test_variants_never_cross_locale_date_order() -> None:
    assert "03/04/2025" in date_age_variants("3 April 2025", profile_id="en-GB")
    assert "04/03/2025" in date_age_variants("April 3, 2025", profile_id="en-US")
