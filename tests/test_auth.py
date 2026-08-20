import pytest
from unittest.mock import patch
from src.config.database import db

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_login_success(client, seed_users):
    response = client.post("/api/v1/auth/login", json={
        "id_number": "admin",
        "password": "admin123"
    })
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["role"] == "admin"
    assert data["first_name"] == "Admin"
    assert data["mustChangePassword"] is True

def test_login_invalid_credentials(client, seed_users):
    response = client.post("/api/v1/auth/login", json={
        "id_number": "admin",
        "password": "wrongpassword"
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"

def test_login_student_role_prohibited(client, seed_users):
    response = client.post("/api/v1/auth/login", json={
        "id_number": "student1",
        "password": "student123"
    })
    assert response.status_code == 401

def test_change_password_success(client, seed_users, admin_headers):
    response = client.put("/api/v1/auth/change-password", headers=admin_headers, json={
        "currentPassword": "admin123",
        "newPassword": "newsecurepassword123"
    })
    assert response.status_code == 200
    assert response.json() == {"message": "Password updated successfully"}

    user = db.users.find_one({"id_number": "admin"})
    assert user["must_change_password"] is False

def test_change_password_invalid_current(client, seed_users, admin_headers):
    response = client.put("/api/v1/auth/change-password", headers=admin_headers, json={
        "currentPassword": "wrongcurrentpassword",
        "newPassword": "newsecurepassword123"
    })
    assert response.status_code == 400
    assert "incorrect" in response.json()["detail"]

def test_change_password_too_short(client, seed_users, admin_headers):
    response = client.put("/api/v1/auth/change-password", headers=admin_headers, json={
        "currentPassword": "admin123",
        "newPassword": "short"
    })
    assert response.status_code == 400
    assert "at least 8 characters" in response.json()["detail"]

def test_recover_password(client, seed_users):
    response = client.post("/api/v1/auth/recover-password", json={
        "id_number": "teacher1"
    })
    assert response.status_code == 200
    assert "recovery email will be sent" in response.json()["message"]

    token_record = db.password_reset_tokens.find_one({"user_id": db.users.find_one({"id_number": "teacher1"})["_id"]})
    assert token_record is not None
    assert token_record["used"] is False

def test_recover_password_logs_resend_error(client, seed_users, caplog):
    with patch("src.modules.auth.auth_service.send_mail", side_effect=Exception("Resend down")):
        with caplog.at_level("ERROR", logger="Auth"):
            response = client.post("/api/v1/auth/recover-password", json={
                "id_number": "teacher1"
            })

    # El endpoint sigue respondiendo igual aunque Resend falle (no revela si el usuario existe)
    assert response.status_code == 200
    assert "recovery email will be sent" in response.json()["message"]

    # Pero el error real queda logueado en el servidor
    assert any("Resend down" in record.message for record in caplog.records)

def test_reset_password_success(client, seed_users):
    client.post("/api/v1/auth/recover-password", json={
        "id_number": "teacher1"
    })
    token_record = db.password_reset_tokens.find_one({"used": False})
    token = token_record["token"]

    response = client.post("/api/v1/auth/reset-password", json={
        "token": token,
        "newPassword": "newteacherpassword123"
    })
    assert response.status_code == 200
    assert response.json() == {"message": "Password reset successfully"}

    token_record_updated = db.password_reset_tokens.find_one({"_id": token_record["_id"]})
    assert token_record_updated["used"] is True

def test_reset_password_invalid_token(client, seed_users):
    response = client.post("/api/v1/auth/reset-password", json={
        "token": "invalid_or_expired_token_value",
        "newPassword": "newpassword123"
    })
    assert response.status_code == 400
    assert "Invalid or expired token" in response.json()["detail"]

def test_logout(client, seed_users, teacher_headers):
    response = client.get("/api/v1/users/groups", headers=teacher_headers)
    assert response.status_code == 200

    response = client.post("/api/v1/auth/logout", headers=teacher_headers)
    assert response.status_code == 200
    assert response.json() == {"message": "Session closed successfully"}

    response = client.get("/api/v1/users/groups", headers=teacher_headers)
    assert response.status_code == 401
    assert "Session expired" in response.json()["detail"]