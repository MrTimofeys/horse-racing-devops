#!/usr/bin/env bash
#
# Резервное копирование базы данных АС «Скачки».
# Поддерживает SQLite и PostgreSQL — СУБД определяется по DATABASE_URL.
#
# Использование:
#   bash scripts/backup.sh                     # на стенде, где развёрнуто приложение
#   BACKUP_DIR=/srv/backups bash scripts/backup.sh
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

mkdir -p "${BACKUP_DIR}"

case "${DATABASE_URL}" in
    sqlite*) DB_LABEL="SQLite" ;;
    postgresql*|postgres*) DB_LABEL="PostgreSQL" ;;
    *) DB_LABEL="${DATABASE_URL%%:*}" ;;
esac

echo "==> Резервное копирование стенда ${STAND}"
echo "    СУБД: ${DB_LABEL}"

case "${DATABASE_URL}" in
    sqlite*)
        DB_FILE="${DATABASE_URL#sqlite:///}"
        [[ "${DB_FILE}" != /* ]] && DB_FILE="${APP_DIR}/${DB_FILE}"
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
        # psycopg-URL -> обычная строка подключения libpq
        CONN="$(printf '%s' "${DATABASE_URL}" | sed -e 's|^postgresql+psycopg://|postgresql://|')"
        pg_dump --no-owner --no-privileges --dbname="${CONN}" --file="${TARGET}"
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
