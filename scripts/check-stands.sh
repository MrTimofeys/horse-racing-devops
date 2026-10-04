#!/usr/bin/env bash
#
# Проверка связности стендов TEST / STAGE / PROD (пункт 3 ЛР 2).
#
# Скрипт:
#   1) проверяет доступность всех машин по ICMP («ping от всех ко всем»);
#   2) проверяет, что приложение отвечает на каждом стенде;
#   3) печатает сводную таблицу.
#
# Использование:
#   bash scripts/check-stands.sh
#   bash scripts/check-stands.sh 10.211.55.4 10.211.55.5 10.211.55.6
#
# Если адреса не указаны, берутся значения по умолчанию из переменных
# окружения TEST_HOST, STAGE_HOST, PROD_HOST.
#
set -uo pipefail

if [[ $# -ge 1 ]]; then
    HOSTS=("$@")
else
    HOSTS=("${TEST_HOST:-10.211.55.4}" "${STAGE_HOST:-10.211.55.5}" "${PROD_HOST:-10.211.55.6}")
fi

NAMES=(test stage prod)
PORT="${APP_PORT:-8080}"

printf '%-8s %-16s %-12s %-30s %s\n' "СТЕНД" "АДРЕС" "PING" "ПРИЛОЖЕНИЕ" "ОТВЕТ"
printf '%s\n' "--------------------------------------------------------------------------------------"

FAILED=0

for i in "${!HOSTS[@]}"; do
    host="${HOSTS[$i]}"
    name="${NAMES[$i]:-стенд-$((i + 1))}"

    if ping -c 1 -W 2 "${host}" >/dev/null 2>&1; then
        ping_state="доступен"
    else
        ping_state="НЕТ ОТВЕТА"
        FAILED=1
    fi

    if body="$(curl -fsS --max-time 4 "http://${host}:${PORT}/api/health" 2>/dev/null)"; then
        app_state="отвечает"
    else
        app_state="НЕ ОТВЕЧАЕТ"
        body=""
        FAILED=1
    fi

    printf '%-8s %-16s %-12s %-30s %s\n' "${name}" "${host}" "${ping_state}" "${app_state}" "${body}"
done

echo
echo "Матрица связности «от всех ко всем» (ping):"
for from in "${HOSTS[@]}"; do
    printf '  %-16s -> ' "${from}"
    for to in "${HOSTS[@]}"; do
        if ping -c 1 -W 2 "${to}" >/dev/null 2>&1; then
            printf 'ok '
        else
            printf '-- '
        fi
    done
    printf '\n'
done

if [[ "${FAILED}" -ne 0 ]]; then
    echo
    echo "Некоторые проверки не прошли. Смотрите docs/DEPLOY_LR2.md, раздел «Диагностика»." >&2
    exit 1
fi

echo
echo "Все стенды доступны, приложение отвечает на каждом."
