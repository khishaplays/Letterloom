"""Process health endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Report that the application process can serve requests."""

    return {"status": "ok"}
