from datetime import datetime

from bson import ObjectId
from pymongo import ReturnDocument

from src.config.database import db, serialize_doc
from src.modules.notifications import notifications_service
from src.modules.users import users_service


STATUS_ALIASES = {
    "presente": "presente",
    "present": "presente",
    "ausente": "ausente",
    "absent": "ausente",
    "tardanza": "tardanza",
    "tardiness": "tardanza",
}


def _resolve_object_id(value: str, field_name: str):
    try:
        return ObjectId(value)
    except Exception:
        raise ValueError(f"Invalid {field_name} format")


def _parse_date(value: str, field_name: str = "date"):
    if not value:
        raise ValueError(f"{field_name} is required")
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        raise ValueError(f"Invalid {field_name} format. Use YYYY-MM-DD")


def _normalize_status(value: str) -> str:
    if not value:
        raise ValueError("status is required")

    normalized = STATUS_ALIASES.get(value.lower())
    if not normalized:
        raise ValueError("Invalid status value")
    return normalized


def _serialize_session(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "date": doc["attendance_date"].strftime("%Y-%m-%d"),
        "group_id": str(doc["group_id"]),
        "subject_id": str(doc["subject_id"]),
        "records": [
            {
                "student_id": str(r["student_id"]),
                "status": r["status"],
                "arrival_time": r.get("arrival_time"),
            }
            for r in doc.get("records", [])
        ],
    }


def create_attendance(body, current_user: dict | None = None) -> dict:
    if not body.records:
        raise ValueError("At least one attendance record is required")

    attendance_date = _parse_date(body.date)
    group_oid = _resolve_object_id(body.group_id, "group_id")
    subject_oid = _resolve_object_id(body.subject_id, "subject_id")

    if not db.groups.find_one({"_id": group_oid}):
        raise ValueError(f"Group not found: {body.group_id}")

    subject = db.subjects.find_one({"_id": subject_oid})
    if not subject:
        raise ValueError(f"Subject not found: {body.subject_id}")

    now = datetime.utcnow()
    record_docs = []
    notification_results = []

    for item in body.records:
        student_oid = _resolve_object_id(item.student_id, "student_id")
        student = db.users.find_one({"_id": student_oid, "role": "student", "active": True})
        if not student:
            raise ValueError(f"Student not found or inactive: {item.student_id}")

        status = _normalize_status(item.status)

        record_docs.append({
            "student_id": student_oid,
            "status": status,
            "arrival_time": item.arrival_time,
        })

        if status == "ausente":
            notification_results.append(
                notifications_service.send_absence_notification(
                    student=student, subject=subject, attendance={"recorded_at": now}, current_user=current_user,
                )
            )
        elif status == "tardanza":
            notification_results.append(
                notifications_service.send_tardiness_notification(
                    student=student, subject=subject, attendance={"recorded_at": now}, current_user=current_user,
                )
            )

    session = db.attendance.find_one_and_update(
        {"attendance_date": attendance_date, "group_id": group_oid, "subject_id": subject_oid},
        {
            "$set": {
                "attendance_date": attendance_date,
                "group_id": group_oid,
                "subject_id": subject_oid,
                "records": record_docs,
                "recorded_by": ObjectId(current_user["id"]) if current_user and current_user.get("id") else None,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )

    return {
        "message": "Attendance registered successfully",
        "session": _serialize_session(session),
        "notifications": notification_results,
    }


def _ensure_parent_can_access_student(student_id: str, current_user: dict):
    if current_user.get("role") != "parent":
        return

    children = users_service.get_children(current_user["id"])
    child_ids = {child["id"] for child in children}
    if student_id not in child_ids:
        raise ValueError("Unauthorized to view this student's attendance")


def get_attendance_history(filters: dict, current_user: dict | None = None) -> list:
    query = {}

    if filters.get("group_id"):
        query["group_id"] = _resolve_object_id(filters["group_id"], "group_id")

    if filters.get("subject_id"):
        query["subject_id"] = _resolve_object_id(filters["subject_id"], "subject_id")

    if filters.get("date"):
        query["attendance_date"] = _parse_date(filters["date"])

    if current_user and current_user.get("role") == "parent":
        children = users_service.get_children(current_user["id"])
        child_ids = [ObjectId(child["id"]) for child in children]
        if not child_ids:
            return []
        query["records.student_id"] = {"$in": child_ids}

    sessions = list(db.attendance.find(query).sort("attendance_date", -1))
    return [_serialize_session(s) for s in sessions]


def get_student_monthly_summary(student_id: str, current_user: dict | None = None, month: int | None = None, year: int | None = None) -> dict:
    student_oid = _resolve_object_id(student_id, "student_id")
    _ensure_parent_can_access_student(student_id, current_user)

    student = db.users.find_one({"_id": student_oid, "role": "student", "active": True})
    if not student:
        raise ValueError("Student not found or inactive")

    now = datetime.utcnow()
    month = month or now.month
    year = year or now.year

    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)

    query = {
        "student_id": student_oid,
        "attendance_date": {"$gte": start, "$lt": end},
    }
    records = list(db.attendance.find(query).sort([("attendance_date", 1)]))

    counts = {"present": 0, "absent": 0, "tardiness": 0}
    by_day = {}

    for record in records:
        try:
            status = _normalize_status(record.get("status"))
        except ValueError:
            status = record.get("status")

        if status == "presente":
            counts["present"] += 1
        elif status == "ausente":
            counts["absent"] += 1
        elif status == "tardanza":
            counts["tardiness"] += 1

        day_key = record["attendance_date"].strftime("%Y-%m-%d")
        by_day.setdefault(day_key, [])
        by_day[day_key].append({
            "id": str(record["_id"]),
            "status": record.get("status"),
            "attendance_date": record["attendance_date"].isoformat(),
            "subject_id": str(record["subject_id"]) if record.get("subject_id") else None,
            "group_id": str(record["group_id"]) if record.get("group_id") else None,
        })

    return {
        "student": serialize_doc(student),
        "period": {"month": month, "year": year},
        "summary": {
            "presente": counts["present"],
            "ausente": counts["absent"],
            "tardanza": counts["tardiness"],
            "present": counts["present"],
            "absent": counts["absent"],
            "tardiness": counts["tardiness"],
        },
        "total_records": len(records),
        "daily_records": by_day,
    }
