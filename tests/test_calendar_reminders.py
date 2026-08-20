"""
Tests para US-R3-BE-025: Servicio de Recordatorios Automáticos.
Cubre el background job calendar_reminders y los endpoints
GET /api/v1/notifications y PUT /api/v1/notifications/{id}/read.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from bson import ObjectId

from src.config.database import db
from src.jobs.calendar_reminders import run_calendar_reminders


# ---------------------------------------------------------------------------
# Helpers de fixtures
# ---------------------------------------------------------------------------

def _insert_parent(test_db, suffix="a") -> ObjectId:
    return test_db.users.insert_one({
        "id_number": f"parent_{suffix}",
        "first_name": "Encargado",
        "last_name": suffix.upper(),
        "email": f"parent_{suffix}@example.com",
        "role": "parent",
        "active": True,
        "created_at": datetime.utcnow(),
    }).inserted_id


def _insert_student(test_db, group_id: ObjectId, suffix="a") -> ObjectId:
    return test_db.users.insert_one({
        "id_number": f"student_{suffix}",
        "first_name": "Estudiante",
        "last_name": suffix.upper(),
        "role": "student",
        "active": True,
        "group_id": group_id,
        "created_at": datetime.utcnow(),
    }).inserted_id


def _link(test_db, parent_id: ObjectId, student_id: ObjectId):
    test_db.parent_students.insert_one({
        "parent_id": parent_id,
        "student_id": student_id,
    })


def _insert_event(test_db, scope: str, group_id=None, hours_from_now: float = 2.0) -> ObjectId:
    start = datetime.utcnow() + timedelta(hours=hours_from_now)
    doc = {
        "title": f"Evento {scope}",
        "description": "Descripción de prueba",
        "scope": scope,
        "group_id": ObjectId(group_id) if group_id else None,
        "start_date": start,
        "end_date": start,
        "active": True,
        "created_at": datetime.utcnow(),
    }
    return test_db.calendar_events.insert_one(doc).inserted_id


# ---------------------------------------------------------------------------
# Tests del background job
# ---------------------------------------------------------------------------

def test_run_reminder_institution_scope(test_db):
    """Evento institucional → recordatorio enviado a todos los encargados con hijos activos."""
    group_id = test_db.groups.insert_one({"name": "TEST-1", "level": "Primaria"}).inserted_id

    parent_a_id = _insert_parent(test_db, "inst_a")
    parent_b_id = _insert_parent(test_db, "inst_b")
    student_a_id = _insert_student(test_db, group_id, "inst_a")
    student_b_id = _insert_student(test_db, group_id, "inst_b")
    _link(test_db, parent_a_id, student_a_id)
    _link(test_db, parent_b_id, student_b_id)

    _insert_event(test_db, scope="institution")

    with patch("src.jobs.calendar_reminders.send_mail"):
        result = run_calendar_reminders()

    assert result["sent"] + result["skipped"] == 2
    assert result["failed"] == 0
    assert test_db.notifications.count_documents({"type": "calendar_reminder"}) == 2


def test_run_reminder_group_scope(test_db):
    """Evento de grupo → solo los encargados de ese grupo reciben recordatorio."""
    group_a_id = test_db.groups.insert_one({"name": "TEST-A", "level": "Primaria"}).inserted_id
    group_b_id = test_db.groups.insert_one({"name": "TEST-B", "level": "Primaria"}).inserted_id

    parent_a_id = _insert_parent(test_db, "grp_a")
    parent_b_id = _insert_parent(test_db, "grp_b")
    student_a_id = _insert_student(test_db, group_a_id, "grp_a")
    student_b_id = _insert_student(test_db, group_b_id, "grp_b")
    _link(test_db, parent_a_id, student_a_id)
    _link(test_db, parent_b_id, student_b_id)

    _insert_event(test_db, scope="group", group_id=str(group_a_id))

    with patch("src.jobs.calendar_reminders.send_mail"):
        result = run_calendar_reminders()

    # Solo el encargado del grupo A debe recibir recordatorio
    assert result["sent"] + result["skipped"] == 1
    notifs = list(test_db.notifications.find({"type": "calendar_reminder"}))
    assert len(notifs) == 1
    assert notifs[0]["parent_id"] == parent_a_id


def test_no_duplicate_reminders(test_db):
    """El job no debe crear un segundo recordatorio si ya existe uno para (evento, encargado)."""
    group_id = test_db.groups.insert_one({"name": "TEST-DUP", "level": "Primaria"}).inserted_id
    parent_id = _insert_parent(test_db, "dup")
    student_id = _insert_student(test_db, group_id, "dup")
    _link(test_db, parent_id, student_id)

    _insert_event(test_db, scope="institution")

    with patch("src.jobs.calendar_reminders.send_mail"):
        result1 = run_calendar_reminders()
        result2 = run_calendar_reminders()

    total_notifs = test_db.notifications.count_documents({"type": "calendar_reminder"})
    assert total_notifs == 1
    assert result2["duplicated"] == 1
    assert result2["sent"] + result2["skipped"] == 0


def test_no_events_in_window(test_db):
    """Si no hay eventos en las próximas 24h, no se genera ninguna notificación."""
    group_id = test_db.groups.insert_one({"name": "TEST-WIN", "level": "Primaria"}).inserted_id
    parent_id = _insert_parent(test_db, "win")
    student_id = _insert_student(test_db, group_id, "win")
    _link(test_db, parent_id, student_id)

    # Evento en 48 horas (fuera de la ventana de 24h)
    _insert_event(test_db, scope="institution", hours_from_now=48)

    with patch("src.jobs.calendar_reminders.send_mail"):
        result = run_calendar_reminders()

    assert result == {"sent": 0, "skipped": 0, "failed": 0, "duplicated": 0}
    assert test_db.notifications.count_documents({"type": "calendar_reminder"}) == 0


def test_reminder_skipped_when_no_email(test_db):
    """Si el encargado no tiene email, se guarda notificación con status 'skipped'."""
    group_id = test_db.groups.insert_one({"name": "TEST-SKIP", "level": "Primaria"}).inserted_id
    parent_id = test_db.users.insert_one({
        "id_number": "parent_noemail",
        "first_name": "Sin",
        "last_name": "Correo",
        # Sin campo "email"
        "role": "parent",
        "active": True,
        "created_at": datetime.utcnow(),
    }).inserted_id
    student_id = _insert_student(test_db, group_id, "noemail")
    _link(test_db, parent_id, student_id)

    _insert_event(test_db, scope="institution")

    result = run_calendar_reminders()

    assert result["skipped"] == 1
    notif = test_db.notifications.find_one({"type": "calendar_reminder", "parent_id": parent_id})
    assert notif is not None
    assert notif["status"] == "skipped"


# ---------------------------------------------------------------------------
# Tests de endpoints REST
# ---------------------------------------------------------------------------

def test_list_reminders_endpoint_empty(client, seed_users, parent_headers):
    """GET /api/v1/notifications retorna lista vacía cuando no hay recordatorios."""
    response = client.get("/api/v1/notifications/", headers=parent_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_list_reminders_endpoint_returns_reminders(client, seed_users, parent_headers, test_db):
    """GET /api/v1/notifications retorna los recordatorios del encargado autenticado."""
    parent_oid = ObjectId(seed_users["parent_id"])

    test_db.notifications.insert_one({
        "type": "calendar_reminder",
        "event_id": ObjectId(),
        "parent_id": parent_oid,
        "title": "Recordatorio Test",
        "body": "Evento mañana",
        "channel": "email",
        "status": "sent",
        "read": False,
        "created_at": datetime.utcnow(),
    })

    response = client.get("/api/v1/notifications/", headers=parent_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Recordatorio Test"
    assert data[0]["read"] is False


def test_list_reminders_only_own(client, seed_users, parent_headers, test_db):
    """GET /api/v1/notifications no devuelve notificaciones de otros encargados."""
    other_parent_id = test_db.users.insert_one({
        "id_number": "other_parent",
        "first_name": "Otro",
        "last_name": "Encargado",
        "role": "parent",
        "active": True,
    }).inserted_id

    test_db.notifications.insert_one({
        "type": "calendar_reminder",
        "event_id": ObjectId(),
        "parent_id": other_parent_id,
        "title": "Otro recordatorio",
        "body": "No debería aparecer",
        "channel": "email",
        "status": "sent",
        "read": False,
        "created_at": datetime.utcnow(),
    })

    response = client.get("/api/v1/notifications/", headers=parent_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_list_reminders_forbidden_for_teacher(client, seed_users, teacher_headers):
    """GET /api/v1/notifications retorna 403 para rol teacher."""
    response = client.get("/api/v1/notifications/", headers=teacher_headers)
    assert response.status_code == 403


def test_mark_as_read_endpoint(client, seed_users, parent_headers, test_db):
    """PUT /api/v1/notifications/{id}/read actualiza read=True."""
    parent_oid = ObjectId(seed_users["parent_id"])
    notif_id = test_db.notifications.insert_one({
        "type": "calendar_reminder",
        "event_id": ObjectId(),
        "parent_id": parent_oid,
        "title": "Pendiente de lectura",
        "body": "Evento mañana",
        "channel": "email",
        "status": "sent",
        "read": False,
        "created_at": datetime.utcnow(),
    }).inserted_id

    response = client.put(f"/api/v1/notifications/{str(notif_id)}/read", headers=parent_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["read"] is True
    assert "read_at" in data

    # Verificar persistencia en BD
    updated = test_db.notifications.find_one({"_id": notif_id})
    assert updated["read"] is True


def test_mark_as_read_wrong_parent(client, seed_users, parent_headers, test_db):
    """PUT /api/v1/notifications/{id}/read devuelve 400 si la notificación es de otro encargado."""
    other_parent_id = test_db.users.insert_one({
        "id_number": "other_p2",
        "first_name": "Otro",
        "last_name": "Encargado",
        "role": "parent",
        "active": True,
    }).inserted_id

    notif_id = test_db.notifications.insert_one({
        "type": "calendar_reminder",
        "event_id": ObjectId(),
        "parent_id": other_parent_id,
        "title": "Notificación ajena",
        "body": "...",
        "channel": "email",
        "status": "sent",
        "read": False,
        "created_at": datetime.utcnow(),
    }).inserted_id

    response = client.put(f"/api/v1/notifications/{str(notif_id)}/read", headers=parent_headers)
    assert response.status_code == 400
    assert "does not belong to you" in response.json()["detail"]


def test_mark_as_read_not_found(client, seed_users, parent_headers):
    """PUT /api/v1/notifications/{id}/read devuelve 400 si la notificación no existe."""
    fake_id = str(ObjectId())
    response = client.put(f"/api/v1/notifications/{fake_id}/read", headers=parent_headers)
    assert response.status_code == 400
    assert "Notification not found" in response.json()["detail"]
