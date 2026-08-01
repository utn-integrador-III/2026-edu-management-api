from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.middleware.role_middleware import require_role
from src.modules.attendance import attendance_service

router = APIRouter()


class AttendanceRecordItem(BaseModel):
    student_id: str = Field(..., min_length=1)
    status: str = Field(..., pattern="^(presente|ausente|tardanza)$")
    arrival_time: Optional[str] = None


class AttendanceCreateRequest(BaseModel):
    date: str
    group_id: str = Field(..., min_length=1)
    subject_id: str = Field(..., min_length=1)
    records: List[AttendanceRecordItem]


@router.post("")
def create_attendance(body: AttendanceCreateRequest, current_user: dict = Depends(require_role("admin", "teacher"))):
    try:
        return attendance_service.create_attendance(body, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
def get_attendance_history(
    group_id: Optional[str] = Query(None),
    subject_id: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
    current_user: dict = Depends(require_role("admin", "teacher", "parent")),
):
    try:
        return attendance_service.get_attendance_history(
            {"group_id": group_id, "subject_id": subject_id, "date": date},
            current_user,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/students/{student_id}/monthly")
def get_monthly_attendance(student_id: str, month: int = Query(..., ge=1, le=12), year: Optional[int] = Query(None, ge=2000), current_user: dict = Depends(require_role("admin", "teacher", "parent"))):
    try:
        return attendance_service.get_student_monthly_summary(student_id, current_user, month=month, year=year)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
