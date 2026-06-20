"""Construiește geojson-urile sub-naționale pentru USA, China, Canada, Australia.

Pornește de la sursele publice (codeforgermany/click_that_hood) și mapează
numele în coduri ISO 3166-2 (US-CA, CN-HB, CA-ON, AU-NSW etc.), apoi salvează
în public/geo/<country>-subnational.geojson cu un property COUNTY_CODE.

Format unificat — MapPage.vue folosește același helper isoFromFeature pentru
toate.
"""

from __future__ import annotations

import json
import logging
import sys
import urllib.request
from pathlib import Path

logger = logging.getLogger("prep_geo")

OUT_DIR = Path(__file__).resolve().parents[1] / "frontend" / "public" / "geo"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SOURCES = {
    "usa": "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/united-states.geojson",
    "china": "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/china.geojson",
    "canada": "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/canada.geojson",
    "australia": "https://raw.githubusercontent.com/codeforgermany/click_that_hood/main/public/data/australia.geojson",
}

# Nume Province_State (în sursele click_that_hood) → ISO 3166-2
US_STATES = {
    "Alabama": "US-AL", "Alaska": "US-AK", "Arizona": "US-AZ", "Arkansas": "US-AR",
    "California": "US-CA", "Colorado": "US-CO", "Connecticut": "US-CT",
    "Delaware": "US-DE", "District of Columbia": "US-DC", "Florida": "US-FL",
    "Georgia": "US-GA", "Hawaii": "US-HI", "Idaho": "US-ID", "Illinois": "US-IL",
    "Indiana": "US-IN", "Iowa": "US-IA", "Kansas": "US-KS", "Kentucky": "US-KY",
    "Louisiana": "US-LA", "Maine": "US-ME", "Maryland": "US-MD",
    "Massachusetts": "US-MA", "Michigan": "US-MI", "Minnesota": "US-MN",
    "Mississippi": "US-MS", "Missouri": "US-MO", "Montana": "US-MT",
    "Nebraska": "US-NE", "Nevada": "US-NV", "New Hampshire": "US-NH",
    "New Jersey": "US-NJ", "New Mexico": "US-NM", "New York": "US-NY",
    "North Carolina": "US-NC", "North Dakota": "US-ND", "Ohio": "US-OH",
    "Oklahoma": "US-OK", "Oregon": "US-OR", "Pennsylvania": "US-PA",
    "Rhode Island": "US-RI", "South Carolina": "US-SC", "South Dakota": "US-SD",
    "Tennessee": "US-TN", "Texas": "US-TX", "Utah": "US-UT", "Vermont": "US-VT",
    "Virginia": "US-VA", "Washington": "US-WA", "West Virginia": "US-WV",
    "Wisconsin": "US-WI", "Wyoming": "US-WY",
}

# Sursa click_that_hood folosește pinyin pentru China. Mapăm la coduri ISO.
CN_PROVINCES = {
    "Anhui": "CN-AH", "Beijing": "CN-BJ", "Chongqing": "CN-CQ",
    "Fujian": "CN-FJ", "Gansu": "CN-GS", "Guangdong": "CN-GD",
    "Guangxi": "CN-GX", "Guizhou": "CN-GZ", "Hainan": "CN-HI",
    "Hebei": "CN-HE", "Heilongjiang": "CN-HL", "Heilongjian": "CN-HL",
    "Henan": "CN-HA", "Hong Kong": "CN-HK", "Hubei": "CN-HB",
    "Hunan": "CN-HN", "Inner Mongolia": "CN-NM", "Jiangsu": "CN-JS",
    "Jiangxi": "CN-JX", "Jilin": "CN-JL", "Liaoning": "CN-LN",
    "Macao": "CN-MO", "Macau": "CN-MO",
    "Ningxia Hui": "CN-NX", "Ningxia": "CN-NX",
    "Qinghai": "CN-QH", "Shaanxi": "CN-SN", "Shandong": "CN-SD",
    "Shanghai": "CN-SH", "Shanxi": "CN-SX", "Sichuan": "CN-SC",
    "Taiwan": "CN-TW", "Tianjin": "CN-TJ", "Tibet": "CN-XZ", "Xizang": "CN-XZ",
    "Xinjiang Uyghur": "CN-XJ", "Xinjiang": "CN-XJ",
    "Yunnan": "CN-YN", "Zhejiang": "CN-ZJ",
}

CA_PROVINCES = {
    "Alberta": "CA-AB", "British Columbia": "CA-BC",
    "Manitoba": "CA-MB", "New Brunswick": "CA-NB",
    "Newfoundland and Labrador": "CA-NL",
    "Newfoundland": "CA-NL",
    "Northwest Territories": "CA-NT", "Nova Scotia": "CA-NS",
    "Nunavut": "CA-NU", "Ontario": "CA-ON",
    "Prince Edward Island": "CA-PE",
    "Quebec": "CA-QC", "Québec": "CA-QC",
    "Saskatchewan": "CA-SK", "Yukon": "CA-YT", "Yukon Territory": "CA-YT",
}

AU_STATES = {
    "Australian Capital Territory": "AU-ACT",
    "New South Wales": "AU-NSW",
    "Northern Territory": "AU-NT",
    "Queensland": "AU-QLD",
    "South Australia": "AU-SA",
    "Tasmania": "AU-TAS",
    "Victoria": "AU-VIC",
    "Western Australia": "AU-WA",
}

MAPPINGS = {
    "usa": US_STATES,
    "china": CN_PROVINCES,
    "canada": CA_PROVINCES,
    "australia": AU_STATES,
}


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())


def process(name: str, url: str) -> None:
    logger.info("[%s] fetching", name)
    g = fetch(url)
    mapping = MAPPINGS[name]
    out_features = []
    skipped = []
    for feat in g.get("features", []):
        props = feat.get("properties", {})
        nm = (props.get("name") or props.get("NAME") or "").strip()
        # Maparea noastră are prefixul de țară (AU-NSW etc.); o preferăm
        # peste iso_3166_2 din sursă care e doar codul scurt (NSW).
        iso = mapping.get(nm) or props.get("iso_3166_2")
        if not iso:
            skipped.append(nm)
            continue
        # Defensiv: dacă iso vine din sursă fără prefix, îl adăugăm.
        if "-" not in iso and len(iso) <= 4:
            country_prefix = {"usa": "US", "china": "CN", "canada": "CA", "australia": "AU"}.get(name)
            if country_prefix:
                iso = f"{country_prefix}-{iso}"
        new_props = {
            "COUNTY_CODE": iso,
            "NAME": nm,
        }
        out_features.append({
            "type": "Feature",
            "geometry": feat["geometry"],
            "properties": new_props,
        })
    fc = {"type": "FeatureCollection", "features": out_features}
    out_path = OUT_DIR / f"{name}-subnational.geojson"
    out_path.write_text(json.dumps(fc, ensure_ascii=False))
    logger.info("[%s] %d features scrise -> %s", name, len(out_features), out_path.name)
    if skipped:
        logger.info("[%s] sărite (nu sunt în mapping): %s", name, skipped)


def main() -> int:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
    for name, url in SOURCES.items():
        try:
            process(name, url)
        except Exception as e:  # noqa: BLE001
            logger.error("[%s] eroare: %s", name, e)
    logger.info("Gata.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
