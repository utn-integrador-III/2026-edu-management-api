from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.middleware.role_middleware import require_role
from src.modules.calendar import calendar_service

router = APIRouter()


class CalendarEventCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: str | None = None
    type: str = Field(default="event")
    start_date: str
    end_date: str | None = None
    group_id: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    location: str | None = None
    subject_id: str | None = None


@router.post("/events")
def create_event(body: CalendarEventCreate, current_user: dict = Depends(require_role("admin","teacher"))):
    try:
        return calendar_service.create_event(body.model_dump(), current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/events")
def get_events(
    group_id: str | None = Query(None),
    type: str | None = Query(None),
    active: bool | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    month: int | None = Query(None),
    year: int | None = Query(None),
    _current_user: dict = Depends(require_role("admin", "teacher")),
):
    filters = {
        "group_id": group_id,
        "type": type,
        "active": active,
        "date_from": date_from,
        "date_to": date_to,
        "month": month,
        "year": year,
    }
    return calendar_service.get_events(filters)


@router.get("/students/{student_id}/events")
def get_student_events(student_id: str, current_user: dict = Depends(require_role("admin", "teacher", "parent"))):
    try:
        return calendar_service.get_student_events(student_id, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))