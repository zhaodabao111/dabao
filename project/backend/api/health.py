from fastapi import APIRouter

from ..schemas import HealthData, SuccessResponse, new_request_id


router = APIRouter(tags=["health"])


@router.get("/health", response_model=SuccessResponse[HealthData])
async def health() -> SuccessResponse[HealthData]:
    """Report that the local API process is available."""
    return SuccessResponse(
        request_id=new_request_id(),
        data=HealthData(status="ok"),
    )
