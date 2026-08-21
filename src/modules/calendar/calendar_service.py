from datetime import datetime

from bson import ObjectId
from pymongo import ReturnDocument

from src.config.database import db, serialize_doc
from src.config.mailer import send_mail
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
    if "start_date" in event and isinstance(event["start_date"], str) and "T" in event["start_date"]:
        event["start_date"] = event["start_date"].split("T")[0]
    if "end_date" in event and isinstance(event["end_date"], str) and "T" in event["end_date"]:
        event["end_date"] = event["end_date"].split("T")[0]
    return event


def _is_event_creator_or_admin(event: dict, current_user: dict) -> bool:
    if not current_user:
        return False

    if current_user.get("role") == "admin":
        return True

    if current_user.get("role") != "teacher":
        return False

    created_by = event.get("created_by")
    if not created_by:
        return False

    try:
        current_user_oid = ObjectId(current_user["id"])
    except Exception:
        return False

    if isinstance(created_by, ObjectId):
        return created_by == current_user_oid
    return str(created_by) == str(current_user_oid)


def _get_group_recipient_emails(group_oid: ObjectId) -> list[str]:
    students = list(db.users.find({"group_id": group_oid, "role": "student", "active": True}))
    if not students:
        return []

    emails = set()
    student_ids = []
    parent_cedulas = set()

    for student in students:
        student_ids.append(student["_id"])
        if student.get("email"):
            emails.add(student["email"].strip().lower())
        if student.get("parent_cedula"):
            parent_cedulas.add(student["parent_cedula"])

    parent_ids = set()
    links = list(db.parent_students.find({"student_id": {"$in": student_ids}}))
    for link in links:
        if link.get("parent_id"):
            parent_ids.add(link["parent_id"])
        if link.get("parent_cedula"):
            parent_cedulas.add(link["parent_cedula"])

    parent_query = {"role": "parent", "active": True}
    or_conditions = []
    if parent_ids:
        or_conditions.append({"_id": {"$in": list(parent_ids)}})
    if parent_cedulas:
        or_conditions.append({"id_number": {"$in": list(parent_cedulas)}})
    if not or_conditions:
        return sorted(emails)

    parent_query["$or"] = or_conditions
    parents = list(db.users.find(parent_query))
    for parent in parents:
        if parent.get("email"):
            emails.add(parent["email"].strip().lower())

    return sorted(emails)


def _format_event_date_range(event: dict) -> str:
    start = event.get("start_date")
    end = event.get("end_date")

    if isinstance(start, datetime):
        start_text = start.strftime("%Y-%m-%d")
    else:
        start_text = str(start) if start else ""

    if isinstance(end, datetime):
        end_text = end.strftime("%Y-%m-%d")
    else:
        end_text = str(end) if end else start_text

    if start_text == end_text:
        return start_text
    return f"{start_text} to {end_text}"


def _notify_group_event_change(event: dict, action: str) -> dict:
    group_id = event.get("group_id")
    if not group_id:
        return {"attempted": False, "sent": 0, "failed": 0, "reason": "Event has no group"}

    try:
        group_oid = ObjectId(group_id) if not isinstance(group_id, ObjectId) else group_id
    except Exception:
        return {"attempted": False, "sent": 0, "failed": 0, "reason": "Invalid group ID in event"}

    recipients = _get_group_recipient_emails(group_oid)
    if not recipients:
        return {"attempted": True, "sent": 0, "failed": 0, "reason": "No recipients with email"}

    group = db.groups.find_one({"_id": group_oid})
    subject_name = None
    if event.get("subject_id"):
        subject = db.subjects.find_one({"_id": event["subject_id"]})
        if subject:
            subject_name = subject.get("name")

    event_title = event.get("title", "Untitled event")
    event_type = event.get("event_type", "academic")
    event_dates = _format_event_date_range(event)
    group_name = group.get("name") if group else "N/A"
    subject_line = f"EduConecta CR - Calendar event {'updated' if action == 'updated' else 'cancelled'}"

    if action == "updated":
        body = (
            f"<p>The event <strong>{event_title}</strong> was updated.</p>"
            f"<ul>"
            f"<li>Type: {event_type}</li>"
            f"<li>Date: {event_dates}</li>"
            f"<li>Group: {group_name}</li>"
            f"<li>Subject: {subject_name or 'N/A'}</li>"
            f"<li>Location: {event.get('location') or 'N/A'}</li>"
            f"</ul>"
        )
    else:
        body = (
            f"<p>The event <strong>{event_title}</strong> was cancelled.</p>"
            f"<ul>"
            f"<li>Type: {event_type}</li>"
            f"<li>Date: {event_dates}</li>"
            f"<li>Group: {group_name}</li>"
            f"<li>Subject: {subject_name or 'N/A'}</li>"
            f"</ul>"
        )

    sent = 0
    failed = 0
    for email in recipients:
        try:
            send_mail(
                to=email,
                subject=subject_line,
                html=(
                    f"<p>Dear family,</p>"
                    f"{body}"
                    f"<p>This notification was generated automatically by EduConecta CR.</p>"
                ),
            )
            sent += 1
        except Exception:
            failed += 1

    return {"attempted": True, "sent": sent, "failed": failed}


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

    subject_oid = None
    if data.get("subject_id"):
        subject_oid = _resolve_object_id(data["subject_id"], "subject_id")
        if not db.subjects.find_one({"_id": subject_oid}):
            raise ValueError("Subject not found")

    event_doc = {
        "title": title,
        "description": (data.get("description") or "").strip() or None,
        "event_type": (data.get("event_type") or "academico").strip(),
        "subject_id": subject_oid, 
        "start_time": data.get("start_time"),
        "end_time": data.get("end_time"),
        "location": data.get("location"),
        "scope": "group" if group_oid else "institution",
        "group_id": group_oid,
        "start_date": start_date,
        "end_date": end_date or start_date,
        "active": True,
        "created_by": ObjectId(current_user["id"]) if current_user.get("id") else None,
        "organizer_name": current_user.get("first_name"),
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
    if filters.get("event_type"):
        query["event_type"] = filters["event_type"]
    if filters.get("active") is not None:
        query["active"] = filters["active"]
    date_from = None
    date_to = None

    if filters.get("month"):
        month = int(filters["month"])
        year = int(filters.get("year") or datetime.utcnow().year)
        if month < 1 or month > 12:
            raise ValueError("month must be between 1 and 12")

        date_from = datetime(year, month, 1)
        if month == 12:
            date_to = datetime(year + 1, 1, 1)
        else:
            date_to = datetime(year, month + 1, 1)
    elif filters.get("date_from") or filters.get("date_to"):
        date_query = {}
        if filters.get("date_from"):
            date_from = _parse_date(filters["date_from"], "date_from")
            date_query["$gte"] = date_from
        if filters.get("date_to"):
            date_to = _parse_date(filters["date_to"], "date_to")
            date_query["$lte"] = date_to
        query["start_date"] = date_query

    if date_from and date_to and filters.get("month"):
        query["start_date"] = {"$gte": date_from, "$lt": date_to}

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


def update_event(event_id: str, data: dict, current_user: dict) -> dict:
    event_oid = _resolve_object_id(event_id, "event_id")
    event = db.calendar_events.find_one({"_id": event_oid})
    if not event:
        raise ValueError("Event not found")

    if not _is_event_creator_or_admin(event, current_user):
        raise ValueError("Unauthorized to edit this event")

    if not data:
        raise ValueError("No fields provided to update")

    update_fields = {}

    if "title" in data:
        title = (data.get("title") or "").strip()
        if not title:
            raise ValueError("title cannot be empty")
        update_fields["title"] = title

    if "description" in data:
        update_fields["description"] = (data.get("description") or "").strip() or None

    for key in ["event_type", "start_time", "end_time", "location"]:
        if key in data:
            update_fields[key] = data.get(key)

    if "subject_id" in data:
        if data.get("subject_id") is None:
            update_fields["subject_id"] = None
        else:
            subject_oid = _resolve_object_id(data["subject_id"], "subject_id")
            if not db.subjects.find_one({"_id": subject_oid}):
                raise ValueError("Subject not found")
            update_fields["subject_id"] = subject_oid

    if "group_id" in data:
        if data.get("group_id") is None:
            update_fields["group_id"] = None
            update_fields["scope"] = "institution"
        else:
            group_oid = _resolve_object_id(data["group_id"], "group_id")
            if not db.groups.find_one({"_id": group_oid}):
                raise ValueError("Group not found")
            update_fields["group_id"] = group_oid
            update_fields["scope"] = "group"

    start_date = event.get("start_date")
    end_date = event.get("end_date")
    if "start_date" in data:
        start_date = _parse_date(data.get("start_date"), "start_date")
        update_fields["start_date"] = start_date
    if "end_date" in data:
        if data.get("end_date") is None:
            end_date = start_date
        else:
            end_date = _parse_date(data.get("end_date"), "end_date")
        update_fields["end_date"] = end_date

    if start_date and end_date and end_date < start_date:
        raise ValueError("end_date must be greater than or equal to start_date")

    update_fields["updated_at"] = datetime.utcnow()

    updated = db.calendar_events.find_one_and_update(
        {"_id": event_oid},
        {"$set": update_fields},
        return_document=ReturnDocument.AFTER,
    )

    notifications = _notify_group_event_change(updated, "updated")
    return {
        "message": "Event updated successfully",
        "event": _serialize_event(updated),
        "notifications": notifications,
    }


def delete_event(event_id: str, current_user: dict) -> dict:
    event_oid = _resolve_object_id(event_id, "event_id")
    event = db.calendar_events.find_one({"_id": event_oid})
    if not event:
        raise ValueError("Event not found")

    if not _is_event_creator_or_admin(event, current_user):
        raise ValueError("Unauthorized to delete this event")

    now = datetime.utcnow()
    deleted = db.calendar_events.find_one_and_update(
        {"_id": event_oid},
        {
            "$set": {
                "active": False,
                "deleted_at": now,
                "updated_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    notifications = _notify_group_event_change(deleted, "cancelled")
    return {
        "message": "Event deleted successfully",
        "event": _serialize_event(deleted),
        "notifications": notifications,
    }