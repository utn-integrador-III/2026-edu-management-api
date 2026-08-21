import pytest
from bson import ObjectId
from src.config.database import db
from datetime import datetime
from jose import jwt
import os

def test_create_event_success(client, seed_users, teacher_headers):
    response = client.post("/api/v1/calendar/events", headers=teacher_headers, json={
        "title": "Examen de Matematicas",
        "description": "Examen correspondiente al I Trimestre",
        "event_type": "examen",
        "start_date": "2026-08-15",
        "end_date": "2026-08-15",
        "group_id": seed_users["group_id"],
        "subject_id": seed_users["subject_id"]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Examen de Matematicas"
    assert data["scope"] == "group"
    assert data["group_id"] == seed_users["group_id"]

def test_create_event_institutional(client, seed_users, admin_headers):
    response = client.post("/api/v1/calendar/events", headers=admin_headers, json={
        "title": "Feriado del Dia de las Madres",
        "description": "No hay lecciones en todo el centro educativo",
        "event_type": "feriado",
        "start_date": "2026-08-15"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "institution"
    assert data["group_id"] is None

def test_create_event_invalid_dates(client, seed_users, teacher_headers):
    response = client.post("/api/v1/calendar/events", headers=teacher_headers, json={
        "title": "Examen Invalido",
        "start_date": "2026-08-15",
        "end_date": "2026-08-10"
    })
    assert response.status_code == 400
    assert "end_date must be greater than or equal to start_date" in response.json()["detail"]

def test_get_events_filters(client, seed_users, teacher_headers):
    db.calendar_events.insert_many([
        {
            "title": "Evento Inst",
            "scope": "institution",
            "start_date": pytest.importorskip("datetime").datetime(2026, 8, 1),
            "active": True
        },
        {
            "title": "Evento Group",
            "scope": "group",
            "group_id": ObjectId(seed_users["group_id"]),
            "start_date": pytest.importorskip("datetime").datetime(2026, 8, 2),
            "active": True
        }
    ])

    response = client.get(f"/api/v1/calendar/events?group_id={seed_users['group_id']}", headers=teacher_headers)
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    assert events[0]["title"] == "Evento Group"

def test_get_student_events(client, seed_users, parent_headers):
    db.calendar_events.insert_many([
        {
            "title": "Dia de la Independencia",
            "scope": "institution",
            "group_id": None,
            "start_date": pytest.importorskip("datetime").datetime(2026, 9, 15),
            "end_date": pytest.importorskip("datetime").datetime(2026, 9, 15),
            "active": True
        },
        {
            "title": "Reunion de Aula 10-A",
            "scope": "group",
            "group_id": ObjectId(seed_users["group_id"]),
            "start_date": pytest.importorskip("datetime").datetime(2026, 9, 20),
            "end_date": pytest.importorskip("datetime").datetime(2026, 9, 20),
            "active": True
        },
        {
            "title": "Reunion de Aula Otro Grupo",
            "scope": "group",
            "group_id": ObjectId(),
            "start_date": pytest.importorskip("datetime").datetime(2026, 9, 20),
            "end_date": pytest.importorskip("datetime").datetime(2026, 9, 20),
            "active": True
        }
    ])

    response = client.get(f"/api/v1/calendar/students/{seed_users['student_id']}/events", headers=parent_headers)
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 2
    titles = [e["title"] for e in events]
    assert "Dia de la Independencia" in titles
    assert "Reunion de Aula 10-A" in titles
    assert "Reunion de Aula Otro Grupo" not in titles


def _create_token(user_id: str, role: str, first_name: str = "User"):
    return jwt.encode(
        {
            "id": user_id,
            "role": role,
            "first_name": first_name,
            "mustChangePassword": False,
        },
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )


def test_update_event_creator_teacher_success(client, seed_users, teacher_headers):
    event_id = db.calendar_events.insert_one({
        "title": "Acto civico",
        "description": "Original",
        "event_type": "actividad",
        "start_date": datetime(2026, 8, 20),
        "end_date": datetime(2026, 8, 20),
        "group_id": ObjectId(seed_users["group_id"]),
        "subject_id": ObjectId(seed_users["subject_id"]),
        "scope": "group",
        "active": True,
        "created_by": ObjectId(seed_users["teacher_id"]),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }).inserted_id

    response = client.put(
        f"/api/v1/calendar/events/{event_id}",
        headers=teacher_headers,
        json={"title": "Acto civico actualizado", "location": "Gimnasio"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Event updated successfully"
    assert data["event"]["title"] == "Acto civico actualizado"
    assert data["notifications"]["attempted"] is True
    assert data["notifications"]["sent"] >= 1


def test_update_event_non_creator_teacher_forbidden(client, seed_users, teacher_headers):
    event_id = db.calendar_events.insert_one({
        "title": "Evento admin",
        "event_type": "actividad",
        "start_date": datetime(2026, 8, 20),
        "end_date": datetime(2026, 8, 20),
        "group_id": ObjectId(seed_users["group_id"]),
        "scope": "group",
        "active": True,
        "created_by": ObjectId(seed_users["admin_id"]),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }).inserted_id

    response = client.put(
        f"/api/v1/calendar/events/{event_id}",
        headers=teacher_headers,
        json={"title": "Cambio no autorizado"},
    )

    assert response.status_code == 403
    assert "Unauthorized" in response.json()["detail"]


def test_update_event_admin_can_edit_any_event(client, seed_users, admin_headers):
    event_id = db.calendar_events.insert_one({
        "title": "Evento docente",
        "event_type": "actividad",
        "start_date": datetime(2026, 8, 22),
        "end_date": datetime(2026, 8, 22),
        "group_id": ObjectId(seed_users["group_id"]),
        "scope": "group",
        "active": True,
        "created_by": ObjectId(seed_users["teacher_id"]),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }).inserted_id

    response = client.put(
        f"/api/v1/calendar/events/{event_id}",
        headers=admin_headers,
        json={"description": "Editado por admin"},
    )

    assert response.status_code == 200
    assert response.json()["event"]["description"] == "Editado por admin"


def test_delete_event_creator_teacher_logical_delete(client, seed_users, teacher_headers):
    event_id = db.calendar_events.insert_one({
        "title": "Excursion",
        "event_type": "actividad",
        "start_date": datetime(2026, 8, 25),
        "end_date": datetime(2026, 8, 25),
        "group_id": ObjectId(seed_users["group_id"]),
        "scope": "group",
        "active": True,
        "created_by": ObjectId(seed_users["teacher_id"]),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }).inserted_id

    response = client.delete(f"/api/v1/calendar/events/{event_id}", headers=teacher_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Event deleted successfully"
    assert data["event"]["active"] is False
    assert data["notifications"]["attempted"] is True

    event_doc = db.calendar_events.find_one({"_id": event_id})
    assert event_doc["active"] is False
    assert event_doc.get("deleted_at") is not None


def test_delete_event_non_creator_teacher_forbidden(client, seed_users):
    other_teacher_id = db.users.insert_one({
        "id_number": "teacher2",
        "first_name": "Laura",
        "last_name": "Mora",
        "role": "teacher",
        "password_hash": "x",
        "must_change_password": False,
        "active": True,
    }).inserted_id
    other_teacher_token = _create_token(str(other_teacher_id), "teacher", "Laura")
    other_teacher_headers = {"Authorization": f"Bearer {other_teacher_token}"}

    event_id = db.calendar_events.insert_one({
        "title": "Solo creador",
        "event_type": "actividad",
        "start_date": datetime(2026, 8, 27),
        "end_date": datetime(2026, 8, 27),
        "group_id": ObjectId(seed_users["group_id"]),
        "scope": "group",
        "active": True,
        "created_by": ObjectId(seed_users["teacher_id"]),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }).inserted_id

    response = client.delete(f"/api/v1/calendar/events/{event_id}", headers=other_teacher_headers)
    assert response.status_code == 403
    assert "Unauthorized" in response.json()["detail"]