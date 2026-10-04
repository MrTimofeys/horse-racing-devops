"""Модель данных АС «Скачки» (SQLAlchemy 2.0).

Состав сущностей определён ТЗ:

* лошади — кличка, пол, возраст, владелец;
* владельцы — имя, адрес, телефон;
* жокеи — имя, адрес, возраст, рейтинг;
* ипподромы — место проведения;
* состязания — дата, время, ипподром, название;
* участники заездов и результаты — лошадь, жокей, занятое место, показанное время.

Таблица ``race_results`` одновременно описывает и объявленный состав заезда
(``place`` и ``finish_time_seconds`` пусты), и его результат — после того как
место и время внесены.
"""

from __future__ import annotations

from datetime import date as DateType
from datetime import datetime, time as TimeType

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .utils import format_place, format_race_time

# --- Справочные значения -------------------------------------------------

HORSE_SEXES: tuple[str, ...] = ("кобыла", "жеребец", "мерин")

RACE_PLANNED = "planned"
RACE_FINISHED = "finished"
RACE_CANCELLED = "cancelled"
RACE_STATUSES: tuple[str, ...] = (RACE_PLANNED, RACE_FINISHED, RACE_CANCELLED)
RACE_STATUS_LABELS: dict[str, str] = {
    RACE_PLANNED: "Запланировано",
    RACE_FINISHED: "Завершено",
    RACE_CANCELLED: "Отменено",
}

ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"
ROLE_VIEWER = "viewer"
USER_ROLES: tuple[str, ...] = (ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER)
USER_ROLE_LABELS: dict[str, str] = {
    ROLE_ADMIN: "Администратор",
    ROLE_OPERATOR: "Оператор",
    ROLE_VIEWER: "Наблюдатель",
}


class User(Base):
    """Учётная запись пользователя системы (ТЗ: авторизация и разграничение прав)."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'operator', 'viewer')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(128), default="")
    role: Mapped[str] = mapped_column(String(16), default=ROLE_OPERATOR)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    # --- Удобные предикаты для шаблонов и зависимостей ---

    @property
    def role_label(self) -> str:
        return USER_ROLE_LABELS.get(self.role, self.role)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def can_edit(self) -> bool:
        """Оператор и администратор могут создавать и изменять записи."""
        return self.role in (ROLE_ADMIN, ROLE_OPERATOR)

    @property
    def display_name(self) -> str:
        return self.full_name or self.username

    def __repr__(self) -> str:  # pragma: no cover - отладочное представление
        return f"<User {self.username} ({self.role})>"


class UserSession(Base):
    """Сессия авторизации.

    Хранится в БД, а не в подписанной cookie: так администратор может
    принудительно завершить сессии пользователя, а сама сессия переживает
    перезапуск серверной части.
    """

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    client_ip: Mapped[str] = mapped_column(String(64), default="")
    # Однократное сообщение, которое показывается после redirect (flash).
    flash: Mapped[str] = mapped_column(Text, default="")

    user: Mapped[User] = relationship(back_populates="sessions")

    @property
    def is_expired(self) -> bool:
        return self.expires_at <= datetime.utcnow()


class Owner(Base):
    """Владелец лошади: имя, адрес, телефон."""

    __tablename__ = "owners"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    address: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    horses: Mapped[list["Horse"]] = relationship(back_populates="owner")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Owner {self.name}>"


class Horse(Base):
    """Лошадь: кличка, пол, возраст, владелец."""

    __tablename__ = "horses"
    __table_args__ = (
        CheckConstraint("age > 0 AND age < 40", name="ck_horses_age"),
        CheckConstraint(
            "sex IN ('кобыла', 'жеребец', 'мерин')", name="ck_horses_sex"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    sex: Mapped[str] = mapped_column(String(16), default="кобыла")
    age: Mapped[int] = mapped_column(Integer, default=1)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("owners.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    owner: Mapped[Owner | None] = relationship(back_populates="horses")
    results: Mapped[list["RaceResult"]] = relationship(
        back_populates="horse", cascade="all, delete-orphan"
    )

    @property
    def owner_name(self) -> str:
        return self.owner.name if self.owner else "не указан"

    @property
    def races(self) -> list["Race"]:
        """Состязания, в которых лошадь участвовала (функция 7 ТЗ)."""
        return [result.race for result in self.results if result.race is not None]

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Horse {self.name}>"


class Jockey(Base):
    """Жокей: имя, адрес, возраст, рейтинг."""

    __tablename__ = "jockeys"
    __table_args__ = (
        CheckConstraint("age >= 16 AND age < 100", name="ck_jockeys_age"),
        CheckConstraint("rating >= 0 AND rating <= 1000", name="ck_jockeys_rating"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    address: Mapped[str] = mapped_column(String(255), default="")
    age: Mapped[int] = mapped_column(Integer, default=18)
    rating: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    results: Mapped[list["RaceResult"]] = relationship(
        back_populates="jockey", cascade="all, delete-orphan"
    )

    @property
    def races(self) -> list["Race"]:
        """Состязания, в которых жокей участвовал (функция 6 ТЗ)."""
        return [result.race for result in self.results if result.race is not None]

    @property
    def wins(self) -> int:
        return sum(1 for result in self.results if result.place == 1)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Jockey {self.name}>"


class Hippodrome(Base):
    """Ипподром — место проведения состязаний."""

    __tablename__ = "hippodromes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    city: Mapped[str] = mapped_column(String(128), default="")
    address: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    races: Mapped[list["Race"]] = relationship(back_populates="hippodrome")

    @property
    def full_name(self) -> str:
        return f"{self.name}, {self.city}" if self.city else self.name

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Hippodrome {self.name}>"


class Race(Base):
    """Состязание: дата, время, ипподром, название."""

    __tablename__ = "races"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'finished', 'cancelled')", name="ck_races_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    race_date: Mapped[DateType] = mapped_column(Date, index=True)
    race_time: Mapped[TimeType] = mapped_column(Time)
    hippodrome_id: Mapped[int] = mapped_column(
        ForeignKey("hippodromes.id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(16), default=RACE_PLANNED)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    hippodrome: Mapped[Hippodrome] = relationship(back_populates="races")
    results: Mapped[list["RaceResult"]] = relationship(
        back_populates="race", cascade="all, delete-orphan"
    )

    @property
    def display_title(self) -> str:
        return self.title or f"Заезд №{self.id}"

    @property
    def status_label(self) -> str:
        return RACE_STATUS_LABELS.get(self.status, self.status)

    @property
    def participants(self) -> list["RaceResult"]:
        """Состав заезда: сначала занявшие места, затем остальные.

        Функция 1 ТЗ — «для каждого состязания показывать список участвующих
        жокеев и лошадей с указанием занятых ими мест и показанного времени».
        """
        return sorted(
            self.results,
            key=lambda r: (
                r.place is None,
                r.place if r.place is not None else 0,
                (r.horse.name if r.horse else "").lower(),
            ),
        )

    @property
    def finished_count(self) -> int:
        return sum(1 for result in self.results if result.place is not None)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Race {self.id} {self.race_date} {self.display_title}>"


class RaceResult(Base):
    """Участие лошади под управлением жокея в состязании и его результат.

    Пока ``place`` и ``finish_time_seconds`` пусты — это заявленный участник.
    После внесения значений запись становится результатом заезда.
    """

    __tablename__ = "race_results"
    __table_args__ = (
        # Одна лошадь и один жокей могут быть заявлены в заезде только один раз.
        UniqueConstraint("race_id", "horse_id", name="uq_results_race_horse"),
        UniqueConstraint("race_id", "jockey_id", name="uq_results_race_jockey"),
        # Занятое место в одном заезде не может повториться (NULL не считается).
        UniqueConstraint("race_id", "place", name="uq_results_race_place"),
        CheckConstraint("place IS NULL OR place > 0", name="ck_results_place_positive"),
        CheckConstraint(
            "finish_time_seconds IS NULL OR finish_time_seconds > 0",
            name="ck_results_time_positive",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    race_id: Mapped[int] = mapped_column(ForeignKey("races.id", ondelete="CASCADE"), index=True)
    horse_id: Mapped[int] = mapped_column(ForeignKey("horses.id", ondelete="CASCADE"))
    jockey_id: Mapped[int] = mapped_column(ForeignKey("jockeys.id", ondelete="CASCADE"))
    place: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finish_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    comment: Mapped[str] = mapped_column(String(255), default="")

    race: Mapped[Race] = relationship(back_populates="results")
    horse: Mapped[Horse] = relationship(back_populates="results")
    jockey: Mapped[Jockey] = relationship(back_populates="results")

    @property
    def place_label(self) -> str:
        return format_place(self.place)

    @property
    def time_label(self) -> str:
        return format_race_time(self.finish_time_seconds)

    @property
    def has_result(self) -> bool:
        return self.place is not None or self.finish_time_seconds is not None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RaceResult race={self.race_id} horse={self.horse_id} place={self.place}>"
