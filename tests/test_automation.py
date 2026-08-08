import pytest
from src.config.database import db

def test_run_users_automation_success(client, seed_users, admin_headers):
    db.users.delete_many({"id_number": {"$in": ["12345678", "604420243", "55667788"]}})

    response = client.post("/api/v1/automation/users", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert "User CSV automation executed successfully" in data["message"]
    assert data["summary"]["inserted"] > 0

    parent = db.users.find_one({"id_number": "604420243"})
    assert parent is not None
    assert parent["role"] == "parent"

def test_run_students_automation_success(client, seed_users, admin_headers):
    db.users.delete_many({"id_number": {"$in": ["12345678", "604420243", "55667788", "111111111", "222222222"]}})
    client.post("/api/v1/automation/users", headers=admin_headers)

    response = client.post("/api/v1/automation/students", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert "Student CSV automation executed successfully" in data["message"]
    assert data["summary"]["inserted"] > 0

    student = db.users.find_one({"id_number": "111111111"})
    assert student is not None
    assert student["role"] == "student"
    assert student["parent_cedula"] == "604420243"

    link = db.parent_students.find_one({"student_cedula": "111111111"})
    assert link is not None
    assert link["parent_cedula"] == "604420243"