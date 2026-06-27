from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.modules.auth.auth_router import router as auth_router
from src.modules.users.users_router import router as users_router
from src.modules.automated_system_CSV.automation_router import router as automation_router

app = FastAPI(title="EduConecta CR API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1/auth",  tags=["auth"])
app.include_router(users_router, prefix="/api/v1/users", tags=["users"])
app.include_router(automation_router, prefix="/api/v1/automation", tags=["automation"])

@app.get("/health")
def health():
    return {"status": "ok"}
