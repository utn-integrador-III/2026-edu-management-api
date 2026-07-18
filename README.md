# Edu Management— Backend API 

> Plataforma de gestión escolar para centros educativos costarricenses. Conecta docentes, padres/madres de familia y administración en un solo sistema centralizado.

---

## Tabla de Contenidos

- [Descripción General](#descripción-general)
- [Stack Tecnológico](#stack-tecnológico)
- [Inicialización del Proyecto](#inicialización-del-proyecto)
- [Configuración de Variables de Entorno](#configuración-de-variables-de-entorno)
- [Sembrado de Base de Datos](#sembrado-de-base-de-datos)
- [Sistema de Automatización y Restricción de Padres](#sistema-de-automatización-y-restricción-de-padres)
- [Mapa de API Endpoints (Roadmap de Releases)](#mapa-de-api-endpoints-roadmap-de-releases)

---

## Descripción General

**Edu Management** es una plataforma web orientada a instituciones educativas de Costa Rica. Su objetivo es digitalizar y centralizar la gestión de asistencia, calificaciones, eventos del calendario escolar y la comunicación entre docentes y familias.

El backend está desarrollado con **FastAPI** y utiliza **MongoDB Atlas** para persistencia de datos. Administra flujos de seguridad (cambios de contraseña obligatorios en el primer ingreso, recuperación de accesos por token temporal) y control de accesos basado en roles.

---

## Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| **Capa de Servidor** | Python 3.12+ (FastAPI) |
| **Base de Datos** | MongoDB (PyMongo para operaciones síncronas, Motor para asíncronas) |
| **Autenticación** | JWT (JSON Web Tokens con blacklist de cierre de sesión en base de datos) |
| **Notificaciones** | Email (SMTP con TLS / MIMEMultipart) |

---

## Inicialización del Proyecto

Sigue estos pasos para instalar y ejecutar el servidor de desarrollo localmente:

### 1. Clonar el repositorio y crear el entorno virtual (`.venv`)
Asegúrate de aislar las dependencias del proyecto creando un entorno virtual local:

* **Windows**:
  ```powershell
  python -m venv .venv
  .\.venv\Scripts\activate
  ```
* **Linux / macOS**:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### 2. Instalar dependencias
Instala los paquetes necesarios utilizando el archivo de requerimientos:
```bash
pip install -r requirements.txt
```

### 3. Ejecutar el servidor de desarrollo
Inicia la API con recarga automática:
```bash
uvicorn main:app --reload
```
La documentación interactiva de Swagger estará disponible en: `http://127.0.0.1:8000/docs`

---

## Configuración de Variables de Entorno

Por motivos de seguridad, **el archivo `.env` NO está incluido en el repositorio** (`.gitignore` lo excluye). Cada desarrollador debe crear un archivo `.env` en la raíz del proyecto local con las credenciales correspondientes.

### Plantilla del archivo `.env`
Crea el archivo e inserta la siguiente estructura:

```env
# Conexión a MongoDB Atlas
MONGODB_URI="mongodb+srv://tu_usuario:tu_contraseña@cluster.mongodb.net/educonecta?retryWrites=true&w=majority"

# Configuración de Seguridad
JWT_SECRET="escribe_una_clave_secreta_y_larga_aqui"
FRONTEND_URL="http://localhost:5173"

# Configuración del Servidor de Correo (SMTP)
EMAIL_FROM="no-reply@educonecta.cr"
SMTP_HOST="smtp.tu-proveedor.com"
SMTP_PORT=587
SMTP_USER="tu_correo_de_correo@smtp.com"
SMTP_PASS="tu_contraseña_smtp"
```

---

## Sembrado de Base de Datos

El backend incluye una rutina de inicialización de base de datos automática al arrancar. Si MongoDB está vacío, el servidor creará de forma automática:
- **Colección de Secciones/Grupos**: Inserta las aulas iniciales (`7-A`, `7-B`, `8-A`, `9-A`) y las secciones requeridas para pruebas de ejemplo (`4-2`, `2-1`, `3-3`, `1-2`).
- **Administrador por defecto**:
  - **Usuario / Cédula**: `admin`
  - **Contraseña temporal**: `admin123` (El sistema forzará su cambio en el primer login).

---

## Sistema de Automatización y Restricción de Padres

El backend incluye scripts independientes de importación local (`readUser.py` y `students.py` dentro de `src/modules/automated_system_CSV/`) para procesar cargas por lote desde archivos CSV, además de endpoints para cargas dinámicas desde la interfaz.

### Restricción Crítica de Negocio
> [!IMPORTANT]
> **No se puede ingresar a ningún estudiante que no tenga un encargado (padre/madre/tutor) previamente registrado en el sistema.**
> - Si se intenta crear un estudiante (vía API o cargando un CSV) cuya cédula de padre (`cedula_padre`) no corresponda a un usuario activo con rol `parent` en la base de datos, **el registro del estudiante será rechazado y omitido**, informando el error en los reportes de carga.

### Vínculo Visual en Base de Datos
Para facilitar la lectura y visualización directa de la relación en MongoDB:
- Cada estudiante guarda en su documento el campo `"parent_cedula": "cedula_del_padre"`.
- Los registros de la colección `parent_students` guardan tanto los identificadores del sistema (`parent_id`, `student_id`) como las cédulas de texto físicas (`parent_cedula`, `student_cedula`).

---

## Mapa de API Endpoints (Roadmap de Releases)

A continuación se detalla la planeación y estado de los endpoints del backend:

### 🚀 Release 1 — Autenticación, Usuarios y CSV (Completado)

#### Módulo de Autenticación (`/api/v1/auth`)
* `POST /login`: Valida credenciales de login y genera tokens JWT.
* `PUT /change-password`: Procesa el cambio obligatorio de contraseña temporal.
* `POST /logout`: Invalida el JWT activo agregándolo a la lista negra (`token_blacklist`).
* `POST /recover-password`: Genera token de recuperación de expiración corta y envía enlace por SMTP.
* `POST /reset-password`: Aplica la nueva contraseña si el token de recuperación es válido.

#### Módulo de Usuarios y Estudiantes (`/api/v1/users`)
* `GET /`: Lista de manera global los usuarios (admite filtros de rol y estado activo).
* `GET /search?q={query}`: Búsqueda indexada y filtrada por coincidencia en nombre, cédula o rol.
* `GET /{user_id}`: Retorna la información general de un usuario específico.
* `POST /`: Crea un nuevo usuario. **Si el rol es `student`, requiere obligatoriamente `parent_id`**.
* `PUT /{user_id}`: Modifica los campos de perfil del usuario.
* `DELETE /{user_id}`: Desactiva lógicamente una cuenta de usuario.
* `GET /parents/{parent_id}/children`: Consulta y lista de estudiantes vinculados a un padre.
* `GET /my-children`: Consulta de hijos de un padre autenticado actualmente.
* `POST /parent-students`: Vincula manualmente la relación padre-estudiante.
* `GET /{student_id}/subjects`: Consulta la lista de materias de un estudiante.
* `POST /{student_id}/subjects`: Asigna materias en bloque a un estudiante.
* `DELETE /{student_id}/subjects/{subject_id}`: Desvincula una materia asignada previamente.

#### Módulo de Automatización CSV (`/api/v1/automation`)
* `POST /users`: Ejecuta la importación por lotes de usuarios del archivo local `users.csv`.
* `POST /students`: Ejecuta la importación por lotes de estudiantes del archivo local `students.csv`.
* `POST /api/v1/users/import/users`: Endpoint HTTP para recibir y procesar un archivo CSV de usuarios cargado desde el frontend.
* `POST /api/v1/users/import/students`: Endpoint HTTP para recibir y procesar un archivo CSV de estudiantes cargado desde el frontend.

---

### 📅 Release 2 — Asistencia, Calendario y Notificaciones Firebase (Próximo)

#### Módulo de Asistencia (`/api/v1/attendance`)
* `POST /`: Registra en lote asistencia diaria (Presente, Ausente, Tardanza) de un grupo.
* `GET /`: Recupera historial de asistencia por materia y fecha.
* `GET /students/{student_id}/monthly`: Retorna estadísticas mensuales para visualización móvil.

#### Módulo de Notificaciones (`/api/v1/notifications`)
* `POST /send-absence`: Detecta ausencias y despacha alertas push a padres vía Firebase (FCM).
* `POST /send-tardiness`: Despacha alerta push con marca de tiempo de llegada tardía a padres vía FCM.

#### Módulo de Calendario Escolar (`/api/v1/calendar`)
* `POST /events`: Registra evento escolar (Examen, Actividad, Feriado) vinculado a una sección.
* `GET /events`: Recupera colección de eventos del calendario de manera histórica.
* `GET /students/{student_id}/events`: Filtra las actividades vigentes que competen al alumno.

---

### 📊 Release 3 — Reportes PDF y Mantenimiento (Futuro)

#### Módulo de Reportes (`/api/v1/reports`)
* `GET /pdf/groups/{group_id}`: Genera dinámicamente un reporte PDF consolidado del grupo con métricas académicas y de asistencia.

#### Edición de Calendario
* `PUT /api/v1/calendar/events/{id}`: Modifica especificaciones de un evento del calendario y alerta de cambios.
* `DELETE /api/v1/calendar/events/{id}`: Elimina evento y notifica la cancelación del mismo.

#### Tareas del Sistema
* `Cron Job`: Proceso automatizado en segundo plano que escanea diariamente eventos de calendario a ocurrir en las próximas 24 horas y despacha recordatorios.
