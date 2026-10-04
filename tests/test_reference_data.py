"""Справочники: владельцы, лошади, жокеи, ипподромы."""

from __future__ import annotations

from sqlalchemy import select

from app import crud
from app.models import Horse, Jockey, Owner


class TestOwners:
    def test_create_and_list(self, admin) -> None:
        response = admin.post(
            "/owners/new",
            data={"name": "Тестовый Владелец", "address": "г. Москва, тестовая ул., 1", "phone": "+7 000 000-00-00"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/owners"

        listing = admin.get("/owners?search=Тестовый")
        assert listing.status_code == 200
        assert "Тестовый Владелец" in listing.text

    def test_name_is_required(self, admin) -> None:
        response = admin.post("/owners/new", data={"name": "   ", "address": "", "phone": ""})
        assert response.status_code == 400
        assert "обязательно" in response.text

    def test_update(self, admin, db) -> None:
        owner = crud.create_owner(db, name="До изменения", address="a", phone="1")
        response = admin.post(
            f"/owners/{owner.id}/edit",
            data={"name": "После изменения", "address": "b", "phone": "2"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        db.expire_all()
        assert db.get(Owner, owner.id).name == "После изменения"

    def test_delete_without_horses(self, admin, db) -> None:
        owner_id = crud.create_owner(db, name="Временный владелец").id
        response = admin.post(f"/owners/{owner_id}/delete", follow_redirects=False)
        assert response.status_code == 303
        # Удаление выполнено в другой сессии, поэтому сбрасываем кэш объектов.
        db.expunge_all()
        assert db.get(Owner, owner_id) is None

    def test_cannot_delete_owner_with_horses(self, admin, db) -> None:
        owner = crud.create_owner(db, name="Владелец с лошадью")
        crud.create_horse(db, name="Лошадь владельца", sex="кобыла", age=4, owner_id=owner.id)

        response = admin.post(f"/owners/{owner.id}/delete", follow_redirects=True)
        assert "Нельзя удалить владельца" in response.text
        db.expunge_all()
        assert db.get(Owner, owner.id) is not None

    def test_search_filter(self, admin, db) -> None:
        crud.create_owner(db, name="Уникальный Поиск Иванов", phone="+7 111")
        response = admin.get("/owners?search=Уникальный Поиск")
        assert "Уникальный Поиск Иванов" in response.text
        assert "Кузнецова" not in response.text


class TestHorses:
    def test_create(self, admin, db) -> None:
        owner = crud.create_owner(db, name="Владелец лошади")
        response = admin.post(
            "/horses/new",
            data={"name": "Тестовая Лошадка", "sex": "кобыла", "age": "5", "owner_id": str(owner.id)},
            follow_redirects=False,
        )
        assert response.status_code == 303

        horse = db.scalars(select(Horse).where(Horse.name == "Тестовая Лошадка")).one()
        assert horse.sex == "кобыла"
        assert horse.age == 5
        assert horse.owner_id == owner.id

    def test_owner_is_optional(self, admin, db) -> None:
        response = admin.post(
            "/horses/new",
            data={"name": "Лошадь без владельца", "sex": "мерин", "age": "6", "owner_id": ""},
            follow_redirects=False,
        )
        assert response.status_code == 303
        horse = db.scalars(select(Horse).where(Horse.name == "Лошадь без владельца")).one()
        assert horse.owner_id is None
        assert horse.owner_name == "не указан"

    def test_invalid_sex_rejected(self, admin) -> None:
        response = admin.post(
            "/horses/new", data={"name": "Лошадь", "sex": "дракон", "age": "5", "owner_id": ""}
        )
        assert response.status_code == 400
        assert "Пол" in response.text

    def test_age_out_of_range_rejected(self, admin) -> None:
        response = admin.post(
            "/horses/new", data={"name": "Лошадь", "sex": "кобыла", "age": "99", "owner_id": ""}
        )
        assert response.status_code == 400
        assert "Возраст" in response.text

    def test_cannot_delete_horse_in_races(self, admin, db) -> None:
        horse = db.scalars(select(Horse).where(Horse.name == "Ветер Перемен")).one()
        horse_id = horse.id
        response = admin.post(f"/horses/{horse_id}/delete", follow_redirects=True)
        assert "Нельзя удалить лошадь" in response.text
        db.expunge_all()
        assert db.get(Horse, horse_id) is not None

    def test_filter_by_owner(self, admin, db) -> None:
        owner = crud.create_owner(db, name="Фильтрующий Владелец")
        crud.create_horse(db, name="Лошадь Фильтра", sex="жеребец", age=3, owner_id=owner.id)
        response = admin.get(f"/horses?owner_id={owner.id}")
        assert "Лошадь Фильтра" in response.text
        assert "Ветер Перемен" not in response.text


class TestJockeys:
    def test_create(self, admin, db) -> None:
        response = admin.post(
            "/jockeys/new",
            data={"name": "Тестовый Жокей", "address": "г. Москва", "age": "27", "rating": "75"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        jockey = db.scalars(select(Jockey).where(Jockey.name == "Тестовый Жокей")).one()
        assert jockey.rating == 75
        assert jockey.age == 27

    def test_age_below_minimum_rejected(self, admin) -> None:
        response = admin.post(
            "/jockeys/new", data={"name": "Юный", "address": "", "age": "10", "rating": "10"}
        )
        assert response.status_code == 400
        assert "16" in response.text

    def test_rating_zero_allowed(self, admin, db) -> None:
        response = admin.post(
            "/jockeys/new",
            data={"name": "Жокей без рейтинга", "address": "", "age": "20", "rating": "0"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        jockey = db.scalars(select(Jockey).where(Jockey.name == "Жокей без рейтинга")).one()
        assert jockey.rating == 0

    def test_rating_above_maximum_rejected(self, admin) -> None:
        response = admin.post(
            "/jockeys/new", data={"name": "Жокей", "address": "", "age": "20", "rating": "5000"}
        )
        assert response.status_code == 400
        assert "1000" in response.text


class TestHippodromes:
    def test_create(self, admin, db) -> None:
        response = admin.post(
            "/hippodromes/new",
            data={"name": "Тестовый ипподром", "city": "Тула", "address": "ул. Тестовая, 1"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        listing = admin.get("/hippodromes?search=Тестовый")
        assert "Тестовый ипподром" in listing.text

    def test_cannot_delete_hippodrome_with_races(self, admin, db) -> None:
        hippodrome = crud.list_hippodromes(db, per_page=1).items[0]
        response = admin.post(f"/hippodromes/{hippodrome.id}/delete", follow_redirects=True)
        assert "Нельзя удалить ипподром" in response.text

    def test_name_required(self, admin) -> None:
        response = admin.post("/hippodromes/new", data={"name": "", "city": "Тула", "address": ""})
        assert response.status_code == 400


class TestNotFound:
    def test_missing_owner(self, admin) -> None:
        assert admin.get("/owners/999999/edit").status_code == 404

    def test_missing_horse(self, admin) -> None:
        assert admin.get("/horses/999999").status_code == 404

    def test_unknown_page(self, admin) -> None:
        response = admin.get("/такой-страницы-нет")
        assert response.status_code == 404
        assert "не найдена" in response.text
