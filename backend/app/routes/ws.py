import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..monitor_service import monitor_service

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/status")
async def status_socket(websocket: WebSocket) -> None:
    # The socket pushes BackendStatus every 2 seconds (PRD requirement) plus
    # event-driven pushes whenever monitoring state changes.
    await websocket.accept()
    queue = await monitor_service.subscribe()

    async def _periodic_push() -> None:
        while True:
            await asyncio.sleep(2)
            await queue.put(monitor_service.snapshot())

    periodic = asyncio.create_task(_periodic_push())
    try:
        while True:
            payload = await queue.get()
            await websocket.send_text(json.dumps(payload))
    except WebSocketDisconnect:
        pass
    finally:
        periodic.cancel()
        monitor_service.unsubscribe(queue)

