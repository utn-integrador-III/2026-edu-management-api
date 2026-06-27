from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from src.modules.auth import auth_service
from src.middleware.auth_middleware import verify_token

router = APIRouter()

class LoginRequest(BaseModel):
    id_number: str
    password: str

class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str

class RecoverPasswordRequest(BaseModel):
    id_number: str

class ResetPasswordRequest(BaseModel):
    token: str
    newPassword: str

# RF-01
@router.post('/login')
def login(body: LoginRequest):
    try:
        return auth_service.login(body.id_number, body.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

# RF-02
@router.put('/change-password')
def change_password(body: ChangePasswordRequest, user: dict = Depends(verify_token)):
    if not body.newPassword or len(body.newPassword) < 8:
        raise HTTPException(status_code=400, detail='New password must be at least 8 characters')
    try:
        auth_service.change_password(user['id'], body.currentPassword, body.newPassword)
        return {'message': 'Password updated successfully'}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# RF-03
@router.post('/recover-password')
def recover_password(body: RecoverPasswordRequest):
    auth_service.forgot_password(body.id_number)
    return {'message': 'If an account exists with that ID number, a recovery email will be sent'}

@router.post('/reset-password')
def reset_password(body: ResetPasswordRequest):
    if not body.newPassword or len(body.newPassword) < 8:
        raise HTTPException(status_code=400, detail='New password must be at least 8 characters')
    try:
        auth_service.reset_password(body.token, body.newPassword)
        return {'message': 'Password reset successfully'}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# RF-04
@router.post('/logout')
def logout(authorization: str = Header(...), user: dict = Depends(verify_token)):
    token = authorization.split(' ')[1]
    auth_service.logout(user['id'], token)
    return {'message': 'Session closed successfully'}
