# Guia de pruebas manuales

Esta guia sirve para probar el backend desde cero, usando Postman o la documentacion interactiva de Swagger.

No modifica el flujo del proyecto; solo describe el orden recomendado para validar autenticacion, creacion de usuarios y el modulo de asistencia.

---

## 1. Requisitos previos

Antes de probar, asegúrate de tener:

- Python y dependencias instaladas.
- Un archivo `.env` configurado en la raiz del proyecto.
- MongoDB accesible.
- El servidor corriendo con:

```bash
uvicorn main:app --reload
```

La documentacion de Swagger queda disponible en:

```text
http://127.0.0.1:8000/docs
```

---

## 2. Usuario inicial para entrar al sistema

Si la base de datos esta vacia, el proyecto crea un administrador por defecto:

- Cédula / ID: `admin`
- Contraseña temporal: `admin123`

Ese usuario debe cambiar la contraseña en el primer ingreso.

---

## 3. Orden recomendado de pruebas

Este es el flujo que conviene seguir para validar todo desde el inicio:

1. Hacer login como admin.
2. Cambiar la contraseña temporal si aplica.
3. Crear un usuario padre.
4. Crear un usuario estudiante vinculado al padre.
5. Crear o verificar materias.
6. Registrar asistencia.
7. Verificar historial y resumen mensual.
8. Revisar el envio de notificaciones por correo.

---

## 4. Probar desde Postman

### 4.1 Configuracion inicial en Postman

Te recomiendo crear una variable de entorno:

- `baseUrl` = `http://127.0.0.1:8000`

Despues de hacer login, guarda el token en otra variable:

- `token` = valor devuelto por `/api/v1/auth/login`

En las requests protegidas usa este header:

```http
Authorization: Bearer {{token}}
```

---

### 4.2 Login

**Metodo:** `POST`

**URL:**

```text
{{baseUrl}}/api/v1/auth/login
```

**Body JSON:**

```json
{
  "id_number": "admin",
  "password": "admin123"
}
```

**Respuesta esperada:**

- `token`
- `mustChangePassword`
- `role`
- `first_name`
- `last_name`

Si `mustChangePassword` viene en `true`, debes ejecutar el cambio de contraseña antes de seguir.

---

### 4.3 Cambio de contraseña

**Metodo:** `PUT`

**URL:**

```text
{{baseUrl}}/api/v1/auth/change-password
```

**Headers:**

```http
Authorization: Bearer {{token}}
```

**Body JSON:**

```json
{
  "currentPassword": "admin123",
  "newPassword": "Admin12345"
}
```

---

### 4.4 Crear padre

**Metodo:** `POST`

**URL:**

```text
{{baseUrl}}/api/v1/users
```

**Headers:**

```http
Authorization: Bearer {{token}}
```

**Body JSON:**

```json
{
  "id_number": "0102030405",
  "first_name": "Maria",
  "last_name": "Perez",
  "role": "parent",
  "email": "maria.perez@example.com",
  "phone": "8888-8888"
}
```

Guarda el `id` devuelto porque lo vas a usar para vincular al estudiante.

---

### 4.5 Crear estudiante vinculado al padre

**Metodo:** `POST`

**URL:**

```text
{{baseUrl}}/api/v1/users
```

**Headers:**

```http
Authorization: Bearer {{token}}
```

**Body JSON:**

```json
{
  "id_number": "0203040506",
  "first_name": "Juan",
  "last_name": "Perez",
  "role": "student",
  "email": "juan.perez@example.com",
  "phone": "8888-1111",
  "group_id": null,
  "birth_date": "2012-05-10",
  "parent_id": "ID_DEL_PADRE"
}
```

Si el padre no existe o esta inactivo, el backend rechazara el registro.

---

### 4.6 Crear o verificar materias

**Metodo:** `POST`

**URL:**

```text
{{baseUrl}}/api/v1/users/subjects
```

**Headers:**

```http
Authorization: Bearer {{token}}
```

**Body JSON:**

```json
{
  "name": "Matematicas",
  "code": "MAT-01",
  "level": "Primaria"
}
```

Si quieres ver las materias ya creadas:

**Metodo:** `GET`

**URL:**

```text
{{baseUrl}}/api/v1/users/subjects
```

---

### 4.7 Registrar asistencia

**Metodo:** `POST`

**URL:**

```text
{{baseUrl}}/api/v1/attendance
```

**Headers:**

```http
Authorization: Bearer {{token}}
```

**Body JSON:**

```json
{
  "records": [
    {
      "student_id": "ID_DEL_ESTUDIANTE",
      "subject_id": "ID_DE_LA_MATERIA",
      "status": "present",
      "group_id": null,
      "note": "Ingreso normal"
    },
    {
      "student_id": "ID_DEL_ESTUDIANTE",
      "subject_id": "ID_DE_LA_MATERIA",
      "status": "absent",
      "group_id": null,
      "note": "No asistio"
    },
    {
      "student_id": "ID_DEL_ESTUDIANTE",
      "subject_id": "ID_DE_LA_MATERIA",
      "status": "tardiness",
      "group_id": null,
      "note": "Llegada tarde"
    }
  ]
}
```

**Resultado esperado:**

- Se guarda el registro con la fecha actual.
- Si el estado es `absent`, se genera una notificacion por correo al padre.
- Si el estado es `tardiness`, se genera una notificacion por correo al padre con la hora exacta.

---

### 4.8 Ver historial de asistencia

**Metodo:** `GET`

**URL:**

```text
{{baseUrl}}/api/v1/attendance
```

**Headers:**

```http
Authorization: Bearer {{token}}
```

**Filtros opcionales por query params:**

- `student_id`
- `subject_id`
- `group_id`
- `date` en formato `YYYY-MM-DD`
- `status` con valores `present`, `absent` o `tardiness`

**Ejemplo:**

```text
{{baseUrl}}/api/v1/attendance?student_id=ID_DEL_ESTUDIANTE&date=2026-07-17
```

Si el usuario es padre, solo vera la asistencia de sus hijos.

---

### 4.9 Ver resumen mensual de un estudiante

**Metodo:** `GET`

**URL:**

```text
{{baseUrl}}/api/v1/attendance/students/ID_DEL_ESTUDIANTE/monthly
```

**Headers:**

```http
Authorization: Bearer {{token}}
```

**Query params opcionales:**

- `month`
- `year`

**Ejemplo:**

```text
{{baseUrl}}/api/v1/attendance/students/ID_DEL_ESTUDIANTE/monthly?month=7&year=2026
```

La respuesta incluye conteo de `present`, `absent` y `tardiness`, ademas de los registros por dia.

---

### 4.10 Probar notificaciones manualmente

Si quieres disparar la notificacion directo sin pasar por el registro de asistencia:

#### Ausencia

**Metodo:** `POST`

**URL:**

```text
{{baseUrl}}/api/v1/notifications/send-absence
```

**Body JSON:**

```json
{
  "student_id": "ID_DEL_ESTUDIANTE",
  "subject_id": "ID_DE_LA_MATERIA",
  "attendance_id": null
}
```

#### Tardanza

**Metodo:** `POST`

**URL:**

```text
{{baseUrl}}/api/v1/notifications/send-tardiness
```

**Body JSON:**

```json
{
  "student_id": "ID_DEL_ESTUDIANTE",
  "subject_id": "ID_DE_LA_MATERIA",
  "attendance_id": null
}
```

---

## 5. Probar desde Swagger

Swagger es util porque ya trae el contrato de la API y permite ejecutar cada endpoint sin configurar colecciones.

### Flujo recomendado en Swagger

1. Abre `http://127.0.0.1:8000/docs`.
2. Ejecuta `POST /api/v1/auth/login`.
3. Copia el token.
4. Usa el boton `Authorize` e ingresa:

```text
Bearer TU_TOKEN
```

5. Ejecuta `POST /api/v1/users` para crear padre y estudiante.
6. Ejecuta `POST /api/v1/attendance` con registros de prueba.
7. Ejecuta `GET /api/v1/attendance` y `GET /api/v1/attendance/students/{student_id}/monthly`.

---

## 6. Casos de prueba sugeridos

### Login

- Login con credenciales correctas.
- Login con contraseña incorrecta.
- Login con usuario inactivo.

### Usuarios

- Crear padre.
- Crear estudiante con `parent_id` valido.
- Intentar crear estudiante sin padre.
- Intentar crear estudiante con padre inexistente.

### Asistencia

- Registrar `present`.
- Registrar `absent` y verificar que se genere notificacion.
- Registrar `tardiness` y verificar que se genere notificacion con hora exacta.
- Consultar historial por fecha.
- Consultar resumen mensual.

### Permisos

- Como padre, consultar solo sus hijos.
- Como admin, consultar todo.

---

## 7. Observaciones importantes

- El backend usa JWT en los endpoints protegidos.
- Las rutas de usuarios, asistencia y notificaciones requieren roles especificos.
- La fecha de asistencia se toma automaticamente en el servidor.
- Las notificaciones se envian por correo, no por Firebase.
