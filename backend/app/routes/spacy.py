"""Endpoint for installing spaCy language models on demand."""

import subprocess
import sys

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..language_profiles import LANGUAGE_PROFILES

router = APIRouter(prefix="/api/spacy", tags=["spacy"])

_ALLOWED_MODELS: set[str] = {
    p.spacy_model
    for p in LANGUAGE_PROFILES.values()
    if p.spacy_model is not None
}


class InstallRequest(BaseModel):
    model: str


@router.post("/install")
async def install_model(body: InstallRequest) -> dict:
    if body.model not in _ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {body.model!r}")

    result = subprocess.run(
        [sys.executable, "-m", "spacy", "download", body.model],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=result.stderr or result.stdout or "Install failed",
        )

    return {"ok": True, "model": body.model, "output": result.stdout}
