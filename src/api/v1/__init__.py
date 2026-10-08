"""Роутеры REST ``/api/v1``."""

from fastapi import APIRouter

from src.api.v1 import (
    admin_catalog,
    admin_dashboard,
    admin_exams,
    admin_finance,
    admin_homework,
    admin_schedule,
    admin_staff,
    admin_students,
    auth,
    files,
    invitations,
    me,
    reference,
    student_homework,
    student_lessons,
    student_reports,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(reference.router)
api_router.include_router(admin_students.router)
api_router.include_router(admin_staff.router)
api_router.include_router(invitations.router)
api_router.include_router(admin_schedule.router)
api_router.include_router(student_lessons.router)
api_router.include_router(student_reports.router)
api_router.include_router(admin_homework.router)
api_router.include_router(admin_exams.router)
api_router.include_router(admin_dashboard.router)
api_router.include_router(admin_catalog.admin_router)
api_router.include_router(admin_catalog.public_router)
api_router.include_router(admin_finance.finance_router)
api_router.include_router(admin_finance.stats_router)
api_router.include_router(admin_finance.audit_router)
api_router.include_router(student_homework.router)
api_router.include_router(files.router)
