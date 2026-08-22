from fastapi import APIRouter, Depends, HTTPException
from src.middleware.role_middleware import require_role
from src.modules.automated_system_CSV import readUser, students

router = APIRouter()

@router.post('/users', dependencies=[Depends(require_role('admin'))])
def run_users_automation():
    try:
        groups = readUser.main()
        # Count operations
        inserted = sum(len(g.get("insertar", [])) for k, g in groups.items() if k != "skipped")
        updated = sum(len(g.get("update", [])) for k, g in groups.items() if k != "skipped")
        deleted = sum(len(g.get("eliminar", [])) for k, g in groups.items() if k != "skipped")
        return {
            "message": "User CSV automation executed successfully",
            "summary": {
                "inserted": inserted,
                "updated": updated,
                "deleted": deleted
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/students', dependencies=[Depends(require_role('admin'))])
def run_students_automation():
    try:
        groups = students.main()
        inserted = len(groups.get("insertar", []))
        updated = len(groups.get("update", []))
        deleted = len(groups.get("eliminar", []))
        return {
            "message": "Student CSV automation executed successfully",
            "summary": {
                "inserted": inserted,
                "updated": updated,
                "deleted": deleted
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
