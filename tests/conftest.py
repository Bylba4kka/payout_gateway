import os

# Тесты ходят в ОТДЕЛЬНУЮ БД и пересоздают в ней таблицы. Задаём до импорта payout_gateway.
# Создать её нужно один раз: CREATE DATABASE payout_gateway_test;
os.environ["POSTGRES_DB"] = os.environ.get("TEST_POSTGRES_DB", "payout_gateway_test")
os.environ["API_TOKEN"] = "test-token"
os.environ["WEBHOOK_URL"] = "http://receiver.test/hook"

import httpx
import pytest_asyncio
from sqlalchemy import text

from payout_gateway import models  # noqa: F401  (регистрирует таблицы в metadata)
from payout_gateway.database import Base, engine
from payout_gateway.main import app

AUTH = {"Authorization": "Bearer test-token"}


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(_schema):
    yield
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE transfers, webhook_deliveries CASCADE"))


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers=AUTH
    ) as c:
        yield c
