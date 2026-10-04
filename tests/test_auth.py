"""Авторизация и разграничение прав доступа (требования ТЗ к защите от НСД)."""

from __future__ import annotations


class TestAuthentication:
    def test_anonymous_redirected_to_login(self, anon) -> None:
        for path in ("/dashboard", "/races", "/horses", "/jockeys", "/owners", "/results", "/hippodromes"):
            response = anon.get(path, follow_redirects=False)
            assert response.status_code == 303, path
            assert response.headers["location"] == "/login", path

    def test_login_page_available_without_auth(self, anon) -> None:
        response = anon.get("/login")
        assert response.status_code == 200
        assert "Вход в систему" in response.text
        # ТЗ: «слепые» пароли — поле ввода пароля скрывает символы.
        assert 'type="password"' in response.text

    def test_successful_login(self, anon) -> None:
        response = anon.post(
            "/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard"
        assert "skachki_session" in response.cookies

    def test_wrong_password(self, anon) -> None:
        response = anon.post("/login", data={"username": "admin", "password": "неверный"})
        assert response.status_code == 401
        assert "Неверный логин или пароль" in response.text

    def test_unknown_user_gives_same_message(self, anon) -> None:
        """Сообщение не должно раскрывать, существует ли такой логин."""
        response = anon.post("/login", data={"username": "нет_такого", "password": "x"})
        assert response.status_code == 401
        assert "Неверный логин или пароль" in response.text

    def test_logout_clears_session(self, admin) -> None:
        assert admin.get("/dashboard", follow_redirects=False).status_code == 200
        response = admin.post("/logout", follow_redirects=False)
        assert response.status_code == 303
        assert admin.get("/dashboard", follow_redirects=False).status_code == 303

    def test_empty_credentials_rejected(self, anon) -> None:
        response = anon.post("/login", data={"username": "", "password": ""})
        assert response.status_code == 401


class TestRolePermissions:
    """Разграничение доступа на уровне задач (ТЗ)."""

    def test_viewer_can_read(self, viewer) -> None:
        for path in ("/dashboard", "/races", "/horses", "/jockeys", "/owners", "/results", "/hippodromes"):
            assert viewer.get(path).status_code == 200, path

    def test_viewer_cannot_open_creation_forms(self, viewer) -> None:
        for path in ("/owners/new", "/horses/new", "/jockeys/new", "/hippodromes/new", "/races/new"):
            assert viewer.get(path).status_code == 403, path

    def test_viewer_cannot_create(self, viewer) -> None:
        response = viewer.post("/owners/new", data={"name": "Попытка наблюдателя"})
        assert response.status_code == 403

    def test_viewer_cannot_delete(self, viewer) -> None:
        response = viewer.post("/owners/1/delete", follow_redirects=False)
        assert response.status_code == 403

    def test_operator_can_create_but_not_delete(self, operator) -> None:
        assert operator.get("/owners/new").status_code == 200
        response = operator.post("/owners/1/delete", follow_redirects=False)
        assert response.status_code == 403

    def test_users_section_is_admin_only(self, operator, viewer) -> None:
        assert operator.get("/users").status_code == 403
        assert viewer.get("/users").status_code == 403

    def test_admin_can_open_users_section(self, admin) -> None:
        response = admin.get("/users")
        assert response.status_code == 200
        assert "admin" in response.text

    def test_403_page_explains_the_reason(self, viewer) -> None:
        response = viewer.get("/users")
        assert "Доступ запрещён" in response.text
        assert "Наблюдатель" in response.text

    def test_api_requires_authorization(self, anon) -> None:
        response = anon.get("/api/races")
        assert response.status_code == 401
        assert response.json()["detail"] == "Требуется авторизация"

    def test_health_is_public(self, anon) -> None:
        response = anon.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
