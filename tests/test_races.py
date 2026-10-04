"""Состязания, состав заездов и результаты — функции 1, 2 и 5 ТЗ."""

from __future__ import annotations

from datetime import date, time

from sqlalchemy import select

from app import crud
from app.models import Horse, Jockey, Race, RaceResult


def _hippodrome_id(db) -> int:
    return crud.list_hippodromes(db, per_page=1).items[0].id


def _make_race(db, **overrides) -> Race:
    params = {
        "title": "Тестовый заезд",
        "race_date": date(2026, 6, 1),
        "race_time": time(12, 0),
        "hippodrome_id": _hippodrome_id(db),
        "status": "planned",
        "notes": "",
    }
    params.update(overrides)
    return crud.create_race(db, **params)


class TestRaceCreation:
    """Функция 2 ТЗ: добавление нового состязания с датой, временем, ипподромом и названием."""

    def test_create_race(self, admin, db) -> None:
        hippodrome_id = _hippodrome_id(db)
        response = admin.post(
            "/races/new",
            data={
                "title": "Кубок тестировщика",
                "race_date": "2026-07-15",
                "race_time": "18:30",
                "hippodrome_id": str(hippodrome_id),
                "status": "planned",
                "notes": "Дистанция 1800 м",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"].startswith("/races/")

        db.expire_all()
        race = db.scalars(select(Race).where(Race.title == "Кубок тестировщика")).one()
        assert race.race_date.isoformat() == "2026-07-15"
        assert race.race_time.strftime("%H:%M") == "18:30"
        assert race.hippodrome_id == hippodrome_id
        assert race.notes == "Дистанция 1800 м"

    def test_title_is_optional(self, admin, db) -> None:
        response = admin.post(
            "/races/new",
            data={
                "title": "",
                "race_date": "2026-08-01",
                "race_time": "10:00",
                "hippodrome_id": str(_hippodrome_id(db)),
                "status": "planned",
                "notes": "",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        db.expire_all()
        race = db.scalars(select(Race).where(Race.race_date == date(2026, 8, 1))).one()
        assert race.display_title == f"Заезд №{race.id}"

    def test_date_is_required(self, admin, db) -> None:
        response = admin.post(
            "/races/new",
            data={
                "title": "Без даты",
                "race_date": "",
                "race_time": "10:00",
                "hippodrome_id": str(_hippodrome_id(db)),
                "status": "planned",
            },
        )
        assert response.status_code == 400
        assert "Дата" in response.text

    def test_time_is_required(self, admin, db) -> None:
        response = admin.post(
            "/races/new",
            data={
                "title": "Без времени",
                "race_date": "2026-08-02",
                "race_time": "",
                "hippodrome_id": str(_hippodrome_id(db)),
                "status": "planned",
            },
        )
        assert response.status_code == 400
        assert "Время" in response.text

    def test_hippodrome_is_required(self, admin) -> None:
        response = admin.post(
            "/races/new",
            data={
                "title": "Без ипподрома",
                "race_date": "2026-08-03",
                "race_time": "10:00",
                "hippodrome_id": "",
                "status": "planned",
            },
        )
        assert response.status_code == 400
        assert "ипподром" in response.text.lower()

    def test_unknown_hippodrome_rejected(self, admin) -> None:
        response = admin.post(
            "/races/new",
            data={
                "title": "Чужой ипподром",
                "race_date": "2026-08-04",
                "race_time": "10:00",
                "hippodrome_id": "999999",
                "status": "planned",
            },
        )
        assert response.status_code == 400
        assert "не найден" in response.text

    def test_invalid_status_rejected(self, admin, db) -> None:
        response = admin.post(
            "/races/new",
            data={
                "title": "Плохой статус",
                "race_date": "2026-08-05",
                "race_time": "10:00",
                "hippodrome_id": str(_hippodrome_id(db)),
                "status": "какой-то",
            },
        )
        assert response.status_code == 400


class TestParticipantsAndResults:
    """Функция 5 ТЗ: результаты состязания — лошадь, жокей, место, показанное время."""

    def test_add_participant_without_result(self, admin, db) -> None:
        race = _make_race(db, title="Заезд без результатов")
        horse = db.scalars(select(Horse)).first()
        jockey = db.scalars(select(Jockey)).first()

        response = admin.post(
            f"/races/{race.id}/participants",
            data={"horse_id": str(horse.id), "jockey_id": str(jockey.id), "place": "", "finish_time": ""},
            follow_redirects=False,
        )
        assert response.status_code == 303
        db.expire_all()
        results = db.scalars(select(RaceResult).where(RaceResult.race_id == race.id)).all()
        assert len(results) == 1
        assert results[0].place is None
        assert results[0].finish_time_seconds is None
        assert results[0].has_result is False

    def test_add_participant_with_result(self, admin, db) -> None:
        race = _make_race(db, title="Заезд с результатом")
        horse = db.scalars(select(Horse)).first()
        jockey = db.scalars(select(Jockey)).first()

        response = admin.post(
            f"/races/{race.id}/participants",
            data={
                "horse_id": str(horse.id),
                "jockey_id": str(jockey.id),
                "place": "1",
                "finish_time": "2:05,30",
                "comment": "рекорд дорожки",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303

        db.expire_all()
        result = db.scalars(select(RaceResult).where(RaceResult.race_id == race.id)).one()
        assert result.place == 1
        assert result.finish_time_seconds == 2 * 60 + 5.30
        assert result.place_label == "1-е место"
        assert result.time_label == "2:05,30"
        assert result.comment == "рекорд дорожки"

    def test_duplicate_horse_rejected(self, admin, db) -> None:
        race = _make_race(db, title="Дубль лошади")
        horse = db.scalars(select(Horse)).first()
        jockeys = db.scalars(select(Jockey)).all()
        admin.post(
            f"/races/{race.id}/participants",
            data={"horse_id": str(horse.id), "jockey_id": str(jockeys[0].id), "place": "", "finish_time": ""},
        )
        response = admin.post(
            f"/races/{race.id}/participants",
            data={"horse_id": str(horse.id), "jockey_id": str(jockeys[1].id), "place": "", "finish_time": ""},
            follow_redirects=True,
        )
        assert "уже заявлена" in response.text

    def test_duplicate_jockey_rejected(self, admin, db) -> None:
        race = _make_race(db, title="Дубль жокея")
        horses = db.scalars(select(Horse)).all()
        jockey = db.scalars(select(Jockey)).first()
        admin.post(
            f"/races/{race.id}/participants",
            data={"horse_id": str(horses[0].id), "jockey_id": str(jockey.id), "place": "", "finish_time": ""},
        )
        response = admin.post(
            f"/races/{race.id}/participants",
            data={"horse_id": str(horses[1].id), "jockey_id": str(jockey.id), "place": "", "finish_time": ""},
            follow_redirects=True,
        )
        assert "уже заявлен" in response.text

    def test_duplicate_place_rejected(self, admin, db) -> None:
        race = _make_race(db, title="Дубль места")
        horses = db.scalars(select(Horse)).all()
        jockeys = db.scalars(select(Jockey)).all()
        admin.post(
            f"/races/{race.id}/participants",
            data={"horse_id": str(horses[0].id), "jockey_id": str(jockeys[0].id), "place": "1", "finish_time": "2:00,00"},
        )
        response = admin.post(
            f"/races/{race.id}/participants",
            data={"horse_id": str(horses[1].id), "jockey_id": str(jockeys[1].id), "place": "1", "finish_time": "2:01,00"},
            follow_redirects=True,
        )
        assert "место уже занято" in response.text

    def test_invalid_time_format_rejected(self, admin, db) -> None:
        race = _make_race(db, title="Плохое время")
        horse = db.scalars(select(Horse)).first()
        jockey = db.scalars(select(Jockey)).first()
        response = admin.post(
            f"/races/{race.id}/participants",
            data={"horse_id": str(horse.id), "jockey_id": str(jockey.id), "place": "1", "finish_time": "очень быстро"},
            follow_redirects=True,
        )
        assert "формате" in response.text

    def test_update_result(self, admin, db) -> None:
        race = _make_race(db, title="Правка результата")
        horse = db.scalars(select(Horse)).first()
        jockey = db.scalars(select(Jockey)).first()
        result = crud.add_participant(db, race, horse_id=horse.id, jockey_id=jockey.id)

        assert result.place is None
        response = admin.post(
            f"/races/{race.id}/results/{result.id}",
            data={"place": "2", "finish_time": "1:40,50", "comment": "фото-финиш"},
            follow_redirects=False,
        )
        assert response.status_code == 303

        db.expire_all()
        updated = db.get(RaceResult, result.id)
        assert updated.place == 2
        assert updated.time_label == "1:40,50"
        assert updated.comment == "фото-финиш"

    def test_remove_participant(self, admin, db) -> None:
        race = _make_race(db, title="Удаление участника")
        horse = db.scalars(select(Horse)).first()
        jockey = db.scalars(select(Jockey)).first()
        result = crud.add_participant(db, race, horse_id=horse.id, jockey_id=jockey.id)

        result_id = result.id
        response = admin.post(f"/races/{race.id}/results/{result_id}/delete", follow_redirects=False)
        assert response.status_code == 303
        db.expunge_all()
        assert db.get(RaceResult, result_id) is None


class TestRaceDetail:
    """Функция 1 ТЗ: список участвующих жокеев и лошадей с местами и временем."""

    def test_race_card_shows_participants_with_places_and_times(self, admin) -> None:
        response = admin.get("/races/1")
        assert response.status_code == 200
        assert "Кубок открытия сезона" in response.text
        assert "Ветер Перемен" in response.text
        assert "1-е" in response.text
        assert "2:05,30" in response.text
        assert "Состав заезда и результаты" in response.text

    def test_race_card_of_missing_race(self, admin) -> None:
        assert admin.get("/races/999999").status_code == 404


class TestRaceStatuses:
    def test_finish_race(self, admin, db) -> None:
        race = _make_race(db, title="Завершаемый заезд")
        response = admin.post(f"/races/{race.id}/finish", follow_redirects=False)
        assert response.status_code == 303
        db.expire_all()
        assert db.get(Race, race.id).status == "finished"
        assert db.get(Race, race.id).status_label == "Завершено"

    def test_cancel_race(self, admin, db) -> None:
        race = _make_race(db, title="Отменяемый заезд")
        admin.post(f"/races/{race.id}/cancel", follow_redirects=False)
        db.expire_all()
        assert db.get(Race, race.id).status == "cancelled"

    def test_delete_race_removes_participants(self, admin, db) -> None:
        race = _make_race(db, title="Удаляемый заезд")
        horse = db.scalars(select(Horse)).first()
        jockey = db.scalars(select(Jockey)).first()
        result = crud.add_participant(db, race, horse_id=horse.id, jockey_id=jockey.id)
        result_id = result.id

        race_id = race.id
        response = admin.post(f"/races/{race_id}/delete", follow_redirects=False)
        assert response.status_code == 303
        db.expunge_all()
        assert db.get(Race, race_id) is None
        # Состав заезда удалён каскадом (ON DELETE CASCADE).
        assert db.get(RaceResult, result_id) is None


class TestRaceFilters:
    def test_filter_by_status(self, admin) -> None:
        response = admin.get("/races?status=finished")
        assert response.status_code == 200
        assert "Кубок открытия сезона" in response.text
        assert "Летнее дерби" not in response.text

    def test_search_by_title(self, admin) -> None:
        response = admin.get("/races?search=Большой всероссийский")
        assert "Приз «Большой всероссийский»" in response.text
        assert "Летнее дерби" not in response.text

    def test_filter_by_hippodrome(self, admin, db) -> None:
        hippodrome = crud.list_hippodromes(db, search="Казанский", per_page=1).items[0]
        response = admin.get(f"/races?hippodrome_id={hippodrome.id}")
        assert "Приз «Большой всероссийский»" in response.text
        assert "Кубок открытия сезона" not in response.text
