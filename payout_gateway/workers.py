"""Фоновая обработка: переводы pending -> completed/failed и доставка вебхуков"""

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from payout_gateway import webhooks
from payout_gateway.config import settings
from payout_gateway.database import async_session_maker
from payout_gateway.executor import ExecutionResult, TransferExecutor
from payout_gateway.models import (
    DeliveryStatus,
    Transfer,
    TransferStatus,
    WebhookDelivery,
)

logger = logging.getLogger(__name__)

# Переводы


async def process_next_transfer(executor: TransferExecutor) -> bool:
    """Берёт самый старый pending-перевод, исполняет, фиксирует итог и ставит вебхук в очередь.

    Возвращает False, если обрабатывать нечего.
    """
    async with async_session_maker() as session, session.begin():
        transfer = await session.scalar(
            select(Transfer)
            .where(Transfer.status == TransferStatus.PENDING)
            .order_by(Transfer.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if transfer is None:
            return False

        try:
            result = await executor.execute(transfer)
        except Exception as exc:
            logger.exception("Executor crashed on transfer %s", transfer.id)
            result = ExecutionResult(
                status=TransferStatus.FAILED,
                from_address=settings.source_wallet_address,
                error=f"executor error: {exc!r}",
            )

        transfer.status = result.status
        transfer.from_address = result.from_address
        transfer.tx_hash = result.tx_hash
        transfer.failure_reason = result.error

        # Смена статуса и постановка вебхука в очередь
        session.add(
            WebhookDelivery(
                transfer_id=transfer.id, payload=webhooks.build_payload(transfer)
            )
        )
        logger.info("Transfer %s -> %s", transfer.id, result.status)
    return True


async def run_transfer_processor(
    executor: TransferExecutor, stop: asyncio.Event
) -> None:
    while not stop.is_set():
        try:
            processed = await process_next_transfer(executor)
        except Exception:
            logger.exception("Transfer processor iteration failed")
            processed = False
        if not processed:
            await _sleep(stop, settings.worker_poll_interval)


# Вебхуки


def _retry_delay(attempts: int) -> timedelta:
    seconds = settings.webhook_retry_base_delay * 2 ** (attempts - 1)
    return timedelta(seconds=min(seconds, settings.webhook_retry_max_delay))


async def dispatch_next_webhook(client: httpx.AsyncClient) -> bool:
    """Отправляет одну доставку. Возвращает False, если нет очереди"""
    async with async_session_maker() as session, session.begin():
        delivery = await session.scalar(
            select(WebhookDelivery)
            .where(
                WebhookDelivery.status == DeliveryStatus.PENDING,
                WebhookDelivery.next_attempt_at <= datetime.now(UTC),
            )
            .order_by(WebhookDelivery.next_attempt_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if delivery is None:
            return False

        body, headers = webhooks.build_request(
            delivery.payload, settings.api_token.get_secret_value()
        )
        delivery.attempts += 1
        try:
            response = await client.post(
                settings.webhook_url, content=body, headers=headers
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            delivery.last_error = f"{type(exc).__name__}: {exc}"[:1000]
            if delivery.attempts >= settings.webhook_max_attempts:
                delivery.status = DeliveryStatus.FAILED
                logger.error(
                    "Webhook %s given up after %d attempts: %s",
                    delivery.id,
                    delivery.attempts,
                    delivery.last_error,
                )
            else:
                delivery.next_attempt_at = datetime.now(UTC) + _retry_delay(
                    delivery.attempts
                )
                logger.warning(
                    "Webhook %s attempt %d failed: %s",
                    delivery.id,
                    delivery.attempts,
                    delivery.last_error,
                )
        else:
            delivery.status = DeliveryStatus.DELIVERED
            delivery.delivered_at = datetime.now(UTC)
            delivery.last_error = None
            logger.info("Webhook %s delivered", delivery.id)
    return True


async def run_webhook_dispatcher(
    client: httpx.AsyncClient, stop: asyncio.Event
) -> None:
    while not stop.is_set():
        try:
            processed = await dispatch_next_webhook(client)
        except Exception:
            logger.exception("Webhook dispatcher iteration failed")
            processed = False
        if not processed:
            await _sleep(stop, settings.worker_poll_interval)


async def _sleep(stop: asyncio.Event, seconds: float) -> None:
    with suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), timeout=seconds)
