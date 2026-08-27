"""Portable capability descriptors shared with the JavaScript package."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from importlib.resources import files

from .resources import normalize_profile_id


@lru_cache(maxsize=2)
def subannotation_capability_manifest(profile_id: str) -> dict:
    profile_id = normalize_profile_id(profile_id)
    path = files("meddeid_language_en").joinpath(
        "resources", "subannotation", f"{profile_id}.json"
    )
    content = path.read_bytes()
    profile = json.loads(content)
    return {
        "contract_version": profile["contractVersion"],
        "profile_id": profile["profileId"],
        "ruleset_id": profile["rulesetId"],
        "runtime": "javascript",
        "package": profile["javascript"]["package"],
        "export": profile["javascript"]["export"],
        "profile_manifest_sha256": hashlib.sha256(content).hexdigest(),
    }


def capability_manifest(profile_id: str) -> dict:
    return {"subannotation": subannotation_capability_manifest(profile_id)}
