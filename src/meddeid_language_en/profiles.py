"""en-GB and en-US LanguageProfile registrations."""

from __future__ import annotations

from functools import partial

from meddeid_core.language import LanguageProfile

from .capabilities import capability_manifest
from .dates import birth_date_variants, date_replacement
from .name_pseudonyms import name_replacement, protect_boundaries
from .lookups import lookup_categories, lookup_manifest, lookup_values
from .postprocess import post_process_spans
from .resources import normalize_profile_id


def _profile(profile_id: str) -> LanguageProfile:
    return LanguageProfile(
        profile_id=profile_id,
        language_tags=(profile_id,),
        post_process_spans=partial(post_process_spans, profile_id=profile_id),
        lookup_categories_provider=partial(lookup_categories, profile_id),
        lookup_values_provider=partial(lookup_values, profile_id),
        resource_manifest_provider=partial(lookup_manifest, profile_id),
        capability_manifest_provider=partial(capability_manifest, profile_id),
        name_boundary_provider=partial(protect_boundaries, profile_id=profile_id),
        name_replacement_provider=partial(name_replacement, profile_id=profile_id),
        date_replacement_provider=partial(date_replacement, profile_id=profile_id),
        birth_date_variants_provider=partial(
            birth_date_variants, profile_id=profile_id
        ),
    )


EN_GB = _profile("en-GB")
EN_US = _profile("en-US")
_PROFILES = {profile.profile_id.lower(): profile for profile in (EN_GB, EN_US)}


def get_profile(profile_id: str) -> LanguageProfile:
    normalized = normalize_profile_id(profile_id)
    try:
        return _PROFILES[normalized.lower()]
    except KeyError as exc:
        available = ", ".join(profile.profile_id for profile in (EN_GB, EN_US))
        raise ValueError(
            f"unsupported English language profile {profile_id!r}; available: {available}"
        ) from exc
