from __future__ import annotations

import json
from pathlib import Path

import pytest

from meddeid_language_en import (
    get_profile,
    lookup_categories,
    lookup_manifest,
    lookup_records,
    lookup_values,
)
from meddeid_language_en.resources import (
    _serialize_records,
    audit_runtime,
    build_records,
    diff,
    load_runtime_records,
    source_lock,
)


@pytest.mark.parametrize("requested, expected", [("en-GB", "en-GB"), ("en_GB", "en-GB"), ("en-US", "en-US"), ("en_US", "en-US")])
def test_only_explicit_english_locales_resolve(requested: str, expected: str) -> None:
    profile = get_profile(requested)
    assert profile.profile_id == expected
    assert profile.language_tags == (expected,)
    assert profile.accepts_language(expected)
    assert not profile.accepts_language("en")


@pytest.mark.parametrize("requested", ["en", "EN", "en-CA", "en-AU"])
def test_bare_or_unsupported_english_fails(requested: str) -> None:
    with pytest.raises(ValueError, match="en-GB, en-US"):
        get_profile(requested)


def test_structured_lookup_contract_and_flat_compatibility() -> None:
    for profile_id in ("en-GB", "en-US"):
        categories = lookup_categories(profile_id)
        assert {"first_names", "family_names", "streets", "localities", "hospitals"} <= set(categories)
        for category in categories:
            records = lookup_records(profile_id, category)
            assert lookup_values(profile_id, category) == tuple(record["value"] for record in records)
            for record in records:
                assert record["normalized"]
                assert record["regions"]
                assert record["source_ids"]
                assert record["value"] == " ".join(record["value"].split())
                assert not any(
                    marker in record["value"]
                    for marker in ("Ã", "Â", "â€", "ï¿½", "�")
                )


def test_profile_scopes_are_explicit_and_exclude_crown_dependencies() -> None:
    gb_areas = set(lookup_values("en-GB", "administrative_areas"))
    assert gb_areas == {"England", "Scotland", "Wales", "Northern Ireland"}
    assert not {"Jersey", "Guernsey", "Isle of Man"} & gb_areas

    us_areas = set(lookup_values("en-US", "administrative_areas"))
    assert len(us_areas) == 56
    assert {"Alabama", "Wyoming", "District of Columbia", "Puerto Rico", "U.S. Virgin Islands", "Guam", "American Samoa", "Northern Mariana Islands"} <= us_areas


def test_resource_audits_and_manifests_are_reproducible() -> None:
    for profile_id in ("en-GB", "en-US"):
        first = audit_runtime(profile_id)
        second = audit_runtime(profile_id)
        assert first == second
        assert first["passed"] is True
        manifest = lookup_manifest(profile_id)
        assert manifest["lookups_sha256"] == first["lookups_sha256"]
        assert len(manifest["lookups_sha256"]) == 64
        assert all(len(resource["logical_sha256"]) == 64 for resource in manifest["resources"].values())


def test_source_locks_have_complete_immutable_provenance() -> None:
    required = {
        "source_id", "source_sha256", "source_hash_kind", "publisher", "dataset", "release", "url", "retrieved_at",
        "license", "attribution", "geographic_scope", "output_categories", "fetch",
    }
    for profile_id in ("en-GB", "en-US"):
        lock = source_lock(profile_id)
        assert lock["adapter_version"] == "2"
        assert lock["profile_id"] == profile_id
        for source in lock["sources"]:
            assert required <= set(source)
            assert source["release"]
            assert "latest" not in source["release"].lower()
            assert len(source["source_sha256"]) == 64
            assert source["retrieved_at"] == "2026-08-20"
            if source["fetch"]:
                assert source["files"]
                assert all(len(item["sha256"]) == 64 for item in source["files"])


def test_runtime_resources_have_real_world_scale_and_required_region_coverage() -> None:
    minimums = {
        "en-GB": {
            "first_names": 39_000,
            "family_names": 1_000,
            "streets": 140_000,
            "localities": 35_000,
            "healthcare_institutions": 38_000,
            "professions": 23_000,
        },
        "en-US": {
            "first_names": 29_000,
            "family_names": 160_000,
            "streets": 56_000,
            "localities": 21_000,
            "healthcare_institutions": 5_200,
            "professions": 6_500,
        },
    }
    for profile_id, categories in minimums.items():
        audit = audit_runtime(profile_id)
        for category, minimum in categories.items():
            assert audit["counts"][category] >= minimum
        assert audit["missing_category_regions"] == {}
        assert audit["source_lock_problems"] == []


def test_python_capability_matches_javascript_manifest() -> None:
    root = Path(__file__).parents[1] / "src" / "meddeid_language_en" / "resources" / "subannotation"
    for profile_id in ("en-GB", "en-US"):
        raw = json.loads((root / f"{profile_id}.json").read_text(encoding="utf-8"))
        capability = get_profile(profile_id).manifest()["capabilities"]["subannotation"]
        assert capability["profile_id"] == raw["profileId"]
        assert capability["export"] == raw["javascript"]["export"]


def test_ssa_names_retain_frequency_and_suppression_metadata() -> None:
    records = lookup_records("en-US", "first_names")
    assert records
    for record in records:
        if "ssa-baby-names" not in record["source_ids"]:
            continue
        assert isinstance(record["weight"], (int, float))
        assert record["attributes"]["release_year"] == 2025
        assert record["attributes"]["suppression_threshold"] == 5


def test_cms_facilities_retain_city_and_county_location_metadata() -> None:
    records = lookup_records("en-US", "hospitals")
    hampshire = next(
        record for record in records
        if record["normalized"] == "hampshire memorial hospital"
    )
    assert hampshire["attributes"]["city"] == "ROMNEY"
    assert hampshire["attributes"]["county"] == "HAMPSHIRE"


def test_cached_resource_rebuilds_are_byte_identical_and_drift_free() -> None:
    cache = Path(__file__).parents[1] / ".cache" / "sources"
    if not cache.exists():
        pytest.skip("raw source cache is deliberately excluded from distributions")
    for profile_id in ("en-GB", "en-US"):
        first = _serialize_records(build_records(profile_id, cache))
        second = _serialize_records(build_records(profile_id, cache))
        runtime = _serialize_records(load_runtime_records(profile_id))
        assert first == second == runtime
        report = diff(profile_id, cache)
        assert report["identical"] is True
        assert report["source_drift"] == []
        assert report["source_files_unavailable"] == []
