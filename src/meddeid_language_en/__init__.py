"""English GB and US language profiles for MedDeID."""

from .capabilities import capability_manifest, subannotation_capability_manifest
from .contacts import is_approved_synthetic_phone
from .dates import (
    ParsedDate,
    birth_date_variants,
    date_age_variants,
    date_replacement,
    parse_date_text,
    pseudonymize_date_text,
    render_parsed_date,
)
from .name_pseudonyms import name_replacement, pseudonymize_name_text
from .lookups import (
    lookup_categories,
    lookup_manifest,
    lookup_records,
    lookup_source,
    lookup_values,
)
from .postprocess import post_process_spans
from .identifiers import (
    classify_identifier,
    is_approved_synthetic_identifier,
    is_valid_identifier,
)
from .profiles import EN_GB, EN_US, LanguageProfile, get_profile

__all__ = [
    "LanguageProfile",
    "name_replacement",
    "pseudonymize_name_text",
    "EN_GB",
    "EN_US",
    "ParsedDate",
    "get_profile",
    "lookup_categories",
    "lookup_records",
    "lookup_values",
    "lookup_source",
    "lookup_manifest",
    "post_process_spans",
    "parse_date_text",
    "date_age_variants",
    "date_replacement",
    "birth_date_variants",
    "pseudonymize_date_text",
    "render_parsed_date",
    "capability_manifest",
    "subannotation_capability_manifest",
    "classify_identifier",
    "is_valid_identifier",
    "is_approved_synthetic_identifier",
    "is_approved_synthetic_phone",
]

__version__ = "0.2.2"
