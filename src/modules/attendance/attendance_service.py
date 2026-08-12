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


def _resolve_session_metadata(student_oid: ObjectId, subject_oid: ObjectId, group_oid: ObjectId | None) -> dict:
    subject = db.subjects.find_one({"_id": subject_oid})

    group = None
    if group_oid:
        group = db.groups.find_one({"_id": group_oid})

    teacher_name = ""
    link_query = {
        "student_id": student_oid,
        "subject_id": subject_oid,
    }
    if group_oid:
        link_query["group_id"] = group_oid

    link = db.student_subjects.find_one(link_query)
    if link and link.get("teacher_id"):
        teacher = db.users.find_one({"_id": ObjectId(link["teacher_id"])})
        if teacher:
            teacher_name = f"{teacher['first_name']} {teacher['last_name']}"

    return {
        "subject_name": subject.get("name") if subject else None,
        "subject_code": subject.get("code") if subject else None,
        "teacher_name": teacher_name,
        "group_name": group.get("name") if group else None,
    }


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


def get_student_monthly_summary(student_id: str, current_user: dict | None = None, month: int | None = None, year: int | None = None) -> list:
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

    sessions = list(db.attendance.find({
        "records.student_id": student_oid,
        "attendance_date": {"$gte": start, "$lt": end},
    }).sort([("attendance_date", 1)]))

    results = []

    for session in sessions:
        record = next((r for r in session.get("records", []) if r.get("student_id") == student_oid), None)
        if not record:
            continue

        status = _normalize_status(record.get("status"))

        metadata = _resolve_session_metadata(
            student_oid=student_oid,
            subject_oid=session["subject_id"],
            group_oid=session.get("group_id"),
        )
        day_key = session["attendance_date"].strftime("%Y-%m-%d")

        results.append({
            "id": str(session["_id"]),
            "date": day_key,
            "status": status,
            "arrival_time": record.get("arrival_time"),
            "attendance_date": session["attendance_date"].isoformat(),
            "student_id": str(student_oid),
            "subject_id": str(session["subject_id"]) if session.get("subject_id") else None,
            "subject_name": metadata["subject_name"],
            "subject_code": metadata["subject_code"],
            "teacher_name": metadata["teacher_name"],
            "group_id": str(session["group_id"]) if session.get("group_id") else None,
            "group_name": metadata["group_name"],
        })

    return results
