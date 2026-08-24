from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.middleware.role_middleware import require_role
from src.modules.reports import reports_service

router = APIRouter()


@router.get("/groups/{group_id}/attendance/pdf")
def get_group_attendance_pdf(
    group_id: str,
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2000),
    _current_user: dict = Depends(require_role("admin", "teacher")),
):
    try:
        pdf_buffer, filename = reports_service.generate_group_attendance_pdf(group_id, month=month, year=year)
        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        detail = str(e)
        if "Group not found" in detail:
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)
