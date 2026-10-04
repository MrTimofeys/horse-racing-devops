"""Раздел «Результаты» и поиск без учёта регистра.

ТЗ (п. «Базовая подсистема») требует навигации между разделами «Состязания»,
«Жокеи», «Лошади», «Владельцы» и «Результаты».
"""

from __future__ import annotations

from app import crud


class TestResultsSection:
    def test_requires_login(self, anon) -> None:
        response = anon.get("/results", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    def test_available_to_viewer(self, viewer) -> None:
        """Раздел доступен любому авторизованному пользователю."""
        assert viewer.get("/results").status_code == 200

    def test_present_in_navigation(self, admin) -> None:
        """Ссылка на раздел есть в главном меню на любой странице."""
        for path in ("/dashboard", "/races", "/horses"):
            assert ">Результаты<" in admin.get(path).text

    def test_shows_places_and_times(self, admin) -> None:
        response = admin.get("/results")
        assert response.status_code == 200
        assert "1-е место" in response.text
        # Показанное время выводится в формате «минуты:секунды,сотые».
        assert ":" in response.text

    def test_only_finished_by_default(self, admin) -> None:
        """Заявленные, но не финишировавшие лошади по умолчанию не показываются."""
        response = admin.get("/results")
        assert response.status_code == 200
        assert "не финишировала" not in response.text

    def test_show_declared_adds_participants(self, admin) -> None:
        plain = admin.get("/results").text
        declared = admin.get("/results?show_declared=true").text
        # С заявленными строк не меньше, а на стенде есть незавершённые заезды —
        # значит, появляется пометка о лошади без результата.
        assert "не финишировала" in declared
        assert len(declared) >= len(plain)

    def test_unknown_search_gives_empty_list(self, admin) -> None:
        response = admin.get("/results", params={"search": "такого-точно-нет"})
        assert response.status_code == 200
        assert "Результаты не найдены" in response.text


class TestSearchIsCaseInsensitive:
    """Поиск не должен зависеть от регистра.

    Отдельная проверка нужна из-за SQLite: его встроенные функции ``lower`` и
    ``upper`` обрабатывают только латиницу, поэтому без переопределения поиск
    по русскому тексту в другом регистре ничего не находил, а на PostgreSQL
    (стенды STAGE и PROD) работал. Поведение стендов расходилось.
    """

    def test_horse_search_lowercase(self, admin) -> None:
        response = admin.get("/horses", params={"search": "ветер"})
        assert response.status_code == 200
        assert "Ветер Перемен" in response.text

    def test_horse_search_uppercase(self, admin) -> None:
        response = admin.get("/horses", params={"search": "ВЕТЕР"})
        assert "Ветер Перемен" in response.text

    def test_jockey_search_lowercase(self, admin) -> None:
        response = admin.get("/jockeys", params={"search": "иванов"})
        assert response.status_code == 200
        assert "Иванов" in response.text

    def test_hippodrome_search_lowercase(self, admin) -> None:
        response = admin.get("/races", params={"search": "казанский"})
        assert response.status_code == 200
        assert "Казанский" in response.text

    def test_results_search_lowercase(self, admin) -> None:
        response = admin.get("/results", params={"search": "казанский"})
        assert response.status_code == 200
        assert "Результаты не найдены" not in response.text

    def test_crud_search_matches_regardless_of_case(self, db) -> None:
        """Проверка на уровне доступа к данным, без участия веб-слоя."""
        lower = crud.list_horses(db, search="ветер").total
        upper = crud.list_horses(db, search="ВЕТЕР").total
        mixed = crud.list_horses(db, search="ВеТеР").total
        assert lower == upper == mixed == 1
