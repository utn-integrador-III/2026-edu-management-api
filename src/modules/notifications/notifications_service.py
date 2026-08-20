from datetime import datetime

from bson import ObjectId

from src.config.database import db, serialize_doc
from src.config.mailer import send_mail


def _resolve_object_id(value: str, field_name: str):
    try:
        return ObjectId(value)
    except Exception:
        raise ValueError(f"Invalid {field_name} format")


def _resolve_parent(student: dict):
    parent = None

    link = db.parent_students.find_one({"student_id": student["_id"]})
    if link:
        parent = db.users.find_one({"_id": link["parent_id"], "active": True, "role": "parent"})

    if not parent and student.get("parent_cedula"):
        parent = db.users.find_one({"id_number": student["parent_cedula"], "active": True, "role": "parent"})

    return parent


def _build_notification_payload(notification_type: str, student: dict, subject: dict, attendance: dict, current_user: dict | None):
    parent = _resolve_parent(student)
    if not parent:
        raise ValueError("Parent not found for the selected student")

    parent_name = f"{parent['first_name']} {parent['last_name']}"
    student_name = f"{student['first_name']} {student['last_name']}"
    subject_name = subject.get("name", "the subject")

    if notification_type == "absence":
        title = "EduConecta CR — Absence alert"
        body = f"We detected an absence for {student_name} in {subject_name}."
    else:
        recorded_at = attendance.get("recorded_at") or datetime.utcnow()
        if isinstance(recorded_at, datetime):
            time_text = recorded_at.strftime("%H:%M")
        else:
            time_text = str(recorded_at)
        title = "EduConecta CR — Tardiness alert"
        body = f"We detected a tardiness for {student_name} in {subject_name} at {time_text}."

    notification_doc = {
        "type": notification_type,
        "parent_id": parent["_id"],
        "student_id": student["_id"],
        "subject_id": subject["_id"],
        "attendance_id": attendance.get("_id"),
        "title": title,
        "body": body,
        "channel": "email",
        "status": "pending",
        "created_at": datetime.utcnow(),
        "created_by": ObjectId(current_user["id"]) if current_user and current_user.get("id") else None,
    }

    return parent, parent_name, notification_doc


def _send_notification(notification_type: str, student: dict, subject: dict, attendance: dict, current_user: dict | None):
    parent, parent_name, notification_doc = _build_notification_payload(notification_type, student, subject, attendance, current_user)

    recipient = parent.get("email")
    if not recipient:
        notification_doc["status"] = "skipped"
        notification_doc["reason"] = "Parent has no email address"
        res = db.notifications.insert_one(notification_doc)
        notification_doc["_id"] = res.inserted_id
        return serialize_doc(notification_doc)

    try:
        send_mail(
            to=recipient,
            subject=notification_doc["title"],
            html=f"""
                <p>Dear {parent_name},</p>
                <p>{notification_doc['body']}</p>
                <p>This notification was generated automatically by EduConecta CR.</p>
            """,
        )
        notification_doc["status"] = "sent"
    except Exception as exc:
        notification_doc["status"] = "failed"
        notification_doc["error"] = str(exc)

    res = db.notifications.insert_one(notification_doc)
    notification_doc["_id"] = res.inserted_id
    return serialize_doc(notification_doc)


def send_absence_notification(student: dict, subject: dict, attendance: dict, current_user: dict | None = None):
    return _send_notification("absence", student, subject, attendance, current_user)


def send_tardiness_notification(student: dict, subject: dict, attendance: dict, current_user: dict | None = None):
    return _send_notification("tardiness", student, subject, attendance, current_user)


def send_absence_by_ids(student_id: str, subject_id: str, attendance_id: str | None = None, current_user: dict | None = None):
    student_oid = _resolve_object_id(student_id, "student_id")
    subject_oid = _resolve_object_id(subject_id, "subject_id")

    student = db.users.find_one({"_id": student_oid, "role": "student", "active": True})
    if not student:
        raise ValueError("Student not found or inactive")

    subject = db.subjects.find_one({"_id": subject_oid})
    if not subject:
        raise ValueError("Subject not found")

    attendance = None
    if attendance_id:
        attendance = db.attendance.find_one({"_id": _resolve_object_id(attendance_id, "attendance_id")})
    if not attendance:
        attendance = {"_id": None, "recorded_at": datetime.utcnow()}

    return _send_notification("absence", student, subject, attendance, current_user)


def send_tardiness_by_ids(student_id: str, subject_id: str, attendance_id: str | None = None, current_user: dict | None = None):
    student_oid = _resolve_object_id(student_id, "student_id")
    subject_oid = _resolve_object_id(subject_id, "subject_id")

    student = db.users.find_one({"_id": student_oid, "role": "student", "active": True})
    if not student:
        raise ValueError("Student not found or inactive")

    subject = db.subjects.find_one({"_id": subject_oid})
    if not subject:
        raise ValueError("Subject not found")

    attendance = None
    if attendance_id:
        attendance = db.attendance.find_one({"_id": _resolve_object_id(attendance_id, "attendance_id")})
    if not attendance:
        attendance = {"_id": None, "recorded_at": datetime.utcnow()}

    return _send_notification("tardiness", student, subject, attendance, current_user)


def list_reminders(parent_id: str) -> list:
    """Devuelve todas las notificaciones de tipo calendar_reminder del encargado autenticado."""
    parent_oid = _resolve_object_id(parent_id, "parent_id")
    docs = list(
        db.notifications.find(
            {"parent_id": parent_oid, "type": "calendar_reminder"}
        ).sort("created_at", -1)
    )
    return [serialize_doc(doc) for doc in docs]


def mark_as_read(notification_id: str, parent_id: str) -> dict:
    """Marca una notificación como leída. Solo el encargado propietario puede hacerlo."""
    notif_oid = _resolve_object_id(notification_id, "notification_id")
    parent_oid = _resolve_object_id(parent_id, "parent_id")

    notification = db.notifications.find_one({"_id": notif_oid})
    if not notification:
        raise ValueError("Notification not found")

    if notification.get("parent_id") != parent_oid:
        raise ValueError("Unauthorized: this notification does not belong to you")

    db.notifications.update_one(
        {"_id": notif_oid},
        {"$set": {"read": True, "read_at": datetime.utcnow()}},
    )
    updated = db.notifications.find_one({"_id": notif_oid})
    return serialize_doc(updated)