from fastapi import APIRouter, Query

from ..language_profiles import profiles_as_api
from ..radio_api import (
    fetch_languages,
    fetch_station_by_id,
    fetch_stations_for_country,
    fetch_stations_for_language,
    search_stations,
)

router = APIRouter(prefix="/api/radio", tags=["radio"])


@router.get("/languages")
async def languages() -> list[dict]:
    return await fetch_languages()


@router.get("/languages/{code}/radios")
async def stations_by_language(
    code: str,
    limit: int = Query(100, ge=1, le=300),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    return await fetch_stations_for_language(code.lower(), limit, offset)


@router.get("/countries/{country_name}/radios")
async def stations_by_country(
    country_name: str,
    limit: int = Query(40, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    return await fetch_stations_for_country(country_name, limit, offset)


@router.get("/radios/search")
async def station_search(q: str = Query(""), limit: int = Query(40, ge=1, le=100)) -> list[dict]:
    return await search_stations(q, limit)


@router.get("/radios/{station_id}")
async def station_by_id(station_id: str) -> dict:
    return await fetch_station_by_id(station_id)


@router.get("/profiles")
async def profiles() -> list[dict]:
    return profiles_as_api()
