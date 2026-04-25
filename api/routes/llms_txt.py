"""llms.txt generator endpoint."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, HttpUrl

from api.services.llms_txt import generate_llms_txt

logger = logging.getLogger(__name__)

router = APIRouter()


class LlmsTxtRequest(BaseModel):
    url: HttpUrl


class LlmsTxtResponse(BaseModel):
    domain: str
    content: str


@router.post("", response_model=LlmsTxtResponse)
def build(req: LlmsTxtRequest) -> LlmsTxtResponse:
    url = str(req.url)
    try:
        content = generate_llms_txt(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("llms.txt generation failed for %s", url)
        raise HTTPException(status_code=500, detail=f"Génération échouée : {e}")
    return LlmsTxtResponse(domain=urlparse(url).netloc, content=content)
