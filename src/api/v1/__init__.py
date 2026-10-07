"""Роутеры REST ``/api/v1``."""

from fastapi import APIRouter

from src.api.v1 import admin_staff, admin_students, auth, invitations, me

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(admin_students.router)
api_router.include_router(admin_staff.router)
api_router.include_router(invitations.router)
