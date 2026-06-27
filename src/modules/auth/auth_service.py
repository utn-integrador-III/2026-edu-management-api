import os
import secrets
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import jwt
from bson import ObjectId
from src.config.database import db
from src.config.mailer import send_mail

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

# RF-01
def login(id_number: str, password: str) -> dict:
    user = db.users.find_one({"id_number": id_number, "active": True})
    
    if not user or user.get('role') == 'student':
        raise ValueError('Invalid credentials')
    if not pwd_context.verify(password, user['password_hash']):
        raise ValueError('Invalid credentials')

    token = jwt.encode(
        {
            'id':                 str(user['_id']),
            'role':               user['role'],
            'first_name':         user['first_name'],
            'mustChangePassword': user['must_change_password'],
            'exp':                datetime.utcnow() + timedelta(hours=24),
        },
        os.getenv('JWT_SECRET'),
        algorithm='HS256',
    )
    return {
        'token':              token,
        'mustChangePassword': user['must_change_password'],
        'role':               user['role'],
        'first_name':         user['first_name'],
        'last_name':          user['last_name'],
    }

# RF-02
def change_password(user_id: str, current_password: str, new_password: str):
    try:
        obj_id = ObjectId(user_id)
    except Exception:
        raise ValueError('Invalid user ID format')
        
    user = db.users.find_one({"_id": obj_id})
    if not user:
        raise ValueError('User not found')
    if not pwd_context.verify(current_password, user['password_hash']):
        raise ValueError('Current password is incorrect')
        
    new_hash = pwd_context.hash(new_password)
    db.users.update_one(
        {"_id": obj_id},
        {"$set": {"password_hash": new_hash, "must_change_password": False}}
    )

# RF-03: enviar link de recuperación
def forgot_password(id_number: str):
    user = db.users.find_one({"id_number": id_number, "active": True})
    if not user or not user.get('email'):
        return

    # Invalidate previous tokens
    db.password_reset_tokens.update_many(
        {"user_id": user['_id'], "used": False},
        {"$set": {"used": True}}
    )
    
    token = secrets.token_hex(32)
    db.password_reset_tokens.insert_one({
        "user_id": user['_id'],
        "token": token,
        "expires_at": datetime.utcnow() + timedelta(hours=1),
        "used": False,
        "created_at": datetime.utcnow()
    })

    frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:5173')
    reset_url = f"{frontend_url}/reset-password?token={token}"

    try:
        send_mail(
            to=user['email'],
            subject='EduConecta CR — Password recovery',
            html=f"""
                <p>Dear {user['first_name']} {user['last_name']},</p>
                <p>We received a request to reset your EduConecta CR password.</p>
                <p>Click the link below to continue (valid for 1 hour):</p>
                <p><a href="{reset_url}">{reset_url}</a></p>
                <p>If you did not make this request, please ignore this email.</p>
            """
        )
    except Exception:
        pass

# RF-03: aplicar nueva contraseña
def reset_password(token: str, new_password: str):
    record = db.password_reset_tokens.find_one({
        "token": token,
        "used": False,
        "expires_at": {"$gt": datetime.utcnow()}
    })
    if not record:
        raise ValueError('Invalid or expired token')
        
    new_hash = pwd_context.hash(new_password)
    db.users.update_one(
        {"_id": ObjectId(record['user_id'])},
        {"$set": {"password_hash": new_hash, "must_change_password": False}}
    )
    db.password_reset_tokens.update_one(
        {"_id": record['_id']},
        {"$set": {"used": True}}
    )

# RF-04
def logout(user_id: str, token: str):
    try:
        obj_id = ObjectId(user_id) if user_id else None
    except Exception:
        obj_id = None
        
    db.token_blacklist.update_one(
        {"token": token},
        {"$setOnInsert": {
            "token": token,
            "user_id": obj_id,
            "created_at": datetime.utcnow()
        }},
        upsert=True
    )
