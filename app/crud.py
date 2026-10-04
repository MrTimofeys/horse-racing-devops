"""Слой доступа к данным и бизнес-правила АС «Скачки».

Правила предметной области, которые проверяются здесь:

* владельца нельзя удалить, пока за ним закреплены лошади;
* ипподром нельзя удалить, пока к нему привязаны состязания;
* лошадь или жокей с историей участия в состязаниях не удаляются — иначе
  пропала бы история заездов;
* в одном заезде лошадь и жокей заявляются по одному разу, а занятые места
  не повторяются.
"""

from __future__ import annotations

from datetime import date
from datetime import date as DateType
from datetime import time as TimeType

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from .models import (
    RACE_CANCELLED,
    RACE_FINISHED,
    ROLE_ADMIN,
    Horse,
    Hippodrome,
    Jockey,
    Owner,
    Race,
    RaceResult,
    User,
)
from .pagination import Page, paginate
from .utils import ValidationError

# ---------------------------------------------------------------------------
# Владельцы
# ---------------------------------------------------------------------------


def get_owner(db: Session, owner_id: int) -> Owner | None:
    return db.get(Owner, owner_id)


def list_owners(db: Session, *, search: str | None = None, page: int = 1, per_page: int = 20) -> Page[Owner]:
    stmt = select(Owner).options(selectinload(Owner.horses)).order_by(Owner.name)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(Owner.name.ilike(pattern), Owner.address.ilike(pattern), Owner.phone.ilike(pattern))
        )
    return paginate(db, stmt, page=page, per_page=per_page)


def create_owner(db: Session, *, name: str, address: str = "", phone: str = "") -> Owner:
    owner = Owner(name=name, address=address, phone=phone)
    db.add(owner)
    db.commit()
    return owner


def update_owner(db: Session, owner: Owner, *, name: str, address: str, phone: str) -> Owner:
    owner.name, owner.address, owner.phone = name, address, phone
    db.commit()
    return owner


def delete_owner(db: Session, owner: Owner) -> None:
    horses_count = db.scalar(
        select(func.count()).select_from(Horse).where(Horse.owner_id == owner.id)
    )
    if horses_count:
        raise ValidationError(
            f"Нельзя удалить владельца: за ним закреплено лошадей — {horses_count}. "
            "Сначала смените владельца у этих лошадей."
        )
    db.delete(owner)
    db.commit()


# ---------------------------------------------------------------------------
# Лошади
# ---------------------------------------------------------------------------


def get_horse(db: Session, horse_id: int) -> Horse | None:
    return db.get(Horse, horse_id)


def list_horses(
    db: Session,
    *,
    search: str | None = None,
    owner_id: int | None = None,
    page: int = 1,
    per_page: int = 20,
) -> Page[Horse]:
    stmt = (
        select(Horse)
        .options(selectinload(Horse.owner))
        .order_by(Horse.name)
    )
    if search:
        stmt = stmt.where(Horse.name.ilike(f"%{search.strip()}%"))
    if owner_id:
        stmt = stmt.where(Horse.owner_id == owner_id)
    return paginate(db, stmt, page=page, per_page=per_page)


def create_horse(db: Session, *, name: str, sex: str, age: int, owner_id: int | None) -> Horse:
    horse = Horse(name=name, sex=sex, age=age, owner_id=owner_id)
    db.add(horse)
    db.commit()
    return horse


def update_horse(
    db: Session, horse: Horse, *, name: str, sex: str, age: int, owner_id: int | None
) -> Horse:
    horse.name, horse.sex, horse.age, horse.owner_id = name, sex, age, owner_id
    db.commit()
    return horse


def delete_horse(db: Session, horse: Horse) -> None:
    results_count = db.scalar(
        select(func.count()).select_from(RaceResult).where(RaceResult.horse_id == horse.id)
    )
    if results_count:
        raise ValidationError(
            f"Нельзя удалить лошадь: она участвует в заездах — {results_count}. "
            "Сначала удалите записи об участии."
        )
    db.delete(horse)
    db.commit()


def horse_history(db: Session, horse: Horse) -> list[RaceResult]:
    """Функция 7 ТЗ: список состязаний каждой лошади."""
    stmt = (
        select(RaceResult)
        .options(
            selectinload(RaceResult.race).selectinload(Race.hippodrome),
            selectinload(RaceResult.jockey),
            selectinload(RaceResult.horse),
        )
        .where(RaceResult.horse_id == horse.id)
    )
    rows = list(db.scalars(stmt).all())
    return sorted(rows, key=lambda r: (r.race.race_date, r.race.race_time), reverse=True)


# ---------------------------------------------------------------------------
# Жокеи
# ---------------------------------------------------------------------------


def get_jockey(db: Session, jockey_id: int) -> Jockey | None:
    return db.get(Jockey, jockey_id)


def list_jockeys(
    db: Session, *, search: str | None = None, page: int = 1, per_page: int = 20
) -> Page[Jockey]:
    stmt = select(Jockey).order_by(Jockey.rating.desc(), Jockey.name)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(or_(Jockey.name.ilike(pattern), Jockey.address.ilike(pattern)))
    return paginate(db, stmt, page=page, per_page=per_page)


def create_jockey(db: Session, *, name: str, address: str, age: int, rating: int) -> Jockey:
    jockey = Jockey(name=name, address=address, age=age, rating=rating)
    db.add(jockey)
    db.commit()
    return jockey


def update_jockey(
    db: Session, jockey: Jockey, *, name: str, address: str, age: int, rating: int
) -> Jockey:
    jockey.name, jockey.address, jockey.age, jockey.rating = name, address, age, rating
    db.commit()
    return jockey


def delete_jockey(db: Session, jockey: Jockey) -> None:
    results_count = db.scalar(
        select(func.count()).select_from(RaceResult).where(RaceResult.jockey_id == jockey.id)
    )
    if results_count:
        raise ValidationError(
            f"Нельзя удалить жокея: он участвует в заездах — {results_count}. "
            "Сначала удалите записи об участии."
        )
    db.delete(jockey)
    db.commit()


def jockey_history(db: Session, jockey: Jockey) -> list[RaceResult]:
    """Функция 6 ТЗ: список состязаний каждого жокея."""
    stmt = (
        select(RaceResult)
        .options(
            selectinload(RaceResult.race).selectinload(Race.hippodrome),
            selectinload(RaceResult.horse),
            selectinload(RaceResult.jockey),
        )
        .where(RaceResult.jockey_id == jockey.id)
    )
    rows = list(db.scalars(stmt).all())
    return sorted(rows, key=lambda r: (r.race.race_date, r.race.race_time), reverse=True)


# ---------------------------------------------------------------------------
# Ипподромы
# ---------------------------------------------------------------------------


def get_hippodrome(db: Session, hippodrome_id: int) -> Hippodrome | None:
    return db.get(Hippodrome, hippodrome_id)


def list_hippodromes(
    db: Session, *, search: str | None = None, page: int = 1, per_page: int = 20
) -> Page[Hippodrome]:
    stmt = select(Hippodrome).order_by(Hippodrome.name)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(or_(Hippodrome.name.ilike(pattern), Hippodrome.city.ilike(pattern)))
    return paginate(db, stmt, page=page, per_page=per_page)


def create_hippodrome(db: Session, *, name: str, city: str, address: str) -> Hippodrome:
    hippodrome = Hippodrome(name=name, city=city, address=address)
    db.add(hippodrome)
    db.commit()
    return hippodrome


def update_hippodrome(
    db: Session, hippodrome: Hippodrome, *, name: str, city: str, address: str
) -> Hippodrome:
    hippodrome.name, hippodrome.city, hippodrome.address = name, city, address
    db.commit()
    return hippodrome


def delete_hippodrome(db: Session, hippodrome: Hippodrome) -> None:
    races_count = db.scalar(
        select(func.count()).select_from(Race).where(Race.hippodrome_id == hippodrome.id)
    )
    if races_count:
        raise ValidationError(
            f"Нельзя удалить ипподром: к нему привязано состязаний — {races_count}."
        )
    db.delete(hippodrome)
    db.commit()


# ---------------------------------------------------------------------------
# Состязания
# ---------------------------------------------------------------------------


def get_race(db: Session, race_id: int) -> Race | None:
    return db.get(Race, race_id)


def load_race(db: Session, race_id: int) -> Race | None:
    """Загрузить состязание вместе с составом заезда (для страницы состязания)."""
    stmt = (
        select(Race)
        .options(
            selectinload(Race.hippodrome),
            selectinload(Race.results).selectinload(RaceResult.horse),
            selectinload(Race.results).selectinload(RaceResult.jockey),
        )
        .where(Race.id == race_id)
    )
    return db.scalars(stmt).first()


def list_races(
    db: Session,
    *,
    search: str | None = None,
    status: str | None = None,
    hippodrome_id: int | None = None,
    date_from: DateType | None = None,
    date_to: DateType | None = None,
    page: int = 1,
    per_page: int = 20,
) -> Page[Race]:
    stmt = (
        select(Race)
        .options(
            selectinload(Race.hippodrome),
            selectinload(Race.results).selectinload(RaceResult.horse),
        )
        .order_by(Race.race_date.desc(), Race.race_time.desc())
    )
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.join(Hippodrome, Race.hippodrome_id == Hippodrome.id).where(
            or_(Race.title.ilike(pattern), Hippodrome.name.ilike(pattern), Hippodrome.city.ilike(pattern))
        )
    if status:
        stmt = stmt.where(Race.status == status)
    if hippodrome_id:
        stmt = stmt.where(Race.hippodrome_id == hippodrome_id)
    if date_from:
        stmt = stmt.where(Race.race_date >= date_from)
    if date_to:
        stmt = stmt.where(Race.race_date <= date_to)
    return paginate(db, stmt, page=page, per_page=per_page)


def create_race(
    db: Session,
    *,
    title: str,
    race_date: DateType,
    race_time: TimeType,
    hippodrome_id: int,
    status: str,
    notes: str = "",
) -> Race:
    """Функция 2 ТЗ: добавление нового состязания."""
    if get_hippodrome(db, hippodrome_id) is None:
        raise ValidationError("Выбранный ипподром не найден")
    race = Race(
        title=title,
        race_date=race_date,
        race_time=race_time,
        hippodrome_id=hippodrome_id,
        status=status,
        notes=notes,
    )
    db.add(race)
    db.commit()
    return race


def update_race(
    db: Session,
    race: Race,
    *,
    title: str,
    race_date: DateType,
    race_time: TimeType,
    hippodrome_id: int,
    status: str,
    notes: str,
) -> Race:
    if get_hippodrome(db, hippodrome_id) is None:
        raise ValidationError("Выбранный ипподром не найден")
    race.title = title
    race.race_date = race_date
    race.race_time = race_time
    race.hippodrome_id = hippodrome_id
    race.status = status
    race.notes = notes
    db.commit()
    return race


def delete_race(db: Session, race: Race) -> None:
    """Удалить состязание вместе с составом заезда (каскад на уровне СУБД)."""
    db.delete(race)
    db.commit()


def finish_race(db: Session, race: Race) -> Race:
    race.status = RACE_FINISHED
    db.commit()
    return race


def cancel_race(db: Session, race: Race) -> Race:
    race.status = RACE_CANCELLED
    db.commit()
    return race


# ---------------------------------------------------------------------------
# Участники заездов и результаты
# ---------------------------------------------------------------------------


def get_result(db: Session, result_id: int) -> RaceResult | None:
    return db.get(RaceResult, result_id)


def get_horse_options(db: Session) -> list[Horse]:
    return list(db.scalars(select(Horse).order_by(Horse.name)).all())


def get_jockey_options(db: Session) -> list[Jockey]:
    return list(db.scalars(select(Jockey).order_by(Jockey.name)).all())


def _assert_place_is_free(db: Session, race_id: int, place: int | None, *, exclude_id: int | None = None) -> None:
    if place is None:
        return
    stmt = select(RaceResult).where(RaceResult.race_id == race_id, RaceResult.place == place)
    if exclude_id is not None:
        stmt = stmt.where(RaceResult.id != exclude_id)
    if db.scalars(stmt).first() is not None:
        raise ValidationError(f"В этом заезде {place}-е место уже занято другим участником")


def add_participant(
    db: Session,
    race: Race,
    *,
    horse_id: int,
    jockey_id: int,
    place: int | None = None,
    finish_time_seconds: float | None = None,
    comment: str = "",
) -> RaceResult:
    """Заявить участника заезда; при желании сразу с результатом.

    Покрывает функции 5 ТЗ (добавление результата прошедшего состязания)
    и заявление состава участников предстоящего заезда.
    """
    if db.get(Horse, horse_id) is None:
        raise ValidationError("Выбранная лошадь не найдена")
    if db.get(Jockey, jockey_id) is None:
        raise ValidationError("Выбранный жокей не найден")

    if db.scalars(
        select(RaceResult).where(RaceResult.race_id == race.id, RaceResult.horse_id == horse_id)
    ).first():
        raise ValidationError("Эта лошадь уже заявлена в данном заезде")

    if db.scalars(
        select(RaceResult).where(RaceResult.race_id == race.id, RaceResult.jockey_id == jockey_id)
    ).first():
        raise ValidationError("Этот жокей уже заявлен в данном заезде")

    _assert_place_is_free(db, race.id, place)

    result = RaceResult(
        race_id=race.id,
        horse_id=horse_id,
        jockey_id=jockey_id,
        place=place,
        finish_time_seconds=finish_time_seconds,
        comment=comment,
    )
    db.add(result)
    db.commit()
    return result


def update_result(
    db: Session,
    result: RaceResult,
    *,
    place: int | None,
    finish_time_seconds: float | None,
    comment: str = "",
) -> RaceResult:
    """Внести или поправить результат конкретного участника заезда."""
    _assert_place_is_free(db, result.race_id, place, exclude_id=result.id)
    result.place = place
    result.finish_time_seconds = finish_time_seconds
    result.comment = comment
    db.commit()
    return result


def remove_participant(db: Session, result: RaceResult) -> None:
    db.delete(result)
    db.commit()


def list_results(
    db: Session,
    *,
    search: str | None = None,
    race_id: int | None = None,
    hippodrome_id: int | None = None,
    jockey_id: int | None = None,
    horse_id: int | None = None,
    only_finished: bool = True,
    page: int = 1,
    per_page: int = 20,
) -> Page[RaceResult]:
    """Сводный список результатов заездов.

    ТЗ (п. «Базовая подсистема») требует навигации между разделами
    «Состязания», «Жокеи», «Лошади», «Владельцы» и «Результаты». Здесь
    собираются итоги заездов: занятые места и показанное время.

    При ``only_finished`` в список попадают только участники с внесённым
    результатом — заявленные, но не финишировавшие лошади не показываются.
    """
    stmt = (
        select(RaceResult)
        .join(RaceResult.race)
        .options(
            selectinload(RaceResult.race).selectinload(Race.hippodrome),
            selectinload(RaceResult.horse),
            selectinload(RaceResult.jockey),
        )
        # Сначала свежие состязания, внутри заезда — по занятым местам.
        .order_by(Race.race_date.desc(), Race.race_time.desc(), RaceResult.place.is_(None), RaceResult.place)
    )

    if only_finished:
        stmt = stmt.where(RaceResult.place.isnot(None))
    if race_id:
        stmt = stmt.where(RaceResult.race_id == race_id)
    if hippodrome_id:
        stmt = stmt.where(Race.hippodrome_id == hippodrome_id)
    if jockey_id:
        stmt = stmt.where(RaceResult.jockey_id == jockey_id)
    if horse_id:
        stmt = stmt.where(RaceResult.horse_id == horse_id)
    if search:
        # Поиск идёт по связанным таблицам, поэтому сначала соединения,
        # и только потом условие с обращением к их столбцам.
        needle = f"%{search.strip()}%"
        stmt = (
            stmt.join(RaceResult.horse)
            .join(RaceResult.jockey)
            .join(Race.hippodrome)
            .where(
                or_(
                    Race.title.ilike(needle),
                    Horse.name.ilike(needle),
                    Jockey.name.ilike(needle),
                    Hippodrome.name.ilike(needle),
                )
            )
        )

    return paginate(db, stmt, page=page, per_page=per_page)


# ---------------------------------------------------------------------------
# Сводка для главной страницы
# ---------------------------------------------------------------------------


def dashboard_stats(db: Session) -> dict[str, int]:
    today = date.today()
    return {
        "horses": db.scalar(select(func.count()).select_from(Horse)) or 0,
        "owners": db.scalar(select(func.count()).select_from(Owner)) or 0,
        "jockeys": db.scalar(select(func.count()).select_from(Jockey)) or 0,
        "hippodromes": db.scalar(select(func.count()).select_from(Hippodrome)) or 0,
        "races": db.scalar(select(func.count()).select_from(Race)) or 0,
        "races_planned": db.scalar(
            select(func.count()).select_from(Race).where(Race.status == "planned", Race.race_date >= today)
        )
        or 0,
        "results": db.scalar(
            select(func.count()).select_from(RaceResult).where(RaceResult.place.is_not(None))
        )
        or 0,
        "users": db.scalar(select(func.count()).select_from(User)) or 0,
    }


def upcoming_races(db: Session, *, limit: int = 5) -> list[Race]:
    today = date.today()
    stmt = (
        select(Race)
        .options(selectinload(Race.hippodrome), selectinload(Race.results))
        .where(Race.status == "planned", Race.race_date >= today)
        .order_by(Race.race_date, Race.race_time)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def recent_races(db: Session, *, limit: int = 5) -> list[Race]:
    stmt = (
        select(Race)
        .options(selectinload(Race.hippodrome), selectinload(Race.results))
        .where(Race.status == RACE_FINISHED)
        .order_by(Race.race_date.desc(), Race.race_time.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def top_jockeys(db: Session, *, limit: int = 5) -> list[Jockey]:
    stmt = (
        select(Jockey)
        .options(selectinload(Jockey.results))
        .order_by(Jockey.rating.desc(), Jockey.name)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Пользователи (управление доступом — только администратор)
# ---------------------------------------------------------------------------


def get_user(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.scalars(select(User).where(User.username == username)).first()


def list_users(
    db: Session, *, search: str | None = None, page: int = 1, per_page: int = 20
) -> Page[User]:
    stmt = select(User).order_by(User.username)
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(or_(User.username.ilike(pattern), User.full_name.ilike(pattern)))
    return paginate(db, stmt, page=page, per_page=per_page)


def create_user(
    db: Session, *, username: str, password: str, full_name: str, role: str
) -> User:
    from .security import hash_password

    if get_user_by_username(db, username) is not None:
        raise ValidationError(f"Пользователь с логином «{username}» уже существует")

    user = User(
        username=username,
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def update_user(
    db: Session, user: User, *, full_name: str, role: str, is_active: bool
) -> User:
    if not is_active and user.role == ROLE_ADMIN and _count_active_admins(db, exclude_id=user.id) == 0:
        raise ValidationError("Нельзя отключить последнего активного администратора")
    if user.role == ROLE_ADMIN and role != ROLE_ADMIN and _count_active_admins(db, exclude_id=user.id) == 0:
        raise ValidationError("Нельзя снять права у последнего активного администратора")

    user.full_name = full_name
    user.role = role
    user.is_active = is_active
    db.commit()
    return user


def set_user_password(db: Session, user: User, password: str) -> User:
    from .security import hash_password

    user.password_hash = hash_password(password)
    db.commit()
    return user


def delete_user(db: Session, user: User, *, acting_user: User) -> None:
    if user.id == acting_user.id:
        raise ValidationError("Нельзя удалить собственную учётную запись")
    if user.role == ROLE_ADMIN and _count_active_admins(db, exclude_id=user.id) == 0:
        raise ValidationError("Нельзя удалить последнего активного администратора")
    db.delete(user)
    db.commit()


def _count_active_admins(db: Session, *, exclude_id: int | None = None) -> int:
    stmt = select(func.count()).select_from(User).where(
        User.role == ROLE_ADMIN, User.is_active.is_(True)
    )
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return db.scalar(stmt) or 0
