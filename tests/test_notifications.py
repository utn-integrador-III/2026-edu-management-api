import pytest
from bson import ObjectId
from src.config.database import db

def test_send_absence_endpoint_success(client, seed_users, teacher_headers):
    response = client.post("/api/v1/notifications/send-absence", headers=teacher_headers, json={
        "student_id": seed_users["student_id"],
        "subject_id": seed_users["subject_id"]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("sent", "skipped", "failed")
    assert data["type"] == "absence"

    notification_doc = db.notifications.find_one({"student_id": ObjectId(seed_users["student_id"])})
    assert notification_doc is not None
    assert notification_doc["type"] == "absence"

def test_send_tardiness_endpoint_success(client, seed_users, teacher_headers):
    response = client.post("/api/v1/notifications/send-tardiness", headers=teacher_headers, json={
        "student_id": seed_users["student_id"],
        "subject_id": seed_users["subject_id"]
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("sent", "skipped", "failed")
    assert data["type"] == "tardiness"

    notification_doc = db.notifications.find_one({"student_id": ObjectId(seed_users["student_id"])})
    assert notification_doc is not None
    assert notification_doc["type"] == "tardiness"

def test_send_notification_student_not_found(client, seed_users, teacher_headers):
    invalid_student_id = str(ObjectId())
    response = client.post("/api/v1/notifications/send-absence", headers=teacher_headers, json={
        "student_id": invalid_student_id,
        "subject_id": seed_users["subject_id"]
    })
    assert response.status_code == 400
    assert "Student not found" in response.json()["detail"]

def test_send_notification_parent_missing(client, seed_users, teacher_headers):
    student_no_parent_id = db.users.insert_one({
        "id_number": "student_orphan",
        "first_name": "NoParent",
        "last_name": "Student",
        "role": "student",
        "active": True
    }).inserted_id

    response = client.post("/api/v1/notifications/send-absence", headers=teacher_headers, json={
        "student_id": str(student_no_parent_id),
        "subject_id": seed_users["subject_id"]
    })
    assert response.status_code == 400
    assert "Parent not found" in response.json()["detail"]