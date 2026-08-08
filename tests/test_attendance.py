import pytest
from bson import ObjectId
from src.config.database import db

def test_create_attendance_success(client, seed_users, teacher_headers):
    response = client.post("/api/v1/attendance", headers=teacher_headers, json={
        "date": "2026-08-08",
        "group_id": seed_users["group_id"],
        "subject_id": seed_users["subject_id"],
        "records": [
            {
                "student_id": seed_users["student_id"],
                "status": "presente",
                "arrival_time": "07:05"
            }
        ]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Attendance registered successfully"
    assert "session" in data
    assert data["session"]["date"] == "2026-08-08"
    assert data["session"]["records"][0]["status"] == "presente"

def test_create_attendance_absence_triggers_notification(client, seed_users, teacher_headers):
    response = client.post("/api/v1/attendance", headers=teacher_headers, json={
        "date": "2026-08-08",
        "group_id": seed_users["group_id"],
        "subject_id": seed_users["subject_id"],
        "records": [
            {
                "student_id": seed_users["student_id"],
                "status": "ausente"
            }
        ]
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["notifications"]) > 0
    assert data["notifications"][0]["status"] in ("sent", "skipped", "failed")

def test_create_attendance_invalid_group(client, seed_users, teacher_headers):
    invalid_group_id = str(ObjectId())
    response = client.post("/api/v1/attendance", headers=teacher_headers, json={
        "date": "2026-08-08",
        "group_id": invalid_group_id,
        "subject_id": seed_users["subject_id"],
        "records": [
            {
                "student_id": seed_users["student_id"],
                "status": "presente"
            }
        ]
    })
    assert response.status_code == 400
    assert "Group not found" in response.json()["detail"]

def test_get_attendance_history(client, seed_users, teacher_headers):
    client.post("/api/v1/attendance", headers=teacher_headers, json={
        "date": "2026-08-08",
        "group_id": seed_users["group_id"],
        "subject_id": seed_users["subject_id"],
        "records": [{"student_id": seed_users["student_id"], "status": "presente"}]
    })

    response = client.get(
        f"/api/v1/attendance?group_id={seed_users['group_id']}&subject_id={seed_users['subject_id']}",
        headers=teacher_headers
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["date"] == "2026-08-08"

def test_get_student_monthly_attendance(client, seed_users, parent_headers):
    db.attendance.insert_one({
        "attendance_date": pytest.importorskip("datetime").datetime(2026, 8, 8),
        "group_id": ObjectId(seed_users["group_id"]),
        "subject_id": ObjectId(seed_users["subject_id"]),
        "records": [
            {
                "student_id": ObjectId(seed_users["student_id"]),
                "status": "presente",
                "arrival_time": "07:15"
            }
        ],
        "created_at": pytest.importorskip("datetime").datetime.utcnow()
    })

    response = client.get(
        f"/api/v1/attendance/students/{seed_users['student_id']}/monthly?month=8&year=2026",
        headers=parent_headers
    )
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["status"] == "presente"
    assert results[0]["student_id"] == seed_users["student_id"]
    assert results[0]["subject_name"] == "Matematicas"

def test_parent_get_unauthorized_student_monthly(client, seed_users, parent_headers):
    other_student_id = db.users.insert_one({
        "id_number": "student2",
        "first_name": "Otro",
        "last_name": "Estudiante",
        "role": "student",
        "active": True
    }).inserted_id

    response = client.get(
        f"/api/v1/attendance/students/{other_student_id}/monthly?month=8&year=2026",
        headers=parent_headers
    )
    assert response.status_code == 400
    assert "Unauthorized" in response.json()["detail"]