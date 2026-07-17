from datetime import datetime, date

from bson import ObjectId

from src.config.database import db, serialize_doc, serialize_list
from src.modules.notifications import notifications_service
from src.modules.users import users_service


def _resolve_object_id(value: str, field_name: str):
    try:
        return ObjectId(value)
    except Exception:
        raise ValueError(f"Invalid {field_name} format")


def create_attendance(records: list, current_user: dict | None = None) -> dict:
    if not records:
        raise ValueError("At least one attendance record is required")

    created_records = []
    notification_results = []

    for item in records:
        student_id = _resolve_object_id(item.student_id, "student_id")
        subject_id = _resolve_object_id(item.subject_id, "subject_id")

        student = db.users.find_one({"_id": student_id, "role": "student", "active": True})
        if not student:
            raise ValueError(f"Student not found or inactive: {item.student_id}")

        subject = db.subjects.find_one({"_id": subject_id})
        if not subject:
            raise ValueError(f"Subject not found: {item.subject_id}")

        group_oid = None
        if item.group_id:
            group_oid = _resolve_object_id(item.group_id, "group_id")
        elif student.get("group_id"):
            group_oid = student["group_id"]

        now = datetime.utcnow()
        attendance_doc = {
            "student_id": student_id,
            "subject_id": subject_id,
            "group_id": group_oid,
            "status": item.status,
            "note": item.note,
            "attendance_date": now,
            "recorded_at": now,
            "recorded_by": ObjectId(current_user["id"]) if current_user and current_user.get("id") else None,
            "created_at": now,
        }

        res = db.attendance.insert_one(attendance_doc)
        attendance_doc["_id"] = res.inserted_id
        created_records.append(serialize_doc(attendance_doc))

        if item.status == "absent":
            notification_results.append(
                notifications_service.send_absence_notification(
                    student=student,
                    subject=subject,
                    attendance=attendance_doc,
                    current_user=current_user,
                )
            )
        elif item.status == "tardiness":
            notification_results.append(
                notifications_service.send_tardiness_notification(
                    student=student,
                    subject=subject,
                    attendance=attendance_doc,
                    current_user=current_user,
                )
            )

    return {
        "message": "Attendance registered successfully",
        "created": len(created_records),
        "records": created_records,
        "notifications": notification_results,
    }


def _parse_date_filter(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        raise ValueError("Invalid date format. Use YYYY-MM-DD")


def _ensure_parent_can_access_student(student_id: str, current_user: dict):
    if current_user.get("role") != "parent":
        return

    children = users_service.get_children(current_user["id"])
    child_ids = {child["id"] for child in children}
    if student_id not in child_ids:
        raise ValueError("Unauthorized to view this student's attendance")


def _attach_related_fields(records: list) -> list:
    output = []
    for record in records:
        student = db.users.find_one({"_id": ObjectId(record.get("student_id"))}) if record.get("student_id") else None
        subject = db.subjects.find_one({"_id": ObjectId(record.get("subject_id"))}) if record.get("subject_id") else None
        group = db.groups.find_one({"_id": ObjectId(record.get("group_id"))}) if record.get("group_id") else None

        record["student_name"] = f"{student['first_name']} {student['last_name']}" if student else None
        record["subject_name"] = subject["name"] if subject else None
        record["group_name"] = group["name"] if group else None
        output.append(record)
    return output


def get_attendance_history(filters: dict, current_user: dict | None = None) -> list:
    query = {}

    if current_user.get("role") == "parent":
        children = users_service.get_children(current_user["id"])
        child_ids = [child["id"] for child in children]
        if not child_ids:
            return []
        if filters.get("student_id"):
            if filters["student_id"] not in child_ids:
                raise ValueError("Unauthorized to view this student's attendance")
            query["student_id"] = _resolve_object_id(filters["student_id"], "student_id")
        else:
            query["student_id"] = {"$in": [ObjectId(child_id) for child_id in child_ids]}
    elif filters.get("student_id"):
        student_oid = _resolve_object_id(filters["student_id"], "student_id")
        query["student_id"] = student_oid
        _ensure_parent_can_access_student(filters["student_id"], current_user)

    if filters.get("subject_id"):
        query["subject_id"] = _resolve_object_id(filters["subject_id"], "subject_id")

    if filters.get("group_id"):
        query["group_id"] = _resolve_object_id(filters["group_id"], "group_id")

    if filters.get("status"):
        query["status"] = filters["status"]

    if filters.get("date"):
        start = _parse_date_filter(filters["date"])
        end = start.replace(hour=23, minute=59, second=59, microsecond=999999)
        query["attendance_date"] = {"$gte": start, "$lte": end}

    records = list(db.attendance.find(query).sort([("attendance_date", -1), ("created_at", -1)]))
    return _attach_related_fields(serialize_list(records))


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
        status = record.get("status")
        if status in counts:
            counts[status] += 1

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
        "summary": counts,
        "total_records": len(records),
        "daily_records": by_day,
    }