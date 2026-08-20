from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
# pyrefly: ignore [missing-import]
from apscheduler.schedulers.background import BackgroundScheduler

from src.modules.auth.auth_router import router as auth_router
from src.modules.attendance.attendance_router import router as attendance_router
from src.modules.calendar.calendar_router import router as calendar_router
from src.modules.reports.reports_router import router as reports_router
from src.modules.users.users_router import router as users_router
from src.modules.notifications.notifications_router import router as notifications_router
from src.modules.automated_system_CSV.automation_router import router as automation_router
from src.jobs.calendar_reminders import run_calendar_reminders

app = FastAPI(title="EduConecta CR API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1/auth",  tags=["auth"])
app.include_router(attendance_router, prefix="/api/v1/attendance", tags=["attendance"])
app.include_router(calendar_router, prefix="/api/v1/calendar", tags=["calendar"])
app.include_router(reports_router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(notifications_router, prefix="/api/v1/notifications", tags=["notifications"])
app.include_router(users_router, prefix="/api/v1/users", tags=["users"])
app.include_router(automation_router, prefix="/api/v1/automation", tags=["automation"])

# Background scheduler: ejecuta el job de recordatorios de calendario cada hora
scheduler = BackgroundScheduler(timezone="UTC")
scheduler.add_job(run_calendar_reminders, "interval", hours=1, id="calendar_reminders")
scheduler.start()

@app.get("/health")
def health():
    return {"status": "ok"}
