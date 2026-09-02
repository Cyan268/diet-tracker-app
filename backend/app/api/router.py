from fastapi import APIRouter

from app.api.routes import ai, auth, diet, health, meta, users

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(meta.router, prefix="/meta", tags=["meta"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(diet.router, tags=["diet"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
