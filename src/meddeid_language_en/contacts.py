"""Approved fictional telephone ranges for English synthetic generation."""

from __future__ import annotations

import re

from .resources import normalize_profile_id


def is_approved_synthetic_phone(value: str, *, profile_id: str) -> bool:
    profile_id = normalize_profile_id(profile_id)
    digits = re.sub(r"\D", "", str(value))
    if profile_id == "en-GB":
        if digits.startswith("44"):
            digits = "0" + digits[2:]
        return bool(re.fullmatch(r"07700900\d{3}", digits))
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) != 10:
        return False
    return digits[3:6] == "555" and 100 <= int(digits[6:]) <= 199
