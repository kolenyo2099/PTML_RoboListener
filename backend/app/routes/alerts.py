import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from ..store import delete_alert, list_alerts, update_alert

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("")
async def alerts(language: str | None = Query(None)) -> list[dict]:
    return list_alerts(language)


@router.get("/export")
async def export_alerts(ids: str = Query("")) -> StreamingResponse:
    selected = set(filter(None, ids.split(",")))
    rows = [alert for alert in list_alerts() if not selected or alert["id"] in selected]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("metadata.json", json.dumps(rows, indent=2, ensure_ascii=False))
        for alert in rows:
            clip = Path(alert.get("clipPath") or "")
            if clip.exists():
                archive.write(clip, f"clips/{clip.name}")
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=radiowatch_alerts.zip"})


@router.get("/{alert_id}")
async def get_alert(alert_id: str) -> dict:
    alert = next((row for row in list_alerts() if row["id"] == alert_id), None)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.get("/{alert_id}/clip")
async def clip(alert_id: str) -> FileResponse:
    alert = next((row for row in list_alerts() if row["id"] == alert_id), None)
    if not alert or not alert.get("clipPath") or not Path(alert["clipPath"]).exists():
        raise HTTPException(status_code=404, detail="Clip file not found")
    return FileResponse(alert["clipPath"], media_type="audio/wav")


@router.patch("/{alert_id}")
async def mark_reviewed(alert_id: str, payload: dict) -> dict:
    alert = update_alert(alert_id, bool(payload.get("reviewed", True)))
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.delete("/{alert_id}")
async def remove_alert(alert_id: str) -> dict:
    delete_alert(alert_id)
    return {"ok": True}
