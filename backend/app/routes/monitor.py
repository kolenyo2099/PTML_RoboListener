from fastapi import APIRouter, HTTPException

from ..models import KeywordConfig, Location, MonitorJob, PipelineConfig, Station, Stream
from ..monitor_service import monitor_service

router = APIRouter(tags=["monitor"])


@router.get("/status")
async def status() -> dict:
    return monitor_service.snapshot()


@router.get("/hardware")
async def hardware() -> dict:
    # This deliberately avoids heavy GPU libraries. It reports safe defaults and
    # leaves real CUDA/MPS probing to a later production backend.
    return {"cpu": True, "cuda": False, "mps": False, "recommendedDevice": "cpu"}


@router.get("/languages/profiles")
async def language_profiles() -> list[dict]:
    from ..language_profiles import profiles_as_api

    return profiles_as_api()


@router.post("/monitor/start")
async def start_monitoring(payload: MonitorJob) -> dict:
    if not payload.stations:
        raise HTTPException(status_code=400, detail="At least one station is required.")
    stations = [
        Station(
            id=s.id,
            name=s.name,
            slug=s.slug,
            location=Location(countryName=s.countryName, countryCode=s.countryCode),
            streams=[Stream(url=url) for url in s.streamUrls],
            languageCode=s.languageCode,
        )
        for s in payload.stations
    ]
    monitor_service.start(stations, payload.keywordConfig, payload.pipelineConfig)
    return monitor_service.snapshot()


@router.delete("/monitor/{station_id:path}")
async def stop_station(station_id: str) -> dict:
    monitor_service.remove(station_id)
    return monitor_service.snapshot()


@router.post("/monitor/{station_id:path}/pause")
async def pause_station(station_id: str) -> dict:
    monitor_service.pause(station_id)
    return monitor_service.snapshot()


@router.post("/monitor/{station_id:path}/resume")
async def resume_station(station_id: str) -> dict:
    monitor_service.resume(station_id)
    return monitor_service.snapshot()


@router.post("/monitor/stop-all")
async def stop_all() -> dict:
    monitor_service.stop_all()
    return monitor_service.snapshot()


@router.patch("/keywords")
async def patch_keywords(payload: KeywordConfig) -> dict:
    monitor_service.patch_keywords(payload)
    return monitor_service.snapshot()


@router.patch("/pipeline")
async def patch_pipeline(payload: PipelineConfig) -> dict:
    monitor_service.patch_pipeline(payload)
    return monitor_service.snapshot()

