import logging
from datetime import datetime, timedelta

from bson import ObjectId

from src.config.database import db
from src.config.mailer import send_mail

logger = logging.getLogger("calendar_reminders")


def _get_parents_for_institution() -> list[dict]:
    """Devuelve todos los encargados que tienen al menos un estudiante activo."""
    # Obtener todos los parent_id únicos con hijos activos
    active_student_ids = [
        doc["_id"] for doc in db.users.find({"role": "student", "active": True}, {"_id": 1})
    ]
    if not active_student_ids:
        return []

    links = db.parent_students.find({"student_id": {"$in": active_student_ids}})
    parent_ids = list({link["parent_id"] for link in links})
    if not parent_ids:
        return []

    parents = list(db.users.find({"_id": {"$in": parent_ids}, "role": "parent", "active": True}))
    return parents


def _get_parents_for_group(group_id: ObjectId) -> list[dict]:
    """Devuelve los encargados de estudiantes que pertenecen al grupo indicado."""
    student_ids = [
        doc["_id"] for doc in db.users.find(
            {"role": "student", "active": True, "group_id": group_id}, {"_id": 1}
        )
    ]
    if not student_ids:
        return []

    links = db.parent_students.find({"student_id": {"$in": student_ids}})
    parent_ids = list({link["parent_id"] for link in links})
    if not parent_ids:
        return []

    parents = list(db.users.find({"_id": {"$in": parent_ids}, "role": "parent", "active": True}))
    return parents


def _already_sent(event_id: ObjectId, parent_id: ObjectId) -> bool:
    """Verifica si ya existe un recordatorio para este par (evento, encargado)."""
    return db.notifications.find_one({
        "type": "calendar_reminder",
        "event_id": event_id,
        "parent_id": parent_id,
    }) is not None


def _build_email_html(parent_name: str, event: dict) -> str:
    start_date = event.get("start_date")
    if isinstance(start_date, datetime):
        date_str = start_date.strftime("%d/%m/%Y")
    else:
        date_str = str(start_date)

    start_time = event.get("start_time") or ""
    time_str = f" a las {start_time}" if start_time else ""
    location = event.get("location")
    location_str = f"<p><strong>Lugar:</strong> {location}</p>" if location else ""
    description = event.get("description")
    desc_str = f"<p>{description}</p>" if description else ""

    return f"""
        <p>Estimado/a {parent_name},</p>
        <p>Le recordamos que mañana se realizará el siguiente evento escolar:</p>
        <p><strong>{event.get('title', 'Evento')}</strong> — {date_str}{time_str}</p>
        {desc_str}
        {location_str}
        <p>Este recordatorio fue generado automáticamente por EduConecta CR.</p>
    """


def _send_reminder(event: dict, parent: dict) -> dict:
    """Envía correo y persiste el recordatorio como notificación. Retorna el doc insertado."""
    event_id: ObjectId = event["_id"]
    parent_id: ObjectId = parent["_id"]
    parent_name = f"{parent.get('first_name', '')} {parent.get('last_name', '')}".strip()

    start_date = event.get("start_date")
    if isinstance(start_date, datetime):
        date_label = start_date.strftime("%d/%m/%Y")
    else:
        date_label = str(start_date)

    title = f"EduConecta CR — Recordatorio: {event.get('title', 'Evento')}"
    body = f"Recordatorio del evento '{event.get('title')}' programado para el {date_label}."

    notification_doc = {
        "type": "calendar_reminder",
        "event_id": event_id,
        "parent_id": parent_id,
        "title": title,
        "body": body,
        "channel": "email",
        "read": False,
        "created_at": datetime.utcnow(),
    }

    recipient = parent.get("email")
    if not recipient:
        notification_doc["status"] = "skipped"
        notification_doc["reason"] = "El encargado no tiene correo electrónico registrado"
    else:
        try:
            send_mail(
                to=recipient,
                subject=title,
                html=_build_email_html(parent_name, event),
            )
            notification_doc["status"] = "sent"
        except Exception as exc:
            logger.warning("Error enviando correo a %s: %s", recipient, exc)
            notification_doc["status"] = "failed"
            notification_doc["error"] = str(exc)

    res = db.notifications.insert_one(notification_doc)
    notification_doc["_id"] = res.inserted_id
    return notification_doc


def run_calendar_reminders() -> dict:
    """
    Job principal. Busca eventos activos que inician en las próximas 24 horas,
    resuelve los encargados según el alcance y envía/persiste recordatorios.
    Retorna un resumen con conteos para logging.
    """
    now = datetime.utcnow()
    window_start = now
    window_end = now + timedelta(hours=24)

    logger.info(
        "Iniciando job calendar_reminders. Ventana: %s → %s",
        window_start.isoformat(),
        window_end.isoformat(),
    )

    events = list(db.calendar_events.find({
        "active": True,
        "start_date": {"$gte": window_start, "$lt": window_end},
    }))

    if not events:
        logger.info("No hay eventos próximos en las siguientes 24 horas.")
        return {"sent": 0, "skipped": 0, "failed": 0, "duplicated": 0}

    sent = skipped = failed = duplicated = 0

    for event in events:
        event_id: ObjectId = event["_id"]
        group_id = event.get("group_id")
        scope = event.get("scope") or ("group" if group_id else "institution")

        # Resolver encargados según alcance
        if scope == "institution" or group_id is None:
            parents = _get_parents_for_institution()
        else:
            parents = _get_parents_for_group(group_id)

        for parent in parents:
            parent_id: ObjectId = parent["_id"]

            # Deduplicación
            if _already_sent(event_id, parent_id):
                duplicated += 1
                continue

            result = _send_reminder(event, parent)

            if result["status"] == "sent":
                sent += 1
            elif result["status"] == "skipped":
                skipped += 1
            else:
                failed += 1

    logger.info(
        "Job calendar_reminders finalizado. Enviados: %d | Omitidos: %d | Fallidos: %d | Duplicados evitados: %d",
        sent, skipped, failed, duplicated,
    )
    return {"sent": sent, "skipped": skipped, "failed": failed, "duplicated": duplicated}
