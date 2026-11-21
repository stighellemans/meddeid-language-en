# Changelog

## [0.2.4] - 2026-11-21

- Render event dates and clinical ages independently with the selected language profile.

- Added deterministic bracketed name aliases for `en-GB` and `en-US`, using each locale’s existing name resources.
- Preserved recognized titles, initials, surname particles, suffixes and credentials. Requires core 0.2.4.

## [0.2.1] - 2026-09-05

- Enabled npm trusted publishing for the coordinated MedDeID suite 0.2.0
  release while preserving the 0.2 language-profile contract.

## [0.2.0] - 2026-08-27

- Infer leading municipality components in non-healthcare organization names
  when a locale locality is followed by a recognized organization-type phrase,
  including sports clubs, schools, colleges, councils, associations,
  authorities, services, and libraries.
- Infer municipality components in healthcare organization names from the
  complete facility record, matching locality region, and facility-name
  structure. This covers both location-led names such as `Dorking Hospital`
  and terminal forms such as `Medical Center Enterprise`, while protecting
  eponymic names such as `Queen Victoria Memorial Hospital`.
- Treat `Doctor` and `Doctors` as identifying `institution` content inside
  healthcare organization names, and classify every standalone healthcare-name
  `of` token as non-identifying `additional_info`.
- Removed the manually incremented English subannotation ruleset version;
  releases and Git history now provide its change history.
- Use `given.familyNN` email-local-part structure and patient metadata to
  classify the final name token as `family`, even when it is also a common
  given name such as `Andrew`.
- Classify a recognized locality as `municipality` when it follows a structural
  healthcare facility construction such as `Infirmary of Edinburgh`, without
  treating institutional `of` names such as `University of Washington` as
  geographic components; classify the `of` locality connector itself as
  non-identifying `additional_info`.
- Split generic healthcare facility/type terms (`Hospital`, `Clinic`,
  `Infirmary`, and `Medical`) from identifying healthcare
  organization names as `medical_info`, while retaining branded clinical
  service phrases such as `Care of the Elderly` and `Prescribing` as
  `institution`.
- Limit email name parsing to the local part before `@`, preventing provider
  and top-level-domain tokens such as `att.net` from being classified as names;
  recognized healthcare-institution domain components remain `institution`.
- Classify generator-provenance national and caregiver professional identifiers
  as `public_id`, including bare numeric GMC values, while keeping MRN and
  report/accession identifiers `internal_id` even when their shapes overlap.
- Parse abbreviated ages such as `43 y/o` into `age_year`, `age_type`,
  `formatting`, and `additional_info`, and use surrounding `age`/`aged` or unit
  context when an age annotation contains only its numeric component.
- Enforce `profession` as the fallback for every non-formatting part of a
  top-level `Profession` span, including competing autodetection candidates,
  while retaining explicit `hobby` and `employment_state` labels.
- Preserve US ZIP-code classification when a preceding state abbreviation,
  such as `FL`, is also a possible unit/floor abbreviation.
- Resolve ambiguous US state abbreviations by address position, preserving
  street components such as `AK Rte`, `Co Rd`, and directional `NE` while
  classifying locality-tail abbreviations before ZIP codes as `region`.
- Give address structure precedence over lookup fallbacks: a leading numeric
  component is a `house_number`, and the penultimate comma-delimited field is
  `municipality`, including multiword and bilingual locality names.
- Treat a sole comma-delimited suffix as `municipality` when the prefix is
  already a delivery line and the suffix has no street, unit, or number
  evidence, while preserving genuine second delivery lines.
- Make `*.locality` generator provenance authoritative across preprocessing
  candidates so ambiguous isolated names cannot inherit a street lookup.
- Classify English ordinal numbers as `day` plus a `formatting` suffix, and use
  internal-only preprocessing seeds so placeholder labels cannot reach output.
- Added automatic benchmark-category handling for profession spans.
- Preserve one-letter name tokens as `initials` when the surname fallback is
  applied, including final initials such as `Kimon J.`.
- Align English subannotation ruleset v2 with the established Dutch and paper
  taxonomy by collapsing locale-specific detail into the canonical categories
  used for cross-language core-PII evaluation.
- Connected English date/age parsing and rendering to the suite-wide
  declarative age policy, removed the independent maximum-exact-age rule, and
  added trusted full birth-date variants for `en-GB` and `en-US`.

## 0.1.0

- Add separate `en-GB` and `en-US` Python language profiles.
- Add structured, provenance-carrying lookup resources and deterministic
  resource audit tooling.
- Add locale-aware post-processing and date/age pseudonymization.
- Add separate JavaScript subannotation registrations for both locales.
