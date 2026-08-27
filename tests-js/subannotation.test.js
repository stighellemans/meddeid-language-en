import assert from 'node:assert/strict';
import test from 'node:test';

import gb from '../js/subannotation-en-gb.js';
import us from '../js/subannotation-en-us.js';

function run(profile, ruleId, category, text, metadata = {}) {
  const rule = profile.rules.find((candidate) => candidate.ruleId === ruleId);
  assert.ok(rule, `missing rule ${ruleId}`);
  return rule.transformSegment({
    item: { metadata }, segment: { begin: 0, end: Array.from(text).length, category }, text,
  });
}

function semantic(parts) {
  return parts.filter((part) => part.category !== 'formatting').map((part) => part.category);
}

test('profiles are strictly separated and resource manifests are pinned', () => {
  assert.equal(gb.profileId, 'en-GB');
  assert.equal(us.profileId, 'en-US');
  assert.deepEqual(gb.languageTags, ['en-GB']);
  assert.deepEqual(us.languageTags, ['en-US']);
  assert.match(gb.resourceManifest.lookups_sha256, /^[a-f0-9]{64}$/u);
  assert.match(us.resourceManifest.lookups_sha256, /^[a-f0-9]{64}$/u);
  assert.equal(gb.resourceManifest.lookups_sha256, 'adc32237486ac62b8661ef3b81547d6c0645fbde0ba0c742b8c6a846f6ed60a0');
  assert.equal(us.resourceManifest.lookups_sha256, 'd8d5a0330c18349c45d9f9fcbebcbac3dd34fd59482a3a8fb4b18b5bf3f53f04');
  assert.ok(gb.resourceManifest.counts.first_names >= 39000);
  assert.ok(gb.resourceManifest.counts.streets >= 140000);
  assert.ok(us.resourceManifest.counts.first_names >= 29000);
  assert.ok(us.resourceManifest.counts.family_names >= 160000);
  assert.ok(us.resourceManifest.counts.streets >= 56000);
  const retiredEnglishOnlyCategories = new Set([
    'middle', 'suffix', 'credential', 'department', 'unit_number', 'email',
    'nhs_number', 'chi_number', 'h_and_c_number', 'nino', 'professional_id',
    'ssn', 'npi', 'mbi', 'state', 'territory', 'urbanization',
  ]);
  for (const profile of [gb, us]) {
    const categories = Object.values(profile.categoryGroups).flat();
    assert.ok(categories.every((category) => !retiredEnglishOnlyCategories.has(category)));
    assert.deepEqual(profile.categoryGroups.Name, ['given', 'family', 'initials', 'title']);
    assert.deepEqual(profile.categoryGroups.ID, ['public_id', 'internal_id']);
    assert.ok(Object.values(profile.seedCategories).every((category) =>
      category.startsWith('__meddeid_seed__:')));
    assert.ok(Object.values(profile.seedCategories).every((category) => !categories.includes(category)));
  }
});

test('numeric and ISO dates use locale-correct token categories', () => {
  assert.deepEqual(semantic(run(gb, 'split_en_gb_date_variants', gb.seedCategories.Date, '03/04/2025')), ['day', 'month', 'year']);
  assert.deepEqual(semantic(run(us, 'split_en_us_date_variants', us.seedCategories.Date, '03/04/2025')), ['month', 'day', 'year']);
  assert.deepEqual(semantic(run(gb, 'split_en_gb_date_variants', gb.seedCategories.Date, '2025-04-03')), ['year', 'month', 'day']);
  assert.deepEqual(semantic(run(us, 'split_en_us_date_variants', us.seedCategories.Date, '2025-04-03')), ['year', 'month', 'day']);
  assert.deepEqual(
    run(gb, 'split_en_gb_date_variants', gb.seedCategories.Date, '7th August 2028').map((part) => part.category),
    ['day', 'formatting', 'formatting', 'month', 'formatting', 'year'],
  );
});

test('abbreviated and context-only ages use benchmark age categories', () => {
  for (const profile of [gb, us]) {
    assert.deepEqual(
      run(
        profile,
        `split_${profile.profileId.toLowerCase().replace('-', '_')}_date_variants`,
        profile.seedCategories.Age_Birthdate,
        '43 y/o',
      ),
      [
        { begin: 0, end: 2, category: 'age_year' },
        { begin: 2, end: 3, category: 'formatting' },
        { begin: 3, end: 4, category: 'age_type' },
        { begin: 4, end: 5, category: 'formatting' },
        { begin: 5, end: 6, category: 'additional_info' },
      ],
    );

    const ruleId = `split_${profile.profileId.toLowerCase().replace('-', '_')}_date_variants`;
    const rule = profile.rules.find((candidate) => candidate.ruleId === ruleId);
    assert.deepEqual(
      rule.transformSegment({
        item: { textContextBefore: 'The patient, aged ', textContextAfter: ', was reviewed.' },
        segment: { begin: 0, end: 2, category: profile.seedCategories.Age_Birthdate },
        text: '43',
      }),
      [{ begin: 0, end: 2, category: 'age_year' }],
    );

    const generatedAgeCases = [
      ['18 m/o', ['age_month', 'formatting', 'age_type', 'formatting', 'additional_info']],
      ['3 wk old', ['age_week', 'formatting', 'age_type', 'formatting', 'additional_info']],
      ['day 3 of life', ['age_type', 'formatting', 'age_day', 'formatting', 'additional_info', 'formatting', 'additional_info']],
      ['3-day-old', ['age_day', 'formatting', 'age_type', 'formatting', 'additional_info']],
      ['6 w/o', ['age_week', 'formatting', 'age_type', 'formatting', 'additional_info']],
      ['2 d/o', ['age_day', 'formatting', 'age_type', 'formatting', 'additional_info']],
    ];
    for (const [text, expectedCategories] of generatedAgeCases) {
      assert.deepEqual(
        run(profile, ruleId, profile.seedCategories.Age_Birthdate, text)
          .map((part) => part.category),
        expectedCategories,
        `${profile.profileId}: ${text}`,
      );
    }
  }
});

test('names map English detail onto the established Dutch and paper categories', () => {
  const gbParts = semantic(run(gb, 'split_name_variants_from_profile', gb.seedCategories.Name, "Dr Emily O'Neill MBBS"));
  assert.deepEqual(gbParts, ['title', 'given', 'family', 'title']);
  const usParts = semantic(run(us, 'split_name_variants_from_profile', us.seedCategories.Name, 'Dr A. Ana de la Cruz Jr MD'));
  assert.ok(usParts.includes('initials'));
  assert.ok(usParts.includes('given'));
  assert.ok(usParts.includes('family'));
  assert.ok(usParts.includes('title'));
  assert.ok(!usParts.includes('middle'));
  assert.ok(!usParts.includes('suffix'));
  assert.ok(!usParts.includes('credential'));

  for (const profile of [gb, us]) {
    assert.deepEqual(
      run(
        profile,
        'split_name_variants_from_profile',
        profile.seedCategories.Name,
        'Kimon J.',
        { patientGivenName: 'Kimon', patientLastName: 'Johns' },
      ),
      [
        { begin: 0, end: 5, category: 'given' },
        { begin: 5, end: 6, category: 'formatting' },
        { begin: 6, end: 7, category: 'initials' },
        { begin: 7, end: 8, category: 'formatting' },
      ],
    );
  }
});

test('profession spans coerce non-formatting fallback labels to profession', () => {
  for (const profile of [gb, us]) {
    const rule = profile.rules.find(
      (candidate) => candidate.ruleId === 'classify_profession_content',
    );
    assert.deepEqual(
      rule.transformSegment({
        item: { gold: { category: 'Profession' } },
        segment: { begin: 0, end: 19, category: 'family' },
        text: 'Clinical Pharmacist',
      }),
      [
        { begin: 0, end: 8, category: 'profession' },
        { begin: 8, end: 9, category: 'formatting' },
        { begin: 9, end: 19, category: 'profession' },
      ],
    );
    for (const category of ['profession', 'hobby', 'employment_state', 'formatting']) {
      assert.equal(
        rule.transformSegment({
          item: { gold: { category: 'Profession' } },
          segment: { begin: 0, end: 4, category },
          text: 'test',
        }),
        null,
      );
    }
  }
});

test('addresses, contacts, institutions, and identifiers use profile rules', () => {
  const addressRule = 'split_address_organization_variants_from_profile';
  assert.ok(semantic(run(gb, addressRule, gb.seedCategories.Address_Location, '10 Baker Street, London, SW1A 2AA')).includes('postal_code'));
  assert.ok(semantic(run(us, addressRule, us.seedCategories.Address_Location, 'URB San Patricio, San Juan, PR 00901')).includes('region'));
  assert.ok(semantic(run(gb, addressRule, gb.seedCategories.Address_Location, 'Flat 4, 10 Baker Street, London SW1A 2AA')).includes('bus_number'));
  assert.ok(semantic(run(gb, addressRule, gb.seedCategories.Address_Location, 'PO Box 42, Belfast BT1 1AA')).includes('postal_office'));
  assert.ok(semantic(run(us, addressRule, us.seedCategories.Address_Location, 'RR 2 Box 152, San Juan, PR 00901')).includes('postal_office'));
  assert.ok(semantic(run(us, addressRule, us.seedCategories.Address_Location, '10 Pennsylvania Avenue NW Apt 4, Washington, DC 20001')).includes('bus_number'));
  assert.ok(semantic(run(us, addressRule, us.seedCategories.Address_Location, '10 Pennsylvania Avenue NW Apt 4, Washington, DC 20001')).includes('region'));
  assert.deepEqual(
    run(
      us,
      addressRule,
      us.seedCategories.Address_Location,
      '878 Franklin St, Miami, FL 33167',
    ).map((part) => part.category),
    [
      'house_number', 'formatting', 'street', 'formatting', 'street',
      'formatting', 'municipality', 'formatting', 'region', 'formatting',
      'postal_code',
    ],
  );
  for (const [text, embeddedToken] of [
    ['593 AK Rte 7, Whittier, AK 99693', 'AK'],
    ['878 4th St NE, Colton, WA 99113', 'NE'],
    ['572 Co Rd 182, Ozan, AR 71855', 'Co'],
  ]) {
    const parts = run(us, addressRule, us.seedCategories.Address_Location, text);
    const embedded = parts.find((part) =>
      text.slice(part.begin, part.end) === embeddedToken && part.begin < text.indexOf(','));
    const tailRegion = parts.find((part) =>
      part.category === 'region' && part.begin > text.lastIndexOf(','));
    assert.equal(embedded?.category, 'street', text);
    assert.ok(tailRegion, text);
    assert.equal(parts.at(-1)?.category, 'postal_code', text);
  }
  assert.deepEqual(
    run(
      us,
      addressRule,
      us.seedCategories.Address_Location,
      '20 W Lanvale St, Bushwood, MD 20618',
    ).map((part) => part.category),
    [
      'house_number', 'formatting', 'street', 'formatting', 'street',
      'formatting', 'street', 'formatting', 'municipality', 'formatting',
      'region', 'formatting', 'postal_code',
    ],
  );
  assert.deepEqual(
    run(
      gb,
      addressRule,
      gb.seedCategories.Address_Location,
      '115 Lathallan Drive, Bridge of Allan, FK9 4AB',
    ).filter((part) => part.category !== 'formatting').map((part) => part.category),
    [
      'house_number', 'street', 'street', 'municipality', 'municipality',
      'municipality', 'postal_code', 'postal_code', 'postal_code', 'postal_code',
    ],
  );
  assert.deepEqual(
    run(
      gb,
      addressRule,
      gb.seedCategories.Address_Location,
      '79 COMMONS HALL ROAD, Newmills',
    ).map((part) => part.category),
    [
      'house_number', 'formatting', 'street', 'formatting', 'street',
      'formatting', 'street', 'formatting', 'municipality',
    ],
  );
  assert.ok(
    !semantic(run(
      gb,
      addressRule,
      gb.seedCategories.Address_Location,
      'Flat 4, 10 Baker Street',
    )).includes('municipality'),
  );
  for (const profile of [gb, us]) {
    const localityRule = profile.rules.find(
      (candidate) => candidate.ruleId === addressRule,
    );
    assert.deepEqual(
      localityRule.transformSegment({
        item: {
          gold: {
            category: 'Address_Location',
            sourceSlot: 'caregiver.locality',
          },
        },
        segment: { begin: 0, end: 5, category: 'street' },
        text: 'Baker',
      }),
      [{ begin: 0, end: 5, category: 'municipality' }],
    );
  }
  for (const profile of [gb, us]) {
    const organizationRule = profile.rules.find(
      (candidate) => candidate.ruleId === addressRule,
    );
    const healthcareParts = (text) => organizationRule.transformSegment({
      item: { gold: { category: 'Organization', subtype: 'Healthcare' } },
      segment: {
        begin: 0,
        end: Array.from(text).length,
        category: profile.seedCategories.Organization,
      },
      text,
    }).map((part) => part.category);

    assert.deepEqual(
      healthcareParts('GOV JUAN F LUIS HOSPITAL & MEDICAL CTR'),
      [
        'institution', 'formatting', 'institution', 'formatting',
        'institution', 'formatting', 'institution', 'formatting',
        'medical_info', 'formatting', 'institution', 'formatting',
        'institution',
      ],
    );
    assert.deepEqual(
      healthcareParts('Care of the Elderly Prescribing'),
      [
        'institution', 'formatting', 'additional_info', 'formatting',
        'institution', 'formatting', 'institution', 'formatting',
        'institution',
      ],
    );
    assert.deepEqual(
      healthcareParts('Royal Infirmary of Edinburgh'),
      [
        'institution', 'formatting', 'medical_info', 'formatting',
        'additional_info', 'formatting', 'municipality',
      ],
    );
    assert.deepEqual(
      healthcareParts('University of Washington Medical Center'),
      [
        'institution', 'formatting', 'additional_info', 'formatting',
        'institution', 'formatting', 'institution', 'formatting',
        'institution',
      ],
    );
    assert.deepEqual(
      healthcareParts("Guy's Hospital Clinic Doctors Infirmary"),
      [
        'institution', 'formatting', 'medical_info', 'formatting',
        'medical_info', 'formatting', 'institution', 'formatting',
        'medical_info',
      ],
    );
    assert.deepEqual(
      healthcareParts('DOCTORS CENTER HOSPITAL CAROLINA LLC'),
      [
        'institution', 'formatting', 'institution', 'formatting',
        'medical_info', 'formatting',
        profile.profileId === 'en-US' ? 'municipality' : 'institution', 'formatting',
        'institution',
      ],
    );
    if (profile.profileId === 'en-GB') {
      assert.deepEqual(
        healthcareParts('Dorking Hospital'),
        ['municipality', 'formatting', 'medical_info'],
      );
      assert.deepEqual(
        healthcareParts('Queen Victoria Memorial Hospital'),
        [
          'institution', 'formatting', 'institution', 'formatting',
          'institution', 'formatting', 'medical_info',
        ],
      );
      assert.deepEqual(
        healthcareParts('Bournemouth Nuffield Hospital'),
        [
          'municipality', 'formatting', 'institution', 'formatting',
          'medical_info',
        ],
      );
      assert.deepEqual(
        organizationRule.transformSegment({
          item: { gold: { category: 'Organization', subtype: 'Other' } },
          segment: {
            begin: 0,
            end: 21,
            category: profile.seedCategories.Organization,
          },
          text: 'Abercrave Sports Club',
        }).map((part) => part.category),
        ['municipality', 'formatting', 'company', 'formatting', 'company'],
      );
    } else {
      assert.deepEqual(
        healthcareParts('Hampshire Memorial Hospital'),
        ['municipality', 'formatting', 'institution', 'formatting', 'medical_info'],
      );
      assert.deepEqual(
        healthcareParts('Medical Center Enterprise'),
        ['institution', 'formatting', 'institution', 'formatting', 'municipality'],
      );
      assert.deepEqual(
        healthcareParts('Mount Desert Island Hospital'),
        [
          'institution', 'formatting', 'institution', 'formatting',
          'institution', 'formatting', 'medical_info',
        ],
      );
    }
    assert.deepEqual(
      organizationRule.transformSegment({
        item: { gold: { category: 'Organization', subtype: 'Healthcare' } },
        segment: { begin: 100, end: 108, category: 'institution' },
        text: 'HOSPITAL',
      }),
      [{ begin: 100, end: 108, category: 'medical_info' }],
    );
    assert.equal(
      organizationRule.transformSegment({
        item: { gold: { category: 'Organization', subtype: 'Healthcare' } },
        segment: { begin: 100, end: 108, category: 'hospital_location' },
        text: 'Ward 7A',
      }),
      null,
    );
    assert.deepEqual(
      organizationRule.transformSegment({
        item: {
          gold: { category: 'Organization', subtype: 'Healthcare' },
          reviewBegin: 100,
          reviewText: 'Royal Infirmary of Edinburgh',
        },
        segment: { begin: 119, end: 128, category: 'institution' },
        text: 'Edinburgh',
      }),
      [{ begin: 119, end: 128, category: 'municipality' }],
    );
    assert.deepEqual(
      organizationRule.transformSegment({
        item: {
          gold: { category: 'Organization', subtype: 'Healthcare' },
          reviewBegin: 100,
          reviewText: 'Royal Infirmary of Edinburgh',
        },
        segment: { begin: 116, end: 118, category: 'institution' },
        text: 'of',
      }),
      [{ begin: 116, end: 118, category: 'additional_info' }],
    );
    assert.deepEqual(
      organizationRule.transformSegment({
        item: { gold: { category: 'Organization', subtype: 'Healthcare' } },
        segment: { begin: 100, end: 107, category: 'medical_info' },
        text: 'DOCTORS',
      }),
      [{ begin: 100, end: 107, category: 'institution' }],
    );
    assert.deepEqual(
      organizationRule.transformSegment({
        item: { gold: { category: 'Organization', subtype: 'Healthcare' } },
        segment: { begin: 100, end: 107, category: 'medical_info' },
        text: 'Medical',
      }),
      [{ begin: 100, end: 107, category: 'institution' }],
    );
    if (profile.profileId === 'en-GB') {
      assert.deepEqual(
        organizationRule.transformSegment({
          item: {
            gold: { category: 'Organization', subtype: 'Healthcare' },
            reviewBegin: 100,
            reviewText: 'Dorking Hospital',
          },
          segment: { begin: 100, end: 107, category: 'institution' },
          text: 'Dorking',
        }),
        [{ begin: 100, end: 107, category: 'municipality' }],
      );
      assert.deepEqual(
        organizationRule.transformSegment({
          item: {
            gold: { category: 'Organization', subtype: 'Other' },
            reviewBegin: 100,
            reviewText: 'Abercrave Sports Club',
          },
          segment: { begin: 100, end: 109, category: 'company' },
          text: 'Abercrave',
        }),
        [{ begin: 100, end: 109, category: 'municipality' }],
      );
      assert.deepEqual(
        organizationRule.transformSegment({
          item: {
            gold: { category: 'Organization', subtype: 'Other' },
            reviewBegin: 300,
            reviewText: 'Seascale Voluntary Service',
          },
          segment: { begin: 300, end: 308, category: 'institution' },
          text: 'Seascale',
        }),
        [{ begin: 300, end: 308, category: 'municipality' }],
      );
      assert.deepEqual(
        organizationRule.transformSegment({
          item: {
            gold: { category: 'Organization', subtype: 'Other' },
            reviewBegin: 300,
            reviewText: 'Llangunllo Community Centre',
          },
          segment: { begin: 321, end: 327, category: 'institution' },
          text: 'Centre',
        }),
        [{ begin: 321, end: 327, category: 'company' }],
      );
    } else {
      assert.deepEqual(
        organizationRule.transformSegment({
          item: {
            gold: { category: 'Organization', subtype: 'Other' },
            reviewBegin: 200,
            reviewText: 'Swatara Senior Center',
          },
          segment: { begin: 200, end: 207, category: 'company' },
          text: 'Swatara',
        }),
        [{ begin: 200, end: 207, category: 'municipality' }],
      );
    }
  }
  const emailParts = semantic(run(us, 'split_contact_variants', us.seedCategories.Contactdetails, 'elly.gubitosi46@outlook.com'));
  assert.ok(emailParts.includes('given'));
  assert.ok(emailParts.includes('family'));
  assert.ok(emailParts.every((category) => ['given', 'family', 'initials', 'institution', 'additional_info'].includes(category)));
  assert.deepEqual(
    semantic(run(
      us,
      'split_contact_variants',
      us.seedCategories.Contactdetails,
      'skailar.proszek52@att.net',
    )),
    ['given', 'family', 'additional_info', 'additional_info', 'additional_info'],
  );
  assert.deepEqual(
    semantic(run(
      gb,
      'split_contact_variants',
      gb.seedCategories.Contactdetails,
      'raffi.andrew28@virginmedia.com',
    )),
    ['given', 'family', 'additional_info', 'additional_info', 'additional_info'],
  );
  assert.ok(
    semantic(run(
      gb,
      'split_contact_variants',
      gb.seedCategories.Contactdetails,
      'appointments@royal.infirmary.of.edinburgh',
    )).slice(1).every((category) => category === 'institution'),
  );
  assert.ok(semantic(run(gb, 'classify_identifier_content', gb.seedCategories.ID, '943 476 5919')).every((category) => category === 'public_id'));
  assert.ok(semantic(run(us, 'classify_identifier_content', us.seedCategories.ID, '000-12-3456')).every((category) => category === 'public_id'));
});

test('synthetic identifier provenance overrides ambiguous surface shapes', () => {
  const cases = [
    [gb, '0010662', 'caregiver.professional_id', 'Caregiver', 'public_id'],
    [gb, '0154781', 'patient.mrn', 'Patient', 'internal_id'],
    [gb, '0123456789', 'patient.report_id', 'Patient', 'internal_id'],
    [gb, '000 000 0000', 'patient.national_id', 'Patient', 'public_id'],
    [us, 'LIC01234567', 'caregiver.professional_id', 'Caregiver', 'public_id'],
    [us, '000-12-3456', 'patient.mrn', 'Patient', 'internal_id'],
  ];
  for (const [profile, text, sourceSlot, subtype, expected] of cases) {
    const rule = profile.rules.find((candidate) => candidate.ruleId === 'classify_identifier_content');
    const parts = rule.transformSegment({
      item: { gold: { sourceSlot, subtype } },
      segment: { begin: 0, end: Array.from(text).length, category: profile.seedCategories.ID },
      text,
    });
    assert.ok(
      semantic(parts).every((category) => category === expected),
      `${profile.profileId} ${sourceSlot} ${text}`,
    );
  }
});
