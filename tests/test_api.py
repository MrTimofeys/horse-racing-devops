"""JSON-API приложения и проверка работоспособности стенда."""

from __future__ import annotations


class TestHealth:
    def test_health_reports_stand_and_database(self, anon) -> None:
        response = anon.get("/api/health")
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["stand"] == "TEST"
        assert payload["database"]["available"] is True
        # Диалект зависит от того, на какой СУБД запущен прогон: набор тестов
        # можно выполнять и на SQLite, и на PostgreSQL.
        assert payload["database"]["dialect"] in {"SQLite", "PostgreSQL"}
        assert payload["version"] == "1.0.0"

    def test_health_does_not_require_login(self, anon) -> None:
        assert anon.get("/api/health").status_code == 200


class TestApiResources:
    def test_whoami(self, admin) -> None:
        payload = admin.get("/api/whoami").json()
        assert payload["username"] == "admin"
        assert payload["role"] == "admin"

    def test_stats(self, admin) -> None:
        payload = admin.get("/api/stats").json()
        assert payload["horses"] >= 8
        assert payload["jockeys"] >= 6
        assert payload["hippodromes"] >= 3
        assert payload["users"] >= 3

    def test_owners(self, admin) -> None:
        payload = admin.get("/api/owners").json()
        assert payload["total"] >= 4
        first = payload["items"][0]
        assert {"id", "name", "address", "phone", "horses_count"} <= set(first)

    def test_horses(self, admin) -> None:
        payload = admin.get("/api/horses").json()
        assert payload["total"] >= 8
        names = {item["name"] for item in payload["items"]}
        assert "Ветер Перемен" in names
        horse = next(item for item in payload["items"] if item["name"] == "Ветер Перемен")
        assert horse["sex"] == "жеребец"
        assert horse["owner_name"]

    def test_jockeys(self, admin) -> None:
        payload = admin.get("/api/jockeys").json()
        assert payload["total"] >= 6
        assert all(item["rating"] >= 0 for item in payload["items"])

    def test_hippodromes(self, admin) -> None:
        payload = admin.get("/api/hippodromes").json()
        assert payload["total"] >= 3

    def test_races_list(self, admin) -> None:
        payload = admin.get("/api/races").json()
        assert payload["total"] >= 4
        race = payload["items"][0]
        assert {"id", "title", "date", "time", "status", "hippodrome", "participants_count"} <= set(race)

    def test_race_detail_includes_participants(self, admin) -> None:
        payload = admin.get("/api/races/1").json()
        assert payload["title"] == "Кубок открытия сезона"
        assert len(payload["participants"]) == 4
        winner = payload["participants"][0]
        assert winner["place"] == 1
        assert winner["finish_time_seconds"] == 125.30
        assert winner["finish_time"] == "2:05,30"
        assert winner["horse"]["name"]
        assert winner["jockey"]["name"]

    def test_race_filter_by_status(self, admin) -> None:
        payload = admin.get("/api/races?status=finished").json()
        assert payload["total"] >= 2
        assert all(item["status"] == "finished" for item in payload["items"])

    def test_missing_race_returns_json_404(self, admin) -> None:
        response = admin.get("/api/races/999999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Состязание не найдено"

    def test_api_returns_401_json_without_login(self, anon) -> None:
        response = anon.get("/api/stats")
        assert response.status_code == 401
        assert response.headers["content-type"].startswith("application/json")


class TestOpenApi:
    def test_schema_is_available(self, admin) -> None:
        response = admin.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        for path in ("/login", "/dashboard", "/races", "/horses", "/jockeys", "/owners", "/api/health"):
            assert path in paths, path

    def test_docs_page(self, admin) -> None:
        assert admin.get("/docs").status_code == 200
