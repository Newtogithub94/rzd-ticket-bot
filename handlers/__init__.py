from aiogram import Router
from .start import router as start_router
from .subscribe import router as subscribe_router
from .manage import router as manage_router

main_router = Router()
main_router.include_router(start_router)
main_router.include_router(subscribe_router)
main_router.include_router(manage_router)
