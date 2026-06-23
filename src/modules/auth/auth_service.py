import os
import secrets
from datetime import datetime, timedelta
from passlib.context import CryptContext
from jose import jwt
from src.config.database import execute, execute_one
from src.config.mailer import send_mail

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

# RF-01
def login(id_number: str, password: str) -> dict:
    user = execute_one(
        'SELECT * FROM users WHERE id_number = %s AND active = true',
        (id_number,)
    )
    if not user or user['role'] == 'student':
        raise ValueError('Invalid credentials')
    if not pwd_context.verify(password, user['password_hash']):
        raise ValueError('Invalid credentials')

    token = jwt.encode(
        {
            'id':                user['id'],
            'role':              user['role'],
            'first_name':        user['first_name'],
            'mustChangePassword': user['must_change_password'],
            'exp':               datetime.utcnow() + timedelta(hours=24),
        },
        os.getenv('JWT_SECRET'),
        algorithm='HS256',
    )
    return {
        'token':             token,
        'mustChangePassword': user['must_change_password'],
        'role':              user['role'],
        'first_name':        user['first_name'],
        'last_name':         user['last_name'],
    }

# RF-02
def change_password(user_id: int, current_password: str, new_password: str):
    user = execute_one('SELECT * FROM users WHERE id = %s', (user_id,))
    if not user:
        raise ValueError('User not found')
    if not pwd_context.verify(current_password, user['password_hash']):
        raise ValueError('Current password is incorrect')
    new_hash = pwd_context.hash(new_password)
    execute(
        'UPDATE users SET password_hash = %s, must_change_password = false WHERE id = %s',
        (new_hash, user_id)
    )

# RF-03: enviar link de recuperación
def forgot_password(id_number: str):
    user = execute_one(
        'SELECT id, email, first_name, last_name FROM users WHERE id_number = %s AND active = true',
        (id_number,)
    )
    if not user or not user.get('email'):
        return

    execute(
        'UPDATE password_reset_tokens SET used = true WHERE user_id = %s AND used = false',
        (user['id'],)
    )
    token = secrets.token_hex(32)
    execute(
        "INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES (%s, %s, NOW() + INTERVAL '1 hour')",
        (user['id'], token)
    )

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
    record = execute_one(
        'SELECT id, user_id FROM password_reset_tokens WHERE token = %s AND used = false AND expires_at > NOW()',
        (token,)
    )
    if not record:
        raise ValueError('Invalid or expired token')
    new_hash = pwd_context.hash(new_password)
    execute(
        'UPDATE users SET password_hash = %s, must_change_password = false WHERE id = %s',
        (new_hash, record['user_id'])
    )
    execute('UPDATE password_reset_tokens SET used = true WHERE id = %s', (record['id'],))

# RF-04
def logout(user_id: int, token: str):
    execute(
        'INSERT INTO token_blacklist (token, user_id) VALUES (%s, %s) ON CONFLICT (token) DO NOTHING',
        (token, user_id)
    )
