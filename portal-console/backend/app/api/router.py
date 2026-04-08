from fastapi import APIRouter

from app.api.routes import auth, operation_logs, projects, servers, settings, ssh_keys

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(servers.router)
api_router.include_router(ssh_keys.router)
api_router.include_router(projects.router)
api_router.include_router(operation_logs.router)
api_router.include_router(settings.router)
