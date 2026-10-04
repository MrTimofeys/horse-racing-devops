#!/usr/bin/env bash
#
# Развёртывание АС «Скачки» на стенде TEST / STAGE / PROD.
#
# Скрипт:
#   1) копирует исходный код репозитория в /opt/horse-racing-devops;
#   2) создаёт виртуальное окружение Python и ставит зависимости;
#   3) формирует файл .env с параметрами конкретного стенда;
#   4) (по желанию) создаёт базу данных PostgreSQL;
#   5) регистрирует и запускает службу systemd skachki.
#
# Использование:
#   sudo bash scripts/install-stand.sh test
#   sudo bash scripts/install-stand.sh stage --port 8080 --with-postgres
#   sudo bash scripts/install-stand.sh prod  --with-postgres --no-demo-data
#
set -euo pipefail

SERVICE_NAME="${SERVICE_NAME:-skachki}"
# Значения можно переопределить переменными окружения — это используется при
# проверке самого скрипта и при нестандартной раскладке каталогов на стенде.
APP_USER="${APP_USER:-skachki}"
APP_DIR="${APP_DIR:-/opt/horse-racing-devops}"
SERVICE_DIR="${SERVICE_DIR:-/etc/systemd/system}"
DB_NAME="${DB_NAME:-skachki}"
DB_USER="${DB_USER:-skachki}"
# Локальная сеть стендов — источник, которому разрешено подключаться к PostgreSQL.
STAND_NETWORK="${STAND_NETWORK:-10.211.55.0/24}"

STAND=""
PORT=""
USE_POSTGRES=0
SEED_DEMO=1

usage() {
    cat <<'EOF'
Использование: sudo bash scripts/install-stand.sh <test|stage|prod> [параметры]

Параметры:
  --port <номер>       порт приложения (по умолчанию 8080)
  --with-postgres      использовать PostgreSQL вместо SQLite
  --no-demo-data       не загружать демонстрационные данные
  -h, --help           показать эту справку
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        test|stage|prod)
            STAND="$1"; shift ;;
        --port)
            PORT="${2:-}"; shift 2 ;;
        --with-postgres)
            USE_POSTGRES=1; shift ;;
        --no-demo-data)
            SEED_DEMO=0; shift ;;
        -h|--help)
            usage; exit 0 ;;
        *)
            echo "Неизвестный параметр: $1" >&2; usage; exit 1 ;;
    esac
done

if [[ -z "${STAND}" ]]; then
    echo "Не указан стенд. Укажите test, stage или prod." >&2
    usage
    exit 1
fi

if [[ "${EUID}" -ne 0 ]]; then
    echo "Скрипт нужно запускать от имени root: sudo bash $0 ${STAND}" >&2
    exit 1
fi

SOURCE_DIR="${SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PORT="${PORT:-8080}"

# Стенд PROD по умолчанию разворачивается без демонстрационных данных.
if [[ "${STAND}" == "prod" && "${SEED_DEMO}" -eq 1 ]]; then
    SEED_DEMO=0
fi

echo "==> Стенд: ${STAND}"
echo "    Исходный код : ${SOURCE_DIR}"
echo "    Каталог      : ${APP_DIR}"
echo "    Порт         : ${PORT}"
echo "    СУБД         : $( [[ ${USE_POSTGRES} -eq 1 ]] && echo PostgreSQL || echo SQLite )"
echo "    Демо-данные  : $( [[ ${SEED_DEMO} -eq 1 ]] && echo да || echo нет )"
echo

# --- 1. Системный пользователь -------------------------------------------
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
    echo "==> Создание системного пользователя ${APP_USER}"
    useradd --system --create-home --shell /usr/sbin/nologin "${APP_USER}"
fi

# --- 2. Копирование кода --------------------------------------------------
echo "==> Копирование исходного кода в ${APP_DIR}"
mkdir -p "${APP_DIR}"
rsync -a --delete \
    --exclude '.git' \
    --exclude '.venv' \
    --exclude 'instance' \
    --exclude '__pycache__' \
    --exclude '.pytest_cache' \
    "${SOURCE_DIR}/" "${APP_DIR}/"

# --- 3. Виртуальное окружение и зависимости ------------------------------
echo "==> Создание виртуального окружения и установка зависимостей"
if [[ ! -x "${APP_DIR}/.venv/bin/python" ]]; then
    python3 -m venv "${APP_DIR}/.venv"
fi
"${APP_DIR}/.venv/bin/pip" install --quiet --upgrade pip
"${APP_DIR}/.venv/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"

if [[ "${USE_POSTGRES}" -eq 1 ]]; then
    "${APP_DIR}/.venv/bin/pip" install --quiet -r "${APP_DIR}/requirements-postgres.txt"
fi

# --- 4. База данных -------------------------------------------------------
if [[ "${USE_POSTGRES}" -eq 1 ]]; then
    echo "==> Подготовка PostgreSQL"
    systemctl enable --now postgresql

    DB_PASSWORD="$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)"

    sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_USER}') THEN
        CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';
    ELSE
        ALTER ROLE ${DB_USER} PASSWORD '${DB_PASSWORD}';
    END IF;
END
\$\$;
SQL

    if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
        sudo -u postgres createdb -O "${DB_USER}" "${DB_NAME}"
    fi

    DATABASE_URL="postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@127.0.0.1:5432/${DB_NAME}"
else
    DATABASE_URL="sqlite:///instance/skachki.db"
fi

# --- 5. Файл конфигурации стенда -----------------------------------------
echo "==> Запись ${APP_DIR}/.env"
mkdir -p "${APP_DIR}/instance"
cat > "${APP_DIR}/.env" <<ENV
# Конфигурация стенда ${STAND}, создана scripts/install-stand.sh
STAND_NAME=${STAND}
DATABASE_URL=${DATABASE_URL}
APP_HOST=0.0.0.0
APP_PORT=${PORT}
SESSION_TTL_HOURS=12
AUTO_SEED=true
SEED_DEMO_DATA=$( [[ ${SEED_DEMO} -eq 1 ]] && echo true || echo false )
DEMO_LOGIN_HINT=$( [[ "${STAND}" == "prod" ]] && echo false || echo true )
ENV

chmod 640 "${APP_DIR}/.env"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

# --- 6. Инициализация базы ------------------------------------------------
# Сбой на этом шаге не прерывает развёртывание: приложение умеет работать без
# базы (отдаёт status=degraded и страницу 503) и создаёт схему самостоятельно,
# как только СУБД станет доступна. Иначе стенд остался бы вообще без службы.
echo "==> Инициализация базы данных"
if [[ "${SEED_DEMO}" -eq 1 ]]; then
    SEED_ARGS="seed --demo"
else
    SEED_ARGS="seed"
fi

mkdir -p "${APP_DIR}/instance"
INIT_LOG="${APP_DIR}/instance/install.log"

if sudo -u "${APP_USER}" bash -c "cd '${APP_DIR}' && set -a && . ./.env && set +a && ./.venv/bin/python -m app.cli init-db && ./.venv/bin/python -m app.cli ${SEED_ARGS}" >"${INIT_LOG}" 2>&1; then
    echo "    Схема создана, начальные данные загружены."
    DATABASE_PREPARED=1
else
    DATABASE_PREPARED=0
    echo "    ВНИМАНИЕ: не удалось подготовить базу данных."
    tail -n 2 "${INIT_LOG}" | sed 's/^/      /'
fi

# --- 6.1. Межсетевой экран -------------------------------------------------
# ТЗ (п. «Требования к защите информации от НСД»): защищённая часть системы
# должна быть отделена от незащищённой части межсетевым экраном. Открывается
# только необходимое: SSH для администрирования и порт самого приложения.
# Порт PostgreSQL доступен лишь адресам локальной сети стендов, а не всем.
echo "==> Настройка межсетевого экрана"
if command -v ufw >/dev/null 2>&1; then
    # Каждое правило добавляется отдельно: сбой одного правила не должен
    # срывать развёртывание стенда, но о нём сообщается в выводе.
    ufw_rule() {
        if ! ufw "$@" >/dev/null 2>&1; then
            echo "    ВНИМАНИЕ: не удалось применить правило ufw $*"
        fi
    }

    ufw --force reset >/dev/null 2>&1 || true

    if ufw default deny incoming >/dev/null 2>&1; then
        echo "    входящие соединения запрещены по умолчанию"
    else
        echo "    ВНИМАНИЕ: не удалось задать политику по умолчанию"
    fi
    ufw default allow outgoing >/dev/null 2>&1 || true

    # Протокол указывается до адреса — таков порядок аргументов в ufw.
    ufw_rule allow 22/tcp comment 'SSH'
    ufw_rule allow "${PORT}/tcp" comment 'АС Скачки'
    # ICMP разрешаем только между стендами: от него зависит проверка связности
    # (scripts/check-stands.sh), но открывать его всему миру не нужно.
    ufw_rule allow proto icmp from "${STAND_NETWORK}" comment 'ping между стендами'
    if [[ ${USE_POSTGRES} -eq 1 ]]; then
        ufw_rule allow proto tcp from "${STAND_NETWORK}" to any port 5432 \
            comment 'PostgreSQL для стендов'
    fi

    # Включаем защиту последней: правило для SSH уже создано, поэтому доступ
    # к стенду не теряется.
    ufw --force enable >/dev/null 2>&1 || echo "    ВНИМАНИЕ: не удалось включить ufw"
    ufw status verbose || true
else
    echo "    (ufw не установлен — установите пакет ufw и повторите развёртывание)"
fi

# --- 7. Служба systemd ----------------------------------------------------
echo "==> Регистрация службы ${SERVICE_NAME}.service"
cat > "${SERVICE_DIR}/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=АС «Скачки» — стенд ${STAND}
Documentation=https://github.com/MrTimofeys/horse-racing-devops
After=network-online.target$( [[ ${USE_POSTGRES} -eq 1 ]] && printf ' postgresql.service' )
Wants=network-online.target$( [[ ${USE_POSTGRES} -eq 1 ]] && printf ' postgresql.service' )

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/uvicorn app.main:app --host \${APP_HOST} --port \${APP_PORT} --workers 2
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

# Ограничения безопасности службы
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

# --- 7.1. Автоматическое резервное копирование ----------------------------
# ТЗ (п. «Требования по сохранности информации при авариях») требует
# возможности организации как автоматического, так и ручного резервного
# копирования. Ручное — это scripts/backup.sh, автоматическое — таймер systemd.
echo "==> Регистрация автоматического резервного копирования"
cat > "${SERVICE_DIR}/${SERVICE_NAME}-backup.service" <<BACKUP_UNIT
[Unit]
Description=Резервное копирование БД АС «Скачки» (стенд ${STAND})
Documentation=https://github.com/MrTimofeys/horse-racing-devops

[Service]
Type=oneshot
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
Environment=APP_DIR=${APP_DIR}
Environment=BACKUP_DIR=${APP_DIR}/backups
ExecStart=/bin/bash ${APP_DIR}/scripts/backup.sh
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}-backup

# Ограничения безопасности службы
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
BACKUP_UNIT

# Ежедневно в 03:30 и через 10 минут после включения машины, если момент
# был пропущен. Persistent=true не даёт пропустить копирование, если машина
# в назначенное время была выключена.
cat > "${SERVICE_DIR}/${SERVICE_NAME}-backup.timer" <<TIMER_UNIT
[Unit]
Description=Ежедневное резервное копирование БД АС «Скачки» (стенд ${STAND})

[Timer]
OnCalendar=*-*-* 03:30:00
OnBootSec=10min
Persistent=true
Unit=${SERVICE_NAME}-backup.service

[Install]
WantedBy=timers.target
TIMER_UNIT

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}-backup.timer" 2>/dev/null || \
    echo "(таймер зарегистрирован; запустите: systemctl enable --now ${SERVICE_NAME}-backup.timer)"

# --- 8. Проверка ----------------------------------------------------------
echo "==> Ожидание запуска службы"
for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

echo
echo "==> Состояние службы"
systemctl --no-pager --lines=0 status "${SERVICE_NAME}" || true

echo
echo "==> Проверка работоспособности"
HEALTH="$(curl -s "http://127.0.0.1:${PORT}/api/health" || true)"
if [[ -z "${HEALTH}" ]]; then
    echo "(служба ещё не отвечает — смотрите journalctl -u ${SERVICE_NAME})"
else
    echo "${HEALTH}"
fi

if [[ "${HEALTH}" == *'"degraded"'* || "${DATABASE_PREPARED:-1}" -eq 0 ]]; then
    cat <<WARN

ВНИМАНИЕ: база данных недоступна.
  Стенд развёрнут, служба ${SERVICE_NAME} зарегистрирована и запущена.
  Приложение отвечает на /api/health (status=degraded) и отдаёт страницу 503.
  Проверьте службу СУБД и строку DATABASE_URL в ${APP_DIR}/.env.
  Схема будет создана автоматически, как только СУБД станет доступна,
  перезапуск службы не требуется.
WARN
fi

cat <<EOF

Стенд ${STAND} развёрнут.

  Панель управления : http://127.0.0.1:${PORT}
  Документация API  : http://127.0.0.1:${PORT}/docs
  Проверка стенда   : curl -s http://127.0.0.1:${PORT}/api/health

Полезные команды:
  sudo systemctl status ${SERVICE_NAME}
  sudo journalctl -u ${SERVICE_NAME} -f
  sudo systemctl restart ${SERVICE_NAME}

Резервное копирование:
  sudo bash scripts/backup.sh                 # создать копию вручную
  bash scripts/backup.sh --list               # список копий
  sudo bash scripts/backup.sh --restore FILE  # восстановить из копии
  systemctl list-timers ${SERVICE_NAME}-backup.timer   # автоматическое копирование
EOF
