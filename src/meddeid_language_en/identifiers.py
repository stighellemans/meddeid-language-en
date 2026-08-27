"""Locale-explicit healthcare and national identifier rules.

Classification recognizes anchored formats. Validation additionally applies
published structural and checksum rules where the identifier defines one.
"""

from __future__ import annotations

import re
from datetime import date

from .resources import normalize_profile_id

NINO_RE = re.compile(
    r"^(?!BG|GB|KN|NK|NT|TN|ZZ)[ABCEGHJ-PRSTW-Z][ABCEGHJ-NPRSTW-Z]\d{6}[A-D]$"
)
ODS_RE = re.compile(r"^[A-Z0-9]{3,6}$")
GB_PROFESSIONAL_RE = re.compile(
    r"^(?:GMC|NMC|GDC|HCPC|GPHC)(?:-TEST)?-[A-Z0-9]{5,10}$"
)
SSN_RE = re.compile(r"^(\d{3})(\d{2})(\d{4})$")
NPI_RE = re.compile(r"^\d{10}$")
MBI_RE = re.compile(
    r"^[1-9][AC-HJKMNP-RT-Y][0-9AC-HJKMNP-RT-Y]\d"
    r"[AC-HJKMNP-RT-Y][0-9AC-HJKMNP-RT-Y]\d"
    r"[AC-HJKMNP-RT-Y]{2}\d{2}$"
)
ANCHORED_INTERNAL_RE = re.compile(
    r"^(?:MRN|REPORT|PAYER|PROVIDER)-(?:GB|US)-[A-Z0-9]{4,20}$"
)
SUITE_DIVERSE_SYNTHETIC_RE = re.compile(
    r"^(?:"
    r"0\d{6,9}|"
    r"[HM]\d{7}|"
    r"0\d{2}\s0?\d{3}\s\d{3}|"
    r"0\d{5}/\d{2}|"
    r"2\d/\d{6}|"
    r"[LA]2\d[A-Z]\d{5}|"
    r"(?:MRN|LAB)-0\d{6,8}|"
    r"S2\d-0\d{6}|"
    r"GMC\s0\d{6}|"
    r"GMC-TEST-0\d{6}|"
    r"LIC\d{8}|"
    r"LIC-\d{8}"
    r")$"
)


def _compact(value: str) -> str:
    return re.sub(r"[\s.-]", "", str(value)).upper()


def _digits(value: str) -> str:
    return re.sub(r"\D", "", str(value))


def _mod11_check(digits: str) -> bool:
    if len(digits) != 10:
        return False
    total = sum(int(value) * weight for value, weight in zip(digits[:9], range(10, 1, -1)))
    check = 11 - total % 11
    expected = 0 if check == 11 else check
    return check != 10 and expected == int(digits[-1])


def _chi_date_valid(digits: str) -> bool:
    if len(digits) != 10:
        return False
    day, month, year = int(digits[:2]), int(digits[2:4]), int(digits[4:6])
    return any(
        _safe_date(century + year, month, day)
        for century in (1900, 2000)
    )


def _safe_date(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def _npi_checksum_valid(digits: str) -> bool:
    if not NPI_RE.fullmatch(digits):
        return False
    payload = "80840" + digits[:-1]
    total = 0
    for index, character in enumerate(reversed(payload)):
        value = int(character)
        if index % 2 == 0:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return (10 - total % 10) % 10 == int(digits[-1])


def classify_identifier(
    value: str, *, profile_id: str, hint: str | None = None
) -> str | None:
    """Return a locale category for one fully anchored identifier string."""

    profile_id = normalize_profile_id(profile_id)
    raw = str(value).strip()
    anchored = re.sub(r"\s", "", raw).upper()
    compact = _compact(raw)
    digits = _digits(raw)
    normalized_hint = str(hint or "").strip().casefold().replace(" ", "_")
    if profile_id == "en-GB":
        if normalized_hint in {"nhs", "nhs_number"} and len(digits) == 10:
            return "nhs_number"
        if normalized_hint in {"chi", "chi_number"} and len(digits) == 10:
            return "chi_number"
        if normalized_hint in {"h&c", "h_and_c", "h_and_c_number"} and len(digits) == 10:
            return "h_and_c_number"
        if NINO_RE.fullmatch(compact):
            return "nino"
        if GB_PROFESSIONAL_RE.fullmatch(anchored):
            return "professional_id"
        if ANCHORED_INTERNAL_RE.fullmatch(anchored):
            return "internal_id"
        if len(digits) == 10 and _chi_date_valid(digits):
            return "chi_number"
        if len(digits) == 10 and _mod11_check(digits):
            return "nhs_number"
        if normalized_hint in {"ods", "ods_code"} and ODS_RE.fullmatch(compact):
            return "ods_code"
        return None

    if ANCHORED_INTERNAL_RE.fullmatch(anchored):
        return "internal_id"
    if MBI_RE.fullmatch(compact):
        return "mbi"
    if NPI_RE.fullmatch(digits) and len(digits) == 10:
        return "npi"
    if SSN_RE.fullmatch(digits):
        return "ssn"
    return None


def is_valid_identifier(
    value: str, *, profile_id: str, hint: str | None = None
) -> bool:
    category = classify_identifier(value, profile_id=profile_id, hint=hint)
    if category is None:
        return False
    compact = _compact(value)
    digits = _digits(value)
    if category == "nhs_number":
        return _mod11_check(digits)
    if category == "chi_number":
        return _chi_date_valid(digits) and _mod11_check(digits)
    if category == "h_and_c_number":
        return len(digits) == 10 and _mod11_check(digits)
    if category == "ssn":
        match = SSN_RE.fullmatch(digits)
        assert match is not None
        area, group, serial = match.groups()
        return area not in {"000", "666"} and int(area) < 900 and group != "00" and serial != "0000"
    if category == "npi":
        return _npi_checksum_valid(digits)
    return True


def is_approved_synthetic_identifier(value: str, *, profile_id: str) -> bool:
    """True only for suite-approved test/non-assignable generation forms."""

    profile_id = normalize_profile_id(profile_id)
    anchored = re.sub(r"\s", "", str(value)).upper()
    compact = _compact(value)
    raw = str(value).strip().upper()
    if SUITE_DIVERSE_SYNTHETIC_RE.fullmatch(raw):
        return True
    if profile_id == "en-GB":
        return bool(
            re.fullmatch(r"(?:MRN|REPORT)-GB-\d{6}", anchored)
            or re.fullmatch(r"GMC-TEST-\d{7}", anchored)
            # Reserved/invalid NINO prefixes and invalid-checksum, zero-led
            # NHS-shaped values are suite-owned non-assignable test data.
            or re.fullmatch(r"(?:BG|GB|KN|NK|NT|TN|ZZ)\d{6}[A-D]", compact)
            or (
                re.fullmatch(r"000\d{7}", _digits(value)) is not None
                and not _mod11_check(_digits(value))
            )
        )
    if re.fullmatch(r"\d{9}", _digits(value)):
        area, group, serial = (
            _digits(value)[:3],
            _digits(value)[3:5],
            _digits(value)[5:],
        )
        if area in {"000", "666"} or int(area) >= 900 or group == "00" or serial == "0000":
            return True
    return bool(
        re.fullmatch(r"(?:MRN|REPORT)-US-\d{6}", anchored)
        # CMS uses 1234567893 as its published NPI check-digit example.
        or anchored == "1234567893"
        or re.fullmatch(r"000\d{6}", _digits(value))
    )
