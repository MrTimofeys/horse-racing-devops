#!/usr/bin/env bash
#
# Подсистема резервного копирования и восстановления АС «Скачки».
#
# ТЗ (п. «Требования по сохранности информации при авариях») требует
# «возможности организации автоматического и ручного резервного копирования
# данных системы средствами системного и базового программного обеспечения
# (ОС, СУБД)» и наличия «специализированной подсистемы резервного копирования
# и восстановления данных» (п. «Требования к информационному обеспечению»).
#
# Копирование и восстановление выполняются вручную — этим скриптом.
# Копии можно создавать по расписанию средствами ОС (cron, systemd-таймер),
# вызывая скрипт без параметров.
#
# Поддерживаются SQLite и PostgreSQL — СУБД определяется по DATABASE_URL.
#
# Использование:
#   bash scripts/backup.sh                          # создать копию (ручной режим)
#   bash scripts/backup.sh --list                   # показать имеющиеся копии
#   bash scripts/backup.sh --restore <файл>         # восстановить из копии
#   BACKUP_DIR=/srv/backups bash scripts/backup.sh  # другой каталог копий
#
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-${APP_DIR}/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"

# Читаем параметры стенда из .env, если он есть.
if [[ -f "${APP_DIR}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    . "${APP_DIR}/.env"
    set +a
fi

DATABASE_URL="${DATABASE_URL:-sqlite:///instance/skachki.db}"
STAMP="$(date +%Y%m%d-%H%M%S)"
STAND="${STAND_NAME:-local}"
SERVICE_NAME="${SERVICE_NAME:-skachki}"

# При автоматическом копировании по таймеру перезапуск службы не нужен,
# а при восстановлении — нужен, чтобы приложение отпустило файл базы.
RESTART_SERVICE="${RESTART_SERVICE:-auto}"

MODE="backup"
RESTORE_FILE=""

usage() {
    cat <<'USAGE'
Использование:
  bash scripts/backup.sh                          # создать копию (ручной режим)
  bash scripts/backup.sh --list                   # показать имеющиеся копии
  bash scripts/backup.sh --restore <файл>         # восстановить из копии
  BACKUP_DIR=/srv/backups bash scripts/backup.sh  # другой каталог копий

Переменные окружения:
  BACKUP_DIR    каталог для копий (по умолчанию <корень проекта>/backups)
  KEEP_DAYS     сколько дней хранить копии (по умолчанию 14)
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --restore)
            MODE="restore"
            RESTORE_FILE="${2:-}"
            [[ -z "${RESTORE_FILE}" ]] && { echo "Не указан файл копии." >&2; exit 2; }
            shift 2
            ;;
        --list)
            MODE="list"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Неизвестный параметр: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

mkdir -p "${BACKUP_DIR}"

case "${DATABASE_URL}" in
    sqlite*) DB_LABEL="SQLite" ;;
    postgresql*|postgres*) DB_LABEL="PostgreSQL" ;;
    *) DB_LABEL="${DATABASE_URL%%:*}" ;;
esac

# --- Вспомогательные функции ----------------------------------------------

# libpq не понимает префикс драйвера SQLAlchemy.
libpq_url() {
    printf '%s' "${DATABASE_URL}" | sed -e 's|^postgresql+psycopg://|postgresql://|'
}

sqlite_file() {
    local file="${DATABASE_URL#sqlite:///}"
    [[ "${file}" != /* ]] && file="${APP_DIR}/${file}"
    printf '%s' "${file}"
}

# Перезапустить службу приложения, чтобы она отпустила файл базы.
restart_app_if_needed() {
    [[ "${RESTART_SERVICE}" == "0" ]] && return 0
    [[ "${RESTART_SERVICE}" == "auto" && "${MODE}" != "restore" ]] && return 0
    if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
        echo "==> Перезапуск службы ${SERVICE_NAME}"
        systemctl restart "${SERVICE_NAME}" || true
    fi
}

# --- Режим: показать копии -------------------------------------------------

if [[ "${MODE}" == "list" ]]; then
    echo "Каталог резервных копий: ${BACKUP_DIR}"
    if ! ls -1 "${BACKUP_DIR}"/*.gz >/dev/null 2>&1; then
        echo "  Копий нет."
        exit 0
    fi
    # Печатаем только имя файла: путь может содержать пробелы, из-за которых
    # разбор вывода по столбцам сбивается.
    while IFS= read -r file; do
        printf '  %-8s %s  %s\n' \
            "$(du -h "${file}" | cut -f1)" \
            "$(date -r "${file}" '+%d.%m.%Y %H:%M' 2>/dev/null || stat -c '%y' "${file}" | cut -c1-16)" \
            "$(basename "${file}")"
    done < <(ls -1tr "${BACKUP_DIR}"/*.gz)
    exit 0
fi

# --- Режим: восстановление -------------------------------------------------

if [[ "${MODE}" == "restore" ]]; then
    if [[ ! -f "${RESTORE_FILE}" ]]; then
        echo "Файл копии не найден: ${RESTORE_FILE}" >&2
        exit 1
    fi

    echo "==> Восстановление стенда ${STAND} из копии"
    echo "    СУБД: ${DB_LABEL}"
    echo "    Файл: ${RESTORE_FILE}"

    case "${DATABASE_URL}" in
        sqlite*)
            DB_FILE="$(sqlite_file)"
            mkdir -p "$(dirname "${DB_FILE}")"

            # Сначала разворачиваем во временный файл: если копия битая,
            # рабочая база останется нетронутой.
            TEMP_RESTORE="${DB_FILE}.restore.$$"
            trap 'rm -f "${TEMP_RESTORE}"' EXIT
            gunzip -c "${RESTORE_FILE}" > "${TEMP_RESTORE}"

            # Проверяем, что это действительно база SQLite.
            if command -v sqlite3 >/dev/null 2>&1; then
                if ! sqlite3 "${TEMP_RESTORE}" "PRAGMA integrity_check;" | grep -q '^ok$'; then
                    echo "Копия повреждена: проверка целостности не пройдена." >&2
                    exit 1
                fi
                echo "    Проверка целостности: ok"
            fi

            [[ -f "${DB_FILE}" ]] && cp -p "${DB_FILE}" "${DB_FILE}.before-restore"
            mv "${TEMP_RESTORE}" "${DB_FILE}"
            trap - EXIT
            echo "    База восстановлена: ${DB_FILE}"
            [[ -f "${DB_FILE}.before-restore" ]] && \
                echo "    Прежняя база сохранена: ${DB_FILE}.before-restore"
            ;;

        postgresql*|postgres*)
            if ! command -v psql >/dev/null 2>&1; then
                echo "Утилита psql не найдена. Установите postgresql-client." >&2
                exit 1
            fi
            CONN="$(libpq_url)"
            # Дамп снимается с --clean --if-exists, поэтому его можно
            # применить поверх существующей базы.
            gunzip -c "${RESTORE_FILE}" | psql --quiet --set ON_ERROR_STOP=1 \
                --dbname="${CONN}" >/dev/null
            echo "    Данные восстановлены в базу по DATABASE_URL"
            ;;

        *)
            echo "Неизвестный тип СУБД в DATABASE_URL: ${DATABASE_URL}" >&2
            exit 1
            ;;
    esac

    restart_app_if_needed
    echo
    echo "Восстановление завершено."
    exit 0
fi

# --- Режим: создание копии -------------------------------------------------

echo "==> Резервное копирование стенда ${STAND}"
echo "    СУБД: ${DB_LABEL}"

case "${DATABASE_URL}" in
    sqlite*)
        DB_FILE="$(sqlite_file)"
        if [[ ! -f "${DB_FILE}" ]]; then
            echo "Файл базы данных не найден: ${DB_FILE}" >&2
            exit 1
        fi
        TARGET="${BACKUP_DIR}/skachki-${STAND}-${STAMP}.db"
        # sqlite3 .backup делает согласованный снимок даже при работающем приложении.
        if command -v sqlite3 >/dev/null 2>&1; then
            sqlite3 "${DB_FILE}" ".backup '${TARGET}'"
        else
            cp "${DB_FILE}" "${TARGET}"
        fi
        gzip -f "${TARGET}"
        echo "    Создан файл: ${TARGET}.gz"
        ;;

    postgresql*|postgres*)
        if ! command -v pg_dump >/dev/null 2>&1; then
            echo "Утилита pg_dump не найдена. Установите postgresql-client." >&2
            exit 1
        fi
        TARGET="${BACKUP_DIR}/skachki-${STAND}-${STAMP}.sql"
        # --clean --if-exists делает дамп пригодным для восстановления поверх
        # непустой базы (см. режим --restore).
        pg_dump --no-owner --no-privileges --clean --if-exists \
            --dbname="$(libpq_url)" --file="${TARGET}"
        gzip -f "${TARGET}"
        echo "    Создан файл: ${TARGET}.gz"
        ;;

    *)
        echo "Неизвестный тип СУБД в DATABASE_URL: ${DATABASE_URL}" >&2
        exit 1
        ;;
esac

echo "==> Удаление копий старше ${KEEP_DAYS} дней"
find "${BACKUP_DIR}" -type f \( -name '*.gz' -o -name '*.db' -o -name '*.sql' \) \
    -mtime "+${KEEP_DAYS}" -print -delete || true

echo
echo "Содержимое каталога резервных копий ${BACKUP_DIR}:"
ls -lh "${BACKUP_DIR}" | tail -n +2
