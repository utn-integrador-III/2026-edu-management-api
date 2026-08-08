import pytest
from bson import ObjectId
from src.config.database import db

def test_get_subjects(client, seed_users, teacher_headers):
    response = client.get("/api/v1/users/subjects", headers=teacher_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["code"] == "MAT-10"

def test_create_subject_success(client, seed_users, admin_headers):
    response = client.post("/api/v1/users/subjects", headers=admin_headers, json={
        "name": "Ciencias",
        "code": "CIE-10",
        "level": "Decimo"
    })
    assert response.status_code == 200
    assert response.json()["code"] == "CIE-10"

def test_create_subject_duplicate_code(client, seed_users, admin_headers):
    response = client.post("/api/v1/users/subjects", headers=admin_headers, json={
        "name": "Matematicas Nueva",
        "code": "MAT-10"
    })
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]

def test_get_groups_admin(client, seed_users, admin_headers):
    response = client.get("/api/v1/users/groups", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) > 0

def test_get_groups_teacher(client, seed_users, teacher_headers):
    response = client.get("/api/v1/users/groups", headers=teacher_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "10-A"

def test_get_my_children(client, seed_users, parent_headers):
    response = client.get("/api/v1/users/my-children", headers=parent_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id_number"] == "student1"

def test_search_users(client, seed_users, admin_headers):
    response = client.get("/api/v1/users/search?q=Pedrito", headers=admin_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["first_name"] == "Pedrito"

def test_get_all_users_by_role(client, seed_users, admin_headers):
    response = client.get("/api/v1/users/?role=teacher", headers=admin_headers)
    assert response.status_code == 200
    teachers = response.json()
    assert len(teachers) == 1
    assert teachers[0]["role"] == "teacher"

def test_create_user_student_with_parent_success(client, seed_users, admin_headers):
    response = client.post("/api/v1/users/", headers=admin_headers, json={
        "id_number": "student_new",
        "first_name": "Carlitos",
        "last_name": "Perez",
        "role": "student",
        "parent_id": seed_users["parent_id"]
    })
    assert response.status_code == 201
    assert response.json()["id_number"] == "student_new"

def test_create_user_student_missing_parent(client, seed_users, admin_headers):
    response = client.post("/api/v1/users/", headers=admin_headers, json={
        "id_number": "student_new",
        "first_name": "Carlitos",
        "last_name": "Perez",
        "role": "student"
    })
    assert response.status_code == 400
    assert "Student must have a parent linked" in response.json()["detail"]

def test_get_user_by_id(client, seed_users, admin_headers):
    response = client.get(f"/api/v1/users/{seed_users['student_id']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["id_number"] == "student1"

def test_update_user(client, seed_users, admin_headers):
    response = client.put(f"/api/v1/users/{seed_users['teacher_id']}", headers=admin_headers, json={
        "first_name": "Maria Elena",
        "last_name": "Castro Diaz",
        "role": "teacher",
        "active": True,
        "email": "maria.elena@example.com"
    })
    assert response.status_code == 200
    assert response.json()["first_name"] == "Maria Elena"

def test_deactivate_user(client, seed_users, admin_headers):
    response = client.delete(f"/api/v1/users/{seed_users['teacher_id']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == {"message": "User deactivated"}

    user = db.users.find_one({"_id": ObjectId(seed_users["teacher_id"])})
    assert user["active"] is False

def test_assign_subjects_to_student(client, seed_users, admin_headers):
    sub_id = db.subjects.insert_one({"name": "Ingles", "code": "ING-10"}).inserted_id

    response = client.post(f"/api/v1/users/{seed_users['student_id']}/subjects", headers=admin_headers, json={
        "assignments": [
            {
                "subject_id": str(sub_id),
                "teacher_id": seed_users["teacher_id"],
                "group_id": seed_users["group_id"],
                "period": "2026"
            }
        ]
    })
    assert response.status_code == 200
    assert response.json() == {"message": "Subjects assigned successfully"}

def test_remove_student_subject(client, seed_users, admin_headers):
    response = client.delete(
        f"/api/v1/users/{seed_users['student_id']}/subjects/{seed_users['subject_id']}?period=2026",
        headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json() == {"message": "Subject removed from student"}

    link = db.student_subjects.find_one({
        "student_id": ObjectId(seed_users["student_id"]),
        "subject_id": ObjectId(seed_users["subject_id"])
    })
    assert link is None

def test_link_parent_student(client, seed_users, admin_headers):
    p_id = db.users.insert_one({"id_number": "parent_new", "first_name": "A", "last_name": "B", "role": "parent", "active": True}).inserted_id
    s_id = db.users.insert_one({"id_number": "student_new", "first_name": "C", "last_name": "D", "role": "student", "active": True}).inserted_id

    response = client.post("/api/v1/users/parent-students", headers=admin_headers, json={
        "parent_id": str(p_id),
        "student_id": str(s_id)
    })
    assert response.status_code == 200
    assert response.json()["message"] == "Relationship linked successfully"

def test_import_users_csv(client, seed_users, admin_headers):
    csv_content = (
        "cedula;nombre;apellido1;apellido2;correo;telefono;tipo_usuario;accion\n"
        "teacher2;Laura;Mora;Solano;laura@example.com;8888-0004;docente;insertar\n"
    )
    response = client.post(
        "/api/v1/users/import/users",
        headers=admin_headers,
        files={"file": ("users.csv", csv_content, "text/csv")}
    )
    assert response.status_code == 200
    assert response.json()["created"] == 1

def test_import_students_csv(client, seed_users, admin_headers):
    db.groups.insert_one({"name": "10-B", "level": "Decimo"})

    csv_content = (
        "cedula;nombre;apellido1;apellido2;nivel;seccion;cedula_padre;accion\n"
        "student2;Carlitos;Perez;Lovera;Decimo;10-B;parent1;insertar\n"
    )
    response = client.post(
        "/api/v1/users/import/students",
        headers=admin_headers,
        files={"file": ("students.csv", csv_content, "text/csv")}
    )
    assert response.status_code == 200
    assert response.json()["created"] == 1