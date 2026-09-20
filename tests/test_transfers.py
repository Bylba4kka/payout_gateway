import asyncio
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, select, update

from payout_gateway.config import settings
from payout_gateway.database import async_session_maker
from payout_gateway.executor import ExecutionResult, MockExecutor
from payout_gateway.models import (
    DeliveryStatus,
    Transfer,
    TransferStatus,
    WebhookDelivery,
)
from payout_gateway.security import generate_signature, verify_signature
from payout_gateway.workers import dispatch_next_webhook, process_next_transfer

TOKEN = "test-token"


def payload(**overrides):
    body = {
        "external_id": "order-1",
        "currency": "USDT",
        "amount": "10.5",
        "destination": "TXyz123",
        "comment": "hello",
    }
    return body | overrides


async def count(model) -> int:
    async with async_session_maker() as s:
        return await s.scalar(select(func.count()).select_from(model))


def receiver(status_code=200):
    """Фейковый получатель вебхуков: складывает запросы в список"""
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(status_code)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), received


# Подпись


def test_signature_matches_spec_formula():
    body = b'{"a":1}'
    expected = hmac.HMAC(
        hashlib.sha256(b"key").digest(), body, hashlib.sha256
    ).hexdigest()
    assert generate_signature("key", body) == expected
    assert verify_signature("key", body, expected)
    assert not verify_signature("other", body, expected)
    assert not verify_signature("key", b'{"a":2}', expected)


# Авторизация


async def test_requires_valid_bearer_token(client):
    r = await client.post(
        "/api/v1/transfer", json=payload(), headers={"Authorization": ""}
    )
    assert r.status_code == 401
    r = await client.post(
        "/api/v1/transfer", json=payload(), headers={"Authorization": "Bearer wrong"}
    )
    assert r.status_code == 401
    assert await count(Transfer) == 0


# Создание и идемпотентность


async def test_create_transfer(client):
    r = await client.post("/api/v1/transfer", json=payload())
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {
        "id",
        "external_id",
        "currency",
        "amount",
        "destination",
        "status",
    }
    assert data["status"] == "pending"
    assert data["amount"] == "10.5"
    assert isinstance(data["amount"], str)


async def test_same_external_id_is_idempotent(client):
    first = await client.post("/api/v1/transfer", json=payload())
    second = await client.post("/api/v1/transfer", json=payload())
    assert second.status_code == 200
    assert second.json() == first.json()
    assert await count(Transfer) == 1


async def test_replay_with_different_payload_returns_original(client):
    first = await client.post("/api/v1/transfer", json=payload())
    second = await client.post(
        "/api/v1/transfer", json=payload(amount="999", destination="other")
    )
    assert second.status_code == 200
    assert second.json() == first.json()
    assert second.json()["amount"] == "10.5"
    assert await count(Transfer) == 1


async def test_concurrent_duplicates_create_one_transfer(client):
    responses = await asyncio.gather(
        *[client.post("/api/v1/transfer", json=payload()) for _ in range(10)]
    )
    assert {r.status_code for r in responses} == {200}
    assert len({r.json()["id"] for r in responses}) == 1
    assert await count(Transfer) == 1


async def test_replay_of_finished_transfer_shows_final_status(client):
    await client.post("/api/v1/transfer", json=payload())
    await process_next_transfer(MockExecutor())
    r = await client.post("/api/v1/transfer", json=payload())
    assert r.json()["status"] == "completed"


async def test_validation(client):
    for bad in (
        payload(amount="0"),
        payload(amount="-5"),
        payload(amount="abc"),
        payload(amount="NaN"),
        payload(amount="0.0000000000000000001"),  # > 18 знаков после запятой
        payload(external_id=""),
        payload(currency=""),
        payload(destination=""),
    ):
        r = await client.post("/api/v1/transfer", json=bad)
        assert r.status_code == 422, bad
    assert await count(Transfer) == 0


async def test_comment_is_optional(client):
    body = payload()
    del body["comment"]
    assert (await client.post("/api/v1/transfer", json=body)).status_code == 200


# Обработка и вебхуки


async def test_completed_transfer_sends_signed_webhook(client):
    created = (await client.post("/api/v1/transfer", json=payload())).json()

    assert await process_next_transfer(MockExecutor()) is True
    assert await process_next_transfer(MockExecutor()) is False  # очередь пуста

    http, received = receiver()
    assert await dispatch_next_webhook(http) is True
    assert await dispatch_next_webhook(http) is False

    (request,) = received
    assert str(request.url) == settings.webhook_url
    body = request.content
    sent = json.loads(body)

    assert sent["id"] == created["id"]
    assert sent["external_id"] == "order-1"
    assert sent["amount"] == "10.5"
    assert sent["status"] == "completed"
    assert list(sent) == [
        "id",
        "external_id",
        "amount",
        "status",
        "details",
    ]
    assert list(sent["details"]) == ["from_address", "to_address", "tx_hash"]
    assert sent["details"]["from_address"] == settings.source_wallet_address
    assert sent["details"]["to_address"] == "TXyz123"
    assert sent["details"]["tx_hash"].startswith("0x")

    assert verify_signature(TOKEN, body, request.headers["X-Signature"])

    async with async_session_maker() as s:
        delivery = await s.scalar(select(WebhookDelivery))
        assert delivery.status == DeliveryStatus.DELIVERED
        assert delivery.attempts == 1


async def test_failed_transfer_sends_failed_webhook(client):
    await client.post("/api/v1/transfer", json=payload(destination="fail-me"))
    await process_next_transfer(MockExecutor())

    http, received = receiver()
    await dispatch_next_webhook(http)
    sent = json.loads(received[0].content)
    assert sent["status"] == "failed"
    assert sent["details"]["tx_hash"] is None


async def test_executor_exception_marks_transfer_failed(client):
    class Boom:
        async def execute(self, transfer):
            raise RuntimeError("node is down")

    await client.post("/api/v1/transfer", json=payload())
    await process_next_transfer(Boom())
    async with async_session_maker() as s:
        t = await s.scalar(select(Transfer))
        assert t.status == TransferStatus.FAILED
        assert "node is down" in t.failure_reason
        assert await s.scalar(select(func.count()).select_from(WebhookDelivery)) == 1


async def test_transfer_is_executed_only_once_under_concurrency(client):
    calls = []

    class Counting:
        async def execute(self, transfer):
            calls.append(transfer.id)
            await asyncio.sleep(0.2)
            return ExecutionResult(TransferStatus.COMPLETED, "w", "0xabc")

    await client.post("/api/v1/transfer", json=payload())
    results = await asyncio.gather(
        *[process_next_transfer(Counting()) for _ in range(5)]
    )
    assert sorted(results) == [False, False, False, False, True]
    assert len(calls) == 1
    assert await count(WebhookDelivery) == 1


async def test_webhook_retries_with_backoff_then_gives_up(client, monkeypatch):
    monkeypatch.setattr(settings, "webhook_max_attempts", 3)
    await client.post("/api/v1/transfer", json=payload())
    await process_next_transfer(MockExecutor())

    http, received = receiver(status_code=500)

    async def make_due():
        async with async_session_maker() as s, s.begin():
            await s.execute(
                update(WebhookDelivery).values(
                    next_attempt_at=datetime.now(UTC) - timedelta(1)
                )
            )

    async def state():
        async with async_session_maker() as s:
            d = await s.scalar(select(WebhookDelivery))
            return d.status, d.attempts, d.next_attempt_at

    # попытка 1
    assert await dispatch_next_webhook(http) is True
    status, attempts, next_at = await state()
    assert (status, attempts) == (DeliveryStatus.PENDING, 1)
    assert next_at > datetime.now(UTC)
    assert await dispatch_next_webhook(http) is False

    await make_due()
    await dispatch_next_webhook(http)  # попытка 2
    assert (await state())[:2] == (DeliveryStatus.PENDING, 2)

    await make_due()
    await dispatch_next_webhook(http)  # попытка 3 = лимит
    assert (await state())[:2] == (DeliveryStatus.FAILED, 3)
    assert len(received) == 3

    await make_due()
    assert await dispatch_next_webhook(http) is False


async def test_webhook_retry_succeeds_after_failure(client):
    await client.post("/api/v1/transfer", json=payload())
    await process_next_transfer(MockExecutor())

    bad, _ = receiver(status_code=503)
    await dispatch_next_webhook(bad)

    async with async_session_maker() as s, s.begin():
        await s.execute(
            update(WebhookDelivery).values(
                next_attempt_at=datetime.now(UTC) - timedelta(1)
            )
        )

    good, received = receiver(200)
    await dispatch_next_webhook(good)
    assert len(received) == 1
    async with async_session_maker() as s:
        d = await s.scalar(select(WebhookDelivery))
        assert d.status == DeliveryStatus.DELIVERED
        assert d.attempts == 2


async def test_workers_do_not_block_each_other(client):
    """Пока один воркер держит перевод, второй берёт следующий, а не ждёт"""
    in_flight = 0
    max_in_flight = 0

    class Slow:
        async def execute(self, transfer):
            nonlocal in_flight, max_in_flight
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.3)
            in_flight -= 1
            return ExecutionResult(TransferStatus.COMPLETED, "w", "0xabc")

    await client.post("/api/v1/transfer", json=payload(external_id="a"))
    await client.post("/api/v1/transfer", json=payload(external_id="b"))
    results = await asyncio.gather(
        process_next_transfer(Slow()), process_next_transfer(Slow())
    )

    assert results == [True, True]
    assert max_in_flight == 2  # исполнялись одновременно
    assert await count(WebhookDelivery) == 2


async def test_signature_is_computed_over_the_bytes_that_are_sent(client):
    await client.post("/api/v1/transfer", json=payload())
    await process_next_transfer(MockExecutor())
    http, received = receiver()
    await dispatch_next_webhook(http)
    req = received[0]
    assert req.headers["X-Signature"] == generate_signature(TOKEN, req.content)
    assert req.headers["Content-Type"] == "application/json"
