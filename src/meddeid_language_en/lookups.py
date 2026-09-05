"""Stable structured lookup access for both English locale profiles."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from functools import lru_cache
from importlib.resources import files
from typing import Any

from .resources import PROFILE_IDS, normalize_profile_id


@lru_cache(maxsize=2)
def _all_records(profile_id: str) -> tuple[dict[str, Any], ...]:
    profile_id = normalize_profile_id(profile_id)
    resource = files("meddeid_language_en").joinpath(
        "resources", profile_id, "lookups.jsonl"
    )
    records = tuple(
        json.loads(line)
        for line in resource.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    if not records:
        raise RuntimeError(f"packaged {profile_id} lookup resource is empty")
    return records


@lru_cache(maxsize=2)
def _by_category(profile_id: str) -> dict[str, tuple[dict[str, Any], ...]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in _all_records(profile_id):
        grouped[record["category"]].append(record)
    return {category: tuple(records) for category, records in sorted(grouped.items())}


def lookup_categories(profile_id: str) -> tuple[str, ...]:
    profile_id = normalize_profile_id(profile_id)
    return tuple(_by_category(profile_id))


def lookup_records(profile_id: str, category: str) -> tuple[dict[str, Any], ...]:
    profile_id = normalize_profile_id(profile_id)
    try:
        return _by_category(profile_id)[category]
    except KeyError as exc:
        expected = ", ".join(lookup_categories(profile_id))
        raise KeyError(
            f"unknown {profile_id} lookup category {category!r}; expected one of: {expected}"
        ) from exc


@lru_cache(maxsize=None)
def lookup_values(profile_id: str, category: str) -> tuple[str, ...]:
    return tuple(record["value"] for record in lookup_records(profile_id, category))


def lookup_source(profile_id: str, category: str | None = None) -> str:
    profile_id = normalize_profile_id(profile_id)
    if category is None:
        return f"meddeid-language-en 0.2.1 {profile_id} locked resources"
    source_ids = sorted(
        {
            source_id
            for record in lookup_records(profile_id, category)
            for source_id in record["source_ids"]
        }
    )
    return f"meddeid-language-en 0.2.1 {profile_id}: {', '.join(source_ids)}"


def _logical_hash(records: tuple[dict[str, Any], ...]) -> str:
    payload = "\n".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for record in records
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@lru_cache(maxsize=2)
def lookup_manifest(profile_id: str) -> dict[str, Any]:
    profile_id = normalize_profile_id(profile_id)
    root = files("meddeid_language_en").joinpath("resources", profile_id)
    content = root.joinpath("lookups.jsonl").read_bytes()
    lock = root.joinpath("sources.lock.json").read_bytes()
    notice = root.joinpath("SOURCES.md").read_bytes()
    audit = root.joinpath("audit.json").read_bytes()
    resources = {}
    for category in lookup_categories(profile_id):
        records = lookup_records(profile_id, category)
        resources[category] = {
            "filename": "lookups.jsonl",
            "logical_sha256": _logical_hash(records),
            "values": len(records),
            "regions": sorted(
                {region for record in records for region in record.get("regions", [])}
            ),
            "source_ids": sorted(
                {
                    source_id
                    for record in records
                    for source_id in record.get("source_ids", [])
                }
            ),
        }
    return {
        "manifest_version": "meddeid.language-resources.v2",
        "package": "meddeid-language-en",
        "package_version": "0.2.1",
        "profile_id": profile_id,
        "lookups_sha256": hashlib.sha256(content).hexdigest(),
        "resources": resources,
        "provenance": {
            "sources_lock_sha256": hashlib.sha256(lock).hexdigest(),
            "sources_notice_sha256": hashlib.sha256(notice).hexdigest(),
            "audit_sha256": hashlib.sha256(audit).hexdigest(),
        },
    }


def manifests() -> dict[str, dict[str, Any]]:
    return {profile_id: lookup_manifest(profile_id) for profile_id in PROFILE_IDS}
