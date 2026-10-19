"""Real vacancies from the National Vacancy Database of Uzbekistan (ish.mehnat.uz, Ministry of Employment and
Poverty Reduction). Public read-only API; results are cached and every vacancy links back to its official page.

Vacancy texts are written by employers: they are shown and passed to the agent as data, never as instructions.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger("foydapay.jobs")

API = "https://ishapi.mehnat.uz/api/v1/vacancies"
SITE = "https://ish.mehnat.uz"
SOURCE = {"name": "National Vacancy Database (Ministry of Employment and Poverty Reduction)", "url": SITE + "/vacancies"}
TIMEOUT = 6
CACHE_TTL = 30 * 60
_cache: dict[tuple, tuple[float, list]] = {}

# SOATO region codes used by the database (first 4 digits).
REGIONS = {
    "1726": "Tashkent city", "1727": "Tashkent region", "1703": "Andijan", "1706": "Bukhara", "1708": "Jizzakh",
    "1710": "Kashkadarya", "1712": "Navoi", "1714": "Namangan", "1718": "Samarkand", "1722": "Surkhandarya",
    "1724": "Syrdarya", "1730": "Fergana", "1733": "Khorezm", "1735": "Karakalpakstan",
}
# hh.uz has no open search API any more (an app token is required), so we link to its search page instead.
HH_AREA = {"1726": "2759", "1727": "2759"}

# Search words per skill. The database matches position names in Uzbek and Russian; Russian names are the most complete.
SKILL_QUERIES = {
    "smartphone": ["курьер", "оператор"],
    "excel-basic": ["оператор", "делопроизводитель"],
    "languages": ["переводчик", "преподаватель"],
    "design": ["дизайнер", "фотограф"],
    "car": ["водитель"],
}
DEFAULT_QUERIES = ["продавец", "кассир", "оператор"]


def queries_for(skills: list[str], has_car: bool, query: str = "") -> list[str]:
    if query:
        return [query[:40]]
    qs = [q for s in skills for q in SKILL_QUERIES.get(s, [])] + (SKILL_QUERIES["car"] if has_car else [])
    return list(dict.fromkeys(qs or DEFAULT_QUERIES))[:3]


def _fetch(region: str | None, query: str) -> list[dict]:
    key = (region, query)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    params = {"per_page": 10, "search": query, **({"company_soato_code": region} if region else {})}
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(2):  # the API sometimes answers 500 on a busy query; one retry, then skip it
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "FoydaPay/1.0 (+https://foydapay.onrender.com)"})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                rows = json.load(r)["data"]["data"]
            break
        except Exception as e:  # noqa: BLE001 - network, HTTP or JSON errors all mean "no results from this query"
            log.info("vacancy search failed (%s, try %d): %s", query, attempt + 1, e)
            rows = None
    if rows is None:
        return []
    out = [normalize(v) for v in rows if v.get("company_name")]
    _cache[key] = (time.time(), out)
    return out


def normalize(v: dict) -> dict:
    try:
        salary = round(float(v.get("position_salary") or 0))
    except (TypeError, ValueError):
        salary = 0
    try:
        rate = float(v.get("position_rate") or 1)
    except (TypeError, ValueError):
        rate = 1.0
    region = str(v.get("company_soato_code4") or "")
    return {
        "id": v["id"],
        "title": (v.get("position_name_ru") or v.get("position_name") or "").strip()[:120],
        "title_uz": (v.get("position_name") or "").strip()[:120],
        "company": str(v.get("company_name") or "").replace('"', "").strip()[:120],
        "salary": salary, "rate": rate,
        "region": REGIONS.get(region, ""), "region_code": region,
        "posted": v.get("date_start"),
        "url": f"{SITE}/vacancies/{v['id']}",
    }


def result(region: str | None, qs: list[str], vacancies: list[dict], limit: int = 8) -> dict:
    seen, merged = set(), []
    for v in vacancies:
        if v["id"] not in seen:
            seen.add(v["id"])
            merged.append(v)
    merged.sort(key=lambda v: -v["salary"])
    hh = "https://hh.uz/search/vacancy?" + urllib.parse.urlencode({"text": qs[0], "area": HH_AREA.get(region or "", "97")})
    return {"source": SOURCE, "region": REGIONS.get(region or "", "Uzbekistan"), "region_code": region or "", "queries": qs,
            "vacancies": merged[:limit], "more": {"hh": hh, "official": SOURCE["url"]},
            "note": "Real vacancies posted by employers. Salaries are per month for the given rate (1.0 = full-time). "
                    "Check the schedule and conditions with the employer; never pay anyone to get a job."}


def search(region: str | None, skills: list[str], has_car: bool = False, query: str = "", limit: int = 8, fetch: bool = True) -> dict:
    """Up to `limit` vacancies for the user's region and skills, best paid first.
    fetch=False returns only the search plan (queries, region, links): the phone then asks the database itself,
    because the database answers slowly or not at all to servers outside Uzbekistan."""
    region = region if region in REGIONS else None
    qs = queries_for(skills, has_car, query)
    batches = []
    if fetch:
        with ThreadPoolExecutor(max_workers=3) as pool:
            batches = list(pool.map(lambda q: _fetch(region, q), qs))
    return result(region, qs, [v for b in batches for v in b], limit)
