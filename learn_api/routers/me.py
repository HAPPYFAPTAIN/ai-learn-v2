"""Read-only bootstrap. No tenant creation, quota allocation or model calls."""
from fastapi import APIRouter, Depends, Response
from learn_api.auth import Principal, get_principal
from learn_api.schemas import MeOut

router = APIRouter(tags=["session"])

@router.get("/me", response_model=MeOut)
def me(response: Response, principal: Principal = Depends(get_principal)) -> MeOut:
    response.headers["Cache-Control"] = "no-store"
    return MeOut(
        userId=principal.official_user_id,
        displayName=principal.display_name or principal.official_user_id,
        capabilities={
            "chat": True, "jobEvents": True,
            "lessonContent": True, "generateRoadmap": True,
            "generateQuiz": True, "streamChat": False,
            "fileDownload": True, "storage": False,
            "coach": True, "polish": True, "models": True,
        },
    )
