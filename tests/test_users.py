"""Управление учётными записями (только администратор)."""

from __future__ import annotations

from sqlalchemy import select

from app.models import User


def _create_user(admin, username: str, password: str = "secret123", role: str = "operator"):
    return admin.post(
        "/users/new",
        data={
            "username": username,
            "full_name": "Тестовый пользователь",
            "role": role,
            "password": password,
            "password2": password,
        },
        follow_redirects=False,
    )


class TestUserManagement:
    def test_admin_sees_users_list(self, admin) -> None:
        response = admin.get("/users")
        assert response.status_code == 200
        for username in ("admin", "operator", "viewer"):
            assert username in response.text

    def test_create_user(self, admin, db) -> None:
        response = _create_user(admin, "new_operator", role="operator")
        assert response.status_code == 303

        db.expire_all()
        user = db.scalars(select(User).where(User.username == "new_operator")).one()
        assert user.role == "operator"
        assert user.is_active is True
        assert user.password_hash.startswith("pbkdf2_sha256$")

    def test_created_user_can_login(self, admin, anon) -> None:
        _create_user(admin, "login_test", password="pass12345")
        response = anon.post(
            "/login", data={"username": "login_test", "password": "pass12345"}, follow_redirects=False
        )
        assert response.status_code == 303

    def test_duplicate_username_rejected(self, admin) -> None:
        _create_user(admin, "duplicate_user")
        response = _create_user(admin, "duplicate_user")
        assert response.status_code == 400
        assert "уже существует" in response.text

    def test_short_password_rejected(self, admin) -> None:
        response = _create_user(admin, "short_pass_user", password="123")
        assert response.status_code == 400
        assert "не менее 6" in response.text

    def test_mismatched_passwords_rejected(self, admin) -> None:
        response = admin.post(
            "/users/new",
            data={
                "username": "mismatch_user",
                "full_name": "",
                "role": "operator",
                "password": "secret123",
                "password2": "secret124",
            },
        )
        assert response.status_code == 400
        assert "не совпадают" in response.text

    def test_invalid_role_rejected(self, admin) -> None:
        response = _create_user(admin, "bad_role_user", role="superuser")
        assert response.status_code == 400

    def test_password_change_works(self, admin, anon, db) -> None:
        _create_user(admin, "password_user", password="oldpassword")

        response = admin.post(
            f"/users/{_user_id(db, 'password_user')}/password",
            data={"password": "brandnew1", "password2": "brandnew1"},
            follow_redirects=False,
        )
        assert response.status_code == 303

        old = anon.post("/login", data={"username": "password_user", "password": "oldpassword"})
        assert old.status_code == 401

        new = anon.post(
            "/login", data={"username": "password_user", "password": "brandnew1"}, follow_redirects=False
        )
        assert new.status_code == 303

    def test_deactivated_user_cannot_login(self, admin, anon, db) -> None:
        _create_user(admin, "disabled_user")
        user_id = _user_id(db, "disabled_user")

        admin.post(
            f"/users/{user_id}/edit",
            data={"full_name": "Отключённый", "role": "operator", "is_active": ""},
            follow_redirects=False,
        )

        response = anon.post(
            "/login", data={"username": "disabled_user", "password": "secret123"}
        )
        assert response.status_code == 401

    def test_admin_cannot_delete_self(self, admin, db) -> None:
        admin_id = _user_id(db, "admin")
        response = admin.post(f"/users/{admin_id}/delete", follow_redirects=True)
        assert "собственную учётную запись" in response.text
        db.expunge_all()
        assert db.get(User, admin_id) is not None

    def test_cannot_remove_last_active_admin(self, admin, db) -> None:
        admin_id = _user_id(db, "admin")
        response = admin.post(
            f"/users/{admin_id}/edit",
            data={"full_name": "Администратор", "role": "viewer", "is_active": "true"},
            follow_redirects=True,
        )
        assert "последнего активного администратора" in response.text

    def test_delete_user(self, admin, db) -> None:
        _create_user(admin, "to_be_deleted")
        user_id = _user_id(db, "to_be_deleted")

        response = admin.post(f"/users/{user_id}/delete", follow_redirects=False)
        assert response.status_code == 303
        db.expire_all()
        assert db.get(User, user_id) is None

    def test_missing_user(self, admin) -> None:
        assert admin.get("/users/999999/edit").status_code == 404
        assert admin.get("/users/999999/password").status_code == 404


def _user_id(db, username: str) -> int:
    db.expire_all()
    return db.scalars(select(User).where(User.username == username)).one().id
