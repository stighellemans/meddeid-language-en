from __future__ import annotations

from meddeid_language_en import post_process_spans


def _seed(text: str, value: str, label: str) -> dict:
    begin = text.index(value)
    return {"begin": begin, "end": begin + len(value), "label": label}


def test_metadata_recovery_name_extension_contacts_and_idempotence() -> None:
    text = "Seen by Dr Emily O'Neill, MBBS. Patient Aisha Khan: aisha.khan@example.test."
    spans = [
        _seed(text, "Emily", "Name:Caregiver"),
        _seed(text, "aisha.khan", "Contactdetails"),
    ]
    metadata = {
        "patient": {"given_name": "Aisha", "family_name": "Khan"},
        "caregivers": [{"given_name": "Emily", "family_name": "O'Neill"}],
    }
    first = post_process_spans(spans, text, metadata, profile_id="en-GB")
    second = post_process_spans(first, text, metadata, profile_id="en-GB")
    assert first == second
    assert any(span["text"].rstrip(".") == "Dr Emily O'Neill, MBBS" and span["label"] == "Name:Caregiver" for span in first)
    assert any(span["text"] == "Aisha Khan" and span["label"] == "Name:Patient" for span in first)
    assert any(span["text"] == "aisha.khan@example.test" for span in first)


def test_locale_date_extension_and_impossible_fragment_rejection() -> None:
    gb_text = "Reviewed on 3 April 2025."
    gb = post_process_spans([_seed(gb_text, "April", "Date")], gb_text, profile_id="en-GB")
    assert [span["text"] for span in gb] == ["3 April 2025"]

    us_text = "Reviewed on April 3, 2025."
    us = post_process_spans([_seed(us_text, "April", "Date")], us_text, profile_id="en-US")
    assert [span["text"] for span in us] == ["April 3, 2025"]

    bad = "Recorded 31/02/2025 in error."
    assert post_process_spans([_seed(bad, "31/02/2025", "Date")], bad, profile_id="en-GB") == []


def test_known_values_balancing_and_deterministic_overlap_resolution() -> None:
    text = "Transfer to (Royal Victoria Hospital), Belfast."
    metadata = {"known_values": [{"value": "Royal Victoria Hospital", "label": "Organization:Healthcare"}]}
    spans = [_seed(text, "Victoria", "Address_Location:Other")]
    first = post_process_spans(spans, text, metadata, profile_id="en-GB")
    second = post_process_spans(list(reversed(spans)), text, metadata, profile_id="en-GB")
    assert first == second
    assert any(span["text"] == "(Royal Victoria Hospital)" for span in first)


def test_name_suffixes_and_credentials_do_not_cross_locale() -> None:
    us_text = "Reviewed by Dr John Smith Jr., MD and Dr Emily Jones, MBBS."
    us_metadata = {"caregivers": [{"name": "John Smith"}, {"name": "Emily Jones"}]}
    us = post_process_spans([], us_text, us_metadata, profile_id="en-US")
    assert any(span["text"] == "Dr John Smith Jr., MD" for span in us)
    assert any(span["text"] == "Dr Emily Jones" for span in us)
    assert not any("MBBS" in span["text"] for span in us)

    gb_text = "Reviewed by Dame Sarah Hughes, MBBS and Dr John Smith, MD."
    gb_metadata = {"caregivers": [{"name": "Sarah Hughes"}, {"name": "John Smith"}]}
    gb = post_process_spans([], gb_text, gb_metadata, profile_id="en-GB")
    assert any(span["text"] == "Dame Sarah Hughes, MBBS" for span in gb)
    assert any(span["text"] == "Dr John Smith" for span in gb)
    assert not any(span["text"].endswith(", MD") for span in gb)
def test_numeric_only_age_prediction_survives_when_context_says_aged() -> None:
    text = "The patient, aged 43, was reviewed."
    begin = text.index("43")
    result = post_process_spans(
        [{"begin": begin, "end": begin + 2, "label": "Age_Birthdate"}],
        text,
        profile_id="en-GB",
    )
    assert [(span["text"], span["label"]) for span in result] == [
        ("43", "Age_Birthdate")
    ]

