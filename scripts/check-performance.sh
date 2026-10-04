#!/usr/bin/env bash
#
# Проверка показателей назначения АС «Скачки».
#
# ТЗ (п. «Требования к показателям назначения»): «Система должна обеспечивать
# возможность одновременной работы 10 пользователей при времени отклика системы
# для операций навигации – не более 3 секунды».
#
# Скрипт входит в систему под учётной записью, затем одновременно запрашивает
# страницы навигации от имени 10 пользователей и измеряет время отклика.
#
# Использование:
#   bash scripts/check-performance.sh                              # стенд на localhost
#   bash scripts/check-performance.sh http://10.211.55.11:8080     # конкретный стенд
#   USERS=20 bash scripts/check-performance.sh                     # другая нагрузка
#
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8080}"
USERS="${USERS:-10}"
LIMIT_SECONDS="${LIMIT_SECONDS:-3}"

LOGIN="${SKACHKI_LOGIN:-admin}"
PASSWORD="${SKACHKI_PASSWORD:-admin123}"

# Страницы навигации: именно они упомянуты в требовании к времени отклика.
PAGES=("/dashboard" "/races" "/horses" "/jockeys" "/owners" "/results" "/hippodromes")

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

echo "==> Проверка показателей назначения"
echo "    Стенд:  ${BASE_URL}"
echo "    Пользователей одновременно: ${USERS}"
echo "    Предел времени отклика:     ${LIMIT_SECONDS} с"
echo

# --- Проверка доступности стенда -------------------------------------------
if ! curl -fsS --max-time 5 "${BASE_URL}/api/health" >/dev/null 2>&1; then
    echo "Стенд не отвечает по адресу ${BASE_URL}." >&2
    echo "Проверьте: systemctl status skachki" >&2
    exit 1
fi

# --- Вход в систему ---------------------------------------------------------
# Каждому «пользователю» — своя сессия, иначе это была бы одна сессия,
# а требование говорит об одновременной работе разных пользователей.
echo "==> Вход в систему под учётной записью ${LOGIN}"
for i in $(seq 1 "${USERS}"); do
    code="$(curl -s -o /dev/null -w '%{http_code}' \
        -c "${TMP_DIR}/cookies-${i}.txt" \
        -d "username=${LOGIN}&password=${PASSWORD}" \
        "${BASE_URL}/login" || true)"
    if [[ "${code}" != "303" ]]; then
        echo "Не удалось войти (код ${code}). Проверьте логин и пароль." >&2
        exit 1
    fi
done
echo "    Получено сессий: ${USERS}"
echo

# --- Одновременные запросы --------------------------------------------------
# Каждый пользователь обходит все страницы навигации подряд; все пользователи
# работают одновременно. Пишем время каждого запроса в отдельный файл.
echo "==> Одновременный обход страниц навигации"
START_TS="$(date +%s)"

for i in $(seq 1 "${USERS}"); do
    (
        for page in "${PAGES[@]}"; do
            curl -s -o /dev/null -b "${TMP_DIR}/cookies-${i}.txt" \
                -w '%{time_total} %{http_code}\n' \
                --max-time 60 "${BASE_URL}${page}" \
                >> "${TMP_DIR}/results-${i}.txt" 2>/dev/null || echo "60.0 000" >> "${TMP_DIR}/results-${i}.txt"
        done
    ) &
done
wait
TOTAL_TS="$(( $(date +%s) - START_TS ))"

cat "${TMP_DIR}"/results-*.txt > "${TMP_DIR}/all.txt"
REQUESTS="$(wc -l < "${TMP_DIR}/all.txt" | tr -d ' ')"

# --- Разбор результатов -----------------------------------------------------
awk -v limit="${LIMIT_SECONDS}" -v users="${USERS}" '
{
    t = $1 + 0
    code = $2

    if (code != 200) { bad++ }
    if (t > max)    { max = t; max_page = NR }
    sum += t
    n++
    if (t > limit) over++
}
END {
    printf "    Всего запросов:        %d\n", n
    printf "    Среднее время отклика: %.3f с\n", (n ? sum / n : 0)
    printf "    Максимальное время:    %.3f с\n", max
    printf "    Превысили предел %s с: %d\n", limit, over + 0
    printf "    Ответов не 200:        %d\n", bad + 0
    printf "\n"
    if (over > 0 || bad > 0) { exit 1 }
    printf "РЕЗУЛЬТАТ: требование выполнено — %d пользователей, отклик не более %s с\n", users, limit
}' "${TMP_DIR}/all.txt" || {
    echo "РЕЗУЛЬТАТ: требование не выполнено" >&2
    exit 1
}

echo "    Полное время обхода всеми пользователями: ${TOTAL_TS} с (${REQUESTS} запросов)"
