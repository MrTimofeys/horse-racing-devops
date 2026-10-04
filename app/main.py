"""Точка входа приложения «Скачки».

Запуск на стенде:

    uvicorn app.main:app --host 0.0.0.0 --port 8080

или

    python -m app.cli run
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import InterfaceError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__, seed
from .config import get_settings
from .database import SessionLocal
from .deps import Forbidden, LoginRequired
from .routers import all_routers
from .web import STATIC_DIR, render, render_offline

settings = get_settings()

logger = logging.getLogger("skachki")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Создать схему БД и наполнить её начальными данными при старте стенда.

    Недоступность СУБД не останавливает приложение: служба поднимается и
    сообщает о проблеме через ``/api/health`` и страницу 503. Это важно для
    стендов STAGE и PROD, где PostgreSQL может запускаться позже приложения.
    """
    ready, error = seed.prepare_stand()

    if ready:
        logger.info(
            "Стенд %s запущен. СУБД: %s.",
            settings.stand_label,
            settings.dialect_label,
        )
    else:
        logger.error(
            "Стенд %s запущен БЕЗ базы данных: %s\n"
            "        Приложение отвечает на /api/health (status=degraded) и отдаёт страницу 503.\n"
            "        Проверьте службу СУБД и строку DATABASE_URL, затем обратитесь к /api/health —\n"
            "        схема будет создана автоматически, как только СУБД станет доступна.",
            settings.stand_label,
            error,
        )

    yield
    logger.info("Стенд %s остановлен", settings.stand_label)


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "Информационная система клуба любителей скачек: учёт лошадей, владельцев, "
        "жокеев, ипподромов, состязаний и результатов заездов.\n\n"
        "Разработана по ТЗ (лабораторная работа № 1) и разворачивается на стендах "
        "TEST / STAGE / PROD (лабораторная работа № 2 «Виртуализация»)."
    ),
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

for _router in all_routers:
    app.include_router(_router)


# --- Обработчики ошибок ---------------------------------------------------


def _wants_json(request: Request) -> bool:
    """API-запросы получают JSON, страницы — HTML."""
    if request.url.path.startswith("/api"):
        return True
    return "application/json" in request.headers.get("accept", "")


@app.exception_handler(LoginRequired)
async def handle_login_required(request: Request, exc: LoginRequired):
    if _wants_json(request):
        return JSONResponse({"detail": "Требуется авторизация"}, status_code=401)
    return RedirectResponse(url="/login", status_code=303)


@app.exception_handler(Forbidden)
async def handle_forbidden(request: Request, exc: Forbidden):
    if _wants_json(request):
        return JSONResponse({"detail": exc.message}, status_code=403)
    with SessionLocal() as db:
        return render(request, db, "errors/403.html", message=exc.message, code=403, status_code=403)


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException):
    if _wants_json(request) or exc.status_code < 400:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    template = "errors/404.html" if exc.status_code == 404 else "errors/error.html"
    with SessionLocal() as db:
        return render(
            request,
            db,
            template,
            message=exc.detail,
            code=exc.status_code,
            status_code=exc.status_code,
        )


@app.exception_handler(OperationalError)
@app.exception_handler(InterfaceError)
async def handle_database_unavailable(request: Request, exc: Exception):
    """СУБД недоступна: отдаём 503 и понятную инструкцию, а не 500 со стеком.

    Обработчик намеренно не обращается к базе (в отличие от остальных страниц
    ошибок), иначе он бы упал повторно. Попутно даём СУБД шанс подняться.
    """
    logger.error("СУБД недоступна при обработке %s: %s", request.url.path, exc)

    ready, _ = seed.prepare_stand()
    if ready:
        return RedirectResponse(url=request.url.path, status_code=303)

    if _wants_json(request):
        return JSONResponse(
            {"detail": "База данных недоступна", "database": {"available": False}},
            status_code=503,
        )

    return render_offline(
        request,
        "errors/503.html",
        status_code=503,
        message="База данных недоступна. Проверьте, что служба СУБД запущена, и повторите попытку.",
        detail=str(exc).splitlines()[0] if str(exc) else None,
    )


@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception):
    logger.exception("Необработанная ошибка при обработке %s", request.url.path)
    if _wants_json(request):
        return JSONResponse({"detail": "Внутренняя ошибка сервера"}, status_code=500)

    message = "Внутренняя ошибка сервера. Подробности записаны в журнал приложения."
    try:
        with SessionLocal() as db:
            return render(request, db, "errors/500.html", message=message, code=500, status_code=500)
    except Exception:  # noqa: BLE001 — отрисовать страницу без обращения к БД
        return render_offline(request, "errors/500.html", status_code=500, message=message, code=500)
