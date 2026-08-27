# en-US source notes

The profile covers the 50 states, District of Columbia, Puerto Rico, U.S.
Virgin Islands, Guam, American Samoa, and the Northern Mariana Islands. Freely
associated sovereign states and minor outlying islands are outside the profile.

SSA given-name data and Census surname data are aggregated public statistics;
no person-level records are ingested. Geographic and public-facility resources
retain territory tags so audits can detect mainland-only regressions.

The SSA adapter combines 2025 national ranks, full 2024 national and territory
frequencies, and 2020 state frequencies. SSA's binary download endpoints reject
automated retrieval in the build environment, so immutable public mirrors of
the publisher bytes are locked alongside their official origin URLs. The
release mix is explicit and cannot advance silently. Counts, sex, source-year
statistics, geographic coverage, and the SSA suppression threshold of five
remain in record attributes.

Census 2025 Gazetteer place/ZCTA data and a ZCTA-constrained GeoNames postal
join supply localities and ZIP geography. The 56 TIGER/Line primary/secondary
road files cover every state or equivalent; the runtime asset keeps the 3,000
lowest SHA-256 normalized road keys per region. Census 2010 supplies the full
published surname table, CMS supplies public facility names for every region,
and the BLS SOC direct-match title file supplies occupations. Facility street
addresses and telephone fields are deliberately discarded.

Generated SSNs use unassignable SSA ranges, phone numbers use the NANPA drama
range where applicable, and other national IDs use published fictitious
examples or deliberately non-assignable forms. Email-domain selection is owned
by `meddeid-data` and uses a deterministic, locale-aware provider mix.
