"""Conservative locale-aware span post-processing for English clinical text."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Iterable

from .dates import parse_date_text
from .lookups import lookup_values
from .resources import normalize_profile_id

CONTACT_RE = re.compile(
    r"(?:https?://|sftp://|file:///|www\.)[^\s<>\]\[{}]+|"
    r"mailto:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|"
    r"tel:\+?[\d() .-]{7,}|"
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|"
    r"\+?[\d(][\d() .-]{6,}\d",
    re.I,
)
TITLE_RE = {
    "en-GB": re.compile(
        r"(?:Mr|Mrs|Ms|Miss|Mx|Dr|Professor|Prof|Sir|Dame|Lord|Lady|Rev)\.?\s+$",
        re.I,
    ),
    "en-US": re.compile(
        r"(?:Mr|Mrs|Ms|Miss|Mx|Dr|Professor|Prof|Rev)\.?\s+$", re.I
    ),
}
CREDENTIAL_RE = {
    "en-GB": re.compile(
        r"^\s*,?\s*(?:MBBS|MBChB|FRCP|MRCP|FRCS|FRCGP|PhD|RN|RGN)"
        r"(?:\s*,\s*(?:MBBS|MBChB|FRCP|MRCP|FRCS|FRCGP|PhD|RN|RGN))*\.?",
        re.I,
    ),
    "en-US": re.compile(
        r"^\s*,?\s*(?:MD|DO|PhD|RN|NP|PA-C|FACP|FAAP|LCSW)"
        r"(?:\s*,\s*(?:MD|DO|PhD|RN|NP|PA-C|FACP|FAAP|LCSW))*\.?",
        re.I,
    ),
}
NAME_SUFFIX_RE = re.compile(r"^\s*,?\s*(?:Jr|Sr|II|III|IV)\.?", re.I)
ROOM_SUFFIX_RE = re.compile(
    r"^(?:\s*,?\s*(?:Ward|Unit|Department|Clinic|Room|Suite)\s+[A-Za-z0-9-]+)+",
    re.I,
)
BRACKETS = {"(": ")", "[": "]", "{": "}"}


def _span(label: str, begin: int, end: int, text: str, **extra: Any) -> dict[str, Any]:
    category, _, subtype = label.partition(":")
    result: dict[str, Any] = {
        "label": label,
        "begin": begin,
        "end": end,
        "text": text[begin:end],
        "category": category,
        "subtype": subtype or None,
    }
    result.update(extra)
    return result


def _normalize(raw: dict[str, Any], text: str) -> dict[str, Any] | None:
    item = deepcopy(raw)
    begin = item.get("begin", item.get("start", item.get("char_begin")))
    end = item.get("end", item.get("char_end", item.get("end_char")))
    label = item.get("label", item.get("type", item.get("entity")))
    try:
        begin, end = int(begin), int(end)
    except (TypeError, ValueError):
        return None
    if not label or begin < 0 or end > len(text) or begin >= end:
        return None
    while begin < end and text[begin].isspace():
        begin += 1
    while end > begin and (text[end - 1].isspace() or text[end - 1] in ",;:"):
        end -= 1
    if begin >= end or not any(character.isalnum() for character in text[begin:end]):
        return None
    item.update(_span(str(label), begin, end, text))
    return item


def _metadata_names(metadata: dict[str, Any] | None) -> Iterable[tuple[str, str]]:
    if not metadata:
        return ()
    values: list[tuple[str, str]] = []
    patient = metadata.get("patient")
    if isinstance(patient, dict):
        given = str(patient.get("given_name", patient.get("first_name", ""))).strip()
        family = str(patient.get("family_name", patient.get("last_name", ""))).strip()
        full = str(patient.get("name", "")).strip() or " ".join(
            value for value in (given, family) if value
        )
        if full:
            values.append((full, "Name:Patient"))
    for caregiver in metadata.get("caregivers", ()):
        if not isinstance(caregiver, dict):
            continue
        given = str(caregiver.get("given_name", caregiver.get("first_name", ""))).strip()
        family = str(caregiver.get("family_name", caregiver.get("last_name", ""))).strip()
        full = str(caregiver.get("name", "")).strip() or " ".join(
            value for value in (given, family) if value
        )
        if full:
            values.append((full, "Name:Caregiver"))
    return values


def _inject_value(
    spans: list[dict[str, Any]], text: str, value: str, label: str, origin: str
) -> None:
    if not value:
        return
    for match in re.finditer(re.escape(value), text, re.I):
        if any(
            span["label"] == label
            and span["begin"] <= match.start()
            and span["end"] >= match.end()
            for span in spans
        ):
            continue
        spans.append(_span(label, match.start(), match.end(), text, origin=origin))


def _extend_contact(span: dict[str, Any], text: str) -> dict[str, Any]:
    if span["label"] != "Contactdetails":
        return span
    for match in CONTACT_RE.finditer(text):
        if match.start() <= span["begin"] < match.end() or match.start() < span["end"] <= match.end():
            end = match.end()
            while end > match.start() and text[end - 1] in ".,;:":
                end -= 1
            return {**span, **_span(span["label"], match.start(), end, text)}
    return span


def _date_candidates(text: str, profile_id: str) -> Iterable[re.Match[str]]:
    months = (
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
        r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|"
        r"Nov(?:ember)?|Dec(?:ember)?)\.?"
    )
    numeric = r"\d{1,2}[/.-]\d{1,2}[/.-](?:\d{2}|\d{4})"
    iso = r"\d{4}-\d{2}-\d{2}"
    textual = (
        rf"\d{{1,2}}(?:st|nd|rd|th)?\s+{months}\s+\d{{2,4}}"
        if profile_id == "en-GB"
        else rf"{months}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{2,4}}"
    )
    pattern = re.compile(rf"(?<!\w)(?:{iso}|{numeric}|{textual})(?!\w)", re.I)
    return pattern.finditer(text)


def _extend_date(
    span: dict[str, Any], text: str, profile_id: str
) -> dict[str, Any] | None:
    if span["label"] not in {"Date", "Age_Birthdate"}:
        return span
    raw = text[span["begin"] : span["end"]]
    context_before = text[max(0, span["begin"] - 48) : span["begin"]]
    context_after = text[span["end"] : min(len(text), span["end"] + 48)]
    if parse_date_text(
        raw,
        profile_id=profile_id,
        label=span["label"],
        context_before=context_before,
        context_after=context_after,
    ):
        return span
    for match in _date_candidates(text, profile_id):
        if match.start() <= span["begin"] and match.end() >= span["end"]:
            parsed = parse_date_text(
                match.group(), profile_id=profile_id, label=span["label"]
            )
            if parsed:
                return {**span, **_span(span["label"], match.start(), match.end(), text)}
    if re.fullmatch(r"[\d\s/.-]+", raw) and not parse_date_text(
        raw,
        profile_id=profile_id,
        label=span["label"],
        context_before=context_before,
        context_after=context_after,
    ):
        return None
    return span


def _extend_name(
    span: dict[str, Any], text: str, profile_id: str
) -> dict[str, Any]:
    if not span["label"].startswith("Name:"):
        return span
    begin, end = span["begin"], span["end"]
    before = text[max(0, begin - 24) : begin]
    title = TITLE_RE[profile_id].search(before)
    if title and span["label"] == "Name:Caregiver":
        begin = max(0, begin - 24) + title.start()
    after = text[end : min(len(text), end + 48)]
    suffix = NAME_SUFFIX_RE.match(after)
    if suffix:
        end += suffix.end()
        after = text[end : min(len(text), end + 48)]
    credential = CREDENTIAL_RE[profile_id].match(after)
    if credential and span["label"] == "Name:Caregiver":
        end += credential.end()
    return {**span, **_span(span["label"], begin, end, text)}


def _extend_organization(span: dict[str, Any], text: str) -> dict[str, Any]:
    if not span["label"].startswith("Organization:"):
        return span
    after = text[span["end"] : min(len(text), span["end"] + 64)]
    suffix = ROOM_SUFFIX_RE.match(after)
    if not suffix:
        return span
    return {
        **span,
        **_span(span["label"], span["begin"], span["end"] + suffix.end(), text),
    }


def _balance(span: dict[str, Any], text: str) -> dict[str, Any]:
    begin, end = span["begin"], span["end"]
    if begin > 0 and text[begin - 1] in BRACKETS and end < len(text) and text[end] == BRACKETS[text[begin - 1]]:
        begin -= 1
        end += 1
    return {**span, **_span(span["label"], begin, end, text)}


def _deduplicate_and_resolve(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[int, int, str], dict[str, Any]] = {}
    for span in spans:
        unique[(span["begin"], span["end"], span["label"])] = span
    ordered = sorted(
        unique.values(),
        key=lambda item: (item["begin"], -(item["end"] - item["begin"]), item["label"]),
    )
    result: list[dict[str, Any]] = []
    for candidate in ordered:
        same_label = next(
            (
                existing
                for existing in result
                if candidate["begin"] < existing["end"]
                and candidate["end"] > existing["begin"]
                and candidate["label"] == existing["label"]
            ),
            None,
        )
        if same_label is not None:
            candidate_length = candidate["end"] - candidate["begin"]
            existing_length = same_label["end"] - same_label["begin"]
            if candidate_length > existing_length:
                result.remove(same_label)
                result.append(candidate)
            continue
        conflict = next(
            (
                existing
                for existing in result
                if candidate["begin"] < existing["end"]
                and candidate["end"] > existing["begin"]
                and candidate["label"] != existing["label"]
            ),
            None,
        )
        if conflict is None:
            result.append(candidate)
            continue
        candidate_length = candidate["end"] - candidate["begin"]
        conflict_length = conflict["end"] - conflict["begin"]
        if candidate_length > conflict_length:
            result.remove(conflict)
            result.append(candidate)
    return sorted(result, key=lambda item: (item["begin"], item["end"], item["label"]))


def post_process_spans(
    spans: list[dict[str, Any]],
    text: str,
    metadata: dict[str, Any] | None = None,
    *,
    profile_id: str,
    recover_names: bool = True,
    regex_observer: Any = None,
) -> list[dict[str, Any]]:
    del regex_observer
    profile_id = normalize_profile_id(profile_id)
    normalized = [item for raw in spans if (item := _normalize(raw, text)) is not None]
    if recover_names:
        for value, label in _metadata_names(metadata):
            _inject_value(normalized, text, value, label, "metadata")
    for known in (metadata or {}).get("known_values", ()):
        if isinstance(known, dict):
            _inject_value(
                normalized,
                text,
                str(known.get("value", "")),
                str(known.get("label", "")),
                "known_value",
            )
    output: list[dict[str, Any]] = []
    for span in normalized:
        processed = _extend_contact(span, text)
        processed = _extend_date(processed, text, profile_id)
        if processed is None:
            continue
        processed = _extend_name(processed, text, profile_id)
        processed = _extend_organization(processed, text)
        processed = _balance(processed, text)
        output.append(processed)
    return _deduplicate_and_resolve(output)


def known_name_tokens(profile_id: str) -> frozenset[str]:
    profile_id = normalize_profile_id(profile_id)
    return frozenset(
        value.casefold()
        for category in ("first_names", "family_names", "surname_particles")
        for value in lookup_values(profile_id, category)
    )
