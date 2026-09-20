
## Cервис вывода средств. Разработан по следующему ТЗ.

POST /api/v1/transfer
```json
{
  "external_id": "string",
  "currency": "string",
  "amount": "string (decimal)",
  "destination": "string",
  "comment": "string | null (optional)"
}
```

ответ

```json 
{
  "id": "string (uuid)",
  "external_id": "string",
  "currency": "string",
  "amount": "string (decimal)",
  "destination": "string",
  "status": "string (enum: completed, failed, pending)"
}
```


**Примечание:** Запросы с одинаковым external_id обрабатываются идемпотентно. При повторном вызове с уже существующим ID игнорировать конфликт и возвращает успешный ответ.


`webhook - перевод с внутреннего кошелка на внешний`


```json
{
  "id": "string (uuid)",
  "external_id": "string",
  "amount": "string (decimal)",
  "status": "string (enum: completed, failed)"
  "details": {
    "from_address": "string",
    "to_address": "string",
    "tx_hash": "string | null (optional)"
  }
}
```

**Примечание:** url для webhook пока будем задавать в env


Aвторизация пока самая простая по статичному bearer токену.
Подпись для webhook генерируется след образом.

``` python
import hmac
import hashlib


def generate_signature(api_key: str, body: bytes) -> str:
    token_hash = sha256(api_key.encode()).digest()
    return hmac.HMAC(token_hash, body, hashlib.sha256).hexdigest()
```

Подпись передается в заголовок X-signature или в другой главное что бы был.


стек задачи: python >= 3.13, postgresql, alembic, sqlalchemy, fastapi

## Запуск приложения

Создать в корне файл .env (Пример файла .env copy)

Запустить приложение
```
make run
```


## Команды

Перечень команд которые могут пригодится в разработке

### Poetry
```bash
poetry config virtualenvs.in-project true      # окружение в ./.venv, один раз на машину
poetry env use /usr/local/bin/python3.14       # привязать проект к нужному Python
poetry install                                 # поставить зависимости из poetry.lock
poetry add fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" asyncpg alembic pydantic-settings httpx  # Добавление зависимостей
poetry add --group dev pytest pytest-asyncio ruff mypy

poetry env info # Проверка
poetry run python --version # Проверка
```                               

### Docker
```bash
make down - погасить контейнер
make build - собрать контейнер
make up - поднять контейнер
make run - последоватльно запустить down -> build -> up
```

### Alembic

Поднять бд
```bash
docker compose up -d db
```

Инициализация Alembic (Один раз)
```bash
poetry run alembic init -t async migrations
```

Генерация миграции
```bash
poetry run alembic revision --autogenerate -m "init"
```

Применение миграции
```bash
poetry run alembic upgrade head
```

Проверка миграции
```bash
poetry run alembic current
```

Локальный запуск веб-сервера

```bash
poetry run uvicorn payout_gateway.main:app --reload --port 8080
```

### Команда для вывода в консоль структуру проекта

```bash
find . \( \
  -path "./venv" -o \
  -path "./.venv" -o \
  -path "./.git" -o \
  -path "*/__pycache__" -o \
  -path "./.ruff_cache" -o \
  -path "./.pytest_cache" -o \
  -path "./.mypy_cache" -o \
  -path "./volumes" \
\) -prune -o -print | \
sed -e 's/[^-][^\/]*\//|   /g' \
    -e 's/|   \([^|]\)/|--- \1/'
```


### Тесты

Поднять бд
```bash
docker compose up -d db
```

Создать отдельную базу
```bash
docker exec db psql -U postgres -c "CREATE DATABASE payout_gateway_test;"
```

Запустить тесты
```bash
poetry run pytest
```


## Структура проекта

``` bash
|--- .flake8                            # Настройки линтера flake
|--- migrations                         # Папка миграций Alembic (Создается автоматически)
|   |--- script.py.mako
|   |--- env.py
|   |--- versions
|   |   |--- bf059c5a7138_init.py
|   |--- README
|--- docker-compose.yaml                # Конфигурация для запуска контейнеров
|--- alembic.ini                        # Конфигурация Alembic (Создается автоматически)
|--- Dockerfile                         # Инструкция по запуска контейнера
|--- Makefile                           # Запуск команд по короткому имени
|--- pyproject.toml                     # Главный конфигуратор проекта
|--- tests                              # Тесты
|   |--- conftest.py
|   |--- __init__.py
|   |--- test_transfers.py
|--- README.md                          # Описание проекта
|--- .dockerignore                      # Черный список файлов для докера
|--- .gitignore                         # Черный список файлов для git
|--- scripts                            # Скрипты для запуска приложения
|   |--- entrypoint.sh
|--- poetry.lock                        # Конфигуратор poetry (Создается автоматически)
|--- payout_gateway                     # Бекенд приложения
|   |--- service.py                     # Бизнес-логика создания перевода. Идемпотентность по `external_id`: повторный запрос возвращает уже существующий перевод.
|   |--- config.py                      # Настройки из переменных окружения и `.env` (БД, токен, URL вебхука, параметры ретраев). 
|   |--- models.py                      # SQLAlchemy-модели: `Transfer` (переводы) и `WebhookDelivery` (очередь доставки вебхуков) со статусами и индексами.
|   |--- database.py                    # Pydantic-схемы: запрос на создание перевода, ответ API и тело вебхука.
|   |--- security.py                    # Проверка статичного bearer-токена и генерация и проверка HMAC-подписи вебхука (заголовок `X-Signature`).
|   |--- __init__.py
|   |--- api.py                         # HTTP-эндпоинт `POST /api/v1/transfer`. Принимает запрос, проверяет токен и передаёт данные в сервисный слой.
|   |--- schemas.py                     # Pydantic-схемы: запрос на создание перевода, ответ API и тело вебхука. |
|   |--- cli.py                         # Единая точка входа для запуска и служебных операций.
|   |--- webhooks.py                    # Формирование тела вебхука, сериализация в JSON и подпись запроса.
|   |--- workers.py                     # Фоновая обработка. Один воркер переводит `pending` в `completed` или `failed`, второй доставляет вебхуки с повторными попытками и экспоненциальной задержкой.
|   |--- main.py                        # Точка входа FastAPI. Создаёт приложение, подключает роутер и на старте запускает два фоновых воркера (переводы и вебхуки).
|   |--- executor.py                    # Интерфейс исполнителя перевода и заглушка `MockExecutor`. Именно здесь подключается реальная система (кошелёк, блокчейн, провайдер).
```
