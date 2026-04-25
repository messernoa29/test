"""Competitor Watch endpoints — orchestrate N parallel audits + LLM synthesis."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from api.models import CompetitorBattle, CompetitorBattleRequest
from api.services.runner import create_battle
from api.services.store import get_store

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("", response_model=CompetitorBattle, status_code=202)
def start_battle(req: CompetitorBattleRequest) -> CompetitorBattle:
    target = str(req.targetUrl)
    competitors = [str(u) for u in req.competitors]
    if target in competitors:
        raise HTTPException(
            status_code=422,
            detail="Le site cible ne peut pas être listé parmi les concurrents.",
        )
    if len(competitors) != len(set(competitors)):
        raise HTTPException(
            status_code=422, detail="Les concurrents doivent être uniques.",
        )
    return create_battle(target, competitors)


@router.get("", response_model=list[CompetitorBattle])
def list_battles() -> list[CompetitorBattle]:
    return get_store().list_battles()


@router.get("/{battle_id}", response_model=CompetitorBattle)
def get_battle(battle_id: str) -> CompetitorBattle:
    battle = get_store().get_battle(battle_id)
    if battle is None:
        raise HTTPException(status_code=404, detail="Battle not found")
    return battle


@router.delete("/{battle_id}", status_code=204)
def delete_battle(battle_id: str) -> Response:
    if not get_store().delete_battle(battle_id):
        raise HTTPException(status_code=404, detail="Battle not found")
    return Response(status_code=204)
