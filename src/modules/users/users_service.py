import csv
import io
from datetime import datetime
from passlib.context import CryptContext
from bson import ObjectId
from src.config.database import db, serialize_doc, serialize_list
from src.config.mailer import send_mail

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

# RF-05: Listar usuarios
def get_all(filters: dict = {}) -> list:
    query = {}
    if filters.get('role'):
        query['role'] = filters['role']
    if filters.get('active') is not None:
        query['active'] = filters['active']
        
    users = list(db.users.find(query).sort([('last_name', 1), ('first_name', 1)]))
    return serialize_list(users)

# RF-05: Obtener usuario por ID
def get_by_id(user_id: str):
    try:
        obj_id = ObjectId(user_id)
    except Exception:
        return None
    user = db.users.find_one({"_id": obj_id})
    return serialize_doc(user)

# RF-05: Crear usuario — contraseña temporal = cédula
def create(data: dict) -> dict:
    if db.users.find_one({"id_number": data['id_number']}):
        raise ValueError("A user with that ID number already exists")
    if data.get('email') and db.users.find_one({"email": data['email']}):
        raise ValueError("A user with that email already exists")

    # Verify parent link if role is student
    parent = None
    if data['role'] == 'student':
        parent_id = data.get('parent_id')
        if not parent_id:
            raise ValueError("Student must have a parent linked. Please specify a parent_id.")
        try:
            parent_oid = ObjectId(parent_id)
            parent = db.users.find_one({"_id": parent_oid, "role": "parent", "active": True})
        except Exception:
            parent = db.users.find_one({"id_number": parent_id, "role": "parent", "active": True})
        if not parent:
            raise ValueError("The parent specified is not registered or is inactive.")

    password_hash = pwd_context.hash(data['id_number'])
    
    # calculate is_adult
    is_adult = False
    if data.get('birth_date'):
        try:
            birth = datetime.strptime(data['birth_date'], '%Y-%m-%d')
            today = datetime.utcnow()
            age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
            is_adult = age >= 18
        except Exception:
            pass

    group_oid = None
    if data.get('group_id'):
        try:
            group_oid = ObjectId(data['group_id'])
        except Exception:
            pass

    new_user = {
        "id_number": data['id_number'],
        "first_name": data['first_name'],
        "last_name": data['last_name'],
        "email": data.get('email'),
        "phone": data.get('phone'),
        "role": data['role'],
        "type": data.get('type'),
        "group_id": group_oid,
        "birth_date": data.get('birth_date'),
        "is_adult": is_adult,
        "password_hash": password_hash,
        "must_change_password": True,
        "active": True,
        "created_at": datetime.utcnow()
    }
    if data['role'] == 'student' and parent:
        new_user["parent_cedula"] = parent["id_number"]
    
    res = db.users.insert_one(new_user)
    new_user["_id"] = res.inserted_id

    if data['role'] == 'student' and parent:
        db.parent_students.update_one(
            {
                "parent_id": parent["_id"],
                "student_id": new_user["_id"]
            },
            {
                "$setOnInsert": {
                    "parent_id": parent["_id"],
                    "parent_cedula": parent["id_number"],
                    "student_id": new_user["_id"],
                    "student_cedula": new_user["id_number"]
                }
            },
            upsert=True
        )

    if data.get('email'):
        try:
            send_mail(
                to=data['email'],
                subject='EduConecta CR — Your access credentials',
                html=f"""
                    <p>Dear {data['first_name']} {data['last_name']},</p>
                    <p>Your EduConecta CR account has been created. Your login credentials are:</p>
                    <ul>
                        <li><strong>ID Number:</strong> {data['id_number']}</li>
                        <li><strong>Temporary password:</strong> {data['id_number']}</li>
                    </ul>
                    <p>You will be asked to change your password on your first login.</p>
                """
            )
        except Exception:
            pass
            
    return serialize_doc(new_user)

# RF-05: Actualizar usuario
def update(user_id: str, data: dict) -> dict:
    try:
        obj_id = ObjectId(user_id)
    except Exception:
        raise ValueError('Invalid user ID format')

    existing_user = db.users.find_one({"_id": obj_id})
    if not existing_user:
        raise ValueError('User not found')

    if data.get('email'):
        conflict = db.users.find_one({"email": data['email']})
        if conflict and conflict['_id'] != obj_id:
            raise ValueError("A user with that email already exists")

    group_oid = None
    if data.get('group_id'):
        try:
            group_oid = ObjectId(data['group_id'])
        except Exception:
            pass

    update_fields = {
        "first_name": data['first_name'],
        "last_name": data['last_name'],
        "email": data.get('email'),
        "phone": data.get('phone'),
        "role": data['role'],
        "type": data.get('type'),
        "group_id": group_oid,
        "active": data['active']
    }

    # Re-evaluate is_adult if birth_date is present
    is_adult = existing_user.get('is_adult', False)
    if existing_user.get('birth_date'):
        try:
            birth = datetime.strptime(existing_user['birth_date'], '%Y-%m-%d')
            today = datetime.utcnow()
            age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
            is_adult = age >= 18
        except Exception:
            pass
    update_fields["is_adult"] = is_adult

    updated = db.users.find_one_and_update(
        {"_id": obj_id},
        {"$set": update_fields},
        return_document=True
    )
    return serialize_doc(updated)

# RF-05: Desactivar usuario
def deactivate(user_id: str):
    try:
        obj_id = ObjectId(user_id)
    except Exception:
        raise ValueError('Invalid user ID format')
        
    res = db.users.update_one({"_id": obj_id}, {"$set": {"active": False}})
    if res.matched_count == 0:
        raise ValueError("User not found")

# Materias
def get_subjects() -> list:
    subjects = list(db.subjects.find().sort([('name', 1)]))
    return serialize_list(subjects)

def create_subject(data: dict) -> dict:
    if db.subjects.find_one({"code": data['code']}):
        raise ValueError("A subject with that code already exists")
        
    new_subj = {
        "name": data['name'],
        "code": data['code'],
        "level": data.get('level'),
        "created_at": datetime.utcnow()
    }
    res = db.subjects.insert_one(new_subj)
    new_subj["_id"] = res.inserted_id
    return serialize_doc(new_subj)

# Grupos
def get_groups() -> list:
    groups = list(db.groups.find().sort([('name', 1)]))
    return serialize_list(groups)

# Hijos del padre
def get_children(parent_id: str) -> list:
    try:
        p_id = ObjectId(parent_id)
    except Exception:
        return []
        
    links = list(db.parent_students.find({"parent_id": p_id}))
    student_ids = [link["student_id"] for link in links]
    
    students = list(db.users.find({"_id": {"$in": student_ids}, "active": True}).sort([('last_name', 1), ('first_name', 1)]))
    for s in students:
        group_name = None
        if s.get("group_id"):
            group = db.groups.find_one({"_id": ObjectId(s["group_id"])})
            if group:
                group_name = group["name"]
        s["group_name"] = group_name
        
    return serialize_list(students)

# RF-06: Materias de un estudiante
def get_student_subjects(student_id: str, period: str = None) -> list:
    try:
        s_id = ObjectId(student_id)
    except Exception:
        return []
        
    query = {"student_id": s_id}
    if period:
        query["period"] = period
        
    links = list(db.student_subjects.find(query))
    results = []
    for link in links:
        subject = db.subjects.find_one({"_id": ObjectId(link["subject_id"])})
        if not subject:
            continue
            
        teacher_name = ""
        if link.get("teacher_id"):
            teacher = db.users.find_one({"_id": ObjectId(link["teacher_id"])})
            if teacher:
                teacher_name = f"{teacher['first_name']} {teacher['last_name']}"
                
        group_name = ""
        if link.get("group_id"):
            group = db.groups.find_one({"_id": ObjectId(link["group_id"])})
            if group:
                group_name = group["name"]
                
        results.append({
            "id": str(subject["_id"]),
            "name": subject["name"],
            "code": subject["code"],
            "level": subject.get("level"),
            "teacher_name": teacher_name,
            "group_name": group_name,
            "period": link["period"]
        })
        
    results.sort(key=lambda x: x["name"])
    return results

# RF-06: Asignar materias a estudiante
def assign_subjects_to_student(student_id: str, assignments: list):
    try:
        s_id = ObjectId(student_id)
    except Exception:
        raise ValueError('Invalid student ID format')
        
    student = db.users.find_one({"_id": s_id, "role": "student", "active": True})
    if not student:
        raise ValueError("Student not found or inactive")

    for a in assignments:
        try:
            sub_id = ObjectId(a["subject_id"])
        except Exception:
            raise ValueError(f"Invalid subject ID format: {a['subject_id']}")
            
        t_id = None
        if a.get("teacher_id"):
            try:
                t_id = ObjectId(a["teacher_id"])
            except Exception:
                pass
                
        g_id = None
        if a.get("group_id"):
            try:
                g_id = ObjectId(a["group_id"])
            except Exception:
                pass

        db.student_subjects.update_one(
            {
                "student_id": s_id,
                "subject_id": sub_id,
                "period": a.get("period", "2026")
            },
            {
                "$set": {
                    "teacher_id": t_id,
                    "group_id": g_id
                }
            },
            upsert=True
        )

# RF-06: Quitar materia a estudiante
def remove_student_subject(student_id: str, subject_id: str, period: str = '2026'):
    try:
        s_id = ObjectId(student_id)
        sub_id = ObjectId(subject_id)
    except Exception:
        return
        
    db.student_subjects.delete_one({
        "student_id": s_id,
        "subject_id": sub_id,
        "period": period
    })

# CSV import: Usuarios — formato: cedula;nombre;apellido1;apellido2;correo;telefono;tipo_usuario;accion
def import_users_from_csv(file_content: bytes) -> dict:
    reader = csv.DictReader(io.StringIO(file_content.decode('utf-8-sig')), delimiter=';')
    results = {'created': 0, 'updated': 0, 'deactivated': 0, 'skipped': 0, 'errors': []}

    for row in reader:
        accion = (row.get('accion') or '').strip().lower()
        tipo   = (row.get('tipo_usuario') or '').strip().lower()
        role   = 'teacher' if tipo.startswith('doc') else 'parent'
        cedula = row.get('cedula', '')

        try:
            if accion in ('insertar', 'insert', 'crear'):
                create({
                    'id_number':  cedula,
                    'first_name': row.get('nombre', ''),
                    'last_name':  f"{row.get('apellido1','')} {row.get('apellido2','')}".strip(),
                    'email':      row.get('correo') or None,
                    'phone':      row.get('telefono') or None,
                    'role':       role,
                })
                results['created'] += 1
            elif accion in ('update', 'actualizar', 'modificar'):
                found = db.users.find_one({'id_number': cedula})
                if not found:
                    results['errors'].append({'row': cedula, 'error': 'Not found for update'})
                    continue
                update(str(found['_id']), {
                    'first_name': row.get('nombre', ''),
                    'last_name':  f"{row.get('apellido1','')} {row.get('apellido2','')}".strip(),
                    'email':      row.get('correo') or None,
                    'phone':      row.get('telefono') or None,
                    'role': role, 'type': None, 'group_id': None, 'active': True,
                })
                results['updated'] += 1
            elif accion in ('eliminar', 'delete', 'borrar'):
                found = db.users.find_one({'id_number': cedula})
                if not found:
                    results['errors'].append({'row': cedula, 'error': 'Not found for delete'})
                    continue
                deactivate(str(found['_id']))
                results['deactivated'] += 1
            else:
                results['skipped'] += 1
        except Exception as e:
            if 'unique' in str(e).lower() or 'already exists' in str(e).lower():
                results['skipped'] += 1
            else:
                results['errors'].append({'row': cedula, 'error': str(e)})

    return results

# CSV import: Estudiantes — formato: cedula;nombre;apellido1;apellido2;nivel;seccion;cedula_padre;accion
def import_students_from_csv(file_content: bytes) -> dict:
    reader = csv.DictReader(io.StringIO(file_content.decode('utf-8-sig')), delimiter=';')
    results = {'created': 0, 'updated': 0, 'deactivated': 0, 'linked': 0, 'skipped': 0, 'errors': []}

    def resolve_group(nivel, seccion):
        if not nivel or not seccion:
            return None
        # Normalize inputs for robust matching (case-insensitive and common accent maps)
        nivel_clean = nivel.strip().lower()
        seccion_clean = seccion.strip().upper()
        
        nivel_map = {
            "septimo": "Septimo",
            "sétimo": "Septimo",
            "séptimo": "Septimo",
            "octavo": "Octavo",
            "noveno": "Noveno",
            "decimo": "Decimo",
            "décimo": "Decimo",
            "undecimo": "Undecimo",
            "undécimo": "Undecimo",
            "duodecimo": "Duodecimo",
            "duodécimo": "Duodecimo",
            "primaria": "Primaria",
            "secundaria": "Secundaria"
        }
        
        nivel_normalized = nivel_map.get(nivel_clean, nivel.strip())
        
        row = db.groups.find_one({
            "level": {"$regex": f"^{nivel_normalized}$", "$options": "i"},
            "name": {"$regex": f"^{seccion_clean}$", "$options": "i"}
        })
        return str(row['_id']) if row else None

    for row in reader:
        accion = (row.get('accion') or '').strip().lower()
        cedula = row.get('cedula', '')

        try:
            if accion in ('insertar', 'insert', 'crear'):
                cedula_padre = row.get('cedula_padre')
                if not cedula_padre:
                    results['errors'].append({'row': cedula, 'error': 'Student must have a parent linked (missing cedula_padre)'})
                    continue
                parent = db.users.find_one({'id_number': cedula_padre, 'role': 'parent', 'active': True})
                if not parent:
                    results['errors'].append({'row': cedula, 'error': f"Parent with ID {cedula_padre} is not registered or is inactive. Student cannot be created."})
                    continue

                group_id = resolve_group(row.get('nivel'), row.get('seccion'))
                student = create({
                    'id_number':  cedula,
                    'first_name': row.get('nombre', ''),
                    'last_name':  f"{row.get('apellido1','')} {row.get('apellido2','')}".strip(),
                    'role':       'student',
                    'group_id':   group_id,
                    'parent_id':  str(parent['_id']),
                })
                results['created'] += 1
                results['linked'] += 1
            elif accion in ('update', 'actualizar', 'modificar'):
                found = db.users.find_one({'id_number': cedula})
                if not found:
                    results['errors'].append({'row': cedula, 'error': 'Not found for update'})
                    continue
                group_id = resolve_group(row.get('nivel'), row.get('seccion'))
                update(str(found['_id']), {
                    'first_name': row.get('nombre', ''),
                    'last_name':  f"{row.get('apellido1','')} {row.get('apellido2','')}".strip(),
                    'email': None, 'phone': None, 'role': 'student',
                    'type': None, 'group_id': group_id, 'active': True,
                })
                results['updated'] += 1
            elif accion in ('eliminar', 'delete', 'borrar'):
                found = db.users.find_one({'id_number': cedula})
                if not found:
                    results['errors'].append({'row': cedula, 'error': 'Not found for delete'})
                    continue
                deactivate(str(found['_id']))
                results['deactivated'] += 1
            else:
                results['skipped'] += 1
        except Exception as e:
            if 'unique' in str(e).lower() or 'already exists' in str(e).lower():
                results['skipped'] += 1
            else:
                results['errors'].append({'row': cedula, 'error': str(e)})

    return results

def search_users(query_str: str) -> list:
    if not query_str:
        return []
    regex_query = {"$regex": query_str, "$options": "i"}
    mongo_filter = {
        "$or": [
            {"first_name": regex_query},
            {"last_name": regex_query},
            {"id_number": regex_query},
            {"role": regex_query}
        ]
    }
    users = list(db.users.find(mongo_filter).sort([('last_name', 1), ('first_name', 1)]))
    return serialize_list(users)

def link_parent_student(parent_ref: str, student_ref: str) -> dict:
    # Resolve parent
    parent = None
    try:
        parent_oid = ObjectId(parent_ref)
        parent = db.users.find_one({"_id": parent_oid, "role": "parent", "active": True})
    except Exception:
        pass
    if not parent:
        parent = db.users.find_one({"id_number": parent_ref, "role": "parent", "active": True})
    if not parent:
        raise ValueError("Parent not found or inactive")

    # Resolve student
    student = None
    try:
        student_oid = ObjectId(student_ref)
        student = db.users.find_one({"_id": student_oid, "role": "student", "active": True})
    except Exception:
        pass
    if not student:
        student = db.users.find_one({"id_number": student_ref, "role": "student", "active": True})
    if not student:
        raise ValueError("Student not found or inactive")

    db.parent_students.update_one(
        {
            "parent_id": parent["_id"],
            "student_id": student["_id"]
        },
        {
            "$setOnInsert": {
                "parent_id": parent["_id"],
                "parent_cedula": parent["id_number"],
                "student_id": student["_id"],
                "student_cedula": student["id_number"]
            }
        },
        upsert=True
    )
    
    # Also update parent_cedula in the student's document
    db.users.update_one(
        {"_id": student["_id"]},
        {"$set": {"parent_cedula": parent["id_number"]}}
    )
    
    return {
        "parent_id": str(parent["_id"]),
        "parent_name": f"{parent['first_name']} {parent['last_name']}",
        "parent_cedula": parent["id_number"],
        "student_id": str(student["_id"]),
        "student_name": f"{student['first_name']} {student['last_name']}",
        "student_cedula": student["id_number"],
        "message": "Relationship linked successfully"
    }

def get_parent_children(parent_id: str) -> list:
    return get_children(parent_id)
