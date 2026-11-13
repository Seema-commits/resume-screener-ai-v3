from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends

from app.services import logging_service
from backend.deps import require

router = APIRouter(prefix="/logs", tags=["logs"])

PAGE_SIZE = 25


@router.get("")
def list_logs(
    errors_only: bool = False, event_type: Optional[str] = None,
    org_id: Optional[int] = None, date_from: Optional[date] = None,
    date_to: Optional[date] = None, page: int = 1,
    user=Depends(require("view_logs")),
):
    """Newest first, 25 per page, with each entry's retention category."""

    filters = {"errors_only": errors_only, "event_type": event_type,
               "org_id": org_id, "date_from": date_from,
               "date_to": date_to or date_from}
    page = max(page, 1)
    items = logging_service.list_logs(
        user, offset=(page - 1) * PAGE_SIZE, limit=PAGE_SIZE, **filters)
    for item in items:
        item["category"] = logging_service.category_of(item["event_type"])
    return {"total": logging_service.count_logs(user, **filters),
            "page": page, "page_size": PAGE_SIZE, "items": items,
            "retention_days": logging_service.RETENTION_DAYS}


@router.get("/event-types")
def event_types(user=Depends(require("view_logs"))):
    return logging_service.event_types(user)
