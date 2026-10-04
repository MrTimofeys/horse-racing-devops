"""Маршруты (роутеры) приложения «Скачки»."""

from . import api, auth, dashboard, hippodromes, horses, jockeys, owners, races, results, users

# Порядок подключения определяет порядок в документации OpenAPI.
all_routers = [
    auth.router,
    dashboard.router,
    owners.router,
    horses.router,
    jockeys.router,
    hippodromes.router,
    races.router,
    results.router,
    users.router,
    api.router,
]

__all__ = ["all_routers"]
