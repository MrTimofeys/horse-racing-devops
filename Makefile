# АС «Скачки» — типовые операции разработчика и администратора стенда.
#
#   make install        установить зависимости приложения
#   make dev            установить зависимости вместе с тестовыми
#   make run            запустить приложение (http://127.0.0.1:8080)
#   make test           прогнать тесты
#   make seed           загрузить демонстрационные данные
#   make reset          полностью пересоздать базу
#   make check          проверить подключение к СУБД

PYTHON ?= python3
VENV   ?= .venv
BIN    := $(VENV)/bin
STAND  ?= test
HOST   ?= 127.0.0.1
PORT   ?= 8080

.PHONY: help venv install dev run test test-cov seed reset check stats info \
        install-stand provision backup clean docker-build

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

venv:  ## создать виртуальное окружение
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip

install: venv  ## установить зависимости приложения
	$(BIN)/pip install -r requirements.txt

dev: venv  ## установить зависимости вместе с тестовыми
	$(BIN)/pip install -r requirements-dev.txt

run:  ## запустить приложение
	$(BIN)/python -m app.cli run --host $(HOST) --port $(PORT)

test:  ## прогнать тесты
	$(BIN)/python -m pytest

test-cov:  ## прогнать тесты с оценкой покрытия
	$(BIN)/python -m pytest --cov=app --cov-report=term-missing

seed:  ## загрузить учётные записи и демонстрационные данные
	$(BIN)/python -m app.cli seed --demo

reset:  ## полностью пересоздать базу данных
	$(BIN)/python -m app.cli reset --yes --demo

check:  ## проверить подключение к СУБД
	$(BIN)/python -m app.cli check

stats:  ## показать количество записей
	$(BIN)/python -m app.cli stats

info:  ## показать параметры текущего стенда
	$(BIN)/python -m app.cli info

provision:  ## установить системные пакеты (Ubuntu/Debian, нужен sudo)
	sudo bash scripts/provision-ubuntu.sh

install-stand:  ## развернуть стенд как службу systemd: make install-stand STAND=test
	sudo bash scripts/install-stand.sh $(STAND)

backup:  ## создать резервную копию базы данных
	bash scripts/backup.sh

clean:  ## удалить временные файлы и кеши
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .coverage htmlcov
