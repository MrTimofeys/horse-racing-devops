#!/usr/bin/env bash
#
# Подготовка виртуальной машины Ubuntu/Debian для стендов TEST / STAGE / PROD.
#
# Устанавливает инструменты разработки согласно выбранному стеку проекта:
# Python 3, систему контроля версий Git, средства сборки и (по желанию) PostgreSQL.
#
# Использование:
#   sudo bash scripts/provision-ubuntu.sh                  # базовый набор
#   sudo bash scripts/provision-ubuntu.sh --with-postgres  # плюс PostgreSQL
#
set -euo pipefail

WITH_POSTGRES=0
for arg in "$@"; do
    case "$arg" in
        --with-postgres) WITH_POSTGRES=1 ;;
        -h|--help)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *)
            echo "Неизвестный параметр: $arg" >&2
            exit 1
            ;;
    esac
done

if [[ "${EUID}" -ne 0 ]]; then
    echo "Скрипт нужно запускать от имени root: sudo bash $0" >&2
    exit 1
fi

echo "==> Обновление списка пакетов"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq

echo "==> Установка базовых инструментов разработки"
apt-get install -y -qq \
    python3 python3-venv python3-dev python3-pip \
    git curl ca-certificates \
    build-essential pkg-config libpq-dev \
    rsync sqlite3 unzip \
    net-tools iputils-ping

if [[ "${WITH_POSTGRES}" -eq 1 ]]; then
    echo "==> Установка PostgreSQL"
    apt-get install -y -qq postgresql postgresql-contrib
    systemctl enable --now postgresql
fi

echo
echo "==> Версии установленных средств разработки"
printf '  Python : %s\n' "$(python3 --version)"
printf '  pip    : %s\n' "$(python3 -m pip --version | awk '{print $2}')"
printf '  Git    : %s\n' "$(git --version)"
printf '  gcc    : %s\n' "$(gcc --version | head -n1)"
if [[ "${WITH_POSTGRES}" -eq 1 ]]; then
    printf '  psql   : %s\n' "$(psql --version)"
fi

# --- Совместимость версии Python -------------------------------------------
# Проекту нужен Python 3.11+. Слишком новые версии (например, 3.14 в не-LTS
# выпуске Ubuntu 26.04) могут не иметь готовых сборок части зависимостей —
# предупреждаем сразу, а не на этапе pip install.
PY_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MAJOR="${PY_VERSION%%.*}"
PY_MINOR="${PY_VERSION##*.}"

echo
if ((PY_MAJOR < 3 || (PY_MAJOR == 3 && PY_MINOR < 11))); then
    echo "ВНИМАНИЕ: Python ${PY_VERSION} старше требуемого 3.11." >&2
    echo "  Установите более новый интерпретатор или используйте Ubuntu 24.04 LTS." >&2
elif ((PY_MAJOR == 3 && PY_MINOR >= 14)); then
    echo "ВНИМАНИЕ: Python ${PY_VERSION} — очень новый выпуск."
    echo "  Готовые сборки отдельных библиотек могут отсутствовать, и pip начнёт"
    echo "  собирать их из исходников (libpq-dev и build-essential уже установлены)."
    echo "  Если сборка окажется проблемной, используйте Ubuntu 24.04 LTS (Python 3.12)."
else
    echo "Версия Python ${PY_VERSION} совместима с проектом."
fi

# В части сборок модуль venv вынесен в отдельный пакет.
if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "ВНИМАНИЕ: модуль venv недоступен. Установите пакет python${PY_VERSION}-venv." >&2
fi

echo
echo "Готово. Дальше выполните:"
echo "  git clone https://github.com/MrTimofeys/horse-racing-devops.git"
echo "  cd horse-racing-devops && sudo bash scripts/install-stand.sh <test|stage|prod>"
