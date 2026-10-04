"""Функции 6 и 7 ТЗ: список состязаний каждого жокея и каждой лошади."""

from __future__ import annotations

from datetime import date, time

from sqlalchemy import select

from app import crud
from app.models import Hippodrome, Horse, Jockey, Owner, Race


def _race_with_result(db, *, title: str, horse: Horse, jockey: Jockey, place: int, seconds: float) -> Race:
    """Создать состязание с единственным участником и известным результатом."""
    hippodrome = db.scalars(select(Hippodrome)).first()
    race = crud.create_race(
        db,
        title=title,
        race_date=date(2026, 9, 9),
        race_time=time(11, 0),
        hippodrome_id=hippodrome.id,
        status="finished",
    )
    crud.add_participant(
        db, race, horse_id=horse.id, jockey_id=jockey.id, place=place, finish_time_seconds=seconds
    )
    return race


class TestJockeyHistory:
    """Функция 6 ТЗ."""

    def test_jockey_card_lists_races(self, admin) -> None:
        response = admin.get("/jockeys/1")
        assert response.status_code == 200
        assert "История участия в состязаниях" in response.text
        # Первый демо-жокей участвовал в «Кубке открытия сезона».
        assert "Кубок открытия сезона" in response.text

    def test_new_race_appears_in_jockey_history(self, admin, db) -> None:
        owner = crud.create_owner(db, name="Владелец истории жокея")
        horse = crud.create_horse(db, name="Лошадь истории жокея", sex="жеребец", age=5, owner_id=owner.id)
        jockey = crud.create_jockey(db, name="Жокей истории", address="", age=30, rating=50)

        _race_with_result(
            db,
            title="Уникальный заезд для жокея",
            horse=horse,
            jockey=jockey,
            place=1,
            seconds=95.25,
        )

        response = admin.get(f"/jockeys/{jockey.id}")
        assert response.status_code == 200
        assert "Уникальный заезд для жокея" in response.text
        assert "Лошадь истории жокея" in response.text
        assert "1:35,25" in response.text
        assert "1-е" in response.text

    def test_jockey_without_races(self, admin, db) -> None:
        jockey = crud.create_jockey(db, name="Жокей без заездов", address="", age=22, rating=10)
        response = admin.get(f"/jockeys/{jockey.id}")
        assert response.status_code == 200
        assert "не участвовал" in response.text

    def test_missing_jockey(self, admin) -> None:
        assert admin.get("/jockeys/999999").status_code == 404


class TestHorseHistory:
    """Функция 7 ТЗ."""

    def test_horse_card_lists_races(self, admin) -> None:
        response = admin.get("/horses/1")
        assert response.status_code == 200
        assert "История участия в состязаниях" in response.text
        assert "Кубок открытия сезона" in response.text

    def test_new_race_appears_in_horse_history(self, admin, db) -> None:
        owner = crud.create_owner(db, name="Владелец истории лошади")
        horse = crud.create_horse(db, name="Лошадь истории", sex="кобыла", age=4, owner_id=owner.id)
        jockey = crud.create_jockey(db, name="Жокей истории лошади", address="", age=28, rating=60)

        _race_with_result(
            db,
            title="Уникальный заезд для лошади",
            horse=horse,
            jockey=jockey,
            place=3,
            seconds=120.0,
        )

        response = admin.get(f"/horses/{horse.id}")
        assert "Уникальный заезд для лошади" in response.text
        assert "Жокей истории лошади" in response.text
        assert "3-е" in response.text

    def test_horse_without_races(self, admin, db) -> None:
        horse = crud.create_horse(db, name="Лошадь без заездов", sex="мерин", age=3, owner_id=None)
        response = admin.get(f"/horses/{horse.id}")
        assert response.status_code == 200
        assert "не участвовала" in response.text

    def test_owner_is_shown_on_horse_card(self, admin, db) -> None:
        owner = crud.create_owner(db, name="Владелец на карточке")
        horse = crud.create_horse(db, name="Лошадь на карточке", sex="жеребец", age=6, owner_id=owner.id)
        response = admin.get(f"/horses/{horse.id}")
        assert "Владелец на карточке" in response.text

    def test_missing_horse(self, admin) -> None:
        assert admin.get("/horses/999999").status_code == 404


class TestHistoryOrdering:
    def test_history_is_sorted_newest_first(self, admin, db) -> None:
        owner = Owner(name="Владелец сортировки")
        db.add(owner)
        db.flush()
        horse = Horse(name="Лошадь сортировки", sex="кобыла", age=5, owner_id=owner.id)
        jockey = Jockey(name="Жокей сортировки", address="", age=30, rating=40)
        db.add_all([horse, jockey])
        db.commit()

        hippodrome = db.scalars(select(Hippodrome)).first()
        for day, title in ((5, "Ранний заезд"), (25, "Поздний заезд")):
            race = crud.create_race(
                db,
                title=title,
                race_date=date(2026, 3, day),
                race_time=time(12, 0),
                hippodrome_id=hippodrome.id,
                status="finished",
            )
            crud.add_participant(db, race, horse_id=horse.id, jockey_id=jockey.id, place=1, finish_time_seconds=100.0)

        response = admin.get(f"/horses/{horse.id}")
        assert response.text.index("Поздний заезд") < response.text.index("Ранний заезд")
