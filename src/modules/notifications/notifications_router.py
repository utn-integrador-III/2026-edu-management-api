from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.middleware.role_middleware import require_role
from src.modules.notifications import notifications_service

router = APIRouter()


class NotificationRequest(BaseModel):
    student_id: str = Field(..., min_length=1)
    subject_id: str = Field(..., min_length=1)
    attendance_id: str | None = None


@router.post("/send-absence")
def send_absence(body: NotificationRequest, current_user: dict = Depends(require_role("admin", "teacher"))):
    try:
        return notifications_service.send_absence_by_ids(
            student_id=body.student_id,
            subject_id=body.subject_id,
            attendance_id=body.attendance_id,
            current_user=current_user,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/send-tardiness")
def send_tardiness(body: NotificationRequest, current_user: dict = Depends(require_role("admin", "teacher"))):
    try:
        return notifications_service.send_tardiness_by_ids(
            student_id=body.student_id,
            subject_id=body.subject_id,
            attendance_id=body.attendance_id,
            current_user=current_user,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/")
def get_reminders(current_user: dict = Depends(require_role("parent"))):
    """Lista los recordatorios de calendario del encargado autenticado."""
    return notifications_service.list_reminders(current_user["id"])


@router.put("/{notification_id}/read")
def read_reminder(notification_id: str, current_user: dict = Depends(require_role("parent"))):
    """Marca una notificación de calendario como leída."""
    try:
        return notifications_service.mark_as_read(notification_id, current_user["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
