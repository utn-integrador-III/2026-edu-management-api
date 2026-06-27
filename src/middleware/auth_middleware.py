import os
from fastapi import HTTPException, Header
from jose import jwt, JWTError
from src.config.database import db

def verify_token(authorization: str = Header(...)):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='Token required')

    token = authorization.split(' ')[1]

    try:
        payload = jwt.decode(token, os.getenv('JWT_SECRET'), algorithms=['HS256'])
    except JWTError:
        raise HTTPException(status_code=401, detail='Invalid or expired token')

    # RF-04: verificar que el token no fue invalidado por logout
    row = db.token_blacklist.find_one({"token": token})
    if row:
        raise HTTPException(status_code=401, detail='Session expired. Please log in again')

    return payload
