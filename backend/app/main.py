"""FastAPI entrypoint for RadioWatch."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import alerts, monitor, radio, spacy, ws
from .store import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="RadioWatch API", version="0.1.0", lifespan=lifespan)

# The frontend runs on a Vite development port. CORS is limited to local origins
# because this backend is intended for single-user localhost operation.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(radio.router)
app.include_router(monitor.router)
app.include_router(alerts.router)
app.include_router(spacy.router)
app.include_router(ws.router)


@app.get("/")
async def root() -> dict:
    return {"name": "RadioWatch API", "status": "ready"}

