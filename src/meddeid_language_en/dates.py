"""Locale-explicit English date/age parsing and format-preserving shifts."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from meddeid_core.age_policy import (
    AgeGranularityPolicy,
    AgePart,
    birthdate_from_age_parts,
    load_age_granularity_policy,
)
from meddeid_core.language import DateReplacement

from .resources import normalize_profile_id

MONTHS = tuple(calendar.month_name[index] for index in range(1, 13))
MONTH_ABBR = tuple(calendar.month_abbr[index] for index in range(1, 13))
MONTH_NUMBER = {
    token.casefold().rstrip("."): index
    for index, month in enumerate(MONTHS, start=1)
    for token in (month, MONTH_ABBR[index - 1], "Sept" if index == 9 else month)
}
WEEKDAYS = "Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split()
SEASONS = {"spring", "summer", "autumn", "fall", "winter"}
APPROXIMATE_PREFIX_RE = re.compile(
    r"^(?P<prefix>(?:about|around|approximately|approx\.?|circa|c\.)\s+)", re.I
)
AGE_RE = re.compile(
    r"^(?:aged?\s*)?(?P<value>\d{1,3})(?:\s*[- ]?)(?P<unit>y/o|m/o|w/o|d/o|years?|yrs?|months?|mos?|weeks?|wks?|days?|gestational weeks?)(?:\s*old)?$",
    re.I,
)
AGE_HYPHEN_RE = re.compile(
    r"^(?P<value>\d{1,3})-(?P<unit>year|month|week|day)-old$", re.I
)
DAY_OF_LIFE_RE = re.compile(
    r"^(?P<unit>day)\s+(?P<value>\d{1,3})\s+of\s+life$", re.I
)
CONTEXTUAL_AGE_PREFIX_RE = re.compile(
    r"(?:^|\W)age(?:d)?\s*(?:[:=]\s*)?$", re.I
)
CONTEXTUAL_AGE_UNIT_RE = re.compile(
    r"^\s*(?:[-–]\s*)?(?P<unit>y/o|m/o|w/o|d/o|years?|yrs?|months?|mos?|weeks?|wks?|days?)\b",
    re.I,
)
ISO_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})$")
NUMERIC_RE = re.compile(
    r"^(?P<a>\d{1,2})(?P<sep>[/.-])(?P<b>\d{1,2})(?P=sep)(?P<year>\d{2}|\d{4})$"
)
GB_TEXT_RE = re.compile(
    r"^(?:(?P<weekday>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+)?"
    r"(?P<day>\d{1,2})(?P<ordinal>st|nd|rd|th)?\s+"
    r"(?P<month>[A-Za-z]+\.?)\s+(?P<year>\d{2}|\d{4})$",
    re.I,
)
US_TEXT_RE = re.compile(
    r"^(?:(?P<weekday>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+)?"
    r"(?P<month>[A-Za-z]+\.?)\s+(?P<day>\d{1,2})(?P<ordinal>st|nd|rd|th)?"
    r"(?P<comma>,?)\s+(?P<year>\d{2}|\d{4})$",
    re.I,
)
MONTH_YEAR_RE = re.compile(
    r"^(?P<month>[A-Za-z]+\.?)\s+(?P<year>\d{4})$", re.I
)
YEAR_RE = re.compile(r"^(?P<year>1\d{3}|20\d{2}|21\d{2})$")
SEASON_RE = re.compile(
    r"^(?P<season>spring|summer|autumn|fall|winter)\s+(?P<year>\d{4})$", re.I
)
GB_SAME_MONTH_RANGE_RE = re.compile(
    r"^(?P<start>\d{1,2})(?P<connector>\s*[-–—]\s*)(?P<end>\d{1,2})\s+"
    r"(?P<month>[A-Za-z]+\.?)\s+(?P<year>\d{4})$",
    re.I,
)
US_SAME_MONTH_RANGE_RE = re.compile(
    r"^(?P<month>[A-Za-z]+\.?)\s+(?P<start>\d{1,2})"
    r"(?P<connector>\s*[-–—]\s*)(?P<end>\d{1,2})(?P<comma>,?)\s+"
    r"(?P<year>\d{4})$",
    re.I,
)
SPACED_RANGE_RE = re.compile(r"^(?P<left>.+?)(?P<connector>\s+(?:to|through|until|–|—)\s+)(?P<right>.+)$", re.I)


@dataclass(frozen=True)
class ParsedDate:
    value: date | None
    precision: str
    style: str
    profile_id: str
    original: str
    attributes: dict[str, Any] = field(default_factory=dict)


def _year(raw: str) -> int:
    value = int(raw)
    if len(raw) == 2:
        return 2000 + value if value <= 30 else 1900 + value
    return value


def _month(raw: str) -> int | None:
    return MONTH_NUMBER.get(raw.casefold().rstrip("."))


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _canonical_age_unit(raw: str) -> str:
    unit = raw.casefold().strip()
    if unit.startswith(("y", "year")):
        return "year"
    if unit.startswith(("m", "month")):
        return "month"
    if unit.startswith(("w", "week", "gest")):
        return "week"
    return "day"


def parse_date_text(
    text: str,
    *,
    profile_id: str,
    label: str = "Date",
    reference_date: date | None = None,
    context_before: str = "",
    context_after: str = "",
) -> ParsedDate | None:
    del reference_date
    profile_id = normalize_profile_id(profile_id)
    original = str(text)
    stripped = original.strip()
    if not stripped or re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", stripped):
        return None
    prefix_match = APPROXIMATE_PREFIX_RE.match(stripped)
    prefix = prefix_match.group("prefix") if prefix_match else ""
    body = stripped[prefix_match.end() :] if prefix_match else stripped

    age_match = (
        AGE_RE.fullmatch(body)
        or AGE_HYPHEN_RE.fullmatch(body)
        or DAY_OF_LIFE_RE.fullmatch(body)
    )
    if age_match and label == "Age_Birthdate":
        return ParsedDate(
            None,
            "relative",
            "age",
            profile_id,
            original,
            {"prefix": prefix, "age": int(age_match.group("value")), "unit": age_match.group("unit")},
        )

    standalone_age = re.fullmatch(r"\d{1,3}", body)
    if standalone_age and label == "Age_Birthdate":
        following_unit = CONTEXTUAL_AGE_UNIT_RE.match(context_after)
        unit = following_unit.group("unit") if following_unit else ""
        if unit or CONTEXTUAL_AGE_PREFIX_RE.search(context_before):
            return ParsedDate(
                None,
                "relative",
                "age_context",
                profile_id,
                original,
                {
                    "prefix": prefix,
                    "age": int(standalone_age.group()),
                    "unit": unit or "years",
                },
            )

    match = ISO_RE.fullmatch(body)
    if match:
        value = _safe_date(int(match["year"]), int(match["month"]), int(match["day"]))
        return ParsedDate(value, "day", "iso", profile_id, original, {"prefix": prefix}) if value else None

    match = NUMERIC_RE.fullmatch(body)
    if match:
        first, second = int(match["a"]), int(match["b"])
        day, month = (first, second) if profile_id == "en-GB" else (second, first)
        value = _safe_date(_year(match["year"]), month, day)
        if value is None:
            return None
        return ParsedDate(
            value,
            "day",
            "numeric",
            profile_id,
            original,
            {
                "prefix": prefix,
                "separator": match["sep"],
                "first_width": len(match["a"]),
                "second_width": len(match["b"]),
                "year_width": len(match["year"]),
            },
        )

    pattern = GB_TEXT_RE if profile_id == "en-GB" else US_TEXT_RE
    match = pattern.fullmatch(body)
    if match:
        month = _month(match["month"])
        value = _safe_date(_year(match["year"]), month or 0, int(match["day"]))
        if value is None:
            return None
        return ParsedDate(
            value,
            "day",
            "gb_text" if profile_id == "en-GB" else "us_text",
            profile_id,
            original,
            {
                "prefix": prefix,
                "month_token": match["month"],
                "ordinal": match.groupdict().get("ordinal") or "",
                "weekday": match.groupdict().get("weekday") or "",
                "comma": match.groupdict().get("comma") or "",
                "year_width": len(match["year"]),
            },
        )

    match = MONTH_YEAR_RE.fullmatch(body)
    if match:
        month = _month(match["month"])
        value = _safe_date(int(match["year"]), month or 0, 1)
        return (
            ParsedDate(
                value,
                "month",
                "month_year",
                profile_id,
                original,
                {"prefix": prefix, "month_token": match["month"]},
            )
            if value
            else None
        )

    match = SEASON_RE.fullmatch(body)
    if match:
        value = date(int(match["year"]), 7, 1)
        return ParsedDate(
            value,
            "season",
            "season",
            profile_id,
            original,
            {"prefix": prefix, "season": match["season"]},
        )

    match = YEAR_RE.fullmatch(body)
    if match:
        return ParsedDate(
            date(int(match["year"]), 1, 1),
            "year",
            "year",
            profile_id,
            original,
            {"prefix": prefix},
        )
    return None


def _case_like(value: str, example: str) -> str:
    if example.isupper():
        return value.upper()
    if example.islower():
        return value.lower()
    return value


def _ordinal(day: int) -> str:
    if 10 <= day % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def render_parsed_date(parsed: ParsedDate, value: date) -> str:
    attrs = parsed.attributes
    prefix = attrs.get("prefix", "")
    if parsed.style == "iso":
        return prefix + value.isoformat()
    if parsed.style == "numeric":
        first, second = (
            (value.day, value.month)
            if parsed.profile_id == "en-GB"
            else (value.month, value.day)
        )
        first_raw = f"{first:0{attrs['first_width']}d}"
        second_raw = f"{second:0{attrs['second_width']}d}"
        year_raw = str(value.year) if attrs["year_width"] == 4 else f"{value.year % 100:02d}"
        return prefix + attrs["separator"].join((first_raw, second_raw, year_raw))
    if parsed.style in {"gb_text", "us_text", "month_year"}:
        token = attrs["month_token"]
        abbreviated = len(token.rstrip(".")) <= 4
        month = MONTH_ABBR[value.month - 1] if abbreviated else MONTHS[value.month - 1]
        if token.endswith(".") and not month.endswith("."):
            month += "."
        month = _case_like(month, token)
        if parsed.style == "month_year":
            return f"{prefix}{month} {value.year}"
        ordinal = _ordinal(value.day) if attrs.get("ordinal") else ""
        weekday = ""
        if attrs.get("weekday"):
            rendered = _case_like(WEEKDAYS[value.weekday()], attrs["weekday"])
            weekday = rendered + (", " if "," in parsed.original else " ")
        year = str(value.year) if attrs.get("year_width", 4) == 4 else f"{value.year % 100:02d}"
        if parsed.style == "gb_text":
            return f"{prefix}{weekday}{value.day}{ordinal} {month} {year}"
        comma = attrs.get("comma", "")
        return f"{prefix}{weekday}{month} {value.day}{ordinal}{comma} {year}"
    if parsed.style == "season":
        return f"{prefix}{_case_like(attrs['season'], attrs['season'])} {value.year}"
    if parsed.style == "year":
        return f"{prefix}{value.year}"
    raise ValueError(f"unsupported parsed date style: {parsed.style}")


def _same_month_range(text: str, profile_id: str, shift: int) -> str | None:
    pattern = GB_SAME_MONTH_RANGE_RE if profile_id == "en-GB" else US_SAME_MONTH_RANGE_RE
    match = pattern.fullmatch(text.strip())
    if not match:
        return None
    month = _month(match["month"])
    start = _safe_date(int(match["year"]), month or 0, int(match["start"]))
    end = _safe_date(int(match["year"]), month or 0, int(match["end"]))
    if start is None or end is None or end < start:
        return None
    shifted_start, shifted_end = start + timedelta(days=shift), end + timedelta(days=shift)
    token = match["month"]
    rendered_month = MONTH_ABBR[shifted_start.month - 1] if len(token.rstrip(".")) <= 4 else MONTHS[shifted_start.month - 1]
    if token.endswith("."):
        rendered_month += "."
    rendered_month = _case_like(rendered_month, token)
    connector = match["connector"]
    if shifted_start.month == shifted_end.month and shifted_start.year == shifted_end.year:
        if profile_id == "en-GB":
            return f"{shifted_start.day}{connector}{shifted_end.day} {rendered_month} {shifted_start.year}"
        return f"{rendered_month} {shifted_start.day}{connector}{shifted_end.day}{match.groupdict().get('comma') or ''} {shifted_start.year}"
    left = f"{shifted_start.day} {MONTHS[shifted_start.month - 1]} {shifted_start.year}" if profile_id == "en-GB" else f"{MONTHS[shifted_start.month - 1]} {shifted_start.day}, {shifted_start.year}"
    right = f"{shifted_end.day} {MONTHS[shifted_end.month - 1]} {shifted_end.year}" if profile_id == "en-GB" else f"{MONTHS[shifted_end.month - 1]} {shifted_end.day}, {shifted_end.year}"
    return left + connector + right


def pseudonymize_date_text(
    text: str,
    *,
    profile_id: str,
    label: str,
    date_shift_days: int,
    reference_date: date | None = None,
    document_creation_date: str | None = None,
    age_granularity_policy: AgeGranularityPolicy | None = None,
    context_before: str = "",
    context_after: str = "",
    **_: Any,
) -> str | None:
    profile_id = normalize_profile_id(profile_id)
    policy = age_granularity_policy or load_age_granularity_policy()
    reference_date = reference_date or _parse_reference_date(
        document_creation_date, profile_id
    )
    if label not in {"Date", "Age_Birthdate"}:
        return None
    ranged = _same_month_range(text, profile_id, date_shift_days)
    if ranged is not None:
        return ranged
    match = SPACED_RANGE_RE.fullmatch(text.strip())
    if match:
        left = pseudonymize_date_text(
            match["left"], profile_id=profile_id, label=label,
            date_shift_days=date_shift_days, reference_date=reference_date,
            age_granularity_policy=policy,
        )
        right = pseudonymize_date_text(
            match["right"], profile_id=profile_id, label=label,
            date_shift_days=date_shift_days, reference_date=reference_date,
            age_granularity_policy=policy,
        )
        return left + match["connector"] + right if left and right else None
    parsed = parse_date_text(
        text,
        profile_id=profile_id,
        label=label,
        reference_date=reference_date,
        context_before=context_before,
        context_after=context_after,
    )
    if parsed is None:
        return None
    if parsed.precision == "relative":
        age = int(parsed.attributes.get("age", 0))
        canonical_unit = _canonical_age_unit(str(parsed.attributes.get("unit", "")))
        source_parts = (AgePart(value=age, unit=canonical_unit),)
        anchor = reference_date or date(2000, 1, 1)
        birthdate = birthdate_from_age_parts(anchor, source_parts)
        generalized = policy.generalize(birthdate, anchor)
        if generalized is None:
            return None
        if generalized == source_parts:
            return text
        return str(parsed.attributes.get("prefix", "")) + _render_english_age_parts(
            generalized
        )
    assert parsed.value is not None
    shifted = parsed.value + timedelta(days=date_shift_days)
    if label == "Age_Birthdate":
        if reference_date is None:
            return str(shifted.year)
        shifted_reference = reference_date + timedelta(days=date_shift_days)
        generalized = policy.generalize(shifted, shifted_reference)
        if generalized is None:
            return None
        return _render_english_age_parts(generalized) + " old"
    return render_parsed_date(parsed, shifted)


def _parse_reference_date(value: str | None, profile_id: str) -> date | None:
    if value is None or not str(value).strip():
        return None
    raw = str(value).strip()
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        parsed = parse_date_text(raw, profile_id=profile_id, label="Date")
        if parsed is None or parsed.value is None or parsed.precision != "day":
            return None
        return parsed.value


def _render_english_age_parts(parts: tuple[AgePart, ...]) -> str:
    rendered: list[str] = []
    for part in parts:
        unit = part.unit if part.value == 1 else f"{part.unit}s"
        rendered.append(f"{part.value} {unit}")
    return ", ".join(rendered)


def date_replacement(
    text: str,
    *,
    profile_id: str,
    label: str,
    date_shift_days: int,
    context_before: str = "",
    context_after: str = "",
    document_creation_date: str | None = None,
    age_granularity_policy: AgeGranularityPolicy,
) -> DateReplacement | None:
    reference_date = _parse_reference_date(document_creation_date, profile_id)
    body = pseudonymize_date_text(
        text,
        profile_id=profile_id,
        label=label,
        date_shift_days=date_shift_days,
        reference_date=reference_date,
        age_granularity_policy=age_granularity_policy,
        context_before=context_before,
        context_after=context_after,
    )
    if body is None:
        return None
    if label == "Date":
        kind = "shifted_date"
    else:
        parsed = parse_date_text(
            text,
            profile_id=profile_id,
            label="Age_Birthdate",
            context_before=context_before,
            context_after=context_after,
        )
        kind = (
            "age_generalized"
            if reference_date is not None
            or (parsed is not None and parsed.precision == "relative")
            else "year_fallback"
        )
    return DateReplacement(body=body, kind=kind)


def birth_date_variants(value: str, *, profile_id: str) -> tuple[str, ...]:
    profile_id = normalize_profile_id(profile_id)
    parsed = parse_date_text(value, profile_id=profile_id, label="Age_Birthdate")
    if parsed is None or parsed.value is None or parsed.precision != "day":
        raise ValueError(f"invalid patient.birth_date {value!r}; expected a full date")
    birthdate = parsed.value
    if profile_id == "en-GB":
        numeric = (
            f"{birthdate.day:02d}/{birthdate.month:02d}/{birthdate.year}",
            f"{birthdate.day}/{birthdate.month}/{birthdate.year}",
        )
        textual = (
            f"{birthdate.day} {MONTHS[birthdate.month - 1]} {birthdate.year}",
            f"{birthdate.day} {MONTH_ABBR[birthdate.month - 1]} {birthdate.year}",
        )
    else:
        numeric = (
            f"{birthdate.month:02d}/{birthdate.day:02d}/{birthdate.year}",
            f"{birthdate.month}/{birthdate.day}/{birthdate.year}",
        )
        textual = (
            f"{MONTHS[birthdate.month - 1]} {birthdate.day}, {birthdate.year}",
            f"{MONTH_ABBR[birthdate.month - 1]} {birthdate.day}, {birthdate.year}",
        )
    candidates = (value.strip(), birthdate.isoformat(), *numeric, *textual)
    return tuple(dict.fromkeys(candidate for candidate in candidates if candidate))


def date_age_variants(
    text: str, *, profile_id: str, label: str = "Date"
) -> tuple[str, ...]:
    profile_id = normalize_profile_id(profile_id)
    parsed = parse_date_text(text, profile_id=profile_id, label=label)
    if parsed is None:
        return ()
    if parsed.precision == "relative":
        value = str(parsed.attributes["age"])
        singular = _canonical_age_unit(str(parsed.attributes["unit"]))
        plural = singular if value == "1" else f"{singular}s"
        abbreviated = {
            "year": f"{value} y/o",
            "month": f"{value} m/o",
            "week": f"{value} wk old",
            "day": f"day {value} of life",
        }[singular]
        return tuple(dict.fromkeys((
            f"aged {value} {plural}",
            f"aged {value}",
            f"{value}-{singular}-old",
            f"{value} {plural} old",
            abbreviated,
        )))
    assert parsed.value is not None
    value = parsed.value
    if profile_id == "en-GB":
        candidates = (
            f"{value.day:02d}/{value.month:02d}/{value.year}",
            f"{value.day} {MONTHS[value.month - 1]} {value.year}",
            f"{value.day} {MONTH_ABBR[value.month - 1]} {value.year}",
            value.isoformat(),
        )
    else:
        candidates = (
            f"{value.month:02d}/{value.day:02d}/{value.year}",
            f"{MONTHS[value.month - 1]} {value.day}, {value.year}",
            f"{MONTH_ABBR[value.month - 1]} {value.day}, {value.year}",
            value.isoformat(),
        )
    original = text.strip()
    return tuple(candidate for candidate in dict.fromkeys(candidates) if candidate != original)
