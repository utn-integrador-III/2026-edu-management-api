from datetime import datetime

from bson import ObjectId

from src.config.database import db, serialize_doc
from src.modules.users import users_service


def _resolve_object_id(value: str, field_name: str):
    try:
        return ObjectId(value)
    except Exception:
        raise ValueError(f"Invalid {field_name} format")


def _parse_date(value: str, field_name: str):
    if not value:
        raise ValueError(f"{field_name} is required")
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        raise ValueError(f"Invalid {field_name} format. Use YYYY-MM-DD")


def _serialize_event(doc: dict) -> dict:
    event = serialize_doc(doc)
    if event.get("scope") is None:
        event["scope"] = "institution" if not event.get("group_id") else "group"
    return event


def create_event(data: dict, current_user: dict) -> dict:
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("title is required")

    start_date = _parse_date(data.get("start_date"), "start_date")
    end_date = None
    if data.get("end_date"):
        end_date = _parse_date(data.get("end_date"), "end_date")
        if end_date < start_date:
            raise ValueError("end_date must be greater than or equal to start_date")

    group_oid = None
    if data.get("group_id"):
        group_oid = _resolve_object_id(data["group_id"], "group_id")
        if not db.groups.find_one({"_id": group_oid}):
            raise ValueError("Group not found")

    event_doc = {
        "title": title,
        "description": (data.get("description") or "").strip() or None,
        "type": (data.get("type") or "event").strip(),
        "scope": "group" if group_oid else "institution",
        "group_id": group_oid,
        "start_date": start_date,
        "end_date": end_date or start_date,
        "active": True,
        "created_by": ObjectId(current_user["id"]) if current_user.get("id") else None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    res = db.calendar_events.insert_one(event_doc)
    event_doc["_id"] = res.inserted_id
    return _serialize_event(event_doc)


def get_events(filters: dict | None = None) -> list:
    filters = filters or {}
    query = {}

    if filters.get("group_id"):
        query["group_id"] = _resolve_object_id(filters["group_id"], "group_id")
    if filters.get("type"):
        query["type"] = filters["type"]
    if filters.get("active") is not None:
        query["active"] = filters["active"]
    if filters.get("date_from") or filters.get("date_to"):
        date_query = {}
        if filters.get("date_from"):
            date_query["$gte"] = _parse_date(filters["date_from"], "date_from")
        if filters.get("date_to"):
            date_query["$lte"] = _parse_date(filters["date_to"], "date_to")
        query["start_date"] = date_query

    events = list(db.calendar_events.find(query).sort([("start_date", -1), ("created_at", -1)]))
    return [_serialize_event(event) for event in events]


def get_student_events(student_id: str, current_user: dict | None = None) -> list:
    student_oid = _resolve_object_id(student_id, "student_id")
    student = db.users.find_one({"_id": student_oid, "role": "student", "active": True})
    if not student:
        raise ValueError("Student not found or inactive")

    if current_user and current_user.get("role") == "parent":
        children = users_service.get_children(current_user["id"])
        child_ids = {child["id"] for child in children}
        if student_id not in child_ids:
            raise ValueError("Unauthorized to view this student's events")

    today = datetime.utcnow().date()
    query = {
        "active": True,
        "$or": [
            {"group_id": None},
            {"group_id": student.get("group_id")},
        ],
        "end_date": {"$gte": datetime.combine(today, datetime.min.time())},
    }

    events = list(db.calendar_events.find(query).sort([("start_date", 1), ("created_at", -1)]))
    return [_serialize_event(event) for event in events]