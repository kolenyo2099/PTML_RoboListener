"""Radio Browser API integration (https://api.radio-browser.info/).

Free and open — no API key required. Multiple mirror servers are discovered
via DNS at startup; falls back to a hardcoded list if DNS is unavailable.
"""

from __future__ import annotations

import random
import socket
import time
from typing import Any

import httpx
from fastapi import HTTPException

from .language_profiles import LANGUAGE_PROFILES
from .settings import RADIO_BROWSER_FALLBACK_SERVERS, RADIO_BROWSER_USER_AGENT

_cache: dict[str, tuple[float, Any]] = {}
CACHE_SECONDS = 15 * 60

# Native names for common ISO-639-1 codes (Radio Browser only gives English names)
_NATIVE_NAMES: dict[str, str] = {
    "es": "Español",           "en": "English",            "fr": "Français",
    "de": "Deutsch",           "pt": "Português",          "ar": "العربية",
    "ru": "Русский",           "zh": "中文",               "it": "Italiano",
    "nl": "Nederlands",        "tr": "Türkçe",             "fa": "فارسی",
    "he": "עברית",             "ur": "اردو",               "hi": "हिन्दी",
    "bn": "বাংলা",             "vi": "Tiếng Việt",        "pl": "Polski",
    "uk": "Українська",        "ro": "Română",             "cs": "Čeština",
    "hu": "Magyar",            "sv": "Svenska",            "da": "Dansk",
    "fi": "Suomi",             "el": "Ελληνικά",           "th": "ภาษาไทย",
    "ko": "한국어",             "ja": "日本語",             "id": "Bahasa Indonesia",
    "sr": "Српски",            "hr": "Hrvatski",           "sk": "Slovenčina",
    "bg": "Български",         "lt": "Lietuvių",           "lv": "Latviešu",
    "et": "Eesti",             "ms": "Bahasa Melayu",      "sw": "Kiswahili",
    "am": "አማርኛ",             "af": "Afrikaans",          "ka": "ქართული",
    "hy": "Հայերեն",           "az": "Azərbaycan",         "kk": "Қазақша",
    "uz": "Oʻzbek",            "ky": "Кыргызча",           "tg": "Тоҷикӣ",
    "mn": "Монгол",            "si": "සිංහල",              "ne": "नेपाली",
    "my": "မြန်မာဘာသာ",        "km": "ខ្មែរ",              "lo": "ລາວ",
    "sq": "Shqip",             "mk": "Македонски",         "bs": "Bosanski",
    "sl": "Slovenščina",       "gl": "Galego",             "ca": "Català",
    "eu": "Euskara",           "cy": "Cymraeg",            "is": "Íslenska",
    "mt": "Malti",             "ga": "Gaeilge",
}

_RTL_CODES: frozenset[str] = frozenset({"ar", "fa", "he", "ur", "ug", "yi", "dv"})

# Module-level server; resolved once at first API call.
_active_server: str | None = None


def _resolve_server() -> str:
    """Return a working Radio Browser mirror via DNS discovery."""
    try:
        records = socket.getaddrinfo("all.api.radio-browser.info", 443, proto=socket.IPPROTO_TCP)
        ips = list({r[4][0] for r in records})
        random.shuffle(ips)
        for ip in ips:
            try:
                hostname, _, _ = socket.gethostbyaddr(ip)
                if "radio-browser" in hostname:
                    return hostname
            except socket.herror:
                pass
    except Exception:
        pass
    return random.choice(RADIO_BROWSER_FALLBACK_SERVERS)


def _base() -> str:
    global _active_server
    if _active_server is None:
        _active_server = _resolve_server()
    return f"https://{_active_server}/json"


def _hdr() -> dict[str, str]:
    return {"User-Agent": RADIO_BROWSER_USER_AGENT}


def _from_cache(key: str) -> Any | None:
    saved = _cache.get(key)
    if saved and time.time() - saved[0] < CACHE_SECONDS:
        return saved[1]
    return None


def _save_cache(key: str, value: Any) -> Any:
    _cache[key] = (time.time(), value)
    return value


# ── Normalisation helpers ──────────────────────────────────────────────────────

def _norm_language(raw: dict) -> dict | None:
    code = (raw.get("iso_639") or "").strip().lower()
    # Skip entries without a valid 2-letter ISO code or with very few stations
    if not code or len(code) > 8 or " " in code:
        return None
    count = int(raw.get("stationcount") or 0)
    if count == 0:
        return None
    name_en = (raw.get("name") or code).strip()
    profile = LANGUAGE_PROFILES.get(code)
    return {
        "code": code,
        "nameEnglish": name_en,
        "nameNative": _NATIVE_NAMES.get(code) or (profile.name_native if profile else name_en),
        "stationCount": count,
        "isRtl": code in _RTL_CODES,
    }


def _norm_station(raw: dict, language_code: str = "") -> dict:
    uuid: str = raw.get("stationuuid") or raw.get("changeuuid") or str(abs(hash(raw.get("name", ""))))
    url: str = raw.get("url_resolved") or raw.get("url") or ""
    bitrate: int = int(raw.get("bitrate") or 0)
    codec: str = (raw.get("codec") or "mp3").lower()
    is_https: bool = url.startswith("https")

    # Derive language code from the station's languagecodes field (comma-separated)
    lang = language_code
    if not lang:
        raw_lang = raw.get("languagecodes") or raw.get("language") or ""
        lang = raw_lang.split(",")[0].strip().lower()

    tags: str = raw.get("tags") or ""
    genre = next((t.strip().title() for t in tags.split(",") if t.strip()), "General")

    return {
        "id": uuid,
        "name": (raw.get("name") or "Unnamed station").strip(),
        "slug": (raw.get("name") or "station").lower().replace(" ", "-")[:64],
        "location": {
            "cityName": (raw.get("state") or "").strip(),
            "countryName": (raw.get("country") or "Unknown").strip(),
            "countryCode": (raw.get("countrycode") or "").upper(),
        },
        "genre": {"text": genre},
        "popularity": {"global": int(raw.get("votes") or 0)},
        "streams": [{"url": url, "bitrate": bitrate, "format": codec, "isHttps": is_https}] if url else [],
        "languageCode": lang,
    }


# ── Public API ─────────────────────────────────────────────────────────────────

async def fetch_languages() -> list[dict]:
    key = "languages"
    if cached := _from_cache(key):
        return cached
    async with httpx.AsyncClient(timeout=20, headers=_hdr()) as client:
        resp = await client.get(f"{_base()}/languages")
    if resp.status_code >= 400:
        return []
    rows: list[dict] = resp.json() if isinstance(resp.json(), list) else []
    langs = [n for row in rows if (n := _norm_language(row))]
    langs.sort(key=lambda x: x["stationCount"], reverse=True)
    return _save_cache(key, langs)


async def _language_name_for_code(code: str) -> str | None:
    """Look up a Radio Browser language name (e.g. 'spanish') from an ISO code (e.g. 'es')."""
    langs = await fetch_languages()
    for lang in langs:
        if lang["code"] == code:
            # Radio Browser stores language names in lowercase
            return lang["nameEnglish"].lower()
    return None


async def fetch_stations_for_language(code: str, limit: int = 100, offset: int = 0) -> list[dict]:
    key = f"stations:{code}:{limit}:{offset}"
    if cached := _from_cache(key):
        return cached
    # Look up the language name — `language={name}&languageExact=true` is much
    # more accurate than the `languagecodes={code}` substring filter.
    language_name = await _language_name_for_code(code)
    params: dict[str, str | int] = {
        "limit": limit,
        "offset": offset,
        "order": "votes",
        "reverse": "true",
        "hidebroken": "true",
    }
    if language_name:
        params["language"] = language_name
        params["languageExact"] = "true"
    else:
        params["languagecodes"] = code
    async with httpx.AsyncClient(timeout=25, headers=_hdr()) as client:
        resp = await client.get(f"{_base()}/stations/search", params=params)
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:300])
    rows: list[dict] = resp.json() if isinstance(resp.json(), list) else []
    return _save_cache(key, [_norm_station(r, code) for r in rows])


async def fetch_stations_for_country(country_name: str, limit: int = 40, offset: int = 0) -> list[dict]:
    key = f"country:{country_name}:{limit}:{offset}"
    if cached := _from_cache(key):
        return cached
    async with httpx.AsyncClient(timeout=25, headers=_hdr()) as client:
        resp = await client.get(
            f"{_base()}/stations/search",
            params={
                "country": country_name,
                "limit": limit,
                "offset": offset,
                "order": "votes",
                "reverse": "true",
                "hidebroken": "true",
            },
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:300])
    rows: list[dict] = resp.json() if isinstance(resp.json(), list) else []
    return _save_cache(key, [_norm_station(r) for r in rows])


async def fetch_station_by_id(station_id: str) -> dict:
    key = f"station:{station_id}"
    if cached := _from_cache(key):
        return cached
    async with httpx.AsyncClient(timeout=15, headers=_hdr()) as client:
        resp = await client.get(f"{_base()}/stations/byuuid/{station_id}")
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text[:300])
    rows = resp.json()
    raw: dict = rows[0] if isinstance(rows, list) and rows else (rows if isinstance(rows, dict) else {})
    if not raw:
        raise HTTPException(status_code=404, detail="Station not found")
    result = _norm_station(raw)
    return _save_cache(key, result)


async def search_stations(query: str, limit: int = 40) -> list[dict]:
    async with httpx.AsyncClient(timeout=15, headers=_hdr()) as client:
        resp = await client.get(
            f"{_base()}/stations/search",
            params={"name": query, "limit": limit, "order": "votes", "reverse": "true", "hidebroken": "true"},
        )
    if resp.status_code >= 400:
        return []
    rows: list[dict] = resp.json() if isinstance(resp.json(), list) else []
    return [_norm_station(r) for r in rows]
