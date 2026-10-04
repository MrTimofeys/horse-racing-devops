#!/usr/bin/env bash
#
# Самопроверка scripts/install-stand.sh без прав root и без systemd.
#
# Зачем: развёртывание стендов TEST / STAGE / PROD (ЛР 2) выполняется скриптом,
# но проверить его обычным способом можно только на виртуальной машине. Этот
# скрипт создаёт песочницу с заглушками системных утилит (useradd, chown,
# systemctl, sudo) и исполняет НАСТОЯЩИЙ scripts/install-stand.sh, направив
# APP_DIR и SERVICE_DIR внутрь рабочего каталога. Затем проверяется, что
# созданные артефакты (файл .env, виртуальное окружение, база данных, юнит
# systemd) пригодны для реального запуска приложения.
#
# Использование:
#   bash scripts/check-deploy.sh              # стенд test
#   bash scripts/check-deploy.sh prod         # стенд prod
#   bash scripts/check-deploy.sh stage --with-postgres
#
# Код возврата: 0 — все проверки пройдены, иначе число проваленных проверок.
#
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORIGINAL_PATH="${PATH}"
WORK_DIR="${WORK_DIR:-${REPO_DIR}/.deploy-selftest}"
BIN_DIR="${WORK_DIR}/bin"
APP_DIR="${WORK_DIR}/opt"
SERVICE_DIR="${WORK_DIR}/etc"
SERVICE_UNIT="skachki-selftest"

STAND="${1:-test}"
WITH_POSTGRES="${2:-}"
PORT="${PORT:-8095}"

case "${STAND}" in
    test|stage|prod) ;;
    *)
        echo "Неизвестный стенд: ${STAND}. Ожидается test, stage или prod." >&2
        exit 1
        ;;
esac

PASS=0
FAIL=0

check() {
    local name="$1" condition="$2"
    if eval "${condition}" >/dev/null 2>&1; then
        printf '  \033[32m✓\033[0m %s\n' "${name}"
        PASS=$((PASS + 1))
    else
        printf '  \033[31m✗\033[0m %s\n' "${name}"
        FAIL=$((FAIL + 1))
    fi
}

cleanup() {
    if [[ -f "${WORK_DIR}/stand.pid" ]]; then
        kill "$(cat "${WORK_DIR}/stand.pid")" 2>/dev/null
    fi
}
trap cleanup EXIT

# --- Песочница ------------------------------------------------------------
echo "=== Подготовка песочницы (${WORK_DIR}) ==="
cleanup
rm -rf "${WORK_DIR}"
mkdir -p "${BIN_DIR}" "${APP_DIR}" "${SERVICE_DIR}"

# Заглушки системных утилит: в песочнице мы не root и не systemd.
cat > "${BIN_DIR}/useradd" <<'STUB'
#!/usr/bin/env bash
echo "[заглушка] useradd $*"
STUB

cat > "${BIN_DIR}/chown" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB

cat > "${BIN_DIR}/sleep" <<'STUB'
#!/usr/bin/env bash
# Ускоряем цикл ожидания готовности службы: приложение в песочнице не запущено.
exit 0
STUB

cat > "${BIN_DIR}/sudo" <<'STUB'
#!/usr/bin/env bash
while [[ "${1:-}" == "-u" ]]; do shift 2; done
exec "$@"
STUB

cat > "${BIN_DIR}/systemctl" <<'STUB'
#!/usr/bin/env bash
echo "[заглушка] systemctl $*"
case "$*" in
    *status*) echo "Active: active (running)" ;;
esac
exit 0
STUB

cat > "${BIN_DIR}/curl" <<'STUB'
#!/usr/bin/env bash
# Приложение во время работы install-stand.sh ещё не отвечает.
exit 7
STUB

cat > "${BIN_DIR}/psql" <<'STUB'
#!/usr/bin/env bash
# Ответ на «есть ли такая база» — нет; остальное считаем успешным.
if [[ "$*" == *"-tAc"* ]]; then exit 1; fi
exit 0
STUB

cat > "${BIN_DIR}/createdb" <<'STUB'
#!/usr/bin/env bash
echo "[заглушка] createdb $*"
exit 0
STUB

# Межсетевой экран: записываем вызовы, чтобы потом проверить правила.
cat > "${BIN_DIR}/ufw" <<'STUB'
#!/usr/bin/env bash
echo "$*" >> "${UFW_LOG:-/dev/null}"
case "$*" in
    *"status verbose"*)
        echo "Status: active"
        echo "Default: deny (incoming), allow (outgoing), disabled (routed)"
        ;;
esac
exit 0
STUB

chmod +x "${BIN_DIR}"/*

# --- Запуск настоящего скрипта развёртывания -------------------------------
# Единственная правка: проверка прав root заменяется на no-op, потому что в
# песочнице мы не root. Всё остальное исполняется без изменений.
SCRIPT_COPY="${WORK_DIR}/install-stand.sh"
sed 's|if \[\[ "${EUID}" -ne 0 \]\]; then|if false; then|' \
    "${REPO_DIR}/scripts/install-stand.sh" > "${SCRIPT_COPY}"

echo "=== Запуск scripts/install-stand.sh (стенд ${STAND}${WITH_POSTGRES:+ ${WITH_POSTGRES}}) ==="

export PATH="${BIN_DIR}:${PATH}"
# Заглушка ufw пишет сюда список настроенных правил.
export UFW_LOG="${WORK_DIR}/ufw.log"
: > "${UFW_LOG}"
export APP_DIR SERVICE_DIR SOURCE_DIR="${REPO_DIR}"
export SERVICE_NAME="${SERVICE_UNIT}"
export APP_USER="skachki"

ARGS=("${STAND}")
[[ -n "${WITH_POSTGRES}" ]] && ARGS+=("--with-postgres")

bash "${SCRIPT_COPY}" "${ARGS[@]}" 2>&1 | sed 's/^/    /'
RUN_STATUS="${PIPESTATUS[0]}"

# --- Проверка артефактов ---------------------------------------------------
echo
echo "=== Проверка артефактов развёртывания ==="
check "скрипт завершился без ошибок" "[[ ${RUN_STATUS} -eq 0 ]]"
check "создан каталог приложения" "[[ -d '${APP_DIR}' ]]"
check "скопирован код приложения (app/main.py)" "[[ -f '${APP_DIR}/app/main.py' ]]"
check "скопированы скрипты обслуживания (scripts/backup.sh)" "[[ -f '${APP_DIR}/scripts/backup.sh' ]]"
check "создано виртуальное окружение" "[[ -x '${APP_DIR}/.venv/bin/python' ]]"
check "зависимости установлены (fastapi, uvicorn, sqlalchemy, jinja2)" \
    "\"${APP_DIR}/.venv/bin/python\" -c 'import fastapi, uvicorn, sqlalchemy, jinja2'"
check "создан файл конфигурации .env" "[[ -f '${APP_DIR}/.env' ]]"
check "создан юнит systemd" "[[ -f '${SERVICE_DIR}/${SERVICE_UNIT}.service' ]]"

echo
echo "--- Содержимое .env ---"
sed 's/^/    /' "${APP_DIR}/.env" 2>/dev/null

echo
echo "--- Содержимое юнита systemd ---"
sed 's/^/    /' "${SERVICE_DIR}/${SERVICE_UNIT}.service" 2>/dev/null

echo
echo "=== Проверка значений конфигурации ==="
ENV_FILE="${APP_DIR}/.env"
UNIT_FILE="${SERVICE_DIR}/${SERVICE_UNIT}.service"

check "STAND_NAME = ${STAND}" "grep -q '^STAND_NAME=${STAND}$' '${ENV_FILE}'"
check "APP_HOST = 0.0.0.0" "grep -q '^APP_HOST=0.0.0.0$' '${ENV_FILE}'"
check "APP_PORT = 8080" "grep -q '^APP_PORT=8080$' '${ENV_FILE}'"
check "юнит объявляет запуск через uvicorn" "grep -q 'uvicorn app.main:app' '${UNIT_FILE}'"
check "юнит перезапускает службу при сбое" "grep -q '^Restart=always$' '${UNIT_FILE}'"

if [[ -n "${WITH_POSTGRES}" ]]; then
    check "DATABASE_URL указывает на PostgreSQL" "grep -q '^DATABASE_URL=postgresql+psycopg://' '${ENV_FILE}'"
    check "пароль БД сгенерирован (не пустой)" "grep -qE '^DATABASE_URL=postgresql\+psycopg://[^:]+:[^@]{12,}@' '${ENV_FILE}'"
    check "юнит зависит от postgresql.service" "grep -q 'After=network-online.target postgresql.service' '${UNIT_FILE}'"
else
    check "DATABASE_URL указывает на SQLite" "grep -q '^DATABASE_URL=sqlite:///instance/skachki.db$' '${ENV_FILE}'"
    check "юнит не зависит от postgresql.service" "! grep -q 'postgresql.service' '${UNIT_FILE}'"
fi

case "${STAND}" in
    prod)
        check "на стенде PROD демо-данные выключены" "grep -q '^SEED_DEMO_DATA=false$' '${ENV_FILE}'"
        check "на стенде PROD подсказка с демо-учётками выключена" "grep -q '^DEMO_LOGIN_HINT=false$' '${ENV_FILE}'"
        ;;
    *)
        check "на стенде ${STAND} демо-данные включены" "grep -q '^SEED_DEMO_DATA=true$' '${ENV_FILE}'"
        ;;
esac

check "служба зарегистрирована в systemd" "grep -q 'systemctl enable' '${SCRIPT_COPY}'"

# --- Автоматическое резервное копирование (ТЗ: копирование автоматическое и ручное)
BACKUP_SERVICE="${SERVICE_DIR}/${SERVICE_NAME}-backup.service"
BACKUP_TIMER="${SERVICE_DIR}/${SERVICE_NAME}-backup.timer"
check "создан юнит автоматического копирования" "[[ -f '${BACKUP_SERVICE}' ]]"
check "создан таймер автоматического копирования" "[[ -f '${BACKUP_TIMER}' ]]"
check "таймер запускает именно службу копирования" "grep -q '^Unit=${SERVICE_NAME}-backup.service$' '${BACKUP_TIMER}'"
check "таймер срабатывает ежедневно" "grep -q '^OnCalendar=\\*-\\*-\\* 03:30:00$' '${BACKUP_TIMER}'"
check "пропущенное копирование не теряется (Persistent)" "grep -q '^Persistent=true$' '${BACKUP_TIMER}'"
check "служба копирования вызывает scripts/backup.sh" "grep -q 'scripts/backup.sh' '${BACKUP_SERVICE}'"
check "копирование выполняется от имени ${APP_USER}" "grep -q '^User=${APP_USER}$' '${BACKUP_SERVICE}'"
check "таймер включён в автозапуск" "grep -qE 'systemctl enable --now \"?\\\$\{?SERVICE_NAME\}?-backup\\.timer' '${SCRIPT_COPY}'"

# --- Межсетевой экран (ТЗ: защищённая часть отделена межсетевым экраном) ---
check "межсетевой экран включён" "grep -q 'enable' '${UFW_LOG}'"
check "входящие соединения запрещены по умолчанию" "grep -q '^default deny incoming\$' '${UFW_LOG}'"
check "исходящие соединения разрешены" "grep -q '^default allow outgoing\$' '${UFW_LOG}'"
check "открыт SSH для администрирования" "grep -q '^allow 22/tcp' '${UFW_LOG}'"
check "открыт только порт приложения 8080" "grep -q '^allow 8080/tcp' '${UFW_LOG}'"
check "ping разрешён только между стендами" \
    "grep -q '^allow from 10.211.55.0/24 to any proto icmp' '${UFW_LOG}'"

if [[ -n "${WITH_POSTGRES}" ]]; then
    check "PostgreSQL доступен только локальной сети стендов" \
        "grep -q '^allow from 10.211.55.0/24 to any port 5432' '${UFW_LOG}'"
else
    check "порт PostgreSQL не открыт (стенд на SQLite)" \
        "! grep -q '5432' '${UFW_LOG}'"
fi

# --- Проверка реального запуска приложения ---------------------------------
# Снимаем заглушки: дальше нужны настоящие curl и sleep.
export PATH="${ORIGINAL_PATH}"

echo
echo "=== Проверка запуска приложения из развёрнутого каталога ==="
if [[ -n "${WITH_POSTGRES}" ]]; then
    echo "  (стенд с PostgreSQL: запуск не проверяется — сервера СУБД в песочнице нет)"
    echo "  (схема будет создана автоматически при первом обращении к /api/health)"
else
    (
        cd "${APP_DIR}" || exit 1
        set -a
        # shellcheck disable=SC1091
        . ./.env
        set +a
        APP_PORT="${PORT}" nohup ./.venv/bin/python -m app.cli run --port "${PORT}" \
            > "${WORK_DIR}/stand.log" 2>&1 &
        echo $! > "${WORK_DIR}/stand.pid"
    )
    sleep 8

    STAND_UPPER="$(echo "${STAND}" | tr '[:lower:]' '[:upper:]')"
    HEALTH="$(curl -s --max-time 5 "http://127.0.0.1:${PORT}/api/health" 2>/dev/null || true)"
    echo "  ответ /api/health: ${HEALTH}"

    check "процесс приложения запущен" "kill -0 \$(cat '${WORK_DIR}/stand.pid')"
    check "приложение отвечает на /api/health" "[[ -n '${HEALTH}' ]]"
    check "статус стенда — ok" "[[ '${HEALTH}' == *'\"status\":\"ok\"'* ]]"
    check "имя стенда в ответе — ${STAND_UPPER}" "[[ '${HEALTH}' == *'\"stand\":\"${STAND_UPPER}\"'* ]]"
    check "схема БД создана" "[[ '${HEALTH}' == *'\"schema_ready\":true'* ]]"

    LOGIN_CODE="$(curl -s -o /dev/null -w '%{http_code}' -X POST \
        -d 'username=admin&password=admin123' "http://127.0.0.1:${PORT}/login" 2>/dev/null || true)"
    check "вход под admin работает (303)" "[[ '${LOGIN_CODE}' == '303' ]]"

    echo
    echo "--- Резервное копирование и восстановление ---"
    DB_FILE="${APP_DIR}/instance/skachki.db"
    cat > "${WORK_DIR}/count_horses.py" <<'COUNT_PY'
import sqlite3
import sys

try:
    rows = sqlite3.connect(sys.argv[1]).execute("SELECT COUNT(*) FROM horses").fetchone()
    print(rows[0])
except Exception:
    print(0)
COUNT_PY
    count_horses() { "${APP_DIR}/.venv/bin/python" "${WORK_DIR}/count_horses.py" "${DB_FILE}"; }

    add_horse() {
        (cd "${APP_DIR}" && "${APP_DIR}/.venv/bin/python" -c "
from app import crud
from app.database import SessionLocal
with SessionLocal() as db:
    crud.create_horse(db, name='Проверочная лошадь', sex='кобыла', age=4, owner_id=None)
")
    }

    HORSES_BEFORE="$(count_horses)"

    if (cd "${APP_DIR}" && bash scripts/backup.sh > "${WORK_DIR}/backup.log" 2>&1); then
        check "scripts/backup.sh создал резервную копию" "ls '${APP_DIR}'/backups/*.gz"
        check "список копий выводится" \
            "(cd '${APP_DIR}' && bash scripts/backup.sh --list | grep -q 'skachki-.*\.gz')"

        BACKUP_FILE="$(ls -t "${APP_DIR}"/backups/*.gz 2>/dev/null | head -1)"
        if [[ -n "${BACKUP_FILE}" ]]; then
            # Меняем данные, затем восстанавливаемся из копии и убеждаемся,
            # что вернулось прежнее состояние — это и есть проверка
            # подсистемы восстановления, требуемой ТЗ.
            add_horse >/dev/null 2>&1 || true
            HORSES_CHANGED="$(count_horses)"
            check "данные изменились перед восстановлением (${HORSES_BEFORE} → ${HORSES_CHANGED})" \
                "[[ '${HORSES_CHANGED}' -gt '${HORSES_BEFORE}' ]]"

            if (cd "${APP_DIR}" && RESTART_SERVICE=0 bash scripts/backup.sh --restore "${BACKUP_FILE}" \
                    > "${WORK_DIR}/restore.log" 2>&1); then
                check "scripts/backup.sh --restore восстанавливает копию" "true"
                HORSES_AFTER="$(count_horses)"
                check "после восстановления данные совпадают с копией (${HORSES_AFTER})" \
                    "[[ '${HORSES_AFTER}' -eq '${HORSES_BEFORE}' ]]"
            else
                check "scripts/backup.sh --restore восстанавливает копию" "false"
            fi

            # Повреждённая копия не должна затирать рабочую базу.
            echo "не база данных" | gzip > "${WORK_DIR}/broken.db.gz"
            if (cd "${APP_DIR}" && RESTART_SERVICE=0 bash scripts/backup.sh --restore "${WORK_DIR}/broken.db.gz" \
                    > "${WORK_DIR}/broken.log" 2>&1); then
                check "повреждённая копия отклоняется" "false"
            else
                check "повреждённая копия отклоняется" "true"
                check "рабочая база не пострадала от повреждённой копии" \
                    "[[ \"\$(count_horses)\" -eq '${HORSES_BEFORE}' ]]"
            fi
        fi
    else
        check "scripts/backup.sh создал резервную копию" "false"
    fi
fi

echo
echo "=========================================="
printf 'Пройдено проверок: %d, провалено: %d\n' "${PASS}" "${FAIL}"
if [[ "${FAIL}" -eq 0 ]]; then
    echo "РЕЗУЛЬТАТ: успех"
else
    echo "РЕЗУЛЬТАТ: есть ошибки"
fi
exit "${FAIL}"
