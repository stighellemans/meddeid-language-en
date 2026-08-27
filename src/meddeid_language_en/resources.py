"""Deterministic resource fetch, build, audit, and diff workflow.

Raw downloads are cached outside the package. Only normalized records whose
source lock permits redistribution are written to packaged runtime assets.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import struct
import unicodedata
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from importlib.resources import files
from pathlib import Path
from typing import Any, Iterable

PROFILE_IDS = ("en-GB", "en-US")
REQUIRED_CATEGORIES = (
    "first_names",
    "family_names",
    "prefixes",
    "name_suffixes",
    "surname_particles",
    "credentials",
    "streets",
    "localities",
    "postal_localities",
    "postal_code_localities",
    "hospitals",
    "healthcare_institutions",
    "other_organisations",
    "professions",
    "departments",
    "administrative_areas",
)
REQUIRED_REGIONS = {
    "en-GB": {"England", "Scotland", "Wales", "Northern Ireland"},
    "en-US": {
        "District of Columbia",
        "Puerto Rico",
        "U.S. Virgin Islands",
        "Guam",
        "American Samoa",
        "Northern Mariana Islands",
    },
}
US_REGION_BY_ABBREVIATION = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico",
    "VI": "U.S. Virgin Islands", "GU": "Guam", "AS": "American Samoa",
    "MP": "Northern Mariana Islands",
}
US_REGION_BY_FIPS = {
    "01": "Alabama", "02": "Alaska", "04": "Arizona", "05": "Arkansas",
    "06": "California", "08": "Colorado", "09": "Connecticut", "10": "Delaware",
    "11": "District of Columbia", "12": "Florida", "13": "Georgia", "15": "Hawaii",
    "16": "Idaho", "17": "Illinois", "18": "Indiana", "19": "Iowa", "20": "Kansas",
    "21": "Kentucky", "22": "Louisiana", "23": "Maine", "24": "Maryland",
    "25": "Massachusetts", "26": "Michigan", "27": "Minnesota", "28": "Mississippi",
    "29": "Missouri", "30": "Montana", "31": "Nebraska", "32": "Nevada",
    "33": "New Hampshire", "34": "New Jersey", "35": "New Mexico", "36": "New York",
    "37": "North Carolina", "38": "North Dakota", "39": "Ohio", "40": "Oklahoma",
    "41": "Oregon", "42": "Pennsylvania", "44": "Rhode Island",
    "45": "South Carolina", "46": "South Dakota", "47": "Tennessee", "48": "Texas",
    "49": "Utah", "50": "Vermont", "51": "Virginia", "53": "Washington",
    "54": "West Virginia", "55": "Wisconsin", "56": "Wyoming", "60": "American Samoa",
    "66": "Guam", "69": "Northern Mariana Islands", "72": "Puerto Rico",
    "78": "U.S. Virgin Islands",
}
SOURCE_REQUIRED_FIELDS = {
    "source_id",
    "source_sha256",
    "source_hash_kind",
    "publisher",
    "dataset",
    "release",
    "url",
    "retrieved_at",
    "license",
    "attribution",
    "geographic_scope",
    "output_categories",
    "fetch",
}


def normalize_profile_id(profile_id: str) -> str:
    normalized = profile_id.strip().replace("_", "-").lower()
    for candidate in PROFILE_IDS:
        if normalized == candidate.lower():
            return candidate
    available = ", ".join(PROFILE_IDS)
    raise ValueError(
        f"unsupported English language profile {profile_id!r}; available: {available}"
    )


def normalize_value(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value))
    return " ".join(value.split()).casefold()


def _project_root() -> Path | None:
    candidate = Path(__file__).resolve().parents[2]
    return candidate if (candidate / "sources").is_dir() else None


def _source_dir(profile_id: str) -> Path:
    root = _project_root()
    if root is None:
        raise RuntimeError(
            "source fetch/build requires a source checkout; packaged installs support audit"
        )
    return root / "sources" / profile_id


def _runtime_dir(profile_id: str) -> Path:
    root = _project_root()
    if root is None:
        raise RuntimeError("packaged resources are read-only")
    return root / "src" / "meddeid_language_en" / "resources" / profile_id


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def source_lock(profile_id: str) -> dict[str, Any]:
    profile_id = normalize_profile_id(profile_id)
    root = _project_root()
    if root is not None:
        return _read_json(root / "sources" / profile_id / "sources.lock.json")
    resource = files("meddeid_language_en").joinpath(
        "resources", profile_id, "sources.lock.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


def _seed_records(profile_id: str) -> list[dict[str, Any]]:
    path = _source_dir(profile_id) / "seed_records.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _locked_file_set_sha256(files_spec: Iterable[dict[str, Any]]) -> str:
    logical = [
        {"cache_filename": item["cache_filename"], "sha256": item["sha256"]}
        for item in sorted(files_spec, key=lambda item: item["cache_filename"])
    ]
    return _sha256(
        json.dumps(logical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def _download(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "meddeid-language-en-resource-builder/0.1 (+https://github.com/stighellemans/meddeid-language-en)"
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def fetch(profile_id: str, cache_dir: Path) -> list[Path]:
    profile_id = normalize_profile_id(profile_id)
    cache_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for source in source_lock(profile_id)["sources"]:
        if not source.get("fetch"):
            continue
        for item in source.get("files", []):
            payload = _download(item["url"])
            actual = _sha256(payload)
            if actual != item["sha256"]:
                raise RuntimeError(
                    f"source hash changed for {item['cache_filename']}: "
                    f"expected {item['sha256']}, got {actual}"
                )
            destination = cache_dir / item["cache_filename"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
            written.append(destination)
    return written


def _dfe_records(cache_dir: Path) -> Iterable[dict[str, Any]]:
    specs = (
        ("dfe-forenames-2014.csv", "first_names", "Forename"),
        ("dfe-surnames-2014.csv", "family_names", "Surname"),
    )
    for filename, category, column in specs:
        path = cache_dir / filename
        if not path.exists():
            continue
        rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
        maximum = max(int(row["Count"]) for row in rows)
        for row in rows:
            yield {
                "category": category,
                "value": row[column],
                "weight": round(int(row["Count"]) / maximum, 8),
                "regions": ["England"],
                "source_ids": ["dfe-school-census-names"],
                "attributes": {"count": int(row["Count"]), "release": "Autumn 2014"},
            }


def _census_surname_records(cache_dir: Path) -> Iterable[dict[str, Any]]:
    path = cache_dir / "census-2010-surnames.zip"
    if not path.exists():
        return
    with zipfile.ZipFile(path) as archive:
        payload = archive.read("Names_2010Census.csv").decode("utf-8-sig")
    rows = csv.DictReader(io.StringIO(payload))
    for row in rows:
        if row["name"] == "ALL OTHER NAMES":
            continue
        yield {
            "category": "family_names",
            "value": row["name"].title(),
            "weight": round(float(row["prop100k"]) / 1000.0, 8),
            "regions": ["United States"],
            "source_ids": ["census-2010-surnames"],
            "attributes": {
                "rank": int(row["rank"]),
                "count": int(row["count"]),
                "per_100k": float(row["prop100k"]),
            },
        }


_XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    result = 0
    for character in letters.upper():
        result = result * 26 + ord(character) - 64
    return result - 1


def _xlsx_rows(path: Path, sheet_name: str) -> Iterable[list[Any]]:
    """Read values from an XLSX worksheet using only the standard library."""

    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            relation.attrib["Id"]: relation.attrib["Target"]
            for relation in relationships.findall(f"{_PKG_REL_NS}Relationship")
        }
        sheet_target: str | None = None
        for sheet in workbook.findall(f".//{_XML_NS}sheet"):
            if sheet.attrib.get("name") == sheet_name:
                sheet_target = targets[sheet.attrib[f"{_REL_NS}id"]]
                break
        if sheet_target is None:
            raise ValueError(f"worksheet {sheet_name!r} not found in {path.name}")
        if not sheet_target.startswith("xl/"):
            sheet_target = "xl/" + sheet_target.lstrip("/")
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [
                "".join(node.text or "" for node in item.findall(f".//{_XML_NS}t"))
                for item in root.findall(f"{_XML_NS}si")
            ]
        worksheet = archive.read(sheet_target)

    for _event, row in ET.iterparse(io.BytesIO(worksheet), events=("end",)):
        if row.tag != f"{_XML_NS}row":
            continue
        values: list[Any] = []
        for cell in row.findall(f"{_XML_NS}c"):
            index = _column_index(cell.attrib.get("r", "A1"))
            while len(values) <= index:
                values.append(None)
            data_type = cell.attrib.get("t")
            if data_type == "inlineStr":
                value: Any = "".join(
                    node.text or "" for node in cell.findall(f".//{_XML_NS}t")
                )
            else:
                node = cell.find(f"{_XML_NS}v")
                raw = node.text if node is not None else None
                if raw is None:
                    value = None
                elif data_type == "s":
                    value = shared[int(raw)]
                elif data_type in {"str", "e"}:
                    value = raw
                else:
                    try:
                        number = float(raw)
                        value = int(number) if number.is_integer() else number
                    except ValueError:
                        value = raw
            values[index] = value
        yield values
        row.clear()


def _name_record(
    value: str,
    *,
    count: int,
    maximum: int,
    regions: list[str],
    source_id: str,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    return {
        "category": "first_names",
        "value": value,
        "weight": round(count / max(maximum, 1), 8),
        "regions": regions,
        "source_ids": [source_id],
        "attributes": {"count": count, **attributes},
    }


def _ons_name_records(cache_dir: Path) -> Iterable[dict[str, Any]]:
    path = cache_dir / "ons-baby-names-1996-2025.xlsx"
    if not path.exists():
        return
    aggregates: dict[str, dict[str, Any]] = {}
    for sheet_name, sex in (("Table_1", "female"), ("Table_2", "male")):
        for row in list(_xlsx_rows(path, sheet_name))[5:]:
            if not row or not isinstance(row[0], str) or len(row) < 3:
                continue
            counts = [int(value) for value in row[2::2] if isinstance(value, (int, float))]
            if not counts:
                continue
            entry = aggregates.setdefault(
                normalize_value(row[0]),
                {"value": row[0], "count": 0, "sexes": set(), "years": 0},
            )
            entry["count"] += sum(counts)
            entry["years"] = max(entry["years"], len(counts))
            entry["sexes"].add(sex)
    maximum = max((item["count"] for item in aggregates.values()), default=1)
    for item in aggregates.values():
        yield _name_record(
            item["value"], count=item["count"], maximum=maximum,
            regions=["England", "Wales"], source_id="ons-baby-names-ew",
            attributes={
                "release_year": 2025, "sexes": sorted(item["sexes"]),
                "observed_year_columns": item["years"], "suppression_threshold": 3,
            },
        )


def _nrs_name_records(cache_dir: Path) -> Iterable[dict[str, Any]]:
    path = cache_dir / "nrs-baby-names-2025.xlsx"
    if not path.exists():
        return
    rows: list[tuple[str, int, str]] = []
    for sheet_name, sex in (("Boys", "male"), ("Girls", "female")):
        for row in list(_xlsx_rows(path, sheet_name))[4:]:
            if len(row) > 2 and isinstance(row[1], str) and isinstance(row[2], (int, float)):
                rows.append((row[1], int(row[2]), sex))
    maximum = max((count for _name, count, _sex in rows), default=1)
    for name, count, sex in rows:
        yield _name_record(
            name, count=count, maximum=maximum, regions=["Scotland"],
            source_id="nrs-baby-names",
            attributes={
                "release_year": 2025, "sexes": [sex], "suppression_threshold": 3,
            },
        )


def _nisra_name_records(cache_dir: Path) -> Iterable[dict[str, Any]]:
    path = cache_dir / "nisra-baby-names-1997-2025.xlsx"
    if not path.exists():
        return
    aggregates: dict[str, dict[str, Any]] = {}
    for sheet_name, sex in (("Table 1", "male"), ("Table 2", "female")):
        for row in list(_xlsx_rows(path, sheet_name))[6:]:
            for offset in range(0, len(row), 3):
                if offset + 1 >= len(row):
                    continue
                name, count = row[offset], row[offset + 1]
                if not isinstance(name, str) or not isinstance(count, (int, float)):
                    continue
                entry = aggregates.setdefault(
                    normalize_value(name),
                    {"value": name, "count": 0, "sexes": set(), "observations": 0},
                )
                entry["count"] += int(count)
                entry["observations"] += 1
                entry["sexes"].add(sex)
    maximum = max((item["count"] for item in aggregates.values()), default=1)
    for item in aggregates.values():
        yield _name_record(
            item["value"], count=item["count"], maximum=maximum,
            regions=["Northern Ireland"], source_id="nisra-baby-names",
            attributes={
                "release_year": 2025, "sexes": sorted(item["sexes"]),
                "annual_observations": item["observations"], "suppression_threshold": 3,
            },
        )


def _stable_sample(records: dict[str, dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return [
        item[1]
        for item in sorted(
            records.items(), key=lambda item: (_sha256(item[0].encode("utf-8")), item[0])
        )[:limit]
    ]


def _codepoint_representatives(path: Path) -> dict[str, str]:
    representatives: dict[str, str] = {}
    with zipfile.ZipFile(path) as archive:
        for filename in sorted(
            name for name in archive.namelist() if name.startswith("Data/CSV/") and name.endswith(".csv")
        ):
            with archive.open(filename) as handle:
                for row in csv.reader(io.TextIOWrapper(handle, encoding="utf-8-sig")):
                    if not row:
                        continue
                    compact = str(row[0]).replace(" ", "").upper()
                    if len(compact) < 5:
                        continue
                    postcode = compact[:-3] + " " + compact[-3:]
                    district = compact[:-3].rstrip("0123456789") + compact[len(compact[:-3].rstrip("0123456789")):len(compact)-3]
                    district = compact[:-3]
                    previous = representatives.get(district)
                    if previous is None or postcode < previous:
                        representatives[district] = postcode
    return representatives


def _os_open_names_records(cache_dir: Path) -> Iterable[dict[str, Any]]:
    names_path = cache_dir / "os-open-names-2026-07.zip"
    postcodes_path = cache_dir / "code-point-open-2026-08.zip"
    if not names_path.exists():
        return
    representatives = _codepoint_representatives(postcodes_path) if postcodes_path.exists() else {}
    roads: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    general: dict[tuple[str, str], dict[str, Any]] = {}
    with zipfile.ZipFile(names_path) as archive:
        for filename in sorted(
            name for name in archive.namelist() if name.startswith("Data/") and name.endswith(".csv")
        ):
            with archive.open(filename) as handle:
                for row in csv.reader(io.TextIOWrapper(handle, encoding="utf-8-sig")):
                    if len(row) < 30:
                        continue
                    value, feature_type, local_type = row[2], row[6], row[7]
                    district, populated_place, region = row[16], row[18], row[29]
                    if not value or region not in {"England", "Scotland", "Wales"}:
                        continue
                    attributes = {
                        "feature_type": feature_type, "local_type": local_type,
                        "postcode_district": district or None,
                        "populated_place": populated_place or None,
                    }
                    base = {
                        "value": value, "regions": [region],
                        "source_ids": ["os-open-names"], "attributes": attributes,
                    }
                    if feature_type == "transportNetwork" and local_type == "Named Road":
                        roads[region].setdefault(normalize_value(value), {"category": "streets", **base})
                    if feature_type == "populatedPlace":
                        for category in ("localities", "postal_localities"):
                            general.setdefault((category, normalize_value(value)), {"category": category, **base})
                    if feature_type == "Other" and local_type in {"Hospital", "Medical Care Accommodation"}:
                        general.setdefault(
                            ("healthcare_institutions", normalize_value(value)),
                            {"category": "healthcare_institutions", **base},
                        )
                        if local_type == "Hospital":
                            general.setdefault(
                                ("hospitals", normalize_value(value)),
                                {"category": "hospitals", **base},
                            )
                    postcode = representatives.get(district)
                    if postcode and populated_place:
                        general.setdefault(
                            ("postal_code_localities", normalize_value(postcode)),
                            {
                                "category": "postal_code_localities", "value": postcode,
                                "regions": [region], "source_ids": ["codepoint-open", "os-open-names"],
                                "attributes": {"postcode_district": district, "locality": populated_place},
                            },
                        )
    for region in sorted(roads):
        yield from _stable_sample(roads[region], 50_000)
    yield from general.values()


def _osni_records(cache_dir: Path) -> Iterable[dict[str, Any]]:
    streets = cache_dir / "osni-streetnames-2015.csv"
    if streets.exists():
        for row in csv.DictReader(streets.read_text(encoding="utf-8-sig").splitlines()):
            value = row.get("STREETNAME", "").strip()
            if value:
                yield {
                    "category": "streets", "value": value, "regions": ["Northern Ireland"],
                    "source_ids": ["osni-open-gazetteer"],
                    "attributes": {"usrn": row.get("USRN"), "gazetteer": "streetnames"},
                }
    places = cache_dir / "osni-place-names-2015.csv"
    if places.exists():
        for row in csv.DictReader(places.read_text(encoding="utf-8-sig").splitlines()):
            value = row.get("PLACENAME", "").strip()
            if value:
                for category in ("localities", "postal_localities"):
                    yield {
                        "category": category, "value": value, "regions": ["Northern Ireland"],
                        "source_ids": ["osni-open-gazetteer"],
                        "attributes": {"gazetteer": "place names"},
                    }


def _nhs_ods_records(cache_dir: Path) -> Iterable[dict[str, Any]]:
    reports = {
        "etr": ("England", "trusts"), "ets": ("England", "sites"),
        "wlhb": ("Wales", "local health boards"), "wlhbsite": ("Wales", "sites"),
        "niorg": ("Northern Ireland", "organisations"),
    }
    hospital_pattern = re.compile(r"\b(hospital|infirmary|hospice|clinic|medical centre|health centre)\b", re.I)
    for report, (region, report_type) in reports.items():
        path = cache_dir / f"nhs-ods-{report}-2026-08-20.csv"
        if not path.exists():
            continue
        for row in csv.reader(path.read_text(encoding="utf-8-sig").splitlines()):
            if len(row) < 2 or not row[1].strip():
                continue
            base = {
                "value": row[1].strip(), "regions": [region], "source_ids": ["nhs-ods"],
                "attributes": {"ods_code": row[0].strip(), "report": report, "report_type": report_type},
            }
            yield {"category": "healthcare_institutions", **base}
            if hospital_pattern.search(row[1]):
                yield {"category": "hospitals", **base}


def _ons_soc_records(cache_dir: Path) -> Iterable[dict[str, Any]]:
    path = cache_dir / "ons-soc-2020-coding-index-2025-12-03.zip"
    if not path.exists():
        return
    with zipfile.ZipFile(path) as archive:
        filename = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
        text = archive.read(filename).decode("cp1252")
    for row in csv.DictReader(io.StringIO(text)):
        value = (row.get("INDEXOCC-natural_word_order") or "").strip()
        if value:
            yield {
                "category": "professions", "value": value, "regions": ["United Kingdom"],
                "source_ids": ["ons-soc-2020"],
                "attributes": {"soc_2020": row.get("SOC_2020"), "unit_group": row.get("SOC2020-UNIT_GROUP_TITLE")},
            }


def _ssa_records(cache_dir: Path) -> Iterable[dict[str, Any]]:
    aggregates: dict[str, dict[str, Any]] = {}

    def add(name: str, sex: str, count: int, region: str, release: str) -> None:
        key = normalize_value(name)
        item = aggregates.setdefault(
            key, {"value": name, "count": 0, "sexes": set(), "regions": set(), "statistics": defaultdict(int)},
        )
        item["count"] += count
        item["sexes"].add({"M": "male", "F": "female"}.get(sex, sex))
        item["regions"].add(region)
        item["statistics"][release] += count

    national = cache_dir / "ssa-national-2024.txt"
    if national.exists():
        for name, sex, count in csv.reader(national.read_text(encoding="utf-8").splitlines()):
            add(name, sex, int(count), "United States", "national_2024")
    state_zip = cache_dir / "ssa-state-through-2020.zip"
    if state_zip.exists():
        with zipfile.ZipFile(state_zip) as archive:
            for filename in sorted(name for name in archive.namelist() if name.upper().endswith(".TXT")):
                text = archive.read(filename).decode("utf-8")
                for abbreviation, sex, year, name, count in csv.reader(io.StringIO(text)):
                    if year == "2020" and abbreviation in US_REGION_BY_ABBREVIATION:
                        add(name, sex, int(count), US_REGION_BY_ABBREVIATION[abbreviation], "state_2020")
    for filename, release in (
        ("ssa-territory-pr-2024.txt", "territory_pr_2024"),
        ("ssa-territory-combined-2024.txt", "territories_2024"),
    ):
        path = cache_dir / filename
        if not path.exists():
            continue
        for abbreviation, sex, year, name, count in csv.reader(path.read_text(encoding="utf-8").splitlines()):
            if year != "2024":
                continue
            if abbreviation in US_REGION_BY_ABBREVIATION:
                add(
                    name, sex, int(count),
                    US_REGION_BY_ABBREVIATION[abbreviation], release,
                )
            elif abbreviation == "TR":
                # SSA's TR file aggregates the four smaller territories. Count
                # it once while retaining the complete publisher scope.
                add(name, sex, int(count), "American Samoa", release)
                aggregates[normalize_value(name)]["regions"].update(
                    {"Guam", "Northern Mariana Islands", "U.S. Virgin Islands"}
                )
    ranks = cache_dir / "ssa-national-ranks-2025.csv"
    if ranks.exists():
        for row in csv.DictReader(ranks.read_text(encoding="utf-8-sig").splitlines()):
            rank = int(row["Rank"])
            for column, sex in (("Girl Name", "female"), ("Boy Name", "male")):
                name = row[column].strip()
                key = normalize_value(name)
                item = aggregates.setdefault(
                    key, {"value": name, "count": 0, "sexes": set(), "regions": set(), "statistics": defaultdict(int)},
                )
                item["sexes"].add(sex)
                item["regions"].add("United States")
                item.setdefault("national_rank_2025", rank)
    maximum = max((item["count"] for item in aggregates.values()), default=1)
    for item in aggregates.values():
        attributes = {
            "release_year": 2025, "frequency_base_year": 2024,
            "state_frequency_year": 2020, "suppression_threshold": 5,
            "suppression_note": "SSA files omit names with fewer than five occurrences in a geographic area.",
            "frequency_representation": "normalized aggregate count",
            "count": item["count"], "sexes": sorted(item["sexes"]),
            "source_statistics": dict(sorted(item["statistics"].items())),
        }
        if "national_rank_2025" in item:
            attributes["national_rank_2025"] = item["national_rank_2025"]
        yield {
            "category": "first_names", "value": item["value"],
            "weight": round(item["count"] / maximum, 8),
            "regions": sorted(item["regions"]), "source_ids": ["ssa-baby-names"],
            "attributes": attributes,
        }


def _census_geography_records(cache_dir: Path) -> Iterable[dict[str, Any]]:
    places = cache_dir / "census-2025-places.zip"
    if places.exists():
        with zipfile.ZipFile(places) as archive:
            filename = next(name for name in archive.namelist() if name.endswith(".txt"))
            text = archive.read(filename).decode("utf-8-sig")
        for row in csv.DictReader(io.StringIO(text), delimiter="|"):
            abbreviation = (row.get("USPS") or "").strip()
            official = (row.get("NAME") or "").strip()
            if not official or abbreviation not in US_REGION_BY_ABBREVIATION:
                continue
            value = re.sub(
                r"\s+(city and borough|unified government|consolidated government|municipality|borough|city|town|village|CDP)$",
                "", official, flags=re.I,
            )
            for category in ("localities", "postal_localities"):
                yield {
                    "category": category, "value": value,
                    "regions": [US_REGION_BY_ABBREVIATION[abbreviation]],
                    "source_ids": ["census-gazetteer"],
                    "attributes": {"official_name": official, "state": abbreviation, "geoid": row.get("GEOID")},
                }
    valid_zips: set[str] = set()
    zctas = cache_dir / "census-2025-zcta.zip"
    if zctas.exists():
        with zipfile.ZipFile(zctas) as archive:
            filename = next(name for name in archive.namelist() if name.endswith(".txt"))
            text = archive.read(filename).decode("utf-8-sig")
        rows = csv.DictReader(io.StringIO(text), delimiter="|")
        for row in rows:
            zip_code = (row.get("GEOID") or row.get("GEOID20") or "").strip()
            if re.fullmatch(r"\d{5}", zip_code):
                valid_zips.add(zip_code)
    postal = cache_dir / "geonames-us-postal-2026-08-20.zip"
    if postal.exists():
        with zipfile.ZipFile(postal) as archive:
            text = archive.read("US.txt").decode("utf-8")
        for row in csv.reader(io.StringIO(text), delimiter="\t"):
            if len(row) < 5 or row[1] not in valid_zips or row[4] not in US_REGION_BY_ABBREVIATION:
                continue
            region = US_REGION_BY_ABBREVIATION[row[4]]
            yield {
                "category": "postal_code_localities", "value": row[1], "regions": [region],
                "source_ids": ["census-gazetteer", "geonames-us-postal"],
                "attributes": {"locality": row[2], "state": row[4]},
            }
            yield {
                "category": "postal_localities", "value": row[2], "regions": [region],
                "source_ids": ["geonames-us-postal"],
                "attributes": {"postal_code": row[1], "state": row[4]},
            }


def _dbf_rows(payload: bytes) -> Iterable[dict[str, str]]:
    record_count = struct.unpack_from("<I", payload, 4)[0]
    header_length, record_length = struct.unpack_from("<HH", payload, 8)
    fields: list[tuple[str, int]] = []
    position = 32
    while position < header_length - 1 and payload[position] != 0x0D:
        name = payload[position:position + 11].split(b"\0", 1)[0].decode("ascii")
        length = payload[position + 16]
        fields.append((name, length))
        position += 32
    for index in range(record_count):
        start = header_length + index * record_length
        record = payload[start:start + record_length]
        if not record or record[0:1] == b"*":
            continue
        offset = 1
        result: dict[str, str] = {}
        for name, length in fields:
            raw_value = record[offset:offset + length].rstrip(b"\0 ")
            try:
                # Current TIGER/Line Puerto Rico DBF values contain UTF-8
                # street names even though many DBF readers assume CP1252.
                decoded = raw_value.decode("utf-8")
            except UnicodeDecodeError:
                decoded = raw_value.decode("cp1252", errors="replace")
            result[name] = decoded.strip()
            offset += length
        yield result


def _tiger_road_records(cache_dir: Path) -> Iterable[dict[str, Any]]:
    root = cache_dir / "tiger-2025-prisec"
    if not root.exists():
        return
    for path in sorted(root.glob("tl_2025_*_prisecroads.zip")):
        match = re.search(r"tl_2025_(\d{2})_", path.name)
        if not match or match.group(1) not in US_REGION_BY_FIPS:
            continue
        region = US_REGION_BY_FIPS[match.group(1)]
        with zipfile.ZipFile(path) as archive:
            filename = next(name for name in archive.namelist() if name.lower().endswith(".dbf"))
            rows = _dbf_rows(archive.read(filename))
            unique: dict[str, dict[str, Any]] = {}
            for row in rows:
                value = row.get("FULLNAME", "").strip()
                if value:
                    unique.setdefault(
                        normalize_value(value),
                        {
                            "category": "streets", "value": value, "regions": [region],
                            "source_ids": ["census-tiger-roads"],
                            "attributes": {"route_type": row.get("RTTYP"), "mtfcc": row.get("MTFCC")},
                        },
                    )
        yield from _stable_sample(unique, 3_000)


def _cms_records(cache_dir: Path) -> Iterable[dict[str, Any]]:
    path = cache_dir / "cms-hospital-general-information-2026-07-22.csv"
    if not path.exists():
        return
    for row in csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()):
        value, abbreviation = row.get("Facility Name", "").strip(), row.get("State", "").strip()
        if not value or abbreviation not in US_REGION_BY_ABBREVIATION:
            continue
        base = {
            "value": value, "regions": [US_REGION_BY_ABBREVIATION[abbreviation]],
            "source_ids": ["cms-provider-data"],
            "attributes": {
                "facility_id": row.get("Facility ID"), "state": abbreviation,
                "city": row.get("City/Town"), "county": row.get("County/Parish"),
                "hospital_type": row.get("Hospital Type"), "ownership": row.get("Hospital Ownership"),
            },
        }
        yield {"category": "hospitals", **base}
        yield {"category": "healthcare_institutions", **base}


def _bls_soc_records(cache_dir: Path) -> Iterable[dict[str, Any]]:
    path = cache_dir / "bls-soc-2018-direct-match-titles.csv"
    if not path.exists():
        return
    for row in csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()):
        value = row.get("2018 SOC Direct Match Title", "").strip()
        if value:
            yield {
                "category": "professions", "value": value, "regions": ["United States"],
                "source_ids": ["bls-soc"],
                "attributes": {"soc_2018": row.get("2018 SOC Code")},
            }


def _merge_attributes(left: Any, right: Any) -> Any:
    if left == right:
        return left
    if isinstance(left, dict) and isinstance(right, dict):
        return {
            key: _merge_attributes(left[key], right[key]) if key in left and key in right else left.get(key, right.get(key))
            for key in sorted(set(left) | set(right))
        }
    left_values = left if isinstance(left, list) else [left]
    right_values = right if isinstance(right, list) else [right]
    return sorted({json.dumps(item, ensure_ascii=False, sort_keys=True): item for item in left_values + right_values}.values(), key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))


def build_records(profile_id: str, cache_dir: Path) -> list[dict[str, Any]]:
    profile_id = normalize_profile_id(profile_id)
    records = list(_seed_records(profile_id))
    if profile_id == "en-GB":
        records.extend(_dfe_records(cache_dir))
        records.extend(_ons_name_records(cache_dir) or ())
        records.extend(_nrs_name_records(cache_dir) or ())
        records.extend(_nisra_name_records(cache_dir) or ())
        records.extend(_os_open_names_records(cache_dir) or ())
        records.extend(_osni_records(cache_dir) or ())
        records.extend(_nhs_ods_records(cache_dir) or ())
        records.extend(_ons_soc_records(cache_dir) or ())
    else:
        records.extend(_census_surname_records(cache_dir) or ())
        records.extend(_ssa_records(cache_dir) or ())
        records.extend(_census_geography_records(cache_dir) or ())
        records.extend(_tiger_road_records(cache_dir) or ())
        records.extend(_cms_records(cache_dir) or ())
        records.extend(_bls_soc_records(cache_dir) or ())

    deduplicated: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        value = unicodedata.normalize("NFKC", str(raw["value"]))
        value = " ".join(value.split())
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError(f"invalid lookup value in {raw.get('category')}: {value!r}")
        record = dict(raw)
        record["value"] = value
        record["normalized"] = normalize_value(value)
        record["regions"] = sorted(set(record.get("regions", [])))
        record["source_ids"] = sorted(set(record.get("source_ids", [])))
        if "ssa-baby-names" in record["source_ids"]:
            attributes = dict(record.get("attributes", {}))
            attributes.setdefault("release_year", 2025)
            attributes.setdefault("suppression_threshold", 5)
            attributes.setdefault(
                "suppression_note",
                "SSA files omit names with fewer than five occurrences in a geographic area.",
            )
            attributes.setdefault("frequency_representation", "normalized weight")
            record["attributes"] = attributes
        key = (record["category"], record["normalized"])
        previous = deduplicated.get(key)
        if previous is None:
            deduplicated[key] = record
        else:
            winner, other = (record, previous) if float(record.get("weight", 0)) > float(previous.get("weight", 0)) else (previous, record)
            merged = dict(winner)
            merged["regions"] = sorted(set(previous.get("regions", ())) | set(record.get("regions", ())))
            merged["source_ids"] = sorted(set(previous.get("source_ids", ())) | set(record.get("source_ids", ())))
            if previous.get("attributes") or record.get("attributes"):
                merged["attributes"] = _merge_attributes(previous.get("attributes", {}), record.get("attributes", {}))
            deduplicated[key] = merged
    return sorted(
        deduplicated.values(),
        key=lambda item: (item["category"], item["normalized"], item["value"]),
    )


def _serialize_records(records: Iterable[dict[str, Any]]) -> bytes:
    lines = [
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for record in records
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def audit_records(
    profile_id: str, records: list[dict[str, Any]], *, payload_sha256: str | None = None
) -> dict[str, Any]:
    profile_id = normalize_profile_id(profile_id)
    lock = source_lock(profile_id)
    sources = lock["sources"]
    source_ids = {source["source_id"] for source in sources}
    counts = Counter(record["category"] for record in records)
    missing_categories = sorted(set(REQUIRED_CATEGORIES) - set(counts))
    unknown_sources = sorted(
        {
            source_id
            for record in records
            for source_id in record.get("source_ids", [])
            if source_id not in source_ids
        }
    )
    empty_provenance = sum(1 for record in records if not record.get("source_ids"))
    regions_by_category: dict[str, set[str]] = defaultdict(set)
    for record in records:
        regions_by_category[record["category"]].update(record.get("regions", []))
    observed_regions = set().union(*regions_by_category.values()) if records else set()
    missing_regions = sorted(REQUIRED_REGIONS[profile_id] - observed_regions)
    missing_category_regions = {
        category: sorted(set(required) - regions_by_category.get(category, set()))
        for category, required in lock.get("required_category_regions", {}).items()
        if set(required) - regions_by_category.get(category, set())
    }
    duplicate_keys = len(records) - len(
        {(item["category"], item["normalized"]) for item in records}
    )
    malformed_records: list[str] = []
    for index, record in enumerate(records, start=1):
        missing = {
            "category", "value", "normalized", "regions", "source_ids"
        } - set(record)
        if missing:
            malformed_records.append(f"record {index} missing {','.join(sorted(missing))}")
            continue
        value = str(record["value"])
        if (
            not value
            or value != " ".join(value.split())
            or any(ord(character) < 32 for character in value)
            or record["normalized"] != normalize_value(value)
            or any(marker in value for marker in ("Ã", "Â", "â€", "ï¿½", "�"))
        ):
            malformed_records.append(f"record {index} has malformed value")
        if not isinstance(record["regions"], list) or not record["regions"]:
            malformed_records.append(f"record {index} has no geographic scope")
        if not isinstance(record["source_ids"], list) or not record["source_ids"]:
            malformed_records.append(f"record {index} has no provenance")
    source_lock_problems: list[str] = []
    for source in sources:
        missing = SOURCE_REQUIRED_FIELDS - set(source)
        if missing:
            source_lock_problems.append(
                f"{source.get('source_id', '<unknown>')} missing {','.join(sorted(missing))}"
            )
        source_hash = str(source.get("source_sha256", ""))
        if len(source_hash) != 64 or any(char not in "0123456789abcdef" for char in source_hash):
            source_lock_problems.append(
                f"{source.get('source_id', '<unknown>')} has invalid source_sha256"
            )
        files_spec = source.get("files", [])
        if source.get("fetch"):
            if not files_spec:
                source_lock_problems.append(f"{source['source_id']} has no locked files")
        for item in files_spec:
            missing_file_fields = {"url", "cache_filename", "sha256"} - set(item)
            if missing_file_fields:
                source_lock_problems.append(
                    f"{source['source_id']} file missing {','.join(sorted(missing_file_fields))}"
                )
            digest = str(item.get("sha256", ""))
            if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
                source_lock_problems.append(
                    f"{source['source_id']} has invalid file SHA-256"
                )
        if (
            files_spec
            and source.get("source_hash_kind") == "ordered raw file hash set"
            and source_hash != _locked_file_set_sha256(files_spec)
        ):
            source_lock_problems.append(
                f"{source['source_id']} source_sha256 does not match its locked file set"
            )
    count_regressions = {
        category: {"minimum": int(minimum), "actual": counts.get(category, 0)}
        for category, minimum in lock.get("expected_minimum_counts", {}).items()
        if counts.get(category, 0) < int(minimum)
    }
    categories_by_normalized: dict[str, set[str]] = defaultdict(set)
    for record in records:
        categories_by_normalized[str(record.get("normalized", ""))].add(
            str(record.get("category", ""))
        )
    semantic_collisions = {
        normalized: sorted(categories)
        for normalized, categories in categories_by_normalized.items()
        if normalized and len(categories) > 1
    }
    ssa_metadata_missing = sum(
        1
        for record in records
        if "ssa-baby-names" in record.get("source_ids", [])
        and (
            "weight" not in record
            or record.get("attributes", {}).get("suppression_threshold") != 5
            or not record.get("attributes", {}).get("release_year")
        )
    )
    problems: list[str] = []
    if missing_categories:
        problems.append(f"missing categories: {', '.join(missing_categories)}")
    if unknown_sources:
        problems.append(f"unknown source IDs: {', '.join(unknown_sources)}")
    if empty_provenance:
        problems.append(f"records without provenance: {empty_provenance}")
    if missing_regions:
        problems.append(f"missing required regions: {', '.join(missing_regions)}")
    if missing_category_regions:
        problems.append(
            "missing category regions: " + ", ".join(sorted(missing_category_regions))
        )
    if duplicate_keys:
        problems.append(f"duplicate normalized keys: {duplicate_keys}")
    if malformed_records:
        problems.append(f"malformed records: {len(malformed_records)}")
    if source_lock_problems:
        problems.append(f"source lock problems: {len(source_lock_problems)}")
    if count_regressions:
        problems.append(
            "count regressions: " + ", ".join(sorted(count_regressions))
        )
    if ssa_metadata_missing:
        problems.append(
            f"SSA records without frequency/suppression metadata: {ssa_metadata_missing}"
        )
    lock_payload = json.dumps(
        lock, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "contract_version": "meddeid.language-resource-audit.v1",
        "profile_id": profile_id,
        "passed": not problems,
        "problems": problems,
        "records": len(records),
        "counts": dict(sorted(counts.items())),
        "count_regressions": count_regressions,
        "regions": sorted(observed_regions),
        "category_region_coverage": {
            category: sorted(regions)
            for category, regions in sorted(regions_by_category.items())
        },
        "missing_category_regions": missing_category_regions,
        "sources": sorted(source_ids),
        "source_sha256": {
            source["source_id"]: source.get("source_sha256") for source in sources
        },
        "sources_lock_logical_sha256": _sha256(lock_payload),
        "source_lock_problems": source_lock_problems,
        "malformed_records": malformed_records[:100],
        "semantic_collisions": {
            "count": len(semantic_collisions),
            "examples": dict(list(sorted(semantic_collisions.items()))[:100]),
        },
        "ssa_metadata_missing": ssa_metadata_missing,
        "lookups_sha256": payload_sha256 or _sha256(_serialize_records(records)),
    }


def write_build(profile_id: str, cache_dir: Path) -> dict[str, Any]:
    profile_id = normalize_profile_id(profile_id)
    records = build_records(profile_id, cache_dir)
    payload = _serialize_records(records)
    audit = audit_records(profile_id, records, payload_sha256=_sha256(payload))
    if not audit["passed"]:
        raise RuntimeError("; ".join(audit["problems"]))
    runtime = _runtime_dir(profile_id)
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "lookups.jsonl").write_bytes(payload)
    (runtime / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    source = _source_dir(profile_id)
    shutil.copyfile(source / "sources.lock.json", runtime / "sources.lock.json")
    shutil.copyfile(source / "SOURCES.md", runtime / "SOURCES.md")
    return audit


def load_runtime_records(profile_id: str) -> list[dict[str, Any]]:
    profile_id = normalize_profile_id(profile_id)
    resource = files("meddeid_language_en").joinpath(
        "resources", profile_id, "lookups.jsonl"
    )
    return [
        json.loads(line)
        for line in resource.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def audit_runtime(profile_id: str) -> dict[str, Any]:
    records = load_runtime_records(profile_id)
    audit = audit_records(profile_id, records)
    if not audit["passed"]:
        raise RuntimeError("; ".join(audit["problems"]))
    return audit


def diff(profile_id: str, cache_dir: Path) -> dict[str, Any]:
    profile_id = normalize_profile_id(profile_id)
    built = build_records(profile_id, cache_dir)
    current = load_runtime_records(profile_id)
    built_keys = {(item["category"], item["normalized"]): item for item in built}
    current_keys = {(item["category"], item["normalized"]): item for item in current}
    source_drift: list[dict[str, str]] = []
    unavailable: list[str] = []
    for source in source_lock(profile_id)["sources"]:
        for item in source.get("files", []):
            path = cache_dir / item["cache_filename"]
            if not path.exists():
                unavailable.append(item["cache_filename"])
                continue
            actual = _sha256(path.read_bytes())
            if actual != item["sha256"]:
                source_drift.append(
                    {
                        "source_id": source["source_id"],
                        "file": item["cache_filename"],
                        "expected_sha256": item["sha256"],
                        "actual_sha256": actual,
                    }
                )
    return {
        "profile_id": profile_id,
        "added": len(set(built_keys) - set(current_keys)),
        "removed": len(set(current_keys) - set(built_keys)),
        "changed": sum(
            built_keys[key] != current_keys[key]
            for key in set(built_keys) & set(current_keys)
        ),
        "identical": _serialize_records(built) == _serialize_records(current),
        "source_drift": source_drift,
        "source_files_unavailable": unavailable,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meddeid-language-en-resources")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("fetch", "build", "audit", "diff"):
        command = subparsers.add_parser(name)
        command.add_argument("--profile", required=True, choices=PROFILE_IDS)
        if name in {"fetch", "build", "diff"}:
            command.add_argument(
                "--cache-dir", type=Path, default=Path(".cache/sources")
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "fetch":
        result: Any = {"downloaded": [str(path) for path in fetch(args.profile, args.cache_dir)]}
    elif args.command == "build":
        result = write_build(args.profile, args.cache_dir)
    elif args.command == "audit":
        result = audit_runtime(args.profile)
    else:
        result = diff(args.profile, args.cache_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
