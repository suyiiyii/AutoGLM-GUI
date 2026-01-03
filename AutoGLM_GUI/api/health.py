from fastapi import APIRouter

from AutoGLM_GUI.version import APP_VERSION

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    return {
        "status": "healthy",
        "version": APP_VERSION,
    }
