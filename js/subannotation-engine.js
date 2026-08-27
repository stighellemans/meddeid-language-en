import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
const MODULE_PATH = fileURLToPath(import.meta.url);

function normalize(value) {
  return String(value ?? '').normalize('NFKC').trim().toLocaleLowerCase('en');
}

function loadProfile(profileId) {
  const root = path.resolve(MODULE_DIR, '..', 'src', 'meddeid_language_en', 'resources');
  const spec = JSON.parse(fs.readFileSync(path.join(root, 'subannotation', `${profileId}.json`), 'utf8'));
  const lookupPath = path.join(root, profileId, 'lookups.jsonl');
  const records = fs.readFileSync(lookupPath, 'utf8').split(/\r?\n/u)
    .filter(Boolean).map((line) => JSON.parse(line));
  const grouped = new Map();
  for (const record of records) {
    if (!grouped.has(record.category)) grouped.set(record.category, []);
    grouped.get(record.category).push(record);
  }
  return { root, spec, lookupPath, records, grouped };
}

function tokenize(value) {
  const chars = Array.from(String(value ?? ''));
  const tokens = [];
  let cursor = 0;
  while (cursor < chars.length) {
    const start = cursor;
    const letter = /\p{L}/u.test(chars[cursor]);
    const digit = /\d/u.test(chars[cursor]);
    cursor += 1;
    while (cursor < chars.length) {
      if (letter && /[\p{L}\p{M}'’]/u.test(chars[cursor])) cursor += 1;
      else if (digit && /\d/u.test(chars[cursor])) cursor += 1;
      else if (!letter && !digit && !/[\p{L}\p{M}\d]/u.test(chars[cursor])) cursor += 1;
      else break;
    }
    const raw = chars.slice(start, cursor).join('');
    tokens.push({
      begin: start, end: cursor, raw, normalized: normalize(raw),
      kind: letter ? 'word' : digit ? 'number' : 'formatting',
    });
  }
  return tokens;
}

function absoluteSegments(segment, tokens, categories, fallbackCategory = 'additional_info') {
  return tokens.map((token, index) => ({
    begin: segment.begin + token.begin,
    end: segment.begin + token.end,
    category: token.kind === 'formatting' ? 'formatting' : categories[index] ?? fallbackCategory,
  }));
}

function phraseTrie(values) {
  const root = new Map();
  for (const value of values) {
    const words = tokenize(value).filter((token) => token.kind !== 'formatting');
    let node = root;
    for (const word of words) {
      if (!node.has(word.normalized)) node.set(word.normalized, new Map());
      node = node.get(word.normalized);
    }
    if (words.length) node.terminal = true;
  }
  return root;
}

function longestPhraseAt(tokens, start, trie) {
  let node = trie;
  let semanticCount = 0;
  let best = 0;
  for (let index = start; index < tokens.length; index += 1) {
    if (tokens[index].kind === 'formatting') continue;
    node = node.get(tokens[index].normalized);
    if (!node) break;
    semanticCount += 1;
    if (node.terminal) best = semanticCount;
  }
  return best;
}

function applyPhrase(tokens, categories, trie, category) {
  for (let index = 0; index < tokens.length; index += 1) {
    if (tokens[index].kind === 'formatting' || categories[index]) continue;
    let remaining = longestPhraseAt(tokens, index, trie);
    if (!remaining) continue;
    for (let cursor = index; cursor < tokens.length && remaining > 0; cursor += 1) {
      if (tokens[cursor].kind !== 'formatting') {
        categories[cursor] = category;
        remaining -= 1;
      }
    }
  }
}

const MONTHS = new Set([
  'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
  'september', 'october', 'november', 'december', 'jan', 'feb', 'mar', 'apr',
  'jun', 'jul', 'aug', 'sep', 'sept', 'oct', 'nov', 'dec',
]);
const WEEKDAYS = new Set([
  'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
  'mon', 'tue', 'tues', 'wed', 'thu', 'thur', 'thurs', 'fri', 'sat', 'sun',
]);
const SEASONS = new Set(['spring', 'summer', 'autumn', 'fall', 'winter']);
const AGE_UNITS = new Map([
  ['year', 'age_year'], ['years', 'age_year'], ['yr', 'age_year'], ['yrs', 'age_year'],
  ['y', 'age_year'], ['yo', 'age_year'],
  ['month', 'age_month'], ['months', 'age_month'], ['mo', 'age_month'], ['mos', 'age_month'], ['m', 'age_month'],
  ['week', 'age_week'], ['weeks', 'age_week'], ['wk', 'age_week'], ['wks', 'age_week'], ['w', 'age_week'],
  ['day', 'age_day'], ['days', 'age_day'], ['d', 'age_day'],
]);
const STREET_TERMS = new Set([
  'street', 'st', 'road', 'rd', 'lane', 'ln', 'avenue', 'ave', 'close', 'drive',
  'dr', 'way', 'crescent', 'terrace', 'gardens', 'place', 'square', 'mews',
  'grove', 'court', 'ct', 'circle', 'boulevard', 'blvd', 'highway', 'hwy',
  'trail', 'trl', 'parkway', 'pkwy',
]);
const DIRECTIONALS = new Set(['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw', 'north', 'south', 'east', 'west']);
const GB_UNIT_TERMS = new Set(['flat', 'unit', 'apartment', 'apt', 'suite', 'room']);
const US_UNIT_TERMS = new Set(['apt', 'apartment', 'suite', 'ste', 'unit', 'room', 'rm', 'floor', 'fl']);
const US_STATE_CODES = new Set([
  'al', 'ak', 'az', 'ar', 'ca', 'co', 'ct', 'de', 'fl', 'ga', 'hi', 'id', 'il',
  'in', 'ia', 'ks', 'ky', 'la', 'me', 'md', 'ma', 'mi', 'mn', 'ms', 'mo', 'mt',
  'ne', 'nv', 'nh', 'nj', 'nm', 'ny', 'nc', 'nd', 'oh', 'ok', 'or', 'pa', 'ri',
  'sc', 'sd', 'tn', 'tx', 'ut', 'vt', 'va', 'wa', 'wv', 'wi', 'wy', 'dc',
]);
const US_TERRITORY_CODES = new Set(['pr', 'vi', 'gu', 'as', 'mp']);
const HEALTHCARE_MEDICAL_INFO_TERMS = new Set([
  'clinic', 'clinics', 'hospital', 'hospitals', 'infirmary', 'infirmaries',
]);
const HEALTHCARE_LOCATION_INTRODUCERS = new Set([
  'center', 'centre', 'clinic', 'clinics', 'ctr', 'hospital', 'hospitals',
  'infirmary', 'infirmaries',
]);
const HEALTHCARE_LOCATION_GENERIC_TERMS = new Set([
  ...HEALTHCARE_LOCATION_INTRODUCERS,
  'city', 'community', 'county', 'general', 'health', 'healthcare', 'medical',
  'memorial', 'regional', 'royal', 'university',
]);
const HEALTHCARE_EPONYM_PREFIXES = new Set([
  'king', 'prince', 'princess', 'queen', 'royal', 'saint', 'st',
]);
const ORGANIZATION_LEGAL_SUFFIXES = new Set([
  'corp', 'corporation', 'inc', 'incorporated', 'limited', 'llc', 'ltd', 'plc',
]);
const OTHER_ORGANIZATION_TYPE_TERMS = new Set([
  'association', 'authority', 'center', 'centre', 'club', 'college', 'council',
  'district', 'library', 'school', 'service', 'services',
]);

function expectedOrdinalSuffix(value) {
  const number = Number(value);
  const lastTwo = number % 100;
  if (lastTwo >= 11 && lastTwo <= 13) return 'th';
  if (number % 10 === 1) return 'st';
  if (number % 10 === 2) return 'nd';
  if (number % 10 === 3) return 'rd';
  return 'th';
}

function numericAgeCategoryFromContext(item) {
  const after = String(item?.textContextAfter ?? '').normalize('NFKC').toLocaleLowerCase('en');
  const afterUnit = /^\s*(?:[-–]\s*)?([\p{L}]+)/u.exec(after)?.[1] ?? '';
  if (AGE_UNITS.has(afterUnit)) return AGE_UNITS.get(afterUnit);

  const before = String(item?.textContextBefore ?? '').normalize('NFKC').toLocaleLowerCase('en');
  if (/(?:^|[^\p{L}])age(?:d)?\s*(?:[:=]\s*)?$/u.test(before)) return 'age_year';
  return null;
}

function parseDate({ item, segment, text, profileId, isAgeBirthdate }) {
  const tokens = tokenize(text);
  const categories = [];
  const semantic = tokens.map((token, index) => ({ token, index }))
    .filter(({ token }) => token.kind !== 'formatting');
  for (let position = 0; position < semantic.length; position += 1) {
    const { token, index } = semantic[position];
    const next = semantic[position + 1];
    if (token.kind === 'number' && next && AGE_UNITS.has(next.token.normalized)) {
      categories[index] = AGE_UNITS.get(next.token.normalized);
      categories[next.index] = 'age_type';
    } else if (
      isAgeBirthdate &&
      AGE_UNITS.has(token.normalized) &&
      next?.token.kind === 'number'
    ) {
      categories[index] = 'age_type';
      categories[next.index] = AGE_UNITS.get(token.normalized);
    } else if (AGE_UNITS.has(token.normalized)) categories[index] = 'age_type';
    else if (MONTHS.has(token.normalized.replace(/\.$/u, ''))) categories[index] = 'month';
    else if (WEEKDAYS.has(token.normalized.replace(/\.$/u, ''))) categories[index] = 'weekday';
    else if (SEASONS.has(token.normalized)) categories[index] = 'season';
  }
  for (let position = 0; position + 1 < tokens.length; position += 1) {
    const numberToken = tokens[position];
    const suffixToken = tokens[position + 1];
    if (
      numberToken.kind === 'number' &&
      suffixToken.kind === 'word' &&
      numberToken.end === suffixToken.begin &&
      Number(numberToken.raw) >= 1 &&
      Number(numberToken.raw) <= 31 &&
      suffixToken.normalized === expectedOrdinalSuffix(numberToken.raw)
    ) {
      categories[position] = 'day';
      categories[position + 1] = 'formatting';
    }
  }
  const numbers = semantic.filter(({ token }) => token.kind === 'number');
  if (/^\s*\d{4}-\d{2}-\d{2}\s*$/u.test(text) && numbers.length === 3) {
    categories[numbers[0].index] = 'year';
    categories[numbers[1].index] = 'month';
    categories[numbers[2].index] = 'day';
  } else if (numbers.length >= 3) {
    const [first, second, third] = numbers;
    if (third.token.raw.length >= 2) {
      categories[first.index] = profileId === 'en-GB' ? 'day' : 'month';
      categories[second.index] = profileId === 'en-GB' ? 'month' : 'day';
      categories[third.index] = 'year';
    }
  }
  for (let position = 0; position < semantic.length; position += 1) {
    const { token, index } = semantic[position];
    if (categories[index] || token.kind !== 'number') continue;
    const previous = semantic[position - 1]?.token;
    const next = semantic[position + 1]?.token;
    if (token.raw.length === 4) categories[index] = 'year';
    else if (next && MONTHS.has(next.normalized.replace(/\.$/u, ''))) categories[index] = 'day';
    else if (previous && MONTHS.has(previous.normalized.replace(/\.$/u, ''))) categories[index] = 'day';
  }
  if (
    isAgeBirthdate &&
    semantic.length === 1 &&
    semantic[0].token.kind === 'number' &&
    semantic[0].token.raw.length < 4 &&
    !categories[semantic[0].index]
  ) {
    const contextualCategory = numericAgeCategoryFromContext(item);
    if (contextualCategory) categories[semantic[0].index] = contextualCategory;
  }
  return absoluteSegments(segment, tokens, categories);
}

function createParsers(profileId, grouped) {
  const values = (category) => (grouped.get(category) ?? []).map((record) => record.value);
  const firstNames = new Set(values('first_names').map(normalize));
  const familyNames = new Set(values('family_names').map(normalize));
  const particles = new Set(values('surname_particles').flatMap((value) =>
    tokenize(value).filter((token) => token.kind !== 'formatting').map((token) => token.normalized)));
  const suffixes = new Set(values('name_suffixes').map(normalize));
  const credentials = new Set(values('credentials').map(normalize));
  const prefixTrie = phraseTrie(values('prefixes'));
  const streetTrie = phraseTrie(values('streets'));
  const localityRecords = grouped.get('localities') ?? [];
  // Synthetic non-healthcare organisation names are built from either the
  // general locality or postal-locality resources. Keep this broader lookup
  // isolated from address and healthcare parsing so postal-name collisions
  // cannot alter those categories.
  const organizationLocalityRecords = [
    ...(grouped.get('localities') ?? []),
    ...(grouped.get('postal_localities') ?? []),
  ];
  const localityTrie = phraseTrie(localityRecords.map((record) => record.value));
  const organizationLocalityTrie = phraseTrie(
    organizationLocalityRecords.map((record) => record.value),
  );
  const institutionTrie = phraseTrie([
    ...values('hospitals'), ...values('healthcare_institutions'), ...values('departments'),
  ]);
  const localityRegions = new Map();
  const localityProminence = new Map();
  const institutionRegions = new Map();
  const institutionLocationNames = new Map();
  function indexRegions(target, records) {
    for (const record of records) {
      const key = normalize(record.value);
      if (!key) continue;
      if (!target.has(key)) target.set(key, new Set());
      for (const region of record.regions ?? []) target.get(key).add(normalize(region));
    }
  }
  indexRegions(localityRegions, organizationLocalityRecords);
  for (const record of organizationLocalityRecords) {
    const key = normalize(record.value);
    const localType = normalize(record.attributes?.local_type);
    const officialNames = [record.attributes?.official_name]
      .flat().filter(Boolean).map(normalize);
    let prominence = 0;
    if (localType === 'city') prominence = 30;
    else if (localType === 'town') prominence = 25;
    else if (localType === 'village') prominence = 10;
    else if (localType) prominence = 5;
    if (officialNames.some((name) => /\bcity$/u.test(name))) prominence = Math.max(prominence, 30);
    if (officialNames.some((name) => /\btown$/u.test(name))) prominence = Math.max(prominence, 25);
    if (officialNames.some((name) => /\b(?:borough|village)$/u.test(name))) {
      prominence = Math.max(prominence, 15);
    }
    if (officialNames.some((name) => /\bcdp$/u.test(name))) prominence = Math.max(prominence, 10);
    localityProminence.set(key, Math.max(localityProminence.get(key) ?? 0, prominence));
  }
  indexRegions(institutionRegions, [
    ...(grouped.get('hospitals') ?? []),
    ...(grouped.get('healthcare_institutions') ?? []),
  ]);
  for (const record of [
    ...(grouped.get('hospitals') ?? []),
    ...(grouped.get('healthcare_institutions') ?? []),
  ]) {
    const key = normalize(record.value);
    if (!key) continue;
    if (!institutionLocationNames.has(key)) institutionLocationNames.set(key, new Set());
    for (const value of [record.attributes?.city, record.attributes?.county]) {
      const locationName = normalize(value);
      if (locationName) institutionLocationNames.get(key).add(locationName);
    }
  }

  function inferHealthcareMunicipalityRange({ item, segment, text }) {
    const contextText = String(item?.reviewText ?? text);
    const contextBegin = Number.isInteger(item?.reviewBegin)
      ? item.reviewBegin : segment.begin;
    const facilityRegions = institutionRegions.get(normalize(contextText));
    // Only generalize when the complete surface is backed by a healthcare
    // institution record. This prevents arbitrary name/locality collisions.
    if (!facilityRegions?.size) return null;

    const contextTokens = tokenize(contextText);
    const semantics = contextTokens.map((token, index) => ({ token, index }))
      .filter(({ token }) => token.kind !== 'formatting');
    const candidates = [];
    const facilityLocationNames = institutionLocationNames.get(normalize(contextText));
    if (facilityLocationNames?.size) {
      const facilityLocationTrie = phraseTrie([...facilityLocationNames]);
      for (let position = 0; position < semantics.length; position += 1) {
        const phraseLength = longestPhraseAt(
          contextTokens,
          semantics[position].index,
          facilityLocationTrie,
        );
        if (!phraseLength) continue;
        const phraseTokens = semantics.slice(position, position + phraseLength);
        candidates.push({
          begin: contextBegin + phraseTokens[0].token.begin,
          end: contextBegin + phraseTokens[phraseTokens.length - 1].token.end,
          // Facility-source city/county metadata is direct evidence and must
          // outrank a coincidental name or locality gazetteer match.
          score: 1_000 + phraseLength,
        });
        position += phraseLength - 1;
      }
    }
    for (let position = 0; position < semantics.length; position += 1) {
      const phraseLength = longestPhraseAt(
        contextTokens,
        semantics[position].index,
        localityTrie,
      );
      if (!phraseLength) continue;
      const phraseTokens = semantics.slice(position, position + phraseLength);
      const normalizedPhrase = phraseTokens.map(({ token }) => token.normalized).join(' ');
      const regions = localityRegions.get(normalizedPhrase);
      position += phraseLength - 1;
      if (
        !regions?.size ||
        phraseTokens.some(({ token }) =>
          token.normalized === 'of' ||
          HEALTHCARE_LOCATION_GENERIC_TERMS.has(token.normalized)) ||
        ![...regions].some((region) => facilityRegions.has(region))
      ) continue;

      const startPosition = position - phraseLength + 1;
      const endPosition = position;
      const previous = semantics[startPosition - 1]?.token;
      if (
        HEALTHCARE_EPONYM_PREFIXES.has(previous?.normalized) &&
        firstNames.has(normalizedPhrase)
      ) continue;
      if (semantics[endPosition + 1]?.token.normalized === 'county') continue;

      const anchorsAfter = semantics
        .map(({ token }, anchorPosition) => ({ token, anchorPosition }))
        .filter(({ token, anchorPosition }) =>
          anchorPosition > endPosition &&
          HEALTHCARE_LOCATION_INTRODUCERS.has(token.normalized) &&
          anchorPosition - endPosition - 1 <= 3);
      const anchorsBefore = semantics
        .map(({ token }, anchorPosition) => ({ token, anchorPosition }))
        .filter(({ token, anchorPosition }) =>
          anchorPosition < startPosition &&
          HEALTHCARE_LOCATION_INTRODUCERS.has(token.normalized) &&
          startPosition - anchorPosition - 1 <= 3);
      const terminalAfterLocation = semantics.slice(endPosition + 1)
        .every(({ token }) => ORGANIZATION_LEGAL_SUFFIXES.has(token.normalized));
      const beforeFacility = anchorsAfter[0] ?? null;
      const afterFacility = terminalAfterLocation
        ? anchorsBefore[anchorsBefore.length - 1] ?? null
        : null;
      if (!beforeFacility && !afterFacility) continue;

      const anchorPosition = beforeFacility?.anchorPosition ?? afterFacility.anchorPosition;
      const distance = beforeFacility
        ? anchorPosition - endPosition - 1
        : startPosition - anchorPosition - 1;
      const nameAmbiguous = firstNames.has(normalizedPhrase) || familyNames.has(normalizedPhrase);
      candidates.push({
        begin: contextBegin + phraseTokens[0].token.begin,
        end: contextBegin + phraseTokens[phraseTokens.length - 1].token.end,
        score: (phraseLength > 1 ? 40 : 0) + (nameAmbiguous ? 0 : 20) +
          (localityProminence.get(normalizedPhrase) ?? 0) - distance,
      });
    }
    candidates.sort((left, right) => right.score - left.score || left.begin - right.begin);
    return candidates[0] ?? null;
  }

  function inferOtherOrganizationMunicipalityRange({ item, segment, text }) {
    const contextText = String(item?.reviewText ?? text);
    const contextBegin = Number.isInteger(item?.reviewBegin)
      ? item.reviewBegin : segment.begin;
    const contextTokens = tokenize(contextText);
    const semantics = contextTokens.map((token, index) => ({ token, index }))
      .filter(({ token }) => token.kind !== 'formatting');
    if (semantics.length < 2) return null;

    const startPositions = semantics[0].token.normalized === 'the' ? [0, 1] : [0];
    const candidates = [];
    for (const startPosition of startPositions) {
      const phraseLength = longestPhraseAt(
        contextTokens,
        semantics[startPosition].index,
        organizationLocalityTrie,
      );
      if (!phraseLength) continue;
      const phraseTokens = semantics.slice(startPosition, startPosition + phraseLength);
      const normalizedPhrase = phraseTokens.map(({ token }) => token.normalized).join(' ');
      if (!localityRegions.has(normalizedPhrase)) continue;
      const endPosition = startPosition + phraseLength - 1;
      const anchor = semantics
        .map(({ token }, position) => ({ token, position }))
        .find(({ token, position }) =>
          position > endPosition &&
          position - endPosition - 1 <= 3 &&
          OTHER_ORGANIZATION_TYPE_TERMS.has(token.normalized));
      if (!anchor) continue;
      candidates.push({
        begin: contextBegin + phraseTokens[0].token.begin,
        end: contextBegin + phraseTokens[phraseTokens.length - 1].token.end,
        score: phraseLength * 100 + (localityProminence.get(normalizedPhrase) ?? 0),
      });
    }
    candidates.sort((left, right) => right.score - left.score || left.begin - right.begin);
    return candidates[0] ?? null;
  }

  function parseName({ item, segment, text }) {
    const tokens = tokenize(text);
    const categories = [];
    const semantics = tokens.map((token, index) => ({ token, index }))
      .filter(({ token }) => token.kind !== 'formatting');
    for (let position = 0; position < semantics.length; position += 1) {
      const { token, index } = semantics[position];
      let assignedGiven = false;
      if (position === 0 && longestPhraseAt(tokens, index, prefixTrie)) categories[index] = 'title';
      else if (firstNames.has(token.normalized)) {
        categories[index] = 'given';
        assignedGiven = true;
      }
      if (particles.has(token.normalized) || (familyNames.has(token.normalized) && !assignedGiven)) categories[index] = 'family';
      if (suffixes.has(token.normalized)) categories[index] = 'family';
      if (credentials.has(token.normalized)) categories[index] = 'title';
      const metaGiven = normalize(item?.metadata?.patientGivenName);
      const metaFamily = normalize(item?.metadata?.patientLastName);
      if (token.normalized === metaGiven) categories[index] = 'given';
      if (token.normalized === metaFamily) categories[index] = 'family';
      // Initials are a more specific surface form than a lookup or metadata
      // match and must survive the final-token surname fallback below.
      if (Array.from(token.raw.replace(/\.$/u, '')).length === 1) categories[index] = 'initials';
    }
    const nameCore = semantics.filter(({ index }) => categories[index] !== 'title');
    if (nameCore.length >= 2) {
      const finalCorePosition = semantics.indexOf(nameCore[nameCore.length - 1]);
      const finalCoreIndex = nameCore[nameCore.length - 1].index;
      if (categories[finalCoreIndex] !== 'initials') {
        categories[finalCoreIndex] = 'family';
      }
      for (let position = finalCorePosition - 1; position >= 0; position -= 1) {
        const { token, index } = semantics[position];
        if (!particles.has(token.normalized)) break;
        categories[index] = 'family';
      }
    }
    const unclassifiedCore = nameCore.filter(({ index }) => !categories[index]);
    for (const { index } of unclassifiedCore) {
      categories[index] = 'given';
    }
    return absoluteSegments(segment, tokens, categories);
  }

  function parseAddressOrOrganization({ item, segment, text, seedGroup }) {
    const tokens = tokenize(text);
    const categories = [];
    if (seedGroup === 'Organization') {
      const isHealthcare = item?.gold?.subtype === 'Healthcare';
      const isOtherOrganization = item?.gold?.subtype === 'Other';
      if (isHealthcare) applyPhrase(tokens, categories, institutionTrie, 'institution');
      const fallbackCategory = isHealthcare ? 'institution' : 'company';
      const municipalityIndexes = new Set();
      if (isHealthcare) {
        const inferredMunicipality = inferHealthcareMunicipalityRange({ item, segment, text });
        if (inferredMunicipality) {
          for (let index = 0; index < tokens.length; index += 1) {
            const absoluteBegin = segment.begin + tokens[index].begin;
            const absoluteEnd = segment.begin + tokens[index].end;
            if (
              tokens[index].kind !== 'formatting' &&
              absoluteBegin < inferredMunicipality.end &&
              absoluteEnd > inferredMunicipality.begin
            ) municipalityIndexes.add(index);
          }
        }
        const localityCategories = [];
        applyPhrase(tokens, localityCategories, localityTrie, 'municipality');
        const semantics = tokens.map((token, index) => ({ token, index }))
          .filter(({ token }) => token.kind !== 'formatting');
        const externalContextIntroducesLocation = (() => {
          const reviewText = String(item?.reviewText ?? '');
          const reviewBegin = Number(item?.reviewBegin ?? 0);
          if (!reviewText || !Number.isInteger(segment?.begin)) return false;
          const localBegin = Math.max(0, segment.begin - reviewBegin);
          const before = Array.from(reviewText).slice(0, localBegin).join('');
          const match = /([\p{L}]+)\s+of\s*$/iu.exec(before);
          return HEALTHCARE_LOCATION_INTRODUCERS.has(normalize(match?.[1]));
        })();
        let promoteLocalityPhrase = false;
        for (let position = 0; position < semantics.length; position += 1) {
          const { index } = semantics[position];
          if (localityCategories[index] !== 'municipality') {
            promoteLocalityPhrase = false;
            continue;
          }
          if (!promoteLocalityPhrase) {
            const previous = semantics[position - 1]?.token;
            const introducer = semantics[position - 2]?.token;
            const internalContextIntroducesLocation =
              previous?.normalized === 'of' &&
              HEALTHCARE_LOCATION_INTRODUCERS.has(introducer?.normalized);
            promoteLocalityPhrase = internalContextIntroducesLocation ||
              (position === 0 && externalContextIntroducesLocation);
          }
          if (promoteLocalityPhrase) municipalityIndexes.add(index);
        }
      } else if (isOtherOrganization) {
        const inferredMunicipality = inferOtherOrganizationMunicipalityRange({
          item, segment, text,
        });
        if (inferredMunicipality) {
          for (let index = 0; index < tokens.length; index += 1) {
            const absoluteBegin = segment.begin + tokens[index].begin;
            const absoluteEnd = segment.begin + tokens[index].end;
            if (
              tokens[index].kind !== 'formatting' &&
              absoluteBegin < inferredMunicipality.end &&
              absoluteEnd > inferredMunicipality.begin
            ) municipalityIndexes.add(index);
          }
        }
      }
      for (let index = 0; index < tokens.length; index += 1) {
        if (tokens[index].kind === 'formatting') continue;
        // Table S4 defines medical_info as non-identifying clinical content
        // embedded in a broader identifying span. Generic facility/type words
        // fit that role, while the proper name and branded service wording
        // remain identifying institution content. Keep this deliberately
        // narrow: identifying service words in phrases such as "Care of the
        // Elderly" and "Prescribing" retain the institution fallback, while
        // the non-identifying connector "of" is handled separately below.
        if (isHealthcare && HEALTHCARE_MEDICAL_INFO_TERMS.has(tokens[index].normalized)) {
          categories[index] = 'medical_info';
        } else if (municipalityIndexes.has(index)) {
          categories[index] = 'municipality';
        } else if (isHealthcare && tokens[index].normalized === 'of') {
          categories[index] = 'additional_info';
        } else if (!categories[index]) categories[index] = fallbackCategory;
      }
    } else {
      const sourceSlot = String(
        item?.gold?.sourceSlot ?? item?.gold?.source_slot ?? '',
      ).trim();
      if (/(?:^|\.)locality$/iu.test(sourceSlot)) {
        // Generator provenance is decisive for isolated locality surfaces:
        // names such as Baker and Washington also occur in street resources.
        return absoluteSegments(segment, tokens, [], 'municipality');
      }
      applyPhrase(tokens, categories, streetTrie, 'street');
      applyPhrase(tokens, categories, localityTrie, 'municipality');
      const compact = String(text);
      const zipPattern = profileId === 'en-GB'
        ? /\b(?:GIR\s?0AA|[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})\b/iu
        : /\b\d{5}(?:-\d{4})?\b/u;
      const zipMatch = zipPattern.exec(compact);
      if (zipMatch) {
        for (let index = 0; index < tokens.length; index += 1) {
          const token = tokens[index];
          if (token.kind !== 'formatting' && token.begin < zipMatch.index + zipMatch[0].length && token.end > zipMatch.index) {
            categories[index] = 'postal_code';
          }
        }
      }
      const semantics = tokens.map((token, index) => ({ token, index }))
        .filter(({ token }) => token.kind !== 'formatting');
      const leading = semantics[0];
      if (
        leading?.token.kind === 'number' &&
        !['bus_number', 'postal_office', 'postal_code'].includes(categories[leading.index])
      ) {
        // Street resources can contain a complete delivery line, including its
        // primary number. At the start of an address this structural role is
        // more reliable than a phrase lookup.
        categories[leading.index] = 'house_number';
      }
      for (let position = 0; position < semantics.length; position += 1) {
        const { token, index } = semantics[position];
        const normalized = token.normalized.replace(/\.$/u, '');
        const next = semantics[position + 1];
        if (STREET_TERMS.has(normalized) || (profileId === 'en-US' && DIRECTIONALS.has(normalized))) {
          categories[index] ??= 'street';
        }
        const unitTerms = profileId === 'en-GB' ? GB_UNIT_TERMS : US_UNIT_TERMS;
        if (unitTerms.has(normalized)) {
          categories[index] = 'bus_number';
          // A state abbreviation such as "FL" is also a common abbreviation
          // for "floor". Never let that ambiguity overwrite a ZIP code that
          // was already identified from the full address surface.
          if (next && next.token.kind === 'number') categories[next.index] ??= 'bus_number';
        }
        if (normalized === 'po' && next?.token.normalized === 'box') {
          categories[index] = 'postal_office';
          categories[next.index] = 'postal_office';
          const boxNumber = semantics[position + 2];
          if (boxNumber?.token.kind === 'number') categories[boxNumber.index] = 'postal_office';
        }
        if (profileId === 'en-US' && ['rr', 'rural', 'route', 'hc', 'box'].includes(normalized)) {
          categories[index] ??= 'postal_office';
          if (next?.token.kind === 'number') categories[next.index] ??= 'postal_office';
        }
        if (
          profileId === 'en-US' &&
          (US_STATE_CODES.has(normalized) || US_TERRITORY_CODES.has(normalized))
        ) {
          const previous = semantics[position - 1];
          const followedByPostalCode = Boolean(next && categories[next.index] === 'postal_code');
          const terminalAfterLocality =
            position === semantics.length - 1 &&
            (
              categories[previous?.index] === 'municipality' ||
              text.slice(0, token.begin).includes(',')
            );
          // State abbreviations are highly ambiguous inside street names:
          // AK Rte, Co Rd, and the directional NE are all real examples. Only
          // promote one to region when its position identifies the locality
          // tail; otherwise retain a street lookup/directional classification
          // or let the normal street fallback handle it.
          if (followedByPostalCode || terminalAfterLocality) categories[index] = 'region';
        }
      }
      const commaOffsets = Array.from(text.matchAll(/,/gu), (match) => match.index);
      if (commaOffsets.length >= 2) {
        const localityBegin = commaOffsets.at(-2) + 1;
        const localityEnd = commaOffsets.at(-1);
        for (let index = 0; index < tokens.length; index += 1) {
          const token = tokens[index];
          if (
            token.kind !== 'formatting' &&
            token.begin >= localityBegin &&
            token.end <= localityEnd
          ) {
            // In both English profiles the penultimate comma-delimited field
            // is the locality. This also covers multiword and bilingual names
            // missing from a finite locality lookup.
            categories[index] = 'municipality';
          }
        }
      } else if (commaOffsets.length === 1) {
        const commaOffset = commaOffsets[0];
        const unitTerms = profileId === 'en-GB' ? GB_UNIT_TERMS : US_UNIT_TERMS;
        const prefixHasDeliveryEvidence = tokens.some((token, index) =>
          token.end <= commaOffset &&
          ['house_number', 'street', 'postal_office'].includes(categories[index]));
        const suffix = tokens.map((token, index) => ({ token, index }))
          .filter(({ token }) => token.kind !== 'formatting' && token.begin > commaOffset);
        const suffixHasDeliveryEvidence = suffix.some(({ token, index }) => {
          const normalized = token.normalized.replace(/\.$/u, '');
          return token.kind === 'number' ||
            STREET_TERMS.has(normalized) ||
            (unitTerms.has(normalized) && categories[index] !== 'region');
        });
        if (prefixHasDeliveryEvidence && suffix.length > 0 && !suffixHasDeliveryEvidence) {
          for (const { index } of suffix) {
            if (!['region', 'postal_code'].includes(categories[index])) {
              categories[index] = 'municipality';
            }
          }
        }
      }
      for (let index = 0; index < tokens.length; index += 1) {
        const token = tokens[index];
        if (categories[index] || token.kind !== 'number') continue;
        categories[index] = 'house_number';
      }
      if (profileId === 'en-US') {
        for (let index = 0; index < tokens.length; index += 1) {
          if (['urb', 'urbanización', 'urbanization'].includes(tokens[index].normalized)) categories[index] = 'region';
        }
      }
      const hasStreetEvidence = categories.includes('street') || categories.includes('house_number');
      for (let index = 0; index < tokens.length; index += 1) {
        if (tokens[index].kind !== 'formatting' && !categories[index]) {
          categories[index] = hasStreetEvidence ? 'street' : 'municipality';
        }
      }
    }
    return absoluteSegments(segment, tokens, categories);
  }

  function parseContact({ item, segment, text }) {
    const tokens = tokenize(text);
    const compact = String(text).trim();
    if (compact.includes('@')) {
      const categories = [];
      const atOffset = Array.from(String(text)).indexOf('@');
      const domainStart = tokens.findIndex((token) => token.begin > atOffset);
      if (domainStart >= 0) {
        const domainCategories = [];
        applyPhrase(tokens.slice(domainStart), domainCategories, institutionTrie, 'institution');
        for (let index = 0; index < domainCategories.length; index += 1) {
          if (domainCategories[index]) categories[domainStart + index] = domainCategories[index];
        }
      }
      for (let index = 0; index < tokens.length; index += 1) {
        const token = tokens[index];
        if (token.kind === 'formatting' || categories[index]) continue;
        if (token.end <= atOffset) {
          if (firstNames.has(token.normalized)) categories[index] = 'given';
          else if (familyNames.has(token.normalized)) categories[index] = 'family';
          else if (Array.from(token.raw).length === 1) categories[index] = 'initials';
          else categories[index] = 'additional_info';
        } else {
          // Name lexicons must never leak into the domain: common TLDs and
          // providers such as net, att, and live can also be surnames/names.
          categories[index] = 'additional_info';
        }
      }
      const localWords = tokens.map((token, index) => ({ token, index }))
        .filter(({ token }) => token.kind === 'word' && token.end <= atOffset);
      const localHasNameSeparator = tokens.some((token) =>
        token.kind === 'formatting' &&
        token.end <= atOffset &&
        /[._-]/u.test(token.raw));
      if (localHasNameSeparator && localWords.length >= 2) {
        // The English generator emits given.familyNN. This surface structure
        // is decisive when the family name is also a common given name.
        categories[localWords.at(-1).index] = 'family';
      }
      const metaGiven = normalize(item?.metadata?.patientGivenName);
      const metaFamily = normalize(item?.metadata?.patientLastName);
      for (const { token, index } of localWords) {
        if (token.normalized === metaGiven) categories[index] = 'given';
        if (token.normalized === metaFamily) categories[index] = 'family';
      }
      return absoluteSegments(segment, tokens, categories);
    }
    let category = 'additional_info';
    if (/^[+\d\s()./-]+$/u.test(compact)) {
      category = compact.replace(/\D/gu, '').length <= 5 ? 'internal_phone' : 'public_phone';
    }
    return absoluteSegments(segment, tokens, []).map((part) => ({
      ...part, category: part.category === 'formatting' ? 'formatting' : category,
    }));
  }

  function parseIdentifier({ item, segment, text }) {
    const compact = String(text).replace(/[\s-]/gu, '').toUpperCase();
    const sourceSlot = String(item?.gold?.sourceSlot ?? item?.gold?.source_slot ?? '').trim();
    let category;
    // Synthetic MRNs, report IDs, and professional IDs intentionally share
    // numeric surface shapes. Prefer their audited generator role when present.
    if (['caregiver.professional_id', 'patient.national_id'].includes(sourceSlot)) {
      category = 'public_id';
    } else if (['patient.mrn', 'patient.report_id'].includes(sourceSlot)) {
      category = 'internal_id';
    } else {
      category = 'internal_id';
      if (profileId === 'en-GB') {
        if (/^\d{10}$/u.test(compact)) category = 'public_id';
        if (/^[A-Z]{2}\d{6}[A-D]$/u.test(compact)) category = 'public_id';
        if (/^GMC/u.test(compact)) category = 'public_id';
      } else {
        if (/^\d{9}$/u.test(compact)) category = 'public_id';
        if (/^\d{10}$/u.test(compact)) category = 'public_id';
        if (/^[1-9][A-HJ-KM-NP-RT-Y][0-9A-HJ-KM-NP-RT-Y]\d[A-HJ-KM-NP-RT-Y][0-9A-HJ-KM-NP-RT-Y]\d[A-HJ-KM-NP-RT-Y]{2}\d{2}$/u.test(compact)) category = 'public_id';
      }
    }
    return absoluteSegments(segment, tokenize(text), []).map((part) => ({
      ...part, category: part.category === 'formatting' ? 'formatting' : category,
    }));
  }
  return { parseName, parseAddressOrOrganization, parseContact, parseIdentifier };
}

export function createSubannotationProfile(profileId) {
  if (!['en-GB', 'en-US'].includes(profileId)) throw new Error(`Unsupported English profile: ${profileId}`);
  const { spec, lookupPath, records, grouped } = loadProfile(profileId);
  const parsers = createParsers(profileId, grouped);
  const rules = Object.freeze([
    Object.freeze({
      ruleId: `split_${profileId.toLowerCase().replace('-', '_')}_date_variants`,
      transformSegment({ item, segment, text }) {
        return [spec.seedCategories.Date, spec.seedCategories.Age_Birthdate].includes(segment.category)
          ? parseDate({
              item,
              segment,
              text,
              profileId,
              isAgeBirthdate: segment.category === spec.seedCategories.Age_Birthdate,
            })
          : null;
      },
    }),
    Object.freeze({
      ruleId: 'classify_profession_content',
      transformSegment({ item, segment, text }) {
        const isProfessionSeed = segment.category === spec.seedCategories.Profession;
        const isProfessionSpan = ['Profession'].includes(
          String(item?.gold?.category ?? item?.gold?.label ?? '').trim(),
        );
        if (!isProfessionSeed && !isProfessionSpan) return null;
        if (
          isProfessionSpan &&
          ['formatting', 'profession', 'hobby', 'employment_state'].includes(segment.category)
        ) {
          return null;
        }
        return absoluteSegments(segment, tokenize(text), [], 'profession');
      },
    }),
    Object.freeze({
      ruleId: 'split_name_variants_from_profile',
      transformSegment({ item, segment, text }) {
        return segment.category === spec.seedCategories.Name
          ? parsers.parseName({ item, segment, text }) : null;
      },
    }),
    Object.freeze({
      ruleId: 'split_address_organization_variants_from_profile',
      transformSegment({ item, segment, text }) {
        const sourceSlot = String(
          item?.gold?.sourceSlot ?? item?.gold?.source_slot ?? '',
        ).trim();
      const isLocalitySpan =
          String(item?.gold?.category ?? item?.gold?.label ?? '').startsWith('Address_Location') &&
          /(?:^|\.)locality$/iu.test(sourceSlot);
        const isHealthcareOrganizationSpan =
          String(item?.gold?.category ?? item?.gold?.label ?? '').startsWith('Organization') &&
          String(item?.gold?.subtype ?? '').trim() === 'Healthcare';
        const isOtherOrganizationSpan =
          String(item?.gold?.category ?? item?.gold?.label ?? '').startsWith('Organization') &&
          String(item?.gold?.subtype ?? '').trim() === 'Other';
        if (segment.category === spec.seedCategories.Address_Location || isLocalitySpan) {
          return parsers.parseAddressOrOrganization({
            item, segment, text, seedGroup: 'Address_Location',
          });
        }
        if (
          segment.category === spec.seedCategories.Organization ||
          (isHealthcareOrganizationSpan && segment.category === 'institution') ||
          (
            isOtherOrganizationSpan &&
            ['company', 'institution'].includes(segment.category)
          ) ||
          (
            isHealthcareOrganizationSpan &&
            segment.category === 'medical_info' &&
            ['doctor', 'doctors', 'medical'].includes(normalize(text))
          )
        ) {
          return parsers.parseAddressOrOrganization({
            item, segment, text, seedGroup: 'Organization',
          });
        }
        return null;
      },
    }),
    Object.freeze({
      ruleId: 'split_contact_variants',
      transformSegment({ item, segment, text }) {
        return segment.category === spec.seedCategories.Contactdetails
          ? parsers.parseContact({ item, segment, text }) : null;
      },
    }),
    Object.freeze({
      ruleId: 'classify_identifier_content',
      transformSegment({ item, segment, text }) {
        return segment.category === spec.seedCategories.ID
          ? parsers.parseIdentifier({ item, segment, text }) : null;
      },
    }),
  ]);
  const counts = {};
  for (const record of records) counts[record.category] = (counts[record.category] ?? 0) + 1;
  return Object.freeze({
    ...spec,
    rules,
    resourceManifest: Object.freeze({
      manifest_version: 'meddeid.language-resources.v2',
      package: 'meddeid-language-en', package_version: '0.2.0',
      profile_id: profileId,
      lookups_sha256: crypto.createHash('sha256').update(fs.readFileSync(lookupPath)).digest('hex'),
      counts: Object.freeze(counts),
    }),
    implementation: Object.freeze({
      package: '@meddeid/language-en', export: spec.javascript.export,
      sha256: crypto.createHash('sha256').update(fs.readFileSync(MODULE_PATH)).digest('hex'),
    }),
  });
}
