import csv
import io
import os
from passlib.context import CryptContext
from src.config.database import execute, execute_one, get_db
from src.config.mailer import send_mail

pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')

# RF-05: Listar usuarios
def get_all(filters: dict = {}) -> list:
    query = """SELECT id, id_number, first_name, last_name, email, phone,
                      role, type, group_id, is_adult, active
               FROM users"""
    params = []
    conditions = []

    if filters.get('role'):
        conditions.append('role = %s')
        params.append(filters['role'])
    if filters.get('active') is not None:
        conditions.append('active = %s')
        params.append(filters['active'])

    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    query += ' ORDER BY last_name, first_name'

    return execute(query, params or None)

# RF-05: Obtener usuario por ID
def get_by_id(user_id: int):
    return execute_one(
        """SELECT id, id_number, first_name, last_name, email, phone,
                  role, type, group_id, is_adult, active
           FROM users WHERE id = %s""",
        (user_id,)
    )

# RF-05: Crear usuario — contraseña temporal = cédula
def create(data: dict) -> dict:
    password_hash = pwd_context.hash(data['id_number'])
    row = execute_one(
        """INSERT INTO users (id_number, first_name, last_name, email, phone,
                              role, type, group_id, birth_date, password_hash, must_change_password)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
           RETURNING id, id_number, first_name, last_name, email, role""",
        (
            data['id_number'], data['first_name'], data['last_name'],
            data.get('email'), data.get('phone'), data['role'],
            data.get('type'), data.get('group_id'), data.get('birth_date'),
            password_hash,
        )
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
    return row

# RF-05: Actualizar usuario
def update(user_id: int, data: dict) -> dict:
    row = execute_one(
        """UPDATE users
           SET first_name = %s, last_name = %s, email = %s, phone = %s,
               role = %s, type = %s, group_id = %s, active = %s
           WHERE id = %s
           RETURNING id, id_number, first_name, last_name, email, role, active""",
        (
            data['first_name'], data['last_name'], data.get('email'),
            data.get('phone'), data['role'], data.get('type'),
            data.get('group_id'), data['active'], user_id,
        )
    )
    if not row:
        raise ValueError('User not found')
    return row

# RF-05: Desactivar usuario
def deactivate(user_id: int):
    rows = execute('UPDATE users SET active = false WHERE id = %s RETURNING id', (user_id,))
    if not rows:
        raise ValueError('User not found')

# Materias
def get_subjects() -> list:
    return execute('SELECT id, name, code, level FROM subjects ORDER BY name')

def create_subject(data: dict) -> dict:
    return execute_one(
        'INSERT INTO subjects (name, code, level) VALUES (%s, %s, %s) RETURNING *',
        (data['name'], data['code'], data.get('level'))
    )

# Grupos
def get_groups() -> list:
    return execute('SELECT id, name, level FROM groups ORDER BY name')

# Hijos del padre
def get_children(parent_id: int) -> list:
    return execute(
        """SELECT u.id, u.first_name, u.last_name, g.name AS group_name
           FROM parent_students ps
           JOIN users u ON u.id = ps.student_id AND u.active = true
           LEFT JOIN groups g ON g.id = u.group_id
           WHERE ps.parent_id = %s
           ORDER BY u.last_name, u.first_name""",
        (parent_id,)
    )

# RF-06: Materias de un estudiante
def get_student_subjects(student_id: int, period: str = None) -> list:
    return execute(
        """SELECT s.id, s.name, s.code, s.level,
                  u.first_name || ' ' || u.last_name AS teacher_name,
                  g.name AS group_name, ss.period
           FROM student_subjects ss
           JOIN subjects s ON s.id = ss.subject_id
           LEFT JOIN users u ON u.id = ss.teacher_id
           LEFT JOIN groups g ON g.id = ss.group_id
           WHERE ss.student_id = %s AND (%s::VARCHAR IS NULL OR ss.period = %s)
           ORDER BY s.name""",
        (student_id, period, period)
    )

# RF-06: Asignar materias a estudiante
def assign_subjects_to_student(student_id: int, assignments: list):
    student = execute_one(
        'SELECT id FROM users WHERE id = %s AND role = %s AND active = true',
        (student_id, 'student')
    )
    if not student:
        raise ValueError('Student not found or inactive')

    with get_db() as conn:
        with conn.cursor() as cur:
            for a in assignments:
                cur.execute(
                    """INSERT INTO student_subjects (student_id, subject_id, teacher_id, group_id, period)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (student_id, subject_id, period)
                       DO UPDATE SET teacher_id = EXCLUDED.teacher_id, group_id = EXCLUDED.group_id""",
                    (student_id, a['subject_id'], a.get('teacher_id'), a.get('group_id'), a.get('period', '2026'))
                )

# RF-06: Quitar materia a estudiante
def remove_student_subject(student_id: int, subject_id: int, period: str = '2026'):
    execute(
        'DELETE FROM student_subjects WHERE student_id = %s AND subject_id = %s AND period = %s',
        (student_id, subject_id, period)
    )

# CSV import: Usuarios — formato: cedula;nombre;apellido1;apellido2;correo;telefono;tipo_usuario;accion
def import_users_from_csv(file_content: bytes) -> dict:
    reader = csv.DictReader(io.StringIO(file_content.decode('utf-8')), delimiter=';')
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
                found = execute_one('SELECT id FROM users WHERE id_number = %s', (cedula,))
                if not found:
                    results['errors'].append({'row': cedula, 'error': 'Not found for update'})
                    continue
                update(found['id'], {
                    'first_name': row.get('nombre', ''),
                    'last_name':  f"{row.get('apellido1','')} {row.get('apellido2','')}".strip(),
                    'email':      row.get('correo') or None,
                    'phone':      row.get('telefono') or None,
                    'role': role, 'type': None, 'group_id': None, 'active': True,
                })
                results['updated'] += 1
            elif accion in ('eliminar', 'delete', 'borrar'):
                found = execute_one('SELECT id FROM users WHERE id_number = %s', (cedula,))
                if not found:
                    results['errors'].append({'row': cedula, 'error': 'Not found for delete'})
                    continue
                deactivate(found['id'])
                results['deactivated'] += 1
            else:
                results['skipped'] += 1
        except Exception as e:
            if 'unique' in str(e).lower():
                results['skipped'] += 1
            else:
                results['errors'].append({'row': cedula, 'error': str(e)})

    return results

# CSV import: Estudiantes — formato: cedula;nombre;apellido1;apellido2;nivel;seccion;cedula_padre;accion
def import_students_from_csv(file_content: bytes) -> dict:
    reader = csv.DictReader(io.StringIO(file_content.decode('utf-8')), delimiter=';')
    results = {'created': 0, 'updated': 0, 'deactivated': 0, 'linked': 0, 'skipped': 0, 'errors': []}

    def resolve_group(nivel, seccion):
        if not nivel or not seccion:
            return None
        row = execute_one('SELECT id FROM groups WHERE level = %s AND name = %s', (nivel, seccion))
        return row['id'] if row else None

    for row in reader:
        accion = (row.get('accion') or '').strip().lower()
        cedula = row.get('cedula', '')

        try:
            if accion in ('insertar', 'insert', 'crear'):
                group_id = resolve_group(row.get('nivel'), row.get('seccion'))
                student = create({
                    'id_number':  cedula,
                    'first_name': row.get('nombre', ''),
                    'last_name':  f"{row.get('apellido1','')} {row.get('apellido2','')}".strip(),
                    'role':       'student',
                    'group_id':   group_id,
                })
                results['created'] += 1

                cedula_padre = row.get('cedula_padre')
                if cedula_padre:
                    parent = execute_one(
                        'SELECT id FROM users WHERE id_number = %s AND role = %s AND active = true',
                        (cedula_padre, 'parent')
                    )
                    if parent:
                        execute(
                            'INSERT INTO parent_students (parent_id, student_id) VALUES (%s, %s) ON CONFLICT DO NOTHING',
                            (parent['id'], student['id'])
                        )
                        results['linked'] += 1
            elif accion in ('update', 'actualizar', 'modificar'):
                found = execute_one('SELECT id FROM users WHERE id_number = %s', (cedula,))
                if not found:
                    results['errors'].append({'row': cedula, 'error': 'Not found for update'})
                    continue
                group_id = resolve_group(row.get('nivel'), row.get('seccion'))
                update(found['id'], {
                    'first_name': row.get('nombre', ''),
                    'last_name':  f"{row.get('apellido1','')} {row.get('apellido2','')}".strip(),
                    'email': None, 'phone': None, 'role': 'student',
                    'type': None, 'group_id': group_id, 'active': True,
                })
                results['updated'] += 1
            elif accion in ('eliminar', 'delete', 'borrar'):
                found = execute_one('SELECT id FROM users WHERE id_number = %s', (cedula,))
                if not found:
                    results['errors'].append({'row': cedula, 'error': 'Not found for delete'})
                    continue
                deactivate(found['id'])
                results['deactivated'] += 1
            else:
                results['skipped'] += 1
        except Exception as e:
            if 'unique' in str(e).lower():
                results['skipped'] += 1
            else:
                results['errors'].append({'row': cedula, 'error': str(e)})

    return results
