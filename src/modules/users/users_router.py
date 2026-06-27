from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from typing import Optional, List
from src.modules.users import users_service
from src.middleware.auth_middleware import verify_token
from src.middleware.role_middleware import require_role

router = APIRouter()

class UserCreate(BaseModel):
    id_number: str
    first_name: str
    last_name: str
    role: str
    email: Optional[str] = None
    phone: Optional[str] = None
    type: Optional[str] = None
    group_id: Optional[str] = None
    birth_date: Optional[str] = None
    parent_id: Optional[str] = None

class ParentStudentLink(BaseModel):
    parent_id: str
    student_id: str

class UserUpdate(BaseModel):
    first_name: str
    last_name: str
    role: str
    active: bool
    email: Optional[str] = None
    phone: Optional[str] = None
    type: Optional[str] = None
    group_id: Optional[str] = None

class SubjectCreate(BaseModel):
    name: str
    code: str
    level: Optional[str] = None

class SubjectAssignment(BaseModel):
    subject_id: str
    teacher_id: Optional[str] = None
    group_id: Optional[str] = None
    period: Optional[str] = '2026'

class AssignSubjectsRequest(BaseModel):
    assignments: List[SubjectAssignment]

# Materias
@router.get('/subjects', dependencies=[Depends(require_role('admin', 'teacher'))])
def get_subjects():
    return users_service.get_subjects()

@router.post('/subjects', dependencies=[Depends(require_role('admin'))])
def create_subject(body: SubjectCreate):
    try:
        return users_service.create_subject(body.model_dump())
    except Exception as e:
        if 'unique' in str(e).lower() or 'already exists' in str(e).lower():
            raise HTTPException(status_code=409, detail='A subject with that code already exists')
        raise HTTPException(status_code=400, detail=str(e))

# Grupos
@router.get('/groups', dependencies=[Depends(require_role('admin', 'teacher'))])
def get_groups():
    return users_service.get_groups()

# Hijos del padre autenticado
@router.get('/my-children')
def get_my_children(user: dict = Depends(require_role('parent'))):
    return users_service.get_children(user['id'])

# CSV import
@router.post('/import/users', dependencies=[Depends(require_role('admin'))])
async def import_users_csv(file: UploadFile = File(...)):
    content = await file.read()
    return users_service.import_users_from_csv(content)

@router.post('/import/students', dependencies=[Depends(require_role('admin'))])
async def import_students_csv(file: UploadFile = File(...)):
    content = await file.read()
    return users_service.import_students_from_csv(content)

# RF-05: CRUD usuarios (solo admin)
@router.get('/search', dependencies=[Depends(require_role('admin'))])
def search_users(q: str = Query(...)):
    return users_service.search_users(q)

@router.get('/', dependencies=[Depends(require_role('admin'))])
def get_all(role: Optional[str] = Query(None), active: Optional[bool] = Query(None)):
    return users_service.get_all({'role': role, 'active': active})

@router.post('/', dependencies=[Depends(require_role('admin'))], status_code=201)
def create_user(body: UserCreate):
    try:
        return users_service.create(body.model_dump())
    except Exception as e:
        if 'unique' in str(e).lower() or 'already exists' in str(e).lower():
            raise HTTPException(status_code=409, detail='A user with that ID number or email already exists')
        raise HTTPException(status_code=400, detail=str(e))

@router.get('/{user_id}', dependencies=[Depends(require_role('admin'))])
def get_by_id(user_id: str):
    user = users_service.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail='User not found')
    return user

@router.put('/{user_id}', dependencies=[Depends(require_role('admin'))])
def update_user(user_id: str, body: UserUpdate):
    try:
        return users_service.update(user_id, body.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete('/{user_id}', dependencies=[Depends(require_role('admin'))])
def deactivate_user(user_id: str):
    try:
        users_service.deactivate(user_id)
        return {'message': 'User deactivated'}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# RF-06: Materias de estudiante
@router.get('/{student_id}/subjects', dependencies=[Depends(require_role('admin', 'teacher'))])
def get_student_subjects(student_id: str, period: Optional[str] = Query(None)):
    return users_service.get_student_subjects(student_id, period)

@router.post('/{student_id}/subjects', dependencies=[Depends(require_role('admin'))])
def assign_subjects(student_id: str, body: AssignSubjectsRequest):
    try:
        users_service.assign_subjects_to_student(student_id, [a.model_dump() for a in body.assignments])
        return {'message': 'Subjects assigned successfully'}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete('/{student_id}/subjects/{subject_id}', dependencies=[Depends(require_role('admin'))])
def remove_subject(student_id: str, subject_id: str, period: Optional[str] = Query('2026')):
    users_service.remove_student_subject(student_id, subject_id, period)
    return {'message': 'Subject removed from student'}

# Relación Padres-Hijos
@router.get('/parents/{parent_id}/children', dependencies=[Depends(require_role('admin', 'teacher'))])
def get_parent_children(parent_id: str):
    return users_service.get_parent_children(parent_id)

@router.post('/parent-students', dependencies=[Depends(require_role('admin'))])
def link_parent_student(body: ParentStudentLink):
    try:
        return users_service.link_parent_student(body.parent_id, body.student_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
