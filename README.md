# meddeid-language-en

Versioned English language capabilities for MedDeID. The package deliberately
contains two locale profiles rather than a generic `en` profile:

- `en-GB` covers England, Scotland, Wales, and Northern Ireland.
- `en-US` covers the 50 states, District of Columbia, Puerto Rico, U.S.
  Virgin Islands, Guam, American Samoa, and the Northern Mariana Islands.

Bare `en` is rejected because numeric dates, addresses, identifiers, clinical
terminology, and synthetic-safe phone ranges differ materially between the two
profiles.

The Python package provides post-processing, structured lookup records,
resource manifests, date/age parsing and pseudonymization. The npm package
provides matching subannotation profiles for the browser toolchain.

English parsing and wording use the same suite-wide declarative age policy as
every other profile; there is no independent English maximum-age algorithm.
Trusted full `patient.birth_date` values are expanded only into bounded,
locale-correct full-year representations.

## Mixed-locale subannotation

`meddeid-subannotate` can route a mixed corpus without splitting it. Install
this package and pin both ordinary profiles in one workspace:

```bash
npm install --no-save @meddeid/language-en@0.2.1
npm run profile -- set en-GB en-US
```

The application selects a child profile by an exact `metadata.lang` match for
each document. It fails when metadata is missing or unsupported rather than
guessing. The router manifest pins both profile descriptors and their lookup
hashes, while every document continues to use only its locale's rules.

## Resource workflow

```bash
python -m meddeid_language_en.resources audit --profile en-GB
python -m meddeid_language_en.resources audit --profile en-US
python -m meddeid_language_en.resources fetch --profile en-US --cache-dir .cache/sources
python -m meddeid_language_en.resources build --profile en-US --cache-dir .cache/sources
python -m meddeid_language_en.resources diff --profile en-US --cache-dir .cache/sources
```

`fetch` verifies the source hash recorded in `sources/*/sources.lock.json`.
`build` is deterministic and writes only licence-compatible derived records.
Unrestricted raw downloads remain in the ignored cache. Each runtime record
retains its source identifier and regional scope.

The committed audits enforce minimum counts and category-level regional
coverage, verify provenance completeness and logical multi-file hashes, and
report malformed values, duplicate keys, semantic collisions, count
regressions, and source drift. Current builds contain roughly 326,000 GB and
345,000 US structured lookup records; exact counts and hashes are recorded in
the profile audit manifests.

The included resources are designed for recognition and deterministic
synthetic generation. Real given-name and family-name tokens are sampled
independently; no person-level source records are ingested. Public institution,
street, and locality names may be used, while phones, email domains, and
identifiers use official fictional/test or deliberately non-assignable forms.

## Synthetic labels

English synthetic generation uses the 14-label token-classifier taxonomy and
must never emit `Anonymize_Other`. The full 15-label MedDeID taxonomy remains
valid for annotation import and other interoperability paths.

The generation allowlist, in its load-bearing order, is exactly:

```text
Address_Location:Caregiver
Address_Location:Other
Address_Location:Patient
Age_Birthdate
Contactdetails
Date
ID:Caregiver
ID:Patient
Name:Caregiver
Name:Other
Name:Patient
Organization:Healthcare
Organization:Other
Profession
```

## Stable name aliases (Python 0.2.3)

The Python name provider uses the existing en-GB / en-US first-name and
family-name resources. It does not download another name database. The shared
core renderer preserves recognized titles, initials and case. English profiles
also supply their own recognized suffixes and credentials.

```python
from meddeid_language_en import pseudonymize_name_text

# Synthetic reproducibility fixture only; use a protected random key in production.
pseudonymize_name_text("Mark Peters", key=bytes(range(32)), scope="study-a")
# "[Bogomil Mackenzie]"
```

`pseudonymize_name_text()` returns a bracketed alias or `None` for an unsupported
shape. Callers must use the original entity label on `None`, never the source
name. The profile hook `replace_name()` returns the same body without brackets.
The public MedDeID runtime selects this with `metadata.name_replacement=true`
for all Name subtypes; false or omission keeps the original labels.

The helper uses the supplied key and scope for deterministic component aliases. A lone given name or surname keeps its alias when rendered as part of a full name. A missing middle name omits only that component. Initials use the first letter of the corresponding alias. The runtime defaults to a patient-specific key within each study. The same alias or initial can refer to multiple people. Workers cache public catalog resources per profile. The JavaScript package exports subannotations separately.
