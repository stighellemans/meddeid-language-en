# en-GB source notes

The profile covers the four nations of the United Kingdom. It does not treat
England-only data as a UK proxy. Every record carries one or more source IDs
defined in `sources.lock.json`.

The current official-data limitation for surnames is explicit: ONS does not
publish a comprehensive current UK surname table. The DfE Autumn 2014 school
census top 1,000 is therefore used as the frequency-bearing core. No electoral
roll, person register, UK BMD-derived, Pointer, or restricted postcode data is
included.

The locked build uses the ONS 1996–2025 England/Wales baby-name workbook, the
NRS 2025 all-name workbook, and the NISRA 1997–2025 all-name workbook. Counts
are aggregated per independent token and suppression thresholds are retained
in record attributes. OS Open Names contributes populated places, public
health sites, and a deterministic sample of up to 50,000 named roads per Great
Britain nation. Code-Point Open contributes one stable representative postcode
per outward district. OSNI OGL gazetteers supply Northern Ireland roads and
places; CPD and Pointer are expressly excluded.

NHS ODS public reports supply England, Wales, and Northern Ireland organisation
and site names. OS Open Names and the curated devolved official directories
complete four-nation hospital coverage. SOC 2020 contributes the natural-word-
order occupation index. Every raw byte set is individually SHA-256 locked; a
multi-file source also carries a logical hash over its ordered file lock.

Real name tokens are independent lookup values, not person records. Public
institution and geographic names may be present. Generated identifiers and
phone numbers come from test, drama, or deliberately non-assignable spaces.
