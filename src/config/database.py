import os
from datetime import datetime
import logging
from pymongo import MongoClient
from bson import ObjectId
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Database")

# Initialize MongoDB Client
uri = os.getenv("MONGODB_URI")
if not uri:
    raise ValueError("MONGODB_URI environment variable is not defined in .env")

client = MongoClient(uri)
db = client.get_database("educonecta")

# Password Hashing Context for Admin Seeding
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

# Ensure Indexes are created
try:
    db.users.create_index("id_number", unique=True)
    try:
        db.users.drop_index("email_1")
    except Exception:
        pass
    db.users.create_index("email", unique=True, partialFilterExpression={"email": {"$type": "string"}})
    db.subjects.create_index("code", unique=True)
    db.token_blacklist.create_index("token", unique=True)
    db.password_reset_tokens.create_index("token", unique=True)
    logger.info("MongoDB indexes verified/created successfully.")
except Exception as e:
    logger.error(f"Error creating MongoDB indexes: {e}")

# Database Seeding Routine
def seed_db():
    try:
        # Seed default groups
        required_groups = [
            {"name": "7-A", "level": "Septimo"},
            {"name": "7-B", "level": "Septimo"},
            {"name": "8-A", "level": "Octavo"},
            {"name": "9-A", "level": "Noveno"},
            {"name": "4-2", "level": "Primaria"},
            {"name": "2-1", "level": "Secundaria"},
            {"name": "3-3", "level": "Primaria"},
            {"name": "1-2", "level": "Secundaria"},
        ]
        seeded_count = 0
        for g in required_groups:
            res = db.groups.update_one(
                {"name": g["name"], "level": g["level"]},
                {"$setOnInsert": {"created_at": datetime.utcnow()}},
                upsert=True
            )
            if res.upserted_id:
                seeded_count += 1
        if seeded_count > 0:
            logger.info(f"Seeded {seeded_count} new groups.")

        # Seed default admin if no admin exists
        if db.users.count_documents({"role": "admin"}) == 0:
            admin_user = {
                "id_number": "admin",
                "first_name": "Admin",
                "last_name": "System",
                "email": "admin@educonecta.cr",
                "phone": "8888-8888",
                "role": "admin",
                "type": "I",
                "group_id": None,
                "birth_date": None,
                "is_adult": True,
                "password_hash": pwd_context.hash("admin123"),
                "must_change_password": True,
                "active": True,
                "created_at": datetime.utcnow()
            }
            db.users.insert_one(admin_user)
            logger.info("Default admin user seeded. Username: admin, Password: admin123")
    except Exception as e:
        logger.error(f"Error seeding database: {e}")

# Run Seeding on import
seed_db()

# Document Serialization Helpers for FastAPI JSON compliance
def serialize_doc(doc):
    if doc is None:
        return None
    # If it's not a dict, convert it (handles custom objects or Cursor result mappings)
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    for key, value in list(doc.items()):
        if isinstance(value, ObjectId):
            doc[key] = str(value)
        elif isinstance(value, datetime):
            doc[key] = value.isoformat()
    return doc

def serialize_list(docs):
    return [serialize_doc(doc) for doc in docs]
