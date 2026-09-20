import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from payout_gateway.api import router
from payout_gateway.config import settings
from payout_gateway.database import engine
from payout_gateway.executor import MockExecutor, TransferExecutor
from payout_gateway.workers import run_transfer_processor, run_webhook_dispatcher

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)


def create_executor() -> TransferExecutor:
    # Тут подключается реальная интеграция
    return MockExecutor()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    stop = asyncio.Event()
    client = httpx.AsyncClient(timeout=settings.webhook_timeout)
    tasks: list[asyncio.Task[None]] = []

    if settings.run_workers:
        tasks = [
            asyncio.create_task(
                run_transfer_processor(create_executor(), stop), name="transfers"
            ),
            asyncio.create_task(run_webhook_dispatcher(client, stop), name="webhooks"),
        ]

    yield

    # Graceful shutdown
    stop.set()
    if tasks:
        _, pending = await asyncio.wait(tasks, timeout=30)
        for task in pending:
            task.cancel()
    await client.aclose()
    await engine.dispose()


app = FastAPI(
    debug=settings.debug,
    title=settings.title,
    description=settings.description,
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}
