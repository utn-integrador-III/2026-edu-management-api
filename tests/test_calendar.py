import pytest
from bson import ObjectId
from src.config.database import db

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