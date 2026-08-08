import os
import sys

# Agregar la raíz del proyecto a sys.path para evitar errores de importación de 'src'
root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_path not in sys.path:
    sys.path.insert(0, root_path)

from datetime import datetime, timedelta
from unittest.mock import MagicMock
import pytest
from jose import jwt

# Configure environment variables for testing
os.environ["MONGODB_URI"] = "mongodb://localhost:27017/test_educonecta"
os.environ["JWT_SECRET"] = "test_secret_key_12345"
os.environ["EMAIL_FROM"] = "test@educonecta.cr"
os.environ["RESEND_API_KEY"] = "re_testkey"

# Mock pymongo with mongomock before loading any app modules
import pymongo
import mongomock
pymongo.MongoClient = mongomock.MongoClient

# Mock mailer module to prevent sending actual emails during tests
import src.config.mailer as mailer
mailer.send_mail = MagicMock()

# Now import app and db
from main import app
from src.config.database import db

from fastapi.testclient import TestClient

@pytest.fixture(scope="session", autouse=True)
def init_test_db():
    # Trigger database seeding which runs on database import
    # This ensures default groups and admin are seeded in the mongomock db.
    pass

@pytest.fixture(autouse=True)
def clear_db():
    # Clear collections before each test to guarantee isolation
    for collection_name in db.list_collection_names():
        db[collection_name].delete_many({})
    
    # Re-run index creations and seeding
    from src.config.database import seed_db
    seed_db()
    yield

@pytest.fixture
def test_db():
    return db

@pytest.fixture
def client():
    return TestClient(app)

def create_test_token(user_id: str, role: str, first_name: str, must_change: bool = False):
    return jwt.encode(
        {
            'id': str(user_id),
            'role': role,
            'first_name': first_name,
            'mustChangePassword': must_change,
            'exp': datetime.utcnow() + timedelta(hours=1),
        },
        os.environ["JWT_SECRET"],
        algorithm='HS256',
    )

@pytest.fixture
def seed_users(test_db):
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
    
    # 1. Create a group
    group_res = test_db.groups.insert_one({"name": "10-A", "level": "Decimo", "created_at": datetime.utcnow()})
    group_id = group_res.inserted_id

    # 2. Create a subject
    subject_res = test_db.subjects.insert_one({"name": "Matematicas", "code": "MAT-10", "level": "Decimo", "created_at": datetime.utcnow()})
    subject_id = subject_res.inserted_id

    # 3. Create parent
    parent_id = test_db.users.insert_one({
        "id_number": "parent1",
        "first_name": "Juan",
        "last_name": "Perez",
        "email": "juan@example.com",
        "phone": "8888-0001",
        "role": "parent",
        "password_hash": pwd_context.hash("parent123"),
        "must_change_password": False,
        "active": True,
        "created_at": datetime.utcnow()
    }).inserted_id

    # 4. Create student
    student_id = test_db.users.insert_one({
        "id_number": "student1",
        "first_name": "Pedrito",
        "last_name": "Perez",
        "email": "pedrito@example.com",
        "phone": "8888-0002",
        "role": "student",
        "group_id": group_id,
        "parent_cedula": "parent1",
        "password_hash": pwd_context.hash("student123"),
        "must_change_password": False,
        "active": True,
        "created_at": datetime.utcnow()
    }).inserted_id

    # Link parent and student
    test_db.parent_students.insert_one({
        "parent_id": parent_id,
        "parent_cedula": "parent1",
        "student_id": student_id,
        "student_cedula": "student1"
    })

    # 5. Create teacher
    teacher_id = test_db.users.insert_one({
        "id_number": "teacher1",
        "first_name": "Maria",
        "last_name": "Castro",
        "email": "maria@example.com",
        "phone": "8888-0003",
        "role": "teacher",
        "password_hash": pwd_context.hash("teacher123"),
        "must_change_password": False,
        "active": True,
        "created_at": datetime.utcnow()
    }).inserted_id

    # Link student to subject and teacher
    test_db.student_subjects.insert_one({
        "student_id": student_id,
        "subject_id": subject_id,
        "group_id": group_id,
        "teacher_id": teacher_id,
        "period": "2026"
    })

    # Retrieve seeded default admin user
    admin_user = test_db.users.find_one({"role": "admin"})
    admin_id = admin_user["_id"] if admin_user else test_db.users.insert_one({
        "id_number": "admin",
        "first_name": "Admin",
        "last_name": "System",
        "email": "admin@educonecta.cr",
        "role": "admin",
        "password_hash": pwd_context.hash("admin123"),
        "must_change_password": False,
        "active": True,
        "created_at": datetime.utcnow()
    }).inserted_id

    return {
        "group_id": str(group_id),
        "subject_id": str(subject_id),
        "parent_id": str(parent_id),
        "student_id": str(student_id),
        "teacher_id": str(teacher_id),
        "admin_id": str(admin_id)
    }

@pytest.fixture
def admin_headers(seed_users):
    token = create_test_token(seed_users["admin_id"], "admin", "Admin", must_change=False)
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def teacher_headers(seed_users):
    token = create_test_token(seed_users["teacher_id"], "teacher", "Maria", must_change=False)
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def parent_headers(seed_users):
    token = create_test_token(seed_users["parent_id"], "parent", "Juan", must_change=False)
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def student_headers(seed_users):
    token = create_test_token(seed_users["student_id"], "student", "Pedrito", must_change=False)
    return {"Authorization": f"Bearer {token}"}