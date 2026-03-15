"""Job status endpoint — poll Celery task status by job_id."""

import logging

from fastapi import APIRouter, Depends

from app.api.auth import get_current_user
from app.models.database import User
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("/{job_id}")
async def job_status(
    job_id: str,
    user: User = Depends(get_current_user),
) -> dict:
    """Return the current status of a background ingestion job.

    States: PENDING, STARTED, SUCCESS, FAILURE, RETRY.
    """
    result = celery_app.AsyncResult(job_id)

    response: dict = {
        "job_id": job_id,
        "state": result.state,
    }

    if result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.result) if result.result else "Unknown error"

    return response
